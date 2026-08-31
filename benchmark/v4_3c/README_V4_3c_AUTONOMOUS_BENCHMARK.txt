V4.3c Autonomous Native DSH FBAW Benchmark — Model-ID Verified

Purpose
-------
V4.3c keeps the V4.3b RF core, optimization goals, cache behavior, native DSH
FBAW tools, persistent Python bridge, accept/reject/rollback authority, and
Python-authorized STOP unchanged.

The only functional addition is observability of the DSH model identity and
DSH-to-tool calls.

New in V4.3c
------------
1. detect_dsh_model_v4_3c.py resolves the configured DSH agent-default-model
   provider/model before the benchmark starts.
2. The launcher prints:
     profile
     provider
     model
     source configuration
3. The resolved identity is passed into the native FBAW tool process.
4. Native tool runtime output prints dsh_provider / dsh_model.
5. Each DSH FBAW tool invocation prints a compact trace containing model,
   tool name, and arguments.

Important interpretation
------------------------
The detector reports the DSH CONFIGURED model selected from the installed
agent-default-model configuration (or an explicit FBAW_DSH_*_OVERRIDE).
This is stronger evidence than V4.3b, which did not print model identity.

DSH can support user/model-page settings that override package defaults.
Therefore the output is deliberately labelled "resolved configured model"
rather than claiming an internal provider response field that DSH does not
expose to this bundle.

For the installed DSH v0.1.1-rc.2 configuration previously observed, the
expected identity is:
  provider = deepseek-official
  model    = deepseek-v4-flash

Run
---
Copy all V4.3c files to D:\AI_Research\dsh-run and run:
  run_v4_3c_autonomous_benchmark.bat

Expected beginning
------------------
DSH MODEL IDENTITY
  profile      = headless
  provider     = deepseek-official
  model        = deepseek-v4-flash
  source       = DSH agent-default-model configuration

Then the native tool runtime should repeat the identity and print tool calls.

Expected ending
---------------
Python-authorized STOP received
NATIVE_DSH_FBAW_OK
DSH MODEL IDENTITY USED BY LAUNCHER
  provider=deepseek-official
  model=deepseek-v4-flash
EXITCODE=0

Score
-----
  python evaluate_v4_3c_autonomous_benchmark.py

The RF benchmark scoring remains the same as V4.3b (7/7). Model identity is
an observability/evidence addition and does not alter RF acceptance criteria.
