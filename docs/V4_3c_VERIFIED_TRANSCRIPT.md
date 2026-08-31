# V4.3c Verified Benchmark Transcript

This is a compact evidence extract from the successful V4.3c run. It is intentionally limited to model identity, agent/tool decisions, final RF metrics, and closure evidence.

## Runtime model identity

```text
DSH MODEL IDENTITY
  profile      = headless
  provider     = deepseek-official
  model        = deepseek-v4-flash
  source       = DSH agent-default-model configuration
```

## Native tool registration and first agent action

```text
[fbaw-native-tools-v4-3c] registered 7 native DSH FBAW tools
[fbaw-native-tools-v4-3c] DSH tool call | model=deepseek-v4-flash | tool=inspect_verified_design | args={"reason":"Establish the current Python-verified FBAW hard-goal state before choosing any engineering action."}
```

## Model-attributed engineering actions

```text
model=deepseek-v4-flash | tool=optimize_ripple | focus_scenario=Q80_Cp40
model=deepseek-v4-flash | tool=realistic_constraint_conflict_probe
model=deepseek-v4-flash | tool=optimize_ripple | focus_scenario=Q80_Cp40
```

The Python RF core subsequently executes the constrained ripple-first branch while preserving deterministic ACCEPT/REJECT authority.

## Final verified state

```text
Q60 ripple        = 0.745393 dB
lower rejection   = 50.240 dB
nominal ripple    = 0.539940 dB
Q80/Cp40 ripple   = 0.6181 dB
```

Hard goals are satisfied: nominal <=0.55 dB, Q80/Cp40 <=0.63 dB, Q60/Cp60 <=0.75 dB, worst far-stop rejection >=45 dB.

## STOP and graceful closure

```text
[fbaw-native-tools-v4-3c] DSH tool call | model=deepseek-v4-flash | tool=stop_if_satisfied
[fbaw-native-tools-v4-3c] Python-authorized STOP received; closing persistent bridge.
[fbaw-python] [V4.3c bridge] graceful shutdown acknowledged; exiting.
NATIVE_DSH_FBAW_OK

DSH MODEL IDENTITY USED BY LAUNCHER
  provider=deepseek-official
  model=deepseek-v4-flash
EXITCODE=0
```

## Interpretation

The verified evidence supports the following claim: DeepSeek V4-Flash is the configured LLM planner for this DSH benchmark; DSH hosts the autonomous tool-use loop; native FBAW tools route engineering actions into a persistent Python bridge; and Python retains numerical authority and authorizes STOP.
