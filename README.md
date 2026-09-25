# Domain-Specific Agentic AI for RF/FBAW Engineering

**A provider-independent, physics-constrained Agentic AI system for
RF/FBAW engineering, implemented through DSH-native, DeepSeek
direct-API, and Cohere cross-provider reference agents.**

This repository demonstrates a **domain-specific Agentic AI
architecture** in which LLMs perform engineering reasoning, planning,
and tool selection, while a deterministic Python RF core retains
numerical verification, state-transition, rollback, and final STOP
authority.

The project uses an **engineering-embedded evaluation** approach: the
evaluated LLM operates inside a real, tool-using engineering workflow
and is judged through deterministic simulation and verified RF outcomes.
This is distinct from an **embedded evaluator** arrangement in which
independent evaluators work inside an AI company. Here, the LLM is
embedded in the engineering system; independent audit and reproduction
are separate mechanisms for establishing experimental credibility.

All three implementations operate through the same fundamental **agentic
engineering loop**:

> **Goal → LLM Planning → Tool Execution → Python RF Verification →
> Accept / Reject / Rollback → Re-plan → Python-authorized STOP**

The **DSH-native FBAW Engineering Agent** remains the primary/reference
implementation. The DeepSeek direct-API and Cohere cross-provider agents
provide reference implementations of the same physics-constrained
Agentic AI architecture.

# 🔬 Latest Research

## Blind Structural Synthesis of 3Rx6 and 3Rx8

We extended the original FBAW Engineering Agent into a **blind
structural-synthesis study** using **OpenAI, DeepSeek, and Cohere** as
planning engines above the same deterministic RF verification framework.

**3Rx2 → 3Rx4 → Blind 3Rx6 → Blind 3Rx8**

  -----------------------------------------------------------------------
  Stage                               Result
  ----------------------------------- -----------------------------------
  **3Rx6 --- selected Cohere          \~0.93 dB robust ripple / \~76.4 dB
  trajectory**                        far rejection

  **3Rx8 --- selected OpenAI          \~1.33 dB robust ripple / \~102 dB
  trajectory**                        far rejection
  -----------------------------------------------------------------------

The experiments also produced clear examples of **result-dependent LLM
engineering reasoning**. In particular, DeepSeek changed engineering
direction after observing unsuccessful verified RF responses rather than
following a fixed parameter-search script.

> **LLM reasons about what to try next. Python determines whether it
> actually worked.**

### RF response evolution

  -------------------------------------------------------------------------------------------------------------
  3Rx2                                                   3Rx4
  ------------------------------------------------------ ------------------------------------------------------
  ![3Rx2                                                 ![3Rx4
  nominal](docs/images/filter-family/3Rx2_nominal.png)   nominal](docs/images/filter-family/3Rx4_nominal.png)

  -------------------------------------------------------------------------------------------------------------

  -------------------------------------------------------------------------------------------------------------
  3Rx6 --- Cohere                                        3Rx8 --- OpenAI
  ------------------------------------------------------ ------------------------------------------------------
  ![3Rx6                                                 ![3Rx8
  nominal](docs/images/filter-family/3Rx6_nominal.png)   nominal](docs/images/filter-family/3Rx8_nominal.png)

  -------------------------------------------------------------------------------------------------------------

**[Read the full technical case study
→](docs/BLIND_STRUCTURAL_SYNTHESIS_3RX6_3RX8.md)**

**Next phase:** 3Rx8 higher-order redesign targeting **far rejection
\>80 dB**, **robust worst-case ripple ≤1.0 dB**, and **required
bandwidth**.

## Long-Term Multi-LLM Autonomous Engineering Benchmark

Building on the completed OpenAI, DeepSeek, and Cohere experiments, the
project is expanding from individual comparative studies into a
structured, long-term benchmark program.

The program has two primary purposes:

1.  **Identify the LLM best suited to our engineering work** through
    fair, reproducible, result-dependent testing.
2.  **Provide objective engineering feedback to LLM developers** on
    long-horizon planning, structured tool use, failure recovery,
    resource allocation, and autonomous problem-solving.

The benchmark will progressively evaluate autonomous cell-by-cell
decisions, local-to-global strategy transitions, multi-objective
robustness, Pareto selection, controlled failure recovery, limited
computation budgets, hidden-history blind synthesis, topology and
embedding re-synthesis, and cross-domain engineering transfer.

Benchmark results will distinguish:

-   **Nominal Performance** --- nominal passband ripple under the
    baseline circuit condition.
-   **Robust Composite Performance** --- separately reported nominal,
    Q80/Cp40, and Q60/Cp60 ripple, with any composite ranking formula
    explicitly declared.
-   **Autonomous Engineering Behavior** --- planning quality,
    result-dependent replanning, rollback, failure recovery, budget use,
    and STOP-decision quality.
-   **Evaluation Integrity** --- versioned run manifests, trace
    completeness, human-intervention disclosure, hidden-history
    protection, and independent reproduction where feasible.

Numerical truth remains the responsibility of the deterministic Python
RF core. Independent reproduction audits the credibility of the
experiment; it does not replace deterministic RF verification.

**[Read the long-term benchmark roadmap
→](FBAW_LLM_Benchmark_Long_Term_Roadmap.md)**

## V1.3 --- Multi-LLM Autonomous Engineering Benchmark

The latest benchmark raises the difficulty from broad
feasibility-oriented blind synthesis to a **tightly constrained,
multi-objective engineering problem**.

Earlier experiments with **3 LLMs** successfully demonstrated blind
higher-order synthesis:

**3Rx4 → Blind 3Rx6 → Blind 3Rx8**

Those studies used comparatively broad acceptance conditions and
primarily tested whether an LLM could autonomously grow the topology and
obtain an engineering-valid higher-order design.

V1.3 tests a more demanding problem:

**6 LLMs → Blind 4Rx3 → 4Rx5 → 18 independent runs**

with explicit simultaneous requirements on **nominal ripple, Q80/Cp40
ripple, Q60/Cp60 ripple, bandwidth, and far rejection**.

  -----------------------------------------------------------------------
  Benchmark               Constraint regime       Result
  ----------------------- ----------------------- -----------------------
  Earlier: 3 LLMs, 3Rx4 → Broad / comparatively   **Successful**
  blind 3Rx6 → blind 3Rx8 permissive              

  V1.3: 6 LLMs, blind     Tight explicit          **0/18 FINAL PASS**
  4Rx3 → 4Rx5             multi-objective limits  

  Human-engineered 4Rx5   Same tight V1.3         **PASS**
  Golden                  requirements            
  -----------------------------------------------------------------------

The V1.3 result therefore does **not** indicate an infeasible RF target.
A verified human-engineered Golden design satisfies the same performance
requirements.

Instead, the benchmark exposes a more difficult reasoning problem:

> **Autonomous synthesis success under broad engineering constraints
> does not necessarily imply autonomous optimization success under a
> narrow, simultaneous, quantitatively defined performance envelope.**

Analysis of the verified trajectories identifies concrete reasoning
limitations involving local-versus-global optimization, nonlinear
constraint-margin exchange, action-to-response causal learning,
nominal/robust optimization cycles, state retention, basin navigation,
recovery efficiency, and endgame decision-making.

The study also derives project-specific improvements for future
engineering LLMs, including explicit constraint-margin vectors, local
sensitivity learning, prediction-before-execution, counterfactual action
comparison, limit-cycle detection, Pareto-state retention, budget-aware
planning, and mandatory belief updates after deterministic verification.

**[Read the complete V1.3 Multi-LLM Autonomous Engineering Benchmark
→](V1_3_Multi_LLM_Autonomous_Engineering_Benchmark_GitHub.md)**

### V1.4 --- Multi-LLM Persistent Verified Evolution

V1.4 extends V1.3 from independent fresh-context runs into a
**long-horizon persistent engineering experiment**.

Four LLMs — **Cohere, xAI, DeepSeek, and Claude** — were evaluated over
the same **30-decision horizon** inside the deterministic engineering
loop. The **Golden 4Rx5 reference was hidden during evolution** and was
revealed only after the runs for post-run comparison.

The study asks whether an LLM can accumulate verified engineering
progress, preserve successful checkpoints, recover from unsuccessful
actions, reuse prior experience, explore Pareto alternatives, and
improve persistently across a long sequence of engineering decisions.

The central observation is:

> **Persistent memory is necessary for long-horizon autonomous
> engineering, but it is not sufficient. The more demanding capability
> is converting accumulated verified experience into better future
> engineering decisions.**

After the Golden reference was unblinded, preserved verified solutions
were compared with it rather than simply using each model's final
Decision #30 endpoint. **DeepSeek CP21** was selected as the closest
verified V1.4 transition point:

- **Nominal ripple:** 0.591294 dB
- **Q80/Cp40 ripple:** 0.609387 dB
- **Q60/Cp60 ripple:** 0.913809 dB

The corresponding Golden ripple values are **0.598967 / 0.684248 /
0.915071 dB**. CP21 satisfied the V1.4 engineering feasibility guards
but did not match every stricter Golden bandwidth/rejection metric, so
it was not a full Golden PASS.

This verified CP21 design becomes the **common starting point for V1.5**,
where the Golden reference is disclosed and all evaluated LLMs face the
same strict nine-metric **BEAT_GOLDEN** challenge.

**V1.3 tests repeated independent engineering. V1.4 tests persistent
verified evolution. V1.5 tests Golden-informed improvement from a common
near-Golden starting point.**

**[Read the complete V1.4 Multi-LLM Persistent Verified Evolution report
→](V1_4_Multi_LLM_Persistent_Verified_Evolution.md)**

The V1.4 publication package also includes the closest-to-Golden result
figure and four **Verified Engineering Evolution** videos for Cohere,
DeepSeek, xAI Grok, and Claude. The videos visualize observable
engineering actions and verified outcomes; they are not hidden
chain-of-thought traces.

The new blind 3Rx6/3Rx8 source code, complete circuit parameters,
internal prompts, and proprietary engineering implementation are not
publicly released. Earlier public reference implementations in this
repository are retained as part of the project history.

------------------------------------------------------------------------

# Original Engineering-Agent Platform

> The sections below document the original public Engineering Agent
> architecture, reference implementations, benchmark workflow, and
> project history retained in this repository.

## Architecture at a glance

![Domain-Specific Agentic AI for RF/FBAW
Engineering](docs/images/Domain-Specific_Agentic-AI_fbaw_agent_architecture.png)

**One domain-specific Agentic AI architecture, three runtime/provider
implementations, with Python retaining RF numerical and state-transition
authority.**

> **Parallel cold-run benchmark (6 workers):** DeepSeek ≈10 min → **4.18
> min (\~2.4×)**; Cohere ≈10 min → **4.14 min (\~2.4×)**.

> **v1.0 runtime-verified configuration:** DeepSeek V4-Flash
> (`deepseek-v4-flash`) through the official DeepSeek provider in DSH.
> The LLM plans and selects engineering tools; Python remains the
> numerical authority.

## What this repository demonstrates

This repository demonstrates a **provider-independent, domain-specific
Agentic AI system for RF/FBAW engineering** implemented through three
runtime/provider paths:

-   **DSH-native FBAW Engineering Agent** --- the **primary/reference
    Agentic AI implementation**
-   **DeepSeek FBAW Engineering Agent** --- a **direct-API reference
    implementation**
-   **Cohere FBAW Engineering Agent** --- a **cross-provider reference
    implementation**

Across all three implementations, the central engineering principle is
the same:

> **The LLM proposes and plans engineering actions; deterministic Python
> tools evaluate physical results and authorize engineering state
> transitions and termination.**

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
├── FBAW_LLM_Benchmark_Long_Term_Roadmap.md
├── V1_3_Multi_LLM_Autonomous_Engineering_Benchmark_GitHub.md
├── V1_4_Multi_LLM_Persistent_Verified_Evolution.md
├── V1_4_Closest_Verified_to_Golden_LARGE_FONT.png
├── videos/
│   ├── Cohere_V1_4_Verified_Engineering_Evolution.mp4
│   ├── DeepSeek_V1_4_Verified_Engineering_Evolution.mp4
│   ├── xAI_Grok_V1_4_Verified_Engineering_Evolution.mp4
│   └── Claude_V1_4_Verified_Engineering_Evolution.mp4
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

## Agentic AI implementation family

This repository presents **one domain-specific Agentic AI architecture
through three runtime/provider implementations**. All three execute the
same fundamental closed loop: **Goal → LLM Planning → Tool Execution →
Python RF Verification → Accept / Reject / Rollback → Re-plan →
Python-authorized STOP**.

  -----------------------------------------------------------------------
  Implementation          Public role             Execution
  ----------------------- ----------------------- -----------------------
  **DSH-native FBAW       **Primary/reference     DSH native tools +
  Engineering Agent**     Agentic AI              persistent Python
                          implementation**        bridge

  **DeepSeek FBAW         **Direct-API reference  Parallel local RF
  Engineering Agent ---   implementation**        candidate verification
  Parallel**                                      

  **Cohere FBAW           **Cross-provider        Parallel local RF
  Engineering Agent ---   reference               candidate verification
  Parallel**              implementation**        

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
and Cohere serial/parallel reference implementations under `providers/`.
The repository now also documents the long-term Multi-LLM Autonomous
Engineering Benchmark through **V1.3 independent repeated engineering**
and **V1.4 Golden-hidden Persistent Verified Evolution**, with V1.4
providing the verified transition point used to initialize V1.5.

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
design-program development to a **domain-specific Agentic AI system**
with autonomous tool use, deterministic RF verification,
rollback/recovery, re-planning, and Python-authorized termination:

``` text
SFR/DFR RF physics
    -> deterministic Python closed-loop optimization
    -> LLM reasoning and engineering planning
    -> tool-using autonomous engineering agent
    -> physics-constrained agentic control loop
    -> Domain-Specific Agentic AI System
         |-- DSH-native primary/reference implementation
         |-- DeepSeek direct-API reference implementation
         `-- Cohere cross-provider reference implementation
```

See [`docs/TECHNICAL_BACKGROUND.md`](docs/TECHNICAL_BACKGROUND.md) for
the relationship between the two background studies and this repository.

## Author

**George X. Ji, Ph.D.**\
Principal Engineer, IWA Systems Inc.

Research and engineering interests include RF/microwave filter design,
FBAW/DFR technologies, physics-constrained optimization, domain-specific
Agentic AI, and LLM/agent harness engineering.
