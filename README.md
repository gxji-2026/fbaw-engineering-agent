# FBAW Engineering Agent

**Provider-independent, physics-constrained FBAW engineering-agent
framework with a flagship DSH-native implementation and direct-API
reference implementations for DeepSeek and Cohere.**

The **DSH-native FBAW Engineering Agent** remains the primary/reference
implementation. DeepSeek and Cohere implementations are included as
provider/runtime references for the same engineering-agent pattern.

## Architecture at a glance

![FBAW Engineering Agent Architecture
Comparison](docs/images/fbaw_agent_architecture_comparison.png)

**One engineering-agent pattern, three runtime/provider implementations,
with Python retaining RF numerical authority.**

> **Parallel cold-run benchmark (6 workers):** DeepSeek ≈10 min → **4.18
> min (\~2.4×)**; Cohere ≈10 min → **4.14 min (\~2.4×)**.

> **v1.0 runtime-verified configuration:** DeepSeek V4-Flash
> (`deepseek-v4-flash`) through the official DeepSeek provider in DSH.
> The LLM plans and selects engineering tools; Python remains the
> numerical authority.

## What this repository demonstrates

This repository demonstrates a **provider-independent FBAW
engineering-agent pattern** implemented through three runtime/provider
paths:

-   **DSH-native FBAW Engineering Agent** --- the primary/reference
    implementation
-   **DeepSeek FBAW Engineering Agent** --- a direct-API reference
    implementation
-   **Cohere FBAW Engineering Agent** --- a cross-provider reference
    implementation

Across all three implementations, the central engineering principle is
the same:

> **The LLM plans and selects engineering actions; deterministic Python
> tools establish numerical truth and retain final acceptance
> authority.**

The implementations differ in their agent runtime, provider interface,
state handling, and execution architecture, while sharing the same
physics-constrained FBAW engineering core and verification philosophy.

### DSH-native implementation as the reference example

The remainder of this section uses the **DSH-native FBAW Engineering
Agent** as the primary runtime-verified example.

In this implementation, an LLM planner runs through **DeepSeek Harness
(DSH)**, chooses among native FBAW engineering tools, receives
Python-verified tool results, re-plans after constraint conflicts or
rejected actions, and stops only when the deterministic Python RF core
authorizes completion.

The DSH-native v1.0 benchmark verifies the complete chain:

``` text
Engineering goal
      |
      v
DeepSeek V4-Flash
  LLM planner
      |
      v
DeepSeek Harness (DSH)
  autonomous agent loop
      |
      v
Native FBAW engineering tools
      |
      v
Persistent Python bridge
      |
      v
Physics-constrained RF core
      |
      +--> simulation / optimization
      +--> ACCEPT / REJECT
      +--> rollback / verified state
      |
      v
result returned to DSH / LLM
      |
      +--> re-plan as needed
      |
      v
Python-authorized STOP
```

## DSH-native model and agent roles

  ---------------------------------------------------------------------------
  Layer                     Role                    Authority
  ------------------------- ----------------------- -------------------------
  **DeepSeek V4-Flash**     LLM planner: interprets Planning only
                            verified state and      
                            selects the next        
                            engineering tool/action 

  **DeepSeek Harness        Agent harness: runs the Execution/orchestration
  (DSH)**                   multi-step loop,        
                            exposes native tools,   
                            routes tool             
                            calls/results           

  **Native FBAW tools**     Structured engineering  Tool boundary
                            interface between the   
                            agent and RF            
                            implementation          

  **Persistent Python       Maintains the           State transport
  bridge**                  engineering session and 
                            verified design state   

  **Python RF core**        RF simulation,          **Numerical authority**
                            constrained             
                            optimization, hard-goal 
                            evaluation,             
                            ACCEPT/REJECT, rollback 

  **`stop_if_satisfied`**   Requests closure after  STOP only when Python
                            all hard goals are      authorizes
                            verified                
  ---------------------------------------------------------------------------

**Important:** DSH is not the LLM. In the verified v1.0 launcher
configuration, DSH uses `deepseek-official / deepseek-v4-flash`.
DeepSeek V4-Pro is not used by this native DSH v1.0 benchmark. The
earlier direct-API DeepSeek Engineering Agent V4.2.3 separately
implements Flash-to-Pro escalation.

## DSH-native runtime-verified model identity

V4.3c adds an observability layer without changing the RF core or
acceptance criteria. The launcher resolves and prints the configured DSH
model before execution, and each native FBAW tool call records the model
identity.

Verified run:

``` text
DSH MODEL IDENTITY
  profile      = headless
  provider     = deepseek-official
  model        = deepseek-v4-flash
  source       = DSH agent-default-model configuration
```

The actual agent trace includes model-attributed calls such as:

``` text
model=deepseek-v4-flash | tool=inspect_verified_design
model=deepseek-v4-flash | tool=optimize_ripple
model=deepseek-v4-flash | tool=realistic_constraint_conflict_probe
model=deepseek-v4-flash | tool=optimize_ripple
model=deepseek-v4-flash | tool=stop_if_satisfied
```

This makes the evidence chain explicit: **DeepSeek V4-Flash -\> DSH -\>
native FBAW tool -\> Python RF core -\> verified result -\> next agent
action -\> Python-authorized STOP.**

## DSH-native verified benchmark result

Hard goals:

  Metric                              Goal    Verified final
  -------------------------- ------------- -----------------
  Nominal passband ripple      \<= 0.55 dB   **0.539940 dB**
  Q80/Cp40 ripple              \<= 0.63 dB     **0.6181 dB**
  Q60/Cp60 ripple              \<= 0.75 dB   **0.745393 dB**
  Worst far-stop rejection       \>= 45 dB     **50.240 dB**

The verified run terminates with:

``` text
model=deepseek-v4-flash | tool=stop_if_satisfied
Python-authorized STOP received; closing persistent bridge.
NATIVE_DSH_FBAW_OK
provider=deepseek-official
model=deepseek-v4-flash
EXITCODE=0
```

## Benchmark tool sequence

A representative successful V4.3c session contains:

``` text
inspect_verified_design
  -> optimize_ripple
  -> realistic_constraint_conflict_probe
  -> optimize_ripple
  -> stop_if_satisfied
```

The sequence is chosen by the LLM planner from Python-verified state.
Numerical acceptance is never delegated to the LLM.

## Source vs. benchmark

The repository separates the engineering implementation from its
verification harness:

-   `agent/` contains the flagship DSH-native FBAW implementation:
    native tools, persistent Python bridge, RF engineering core, and DSH
    patch.
-   `providers/deepseek/` contains the direct-API DeepSeek serial
    baseline and parallel reference implementation.
-   `providers/cohere/` contains the Cohere serial baseline and parallel
    cross-provider reference implementation.
-   `benchmark/v4_3c/` contains the runtime-model-verified DSH launcher,
    evaluator, scoring script, and benchmark instructions.
-   `docs/` contains compact verification evidence plus the
    provider/runtime comparison.

This separation makes the repository an engineering-agent implementation
first, with the benchmark serving as reproducible evidence.

## Repository layout

``` text
fbaw-engineering-agent/
├── README.md
├── LICENSE
├── .gitignore
├── agent/
│   ├── fbaw_dsh_native_tools_v4_3c.ts
│   ├── fbaw_dsh_native_bridge_v4_3c.py
│   ├── fbaw_engineering_agent_3Rx4_V4_3c_autonomous_core.py
│   └── fbaw_native_v4_3c.patch.yml
├── providers/
│   ├── deepseek/
│   │   ├── deepseek_fbaw_agent_serial.py
│   │   └── deepseek_fbaw_agent_parallel.py
│   └── cohere/
│       ├── cohere_fbaw_agent_serial.py
│       └── cohere_fbaw_agent_parallel.py
├── benchmark/
│   └── v4_3c/
└── docs/
    ├── TECHNICAL_BACKGROUND.md
    ├── V4_3c_VERIFIED_TRANSCRIPT.md
    └── provider_comparison.md
```

## Run on Windows

The current benchmark reflects the verified local setup and expects DSH
plus Python to be installed. Copy the V4.3c benchmark files to the DSH
working directory (the verified launcher uses `D:\AI_Research\dsh-run`)
and run:

``` bat
run_v4_3c_autonomous_benchmark.bat
```

Then score the generated session summary:

``` bat
benchmark\v4_3c\score_agent.bat
```

A successful run should end with `NATIVE_DSH_FBAW_OK` and `EXITCODE=0`.

## Design principle

The central safety/engineering rule is separation of authority:

-   **LLM:** planning and engineering action selection.
-   **DSH:** agent orchestration and native tool execution.
-   **Python:** deterministic RF truth, state, constraints, rollback,
    and STOP authorization.

This prevents the LLM from inventing S-parameters, component values,
margins, or completion status.

## Implementation family

This repository presents **one FBAW engineering-agent framework through
three runtime/provider implementations**:

  -----------------------------------------------------------------------
  Implementation          Public role             Execution
  ----------------------- ----------------------- -----------------------
  **DSH-native FBAW       **Primary/reference     DSH native tools +
  Engineering Agent**     implementation**        persistent Python
                                                  bridge

  **DeepSeek FBAW         Direct-API reference    Parallel local RF
  Engineering Agent ---                           candidate verification
  Parallel**                                      

  **Cohere FBAW           Cross-provider          Parallel local RF
  Engineering Agent ---   reference               candidate verification
  Parallel**                                      

  DeepSeek FBAW           Baseline/reference      Serial
  Engineering Agent ---                           
  Serial                                          

  Cohere FBAW Engineering Baseline/reference      Serial
  Agent --- Serial                                
  -----------------------------------------------------------------------

The public distinction is **runtime/provider + execution mode**, not the
internal development revision number. `V4.3c`, `V4.3-P3`, `V4.1`, and
`V4.1-P3` remain development-lineage identifiers.

The DeepSeek and Cohere parallel variants parallelize independent
**Python RF candidate verification**, not LLM/API calls. Engineering
ranking and acceptance remain Python-controlled.

### Cohere parallel cold-run benchmark

Validated with six local workers:

``` text
elapsed_s   = 248.29
elapsed_min = 4.138
workers     = 6
```

The parallel run reproduced the verified checkpoint:

  Scenario              Ripple   Far-stop rejection
  ---------- ----------------- --------------------
  Nominal      **0.539940 dB**   51.177 / 55.633 dB
  Q80/Cp40     **0.618137 dB**   50.583 / 56.093 dB
  Q60/Cp60     **0.745393 dB**   50.240 / 56.311 dB

Transmission-zero locations remained approximately **6.2221 / 7.3995
GHz**.

See [`docs/provider_comparison.md`](docs/provider_comparison.md) for the
implementation map and versioning policy.

## Version

**v1.1** --- provider/runtime organization update. The runtime-verified
V4.3c DSH-native benchmark remains the flagship reference, with DeepSeek
and Cohere serial/parallel reference implementations added under
`providers/`.

## Technical Background

This engineering agent builds on two stages of prior FBAW research.

1.  **SFR-based transmission-zero synthesis and DFR realization**

    X. Ji and R. Zhu, "SFR-Based Transmission Zero Synthesis and DFR
    Realization of Wideband FBAW Filters for 6G FR3 (6.425--7.125 GHz),"
    2026.

    This work establishes the RF-physics foundation: embedded-impedance
    transmission-zero synthesis, extraction of lower and upper spectral
    targets, and transmission-zero-to-resonator mapping for DFR
    realization.

2.  **AI-assisted physics-constrained closed-loop optimization**

    X. Ji and R. Zhu, "AI-Assisted Physics-Constrained Closed-Loop
    Optimization of Robust DFR-Based Wideband FBAW Filters for 6G FR3,"
    2026.

    This work extends the physical synthesis methodology with an
    LLM-assisted Python optimization layer, multi-condition robustness
    evaluation, and ADS-calibrated numerical verification.

The present repository extends this progression from AI-assisted
design-program development to an autonomous tool-using engineering-agent
architecture:

``` text
SFR/DFR physics
    -> deterministic Python closed-loop optimization
    -> DSH + DeepSeek V4-Flash autonomous engineering agent
    -> native engineering tools
    -> Python-verified design state
```

See [`docs/TECHNICAL_BACKGROUND.md`](docs/TECHNICAL_BACKGROUND.md) for
the relationship between the two background studies and this repository.

## Author

**George X. Ji, Ph.D.**\
Principal Engineer, IWA Systems Inc.

Research and engineering interests include RF/microwave filter design,
FBAW/DFR technologies, physics-constrained optimization, and LLM-based
autonomous engineering agents.
