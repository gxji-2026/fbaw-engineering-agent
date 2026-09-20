# Long-Term Roadmap: Multi-LLM Autonomous RF/FBAW Engineering Benchmark

## Open Invitation to LLM Developers and Research Partners

This project is building a public, reproducible benchmark for evaluating how large language models behave as autonomous engineering decision-makers in RF/FBAW filter synthesis.

The objective is not to ask an LLM to replace deterministic simulation or numerical optimization. Instead, the benchmark evaluates whether an LLM can select engineering strategies, interpret verified RF results, recover from unsuccessful decisions, and use a limited computation budget effectively.

The governing architecture is:

**Engineering Goal → LLM Planning → Tool Execution → Python Verification → Accept / Reject / Rollback → Re-plan → Python-authorized STOP**

The LLM proposes actions and explains its engineering reasoning. The deterministic Python core owns numerical truth, circuit evaluation, constraint enforcement, checkpoints, rollback, and final authorization to stop.

This benchmark uses an **engineering-embedded evaluation** approach: the evaluated LLM is placed inside a real, tool-using engineering workflow and judged through deterministic simulation and verified outcomes. This is distinct from **embedded evaluator** arrangements in which independent evaluators work inside an AI company with employee-like access. The two approaches may complement one another, but they address different questions. This benchmark primarily asks how an LLM behaves when embedded in an engineering system; independent audit and reproduction provide the additional assurance that the experiment itself was conducted and reported correctly.

We welcome participation from LLM companies, research laboratories, universities, RF engineers, optimization researchers, and agent-platform developers.

## Purpose of This Benchmark

This benchmark has two primary purposes:

1. **To identify the LLM best suited to our engineering work.**  
   Through fair, reproducible, and result-dependent testing, we evaluate which models most effectively support our RF/FBAW engineering workflow—including planning, tool selection, cell-by-cell and joint optimization decisions, failure recovery, robustness trade-offs, and efficient use of computational resources.

2. **To help LLM developers improve their models and advance AI for engineering.**  
   The benchmark provides objective, verified feedback on model strengths, limitations, decision patterns, tool-use reliability, and failure modes. We hope these findings can help model providers improve engineering reasoning, long-horizon planning, structured tool use, and autonomous problem-solving capabilities.

The purpose is not simply to rank models or declare a universal winner. Different models may be better suited to different engineering tasks. Our goal is to find the best practical match for our work while contributing useful, evidence-based feedback to the broader development of AI.

We welcome constructive communication and long-term collaboration with LLM companies. Providers interested in detailed performance traces, additional tests, customized engineering challenges, or recurring evaluation of new model versions are invited to contact us privately.

## 1. Current Engineering Domain

The initial benchmark focuses on embedded-impedance synthesis of Lower-FR3 FBAW/DFR filters.

Current product band:

- Passband: 6.425–7.125 GHz
- Product bandwidth: 0.700 GHz
- Engineering bandwidth guardrail: at least 0.750 GHz
- Resonator series-frequency families: approximately 7.37, 7.40, and 7.45 GHz
- Evaluation conditions: nominal, Q80/Cp40, and Q60/Cp60
- Key objectives: low passband ripple, adequate bandwidth, high far-stopband rejection, and robustness

The benchmark will expand from verified lower-order checkpoints to higher-order product-family synthesis, including 3Rx1–3Rx8 and 4Rx structures.

### Understanding the 3Rx and 4Rx Filter Families

The topology names used in this benchmark follow the circuit definitions already implemented in the previously published Python reference code. They are engineering structure labels, not software-version or LLM-version numbers.

The notation has two parts:

- **3Rx** or **4Rx** identifies the number of resonator instances in each repeated synthesis cell.
- The trailing number identifies the number of cascaded cells. For example, **3Rx4** is a four-cell filter constructed from the 3Rx cell topology, while **4Rx6** is a six-cell filter constructed from the 4Rx cell topology.

In the published 3Rx implementation, each cell contains:

1. A series high-frequency resonator.
2. A shunt branch containing a low-frequency resonator in parallel with a high-frequency resonator.

This produces three resonator instances per cell. The cell also contains its embedded inductive and capacitive matching elements. A first-cell shunt inductor and a final-cell shunt inductor provide end embedding, and the final series inductance is represented by three physical segments in the verified circuit model.

The published 4Rx implementation retains the confirmed 3Rx portion and inserts a second series high-frequency resonator after the shunt resonator node and before the following matching section. Each repeated cell therefore contains:

1. A first series high-frequency resonator.
2. The low-frequency and high-frequency resonators in the parallel shunt branch.
3. A second series high-frequency resonator.

The difference between 3Rx and 4Rx is therefore a real circuit-topology change, not merely an increase in the number of optimization variables.

Increasing the cell count can increase far-stopband rejection and provide additional synthesis freedom, but it also increases parameter coupling and may worsen passband ripple, insertion loss, sensitivity, or worst-case robustness. Higher-order migration is consequently treated as an engineering synthesis problem rather than a simple copy-and-repeat operation.

Within the benchmark, an LLM may be asked to select insertion positions, initialize added cells, choose between cell-by-cell and joint optimization, allocate optimization effort across cells, or determine that the embedding network must be re-synthesized. Python remains responsible for constructing the legal network, enforcing the topology definition, calculating S-parameters, and verifying every reported result.

This section summarizes concepts that are already present in the public Python implementations. It is included so that readers and participating model developers can interpret the benchmark terminology and reasoning tasks consistently.

## 2. Research Questions

The program is designed to answer the following questions:

1. Can an LLM make useful engineering decisions when it does not know the historical best solution?
2. Can it select topology-growth actions, insertion positions, and parameter initialization methods from observed RF results?
3. Can it decide autonomously whether cell-by-cell optimization is necessary?
4. If local optimization is selected, can it choose the cells, parameter subsets, order, and number of passes?
5. Can it determine when to switch from local optimization to joint or global refinement?
6. Can it balance nominal, Q80, and Q60 performance without violating bandwidth and rejection guards?
7. Can it recognize stagnation, overfitting, or destructive optimization and invoke rollback?
8. Can it allocate a limited action and computation budget intelligently?
9. Can it explain the engineering basis, limitations, and risks of the final solution?
10. Are its decisions repeatable across independent runs and model versions?
11. Can the complete experiment—including disclosed inputs, hidden information, human intervention, resource use, and reported results—be independently audited and reproduced?

## 3. Long-Term Benchmark Levels

### Level 0 — Interface and Compliance

The model must:

- Produce valid structured actions.
- Select only legal tools and parameter ranges.
- Interpret the returned engineering state correctly.
- Avoid fabricating unverified RF results.
- Accept Python verification as authoritative.

### Level 1 — Single-Decision Engineering

The model selects one engineering action, such as:

- Cell insertion position
- Source cells used for initialization
- Average, blend, copy, symmetric, or asymmetric initialization
- Parameter subset for refinement

The purpose is to measure basic engineering judgment without a long planning horizon.

### Level 2 — Result-Dependent Replanning

The model observes the verified result of every action and decides what to do next. It must respond differently to improvement, stagnation, constraint failure, or regression.

### Level 3 — Autonomous Cell-by-Cell Decision

Cell-by-cell optimization becomes an available option, but the model is not told whether it should use it.

The model decides:

- Whether cell-by-cell optimization is appropriate
- Which cells to optimize
- Forward, reverse, center-out, edge-in, or custom order
- Which parameters to expose for each cell
- How many passes to run
- When to stop local refinement
- When to transition to joint optimization

Python executes all numerical optimization and independently verifies every result.

### Level 4 — Multi-Objective Robustness

The model must manage competing objectives across nominal, Q80/Cp40, and Q60/Cp60 conditions. It may adjust objective weights, but hard engineering guards remain under Python control.

### Level 5 — Pareto Strategy Selection

The model receives multiple verified candidates and must choose whether to:

- Improve ripple
- Preserve bandwidth margin
- Increase far-stopband rejection
- Improve worst-case robustness
- Retain multiple Pareto candidates

The benchmark scores both final performance and the quality of the trade-off decision.

### Level 6 — Failure Recovery

Controlled failure modes are introduced, including:

- Invalid or ineffective actions
- Optimization stagnation
- Local minima
- Constraint violations
- Excessive symmetry
- Excessive parameter freedom
- Improvement in one condition with degradation in another

The model must diagnose the outcome, roll back when justified, and select a materially different strategy.

### Level 7 — Limited-Budget Autonomous Engineering

The model receives a fixed allowance of actions, simulations, optimizer calls, tokens, and wall-clock time. It must allocate these resources between exploration, local refinement, joint optimization, verification, and final confirmation.

### Level 8 — Hidden-History Blind Synthesis

Only verified lower-order checkpoints are disclosed. Historical higher-order solutions remain hidden. The model must build a higher-order design without copying a known answer.

This level measures genuine result-dependent engineering rather than reproduction of previous solutions.

### Level 9 — Topology and Embedding Re-synthesis

The model may conclude that parameter tuning alone is insufficient. It can propose a controlled topology or embedding re-synthesis, subject to predefined legal transformations and independent verification.

### Level 10 — Cross-Domain Generalization

After the FBAW benchmark is stable, the same agent architecture may be evaluated in adjacent deterministic engineering domains, such as:

- mmWave beam-steering transmit chains
- RF power-amplifier matching
- Antenna tuning
- Battery design and operating-policy optimization
- Semiconductor device or process optimization

Domain-specific simulators remain the numerical authority in every case.

## 4. Participating Model Families

The benchmark is intended to support models from multiple providers and architectural families, including but not limited to:

- OpenAI
- DeepSeek
- Cohere
- Anthropic Claude
- xAI Grok
- Google Gemini
- Alibaba Qwen
- Mistral AI
- Kimi
- Zhipu GLM
- Open-weight and locally hosted research models

Participation does not imply endorsement. Every model is evaluated under a declared, reproducible configuration.

## 5. Fair-Test Protocol

Every comparative run should use the same:

- Starting checkpoints and disclosed information
- Hidden-history policy
- Legal action space
- Parameter bounds
- Objective definitions and hard guards
- Action and computation budget
- Numerical simulator and optimizer version
- Random-seed policy
- Result schema and logging format

Provider-specific reasoning controls may be used, but they must be disclosed. Fixed dated model versions are preferred for reproducibility; aliases may be evaluated separately as continuously evolving systems.

No model may claim an RF result that has not been returned and verified by the deterministic engineering core.

## 6. Evaluation Metrics

### Two Separate RF Evaluation Tracks

Benchmark results must be reported in two distinct tracks. They must not be collapsed into a single ripple value.

#### Track A — Nominal Performance

This track reports **nominal passband ripple** under the baseline circuit condition. It evaluates the quality of the synthesized passband without additional inductor-loss or parasitic-capacitance stress.

The primary reported result is:

- Nominal passband ripple

Bandwidth, far-stopband rejection, transmission-zero locations, and insertion loss must still satisfy the applicable benchmark guards.

#### Track B — Robust Composite Performance

This track evaluates the design across the complete set of nominal and non-ideal conditions:

- Nominal passband ripple
- Q80/Cp40 passband ripple
- Q60/Cp60 passband ripple

The Q80/Cp40 and Q60/Cp60 cases represent progressively more demanding loss and parasitic-capacitance conditions. They should not be described simply as external interference.

The benchmark must publish all three ripple values separately. A composite score may additionally be used for ranking, but its formula and weights must be declared in the benchmark specification. The individual values may not be hidden by the composite score.

A model may therefore lead the Nominal Performance track without leading the Robust Composite Performance track. Both distinctions are technically meaningful and must be preserved in the public results.

### RF Performance

- Nominal passband ripple
- Q80/Cp40 ripple
- Q60/Cp60 ripple
- 3 dB bandwidth
- Lower and upper far-stopband rejection
- Transmission-zero locations
- Best and worst insertion loss
- Constraint margin

### Autonomous Reasoning

- Valid-action rate
- Quality of insertion and initialization decisions
- Cell-by-cell optimization decision quality
- Cell-selection and optimization-order quality
- Timing of transition to joint optimization
- Response to nominal-versus-robustness conflicts
- Stagnation detection
- Rollback quality
- STOP-decision quality
- Engineering explanation quality

### Efficiency and Reliability

- Number of actions and simulator calls
- Optimizer evaluations
- Input and output tokens
- Wall-clock time
- Estimated API cost
- Success rate across repeated runs
- Result variance
- Schema or tool-call failure rate
- Reproducibility across model snapshots

### Evaluation Integrity and Auditability

- Run-manifest completeness
- Action- and verification-trace completeness
- Unverified-claim rate
- Undisclosed human-intervention count
- Protocol-deviation count
- Hidden-history contamination incidents
- Result-to-raw-record consistency
- Independent-rerun agreement
- Configuration reproducibility
- Critical-incident reporting completeness

Human involvement must be classified for every published run:

1. **Fully autonomous** — no human changes to model decisions or run configuration after execution begins.
2. **Human-supervised** — a human may monitor, pause, or terminate execution for safety or infrastructure reasons but does not provide engineering decisions.
3. **Human-assisted** — a human modifies prompts, parameters, checkpoints, optimization strategy, or engineering decisions during the run.

These categories must be reported separately and must not be combined in a single autonomous-performance ranking.

## 7. Result Categories

Results should be published in separate categories:

1. **Best RF Result** — strongest verified final circuit performance.
2. **Best Robust Result** — strongest worst-case nominal/Q80/Q60 performance.
3. **Best Autonomous Engineer** — highest combined reasoning, recovery, and RF score.
4. **Best Efficiency** — strongest result per unit of computation, time, and API cost.
5. **Best Open Model** — best reproducible open-weight or locally hosted result.
6. **Most Reproducible Model** — lowest variance across repeated runs.
7. **Most Auditable Result** — most complete trace, configuration disclosure, intervention record, and independent-reproduction evidence.

A single overall ranking should not replace the detailed metric table.

## 8. Publication and Reproducibility Plan

The public repository will progressively include:

- Benchmark specification and version history
- Architecture and execution-flow documentation
- Sanitized reference checkpoints
- Legal action schemas
- Provider adapters where redistribution is permitted
- Deterministic verification code
- Versioned run manifests and environment information
- Machine-readable result records
- RF plots and Pareto summaries
- Failure and rollback traces
- Model cards for each evaluated configuration
- A public leaderboard with dated results
- Human-intervention declarations
- Independent-rerun records for major leaderboard results

Secrets, API keys, proprietary simulator files, and restricted model outputs will never be committed.

Every published result should identify the benchmark version, model ID, model snapshot if available, reasoning configuration, action budget, software environment, and verification status.

### Evaluation Integrity and Independent Reproduction

Numerical verification establishes whether a reported RF result is correct. Benchmark integrity additionally requires evidence that the model received only the declared information, operated within the declared action space and budget, and was not assisted by undisclosed human intervention.

Every published run should therefore include a versioned run manifest containing, at minimum:

- Benchmark, verifier, simulator, optimizer, and provider-adapter versions
- Exact model ID and snapshot when available
- System and task prompts, subject to clearly identified security or licensing redactions
- Disclosed checkpoints and declared hidden-history boundary
- Legal action schema, parameter bounds, objectives, and hard guards
- Random-seed policy and actual seeds when available
- Action, simulation, optimizer-evaluation, token, cost, and wall-clock budgets
- Software and hardware environment
- Complete action, verification, checkpoint, rollback, and STOP records
- Human-intervention classification and event log

Major leaderboard results should, where feasible, be independently rerun using the same deterministic verifier and declared manifest. Independent reproduction is distinct from engineering-embedded LLM evaluation: the former audits the credibility of the experiment, while the latter evaluates an LLM operating inside the engineering workflow.

Public challenges may include held-out checkpoints, parameter perturbations, failure injections, objective-weight scenarios, and topology-migration tasks. Their contents should remain inaccessible to evaluated models until the applicable test is complete. Any accidental exposure or historical-solution contamination must be recorded and the affected run excluded from blind-test rankings.

Funding, API credits, provider support, and configuration guidance must be disclosed. Sponsors and model providers may identify implementation or configuration errors, but they may not alter scoring rules after a run, suppress unfavorable verified results, or require a favorable conclusion. Disputed results should preserve the original records and document the positions of the benchmark team, provider, and independent reviewer where applicable.

## 9. Proposed Program Phases

### Phase A — Foundation

- Freeze the first public benchmark specification.
- Stabilize structured actions and Python verification.
- Reproduce existing OpenAI, DeepSeek, and Cohere baselines.
- Add Claude, Grok, and Gemini adapters.

### Phase B — Strategy Expansion

- Add autonomous cell-by-cell decision-making.
- Add parameter-subset and optimization-order selection.
- Add controlled joint/global refinement.
- Publish repeated-run statistics rather than single best runs.

### Phase C — Advanced Reasoning

- Add Pareto decision-making and robustness conflicts.
- Add controlled failure injection and recovery scoring.
- Add limited-budget resource allocation.
- Add hidden-history blind challenges.

### Phase D — Product-Family Scaling

- Extend evaluations across 3Rx1–3Rx8 and 4Rx structures.
- Compare migration, insertion, and re-synthesis strategies.
- Measure whether model performance transfers across order and resonator frequency.

### Phase E — Independent Participation

- Publish submission templates and verification requirements.
- Accept externally generated run manifests and traces.
- Re-run leading submissions with the reference verifier where feasible.
- Establish a transparent issue and review process for disputed results.
- Introduce versioned run manifests and human-intervention declarations.
- Pilot independent reruns of major leaderboard results.
- Establish procedures for held-out challenge custody and contamination reporting.

### Phase F — Cross-Domain Engineering

- Transfer the architecture to additional simulation-driven engineering problems.
- Separate general agent capability from domain-specific prompting and tools.
- Study whether the same model demonstrates consistent engineering behavior across domains.

## 10. Invitation to LLM Companies

We invite LLM developers and platform providers to participate through any of the following:

- Provide API credits or research access for reproducible evaluation.
- Recommend the correct production model and reasoning configuration.
- Supply technical guidance for structured outputs and tool calling.
- Review provider adapters for correct API usage.
- Submit an official model configuration for testing.
- Reproduce benchmark runs independently.
- Sponsor additional repeated runs or larger action budgets.
- Collaborate on agent reliability, evaluation methodology, and engineering reasoning research.

Support does not purchase a favorable result. Sponsored and non-sponsored runs will be clearly labeled, and the deterministic verifier will apply the same engineering criteria to every participant.

## 11. Participation Process

Interested organizations and researchers may:

1. Open a GitHub issue titled **Model Participation: [Organization / Model]**.
2. Identify the exact model or model family proposed for evaluation.
3. State whether API access, credits, configuration guidance, or engineering collaboration is offered.
4. Disclose any required settings or limitations.
5. Agree that published results will include both successful and unsuccessful verified runs under the declared protocol.

Private preliminary discussions may be used for integration details, but benchmark rules and final verified results should remain public.

### Private Technical Review and Long-Term Testing Partnerships

LLM companies may contact the project privately when they require more detailed information about their model's engineering behavior, including action traces, decision patterns, failure modes, rollback history, tool-use reliability, RF-performance progression, and comparisons across repeated runs.

Providers may also request additional or more demanding tests tailored to capabilities such as long-horizon planning, cell-by-cell optimization, adaptive objective weighting, failure recovery, limited-budget reasoning, or cross-domain engineering transfer. The scope, confidentiality, publication status, computation budget, and expected deliverables for such evaluations will be agreed upon before testing begins.

The project welcomes long-term testing relationships with LLM companies, including recurring evaluations of new model versions, joint design of advanced engineering benchmarks, technical review of model behavior, and independently verified progress tracking over time.

Private collaboration does not alter the standards of the public benchmark. Any result submitted to the public leaderboard must follow the published protocol, disclose relevant model and test configurations, and pass the same deterministic verification process applied to every participant. Confidential evaluations may remain private by prior agreement and will not be presented as public benchmark results without authorization.

## 12. Collaboration Principles

- Numerical truth comes from deterministic engineering tools.
- All models receive equivalent benchmark information and constraints.
- Negative results and failed strategies are scientifically valuable.
- Reproducibility is more important than promotional claims.
- Provider support is welcome, but benchmark governance remains independent.
- Funding, API credits, configuration guidance, and material conflicts of interest are disclosed.
- Autonomous, supervised, and human-assisted runs are labeled and reported separately.
- Independent reproduction audits experimental credibility; deterministic verification remains the authority for RF numerical truth.
- Engineering safety, IP restrictions, and data confidentiality are respected.
- The benchmark will evolve through explicit versioned specifications.

## 13. Long-Term Vision

The long-term goal is to establish a credible public standard for evaluating domain-specific agentic AI in engineering—not only whether an LLM can generate text or code, but whether it can make disciplined, auditable, result-dependent engineering decisions under incomplete information, competing objectives, hard constraints, and limited resources.

The central question is:

> **Which LLM behaves most like an autonomous engineer while still respecting deterministic tools as the authority for numerical truth?**

Organizations interested in supporting or participating in this research are warmly invited to join the discussion through GitHub issues and future benchmark calls.
