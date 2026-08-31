import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import { resolve } from 'node:path'
import { existsSync } from 'node:fs'

export const name = 'fbaw-native-tools-v4-3c'
export const inject = ['tools']

type JsonObject = Record<string, unknown>
type Pending = {
  resolve: (value: JsonObject) => void
  reject: (reason?: unknown) => void
}

class PythonBridge {
  private proc: any = null
  private rl: any = null
  private pending = new Map<string, Pending>()
  private seq = 0
  private ready: Promise<void> | null = null
  private shuttingDown = false

  private start(): Promise<void> {
    if (this.ready) return this.ready

    this.ready = new Promise<void>((resolveReady, rejectReady) => {
      const python = process.env.FBAW_DSH_PYTHON || 'python'
      const bridgePath = resolve(
        process.env.FBAW_DSH_BRIDGE ||
          resolve(process.cwd(), 'fbaw_dsh_native_bridge_v4_3c.py'),
      )
      const spawnCwd = process.env.FBAW_DSH_WORKDIR || process.cwd()

      const args = [
        bridgePath,
        '--goal-nominal-ripple', process.env.FBAW_GOAL_NOMINAL || '0.55',
        '--goal-q80-ripple', process.env.FBAW_GOAL_Q80 || '0.63',
        '--goal-q60-ripple', process.env.FBAW_GOAL_Q60 || '0.75',
        '--goal-rejection', process.env.FBAW_GOAL_REJECTION || '45',
        '--outdir', process.env.FBAW_DSH_OUTDIR || 'fbaw_3Rx4_native_dsh_output',
      ]

      if (process.env.FBAW_CHECKPOINT_CACHE) {
        args.push('--checkpoint-cache', process.env.FBAW_CHECKPOINT_CACHE)
      }
      if (process.env.FBAW_DISABLE_CHECKPOINT_CACHE === '1') {
        args.push('--no-checkpoint-cache')
      }
      if (process.env.FBAW_COMSOL_LOW) {
        args.push('--comsol-low', process.env.FBAW_COMSOL_LOW)
      }
      if (process.env.FBAW_COMSOL_HIGH) {
        args.push('--comsol-high', process.env.FBAW_COMSOL_HIGH)
      }
      if (process.env.FBAW_DSH_STRESS === '0') {
        args.push('--no-native-stress-protocol')
      }

      process.stderr.write(
        '[fbaw-native-tools-v4-3c] runtime\n' +
        `  dsh_provider=${process.env.FBAW_DSH_RESOLVED_PROVIDER || 'unresolved'}\n` +
        `  dsh_model=${process.env.FBAW_DSH_RESOLVED_MODEL || 'unresolved'}\n` +
        `  dsh_model_source=${process.env.FBAW_DSH_MODEL_SOURCE || 'unresolved'}\n` +
        `  python=${python}\n` +
        `  python_exists=${existsSync(python)}\n` +
        `  bridge=${bridgePath}\n` +
        `  bridge_exists=${existsSync(bridgePath)}\n` +
        `  spawn_cwd=${spawnCwd}\n` +
        `  spawn_cwd_exists=${existsSync(spawnCwd)}\n`
      )

      const proc = spawn(python, args, {
        cwd: spawnCwd,
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
      })
      this.proc = proc

      proc.stderr.on('data', (chunk: Buffer) => {
        process.stderr.write(`[fbaw-python] ${String(chunk)}`)
      })

      const rl = createInterface({ input: proc.stdout })
      this.rl = rl
      let readySeen = false

      rl.on('line', (line: string) => {
        let msg: JsonObject
        try {
          msg = JSON.parse(line) as JsonObject
        } catch {
          if (!readySeen) {
            rejectReady(new Error(`Invalid FBAW bridge JSON before ready: ${line}`))
          }
          return
        }

        if (msg.event === 'ready') {
          readySeen = true
          process.stderr.write(
            `[fbaw-native-tools-v4-3c] Python bridge ready; cache=${String(msg.checkpoint_cache_status)}\n`
          )
          resolveReady()
          return
        }

        const id = typeof msg.id === 'string' ? msg.id : ''
        const waiter = this.pending.get(id)
        if (!waiter) return
        this.pending.delete(id)

        if (msg.ok === true) {
          waiter.resolve((msg.result || {}) as JsonObject)
        } else {
          waiter.reject(new Error(String(msg.error || 'Unknown FBAW bridge error')))
        }
      })

      proc.on('error', (err: Error) => {
        if (!readySeen) rejectReady(err)
        for (const waiter of this.pending.values()) waiter.reject(err)
        this.pending.clear()
      })

      proc.on('exit', (code: number | null, signal: NodeJS.Signals | null) => {
        if (!this.shuttingDown) {
          const err = new Error(
            `FBAW Python bridge exited code=${String(code)} signal=${String(signal)}`,
          )
          if (!readySeen) rejectReady(err)
          for (const waiter of this.pending.values()) waiter.reject(err)
        }
        this.pending.clear()
        this.proc = null
        this.rl = null
        this.ready = null
        process.stderr.write(
          `[fbaw-native-tools-v4-3c] Python bridge exited code=${String(code)} signal=${String(signal)}\n`
        )
      })
    })

    return this.ready
  }

  async call(tool: string, args: JsonObject): Promise<JsonObject> {
    await this.start()
    if (!this.proc) throw new Error('FBAW bridge is not running')

    const id = `dsh-${++this.seq}`
    const promise = new Promise<JsonObject>((resolveCall, rejectCall) => {
      this.pending.set(id, { resolve: resolveCall, reject: rejectCall })
    })

    this.proc.stdin.write(JSON.stringify({ id, tool, arguments: args }) + '\n')
    return promise
  }

  async shutdown(): Promise<void> {
    if (!this.proc || this.shuttingDown) return
    this.shuttingDown = true
    try {
      await this.call('__shutdown__', {})
    } catch (err) {
      process.stderr.write(
        `[fbaw-native-tools-v4-3c] graceful shutdown RPC failed: ${String(err)}\n`
      )
    }

    try { this.proc?.stdin?.end() } catch {}
    try { this.rl?.close() } catch {}

    // Give Python a short grace period; force termination only if it lingers.
    const proc = this.proc
    if (proc) {
      await new Promise<void>((resolveDone) => {
        let settled = false
        const done = () => {
          if (settled) return
          settled = true
          resolveDone()
        }
        proc.once('exit', done)
        setTimeout(() => {
          if (!settled && proc.exitCode === null) {
            process.stderr.write(
              '[fbaw-native-tools-v4-3c] bridge did not exit after grace period; terminating.\n'
            )
            try { proc.kill() } catch {}
          }
          done()
        }, 1500)
      })
    }
  }
}

const bridge = new PythonBridge()

const output = {
  schema: { type: 'string' },
  render: (_args: unknown, value: unknown) => [
    { type: 'text', text: String(value) },
  ],
}

function encode(value: JsonObject): string {
  return JSON.stringify(value)
}

function requireObject(args: unknown): JsonObject {
  if (args === null || typeof args !== 'object' || Array.isArray(args)) {
    throw new Error('tool arguments must be an object')
  }
  return args as JsonObject
}

function requireString(args: JsonObject, key: string): string {
  const value = args[key]
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`${key} must be a non-empty string`)
  }
  return value
}

function reasonParameters() {
  return {
    type: 'object',
    properties: {
      reason: {
        type: 'string',
        description: 'Engineering rationale based only on the Python-verified state.',
      },
    },
    required: ['reason'],
    additionalProperties: false,
  }
}

function registerReasonTool(
  ctx: any,
  toolName: string,
  description: string,
  shutdownAfterAuthorizedStop = false,
) {
  ctx.tools.register({
    name: toolName,
    description,
    parameters: reasonParameters(),
    output,
    async execute(rawArgs: unknown) {
      const args = requireObject(rawArgs)
      requireString(args, 'reason')
      process.stderr.write(
        `[fbaw-native-tools-v4-3c] DSH tool call | model=${process.env.FBAW_DSH_RESOLVED_MODEL || 'unresolved'} | tool=${toolName} | args=${JSON.stringify(args)}\n`
      )
      const result = await bridge.call(toolName, args)

      if (
        shutdownAfterAuthorizedStop &&
        result.stop_allowed === true
      ) {
        process.stderr.write(
          '[fbaw-native-tools-v4-3c] Python-authorized STOP received; closing persistent bridge.\n'
        )
        await bridge.shutdown()
      }

      return encode(result)
    },
  })
}

export function apply(ctx: any) {
  registerReasonTool(
    ctx,
    'inspect_verified_design',
    'Inspect the current Python-verified FBAW hard-goal state. Must be the first engineering tool.',
  )

  registerReasonTool(
    ctx,
    'realistic_constraint_conflict_probe',
    'Run the Python simulated constraint-conflict probe and preserve the verified state on rejection.',
  )

  registerReasonTool(
    ctx,
    'controlled_failure_probe',
    'Test-only controlled rollback probe; changes no accepted RF state.',
  )

  ctx.tools.register({
    name: 'optimize_ripple',
    description:
      'Run Python physics-constrained ripple optimization for one verified scenario. Python owns RF simulation, acceptance, and rollback.',
    parameters: {
      type: 'object',
      properties: {
        focus_scenario: {
          type: 'string',
          enum: ['nominal', 'Q80_Cp40', 'Q60_Cp60'],
        },
        reason: { type: 'string' },
      },
      required: ['focus_scenario', 'reason'],
      additionalProperties: false,
    },
    output,
    async execute(rawArgs: unknown) {
      const args = requireObject(rawArgs)
      const focus = requireString(args, 'focus_scenario')
      requireString(args, 'reason')
      if (!['nominal', 'Q80_Cp40', 'Q60_Cp60'].includes(focus)) {
        throw new Error(
          'focus_scenario must be nominal, Q80_Cp40, or Q60_Cp60',
        )
      }
      process.stderr.write(
        `[fbaw-native-tools-v4-3c] DSH tool call | model=${process.env.FBAW_DSH_RESOLVED_MODEL || 'unresolved'} | tool=optimize_ripple | args=${JSON.stringify(args)}\n`
      )
      return encode(await bridge.call('optimize_ripple', args))
    },
  })

  registerReasonTool(
    ctx,
    'recover_rejection',
    'Run Python far-stop rejection recovery when the verified rejection hard constraint fails.',
  )

  registerReasonTool(
    ctx,
    'stop_if_satisfied',
    'Request engineering STOP. Python authorizes only when every hard goal is verified satisfied.',
    true,
  )

  ctx.tools.register({
    name: 'close_engineering_session',
    description:
      'Close the persistent Python engineering bridge after the requested headless task is complete. This is lifecycle cleanup only and does NOT mean engineering goals are satisfied.',
    parameters: {
      type: 'object',
      properties: {
        reason: { type: 'string' },
      },
      required: ['reason'],
      additionalProperties: false,
    },
    output,
    async execute(rawArgs: unknown) {
      const args = requireObject(rawArgs)
      requireString(args, 'reason')
      await bridge.shutdown()
      return encode({
        session_closed: true,
        engineering_success_implied: false,
        reason: args.reason,
      })
    },
  })

  process.stderr.write(
    '[fbaw-native-tools-v4-3c] registered 7 native DSH FBAW tools\n',
  )
}
