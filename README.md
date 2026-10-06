# AI-Aided Hybrid Beamforming for 6G FR3

**Real-time AI-aided hybrid downlink beamforming for 6G FR3 under imperfect CSI and outage constraints, with emphasis on reproducible GPU implementation, operational failure analysis, pre-failure early warning, hierarchical recovery, and large-scale statistical validation.**

**Research project:** George X. Ji, Ph.D.  
**Status:** Active research — System V0.5  

---

## 1. Overview

This repository presents an independent research program on AI-aided hybrid downlink beamforming for future 6G FR3 wireless systems.

The work uses previously published model-driven deep-learning research on hybrid beamforming under imperfect channel-state information (CSI) and probabilistic outage constraints as a **scientific reference and baseline**. From that starting point, this project develops an independent engineering research path centered on GPU reproduction, real-time operation, failure-state characterization, pre-failure early warning, hierarchical recovery, and large-scale validation.

The central system-level question is:

> **Given a beamforming system designed and evaluated under a nonzero statistical outage constraint, can operational failures be detected early and repaired efficiently without changing the underlying statistical formulation?**

The long-term objective is therefore not simply to report average model performance. It is to understand and improve what happens at the frame level when the system approaches or enters a QoS failure state.

---

## 2. Research Philosophy

The project follows a common engineering philosophy shared with our parallel FBAW filter research track:

> **AI-assisted decisions + deterministic engineering verification**

AI or learned models may provide inference, prediction, prioritization, or supervisory decisions. Numerical and engineering validity remains subject to deterministic evaluation against explicitly defined physical/system constraints.

At the portfolio level, the two research tracks address complementary layers:

- **FBAW Filter Engineering** — AI-aided RF device/front-end and filter synthesis.
- **AI-Aided Hybrid Beamforming — 6G FR3** — AI-aided wireless PHY/system engineering.

Together they form a broader **AI-Aided 6G Engineering** research direction spanning RF hardware and wireless system operation.

---

## 3. Research Roadmap

```text
Published Model-Driven DL Research
              |
              v
     Independent Reproduction
              |
              v
       GPU Implementation
              |
              v
       Real-Time System
              |
              v
    Failure / Outage Analysis
              |
              v
   Pre-Failure Early Warning
              |
              v
      Hierarchical Repair
              |
              v
   20K+ Statistical Validation
              |
              v
 Future LLM Exception Supervisor
```

The roadmap deliberately separates **baseline reproduction**, **system instrumentation**, **failure analysis**, and **new recovery mechanisms** so that improvements can be attributed and verified independently.

---

## 4. Scientific Reference Baseline

The starting scientific reference is published work on **hybrid downlink beamforming with outage constraints under imperfect CSI using model-driven deep learning**.

The reference problem combines:

- hybrid analog/digital downlink beamforming;
- imperfect CSI;
- probabilistic QoS/outage constraints;
- learned/model-driven optimization;
- deep-unrolling/model-aided neural architecture concepts; and
- evaluation across channel/CSI and operating conditions.

This repository does **not** redistribute the referenced authors' source code, datasets, checkpoints, figures, tables, or copyrighted text. The published work is cited only as scientific background and a baseline for independent research.

---

## 5. Independent Reproduction and GPU Track

The first stage of this project establishes a reproducible computational baseline before introducing new system-level mechanisms.

### Phase 0 — Reproduction baseline

The reproduction track preserves the reference problem formulation and key experimental settings while establishing an independently controlled implementation and evaluation workflow.

Representative frozen baseline settings include:

- 4 x 4 BS configuration;
- 3 users;
- 5 RF chains;
- imperfect-CSI/outage-constrained operation;
- target outage setting `P_out = 0.10`;
- model family: `HybridUnrolled / MSA_LOGCONV_4I_3L_F2x32`;
- two-stage training/evaluation workflow; and
- fixed evaluation configurations used for consistency studies.

### CPU-to-GPU engineering

The implementation path was intentionally staged:

1. CPU smoke/pilot verification;
2. direct GPU-port baseline;
3. GPU consistency and timing evaluation;
4. GPU-native Level-2 implementation optimization without changing algorithm mathematics; and
5. only later, if justified, algorithm/workload-level optimization.

The direct GPU-port baseline is frozen as the reproducibility reference. Level-2 GPU-native work is intended to improve implementation efficiency while preserving the underlying mathematics.

This separation prevents runtime optimization from being confused with algorithmic improvement.

---

## 6. From Statistical Outage to Operational Failure

A statistical outage target such as

```text
P_out = 0.10
```

is part of the reference problem formulation. This project does **not** redefine that statistical setting simply to make failures disappear.

Instead, the system research asks a different question:

> **Can a system operating under the same statistical outage setting convert a substantial fraction of imminent or realized frame-level failures into successful operational outcomes through detection and repair?**

Conceptually:

```text
~10% statistical outage setting
            |
            v
frame-level failure characterization
            |
            v
pre-failure detection / recoverability assessment
            |
            v
hierarchical repair
            |
            v
minimize operational failure rate
```

This distinction between **statistical outage formulation** and **operational failure behavior** is a central theme of the project.

---

## 7. Real-Time System Evolution

### System V0.3 — Real-time repair baseline

System V0.3 established the real-time/failure-repair framework used as the frozen simulator foundation for subsequent studies.

The goal is not to retrain the reference model whenever a frame fails. Instead, the system treats the trained beamforming solution as the nominal operating point and investigates deterministic, bounded interventions when QoS constraints are threatened or violated.

### System V0.4 — Failure-State Capture

System V0.4 introduced explicit failure-state capture and instrumentation.

The purpose of this stage is observational:

- capture PRE-REPAIR QoS failure states;
- preserve temporal/frame history;
- characterize failure episodes and onset events;
- evaluate repair outcomes;
- separate recoverable and difficult cases; and
- create data for later early-warning studies.

The frozen workflow avoids training, LLM intervention, and opportunistic retuning during data capture.

Representative P17 audit data currently used as a validated reference contains:

- 4,000 evaluated frames;
- 930 PRE-REPAIR QoS-outage failure frames;
- 331 failure-onset events;
- 303 complete pre-failure windows; and
- 28 incomplete windows.

These figures are research-stage measurements from the frozen audit workflow, not claims of universal system performance.

---

## 8. Internal Audit Status

Internal trajectory audits for selected pilot-power cases were used to determine whether additional model-internal investigation was necessary.

The **P10 / P14 / P20 / P24 internal audit is currently frozen**. The project does not continue deeper model-internal analysis unless that research question is explicitly reopened.

This decision keeps the project focused on the higher-value system question:

> What observable pre-failure information can support reliable operational intervention?

---

## 9. System V0.5 — Pre-Failure Early Warning + Hierarchical Repair

**Current research phase**

System V0.5 shifts the emphasis from post-failure inspection toward **pre-failure trajectory analysis and recoverability-aware intervention**.

The primary objective is:

> **Preserve the reference statistical outage setting while reducing the final operational failure rate through early warning and hierarchical repair.**

### Phase A — Pre-Failure Early-Warning Study

The first V0.5 study reuses frozen System V0.4 failure-capture data and adds instrumentation rather than changing the beamforming mathematics.

For each failure-onset event, the analysis examines historical states before the onset, including windows such as:

```text
t0-5 ... t0-2, t0-1, t0
```

Candidate precursor information includes frame-level QoS/SINR margins, trajectory evolution, mobility context, and other state variables already available to the system.

At this stage:

- thresholds are descriptive/research quantities;
- no final SAFE -> AT-RISK supervisor threshold is frozen;
- no new training is introduced;
- no LLM is placed in the real-time control loop; and
- no claim is made yet that early warning reduces the final failure rate.

Those claims require subsequent repair experiments and frozen-rule validation.

### Phase B — Recoverability and residual-failure analysis

Failure cases are studied according to their repair behavior rather than treated as a single homogeneous class.

A working hierarchy includes categories such as:

```text
EASY
  -> low-cost / fast recovery candidate

MODERATE
  -> requires stronger deterministic repair or supervisory reasoning

HARD
  -> difficult or unrecoverable under the available repair hierarchy
```

In the current P17 reference study, FAST recovery has demonstrated complete recovery of the audited EASY subset (97/97), while MODERATE and HARD cases motivate deeper hierarchical-repair research. This is an internal research result to be subjected to larger frozen-rule validation before being generalized.

---

## 10. Hierarchical Repair Concept

The intended architecture is deliberately hierarchical so that expensive or disruptive interventions are not used when a simpler repair is sufficient.

Conceptually:

```text
NORMAL OPERATION
      |
      v
PRE-FAILURE RISK DETECTION
      |
      v
FAST / LOW-COST REPAIR
      |
      +---- success ---> continue operation
      |
      v
DIGITAL / POWER REPAIR
      |
      +---- success ---> continue operation
      |
      v
RF / BEAM RESELECTION
      |
      +---- success ---> continue operation
      |
      v
EXCEPTION / HARD CASE
```

The exact hierarchy remains subject to deterministic testing. The design principle is to preserve the existing RF state when possible and escalate only when necessary.

A future research question is whether a lightweight supervisor can identify which intervention is appropriate **before** a QoS failure becomes operationally unavoidable.

---

## 11. LLM Role — Deferred Exception Supervision

LLMs are **not** used as replacements for the numerical beamforming solver or deterministic QoS verification.

The current architecture intentionally keeps the LLM out of the fast real-time loop.

A future LLM role may be investigated for **exception supervision**, particularly for MODERATE or otherwise ambiguous cases where deterministic low-cost repair is insufficient.

Potential responsibilities include:

- selecting among verified repair strategies;
- interpreting failure context;
- proposing bounded candidate actions;
- prioritizing escalation paths; and
- supporting offline engineering analysis.

Every proposed action would remain subject to deterministic system verification before acceptance.

Thus the intended control philosophy is:

```text
LLM / AI supervisor proposes or prioritizes
                 |
                 v
Deterministic beamforming/QoS engine verifies
                 |
                 v
          ACCEPT / REJECT
```

---

## 12. Large-Scale Validation

Small and medium research runs are used to discover mechanisms and freeze rules; they are not sufficient for final statistical claims.

The planned validation stage therefore targets **20,000+ frames/configurations as appropriate to the frozen experiment design**, with emphasis on:

- final operational failure rate;
- statistical confidence;
- mobility dependence;
- pilot/CSI-quality dependence;
- early-warning precision and recall;
- false-warning rate;
- repair success probability;
- repair cost/latency;
- escalation frequency; and
- performance under unseen or shifted conditions.

Crucially, thresholds and repair rules should be frozen before the final large-scale evaluation to avoid tuning on the test population.

---

## 13. Current Research Questions

The project is currently organized around several linked questions:

1. **Pre-failure observability** — Are there repeatable frame-history signatures before QoS failure onset?
2. **Lead time** — How early can risk be detected while remaining actionable?
3. **Recoverability** — Can impending failures be separated into EASY, MODERATE, and HARD intervention classes?
4. **Minimal intervention** — What is the lowest-cost repair that restores QoS?
5. **Operational reliability** — How much can final unrecovered failure be reduced while preserving the original statistical outage setting?
6. **Generalization** — Do frozen warning/repair rules remain effective across mobility and CSI/pilot conditions?
7. **AI supervision** — Can an AI/LLM supervisor improve exception handling without replacing deterministic numerical authority?

---

## 14. Repository Structure

```text
AI-Aided-Hybrid-Beamforming-6G-FR3/
|
|-- README.md
|-- LICENSE
|-- CITATION.cff
|
|-- docs/
|   |-- research_roadmap.md
|   |-- system_architecture.md
|   `-- attribution.md
|
|-- gpu_reproduction/
|   |-- README.md
|   `-- results/
|
|-- realtime_system/
|   |-- README.md
|   `-- results/
|
|-- failure_analysis/
|   |-- README.md
|   `-- results/
|
|-- early_warning/
|   |-- README.md
|   `-- results/
|
|-- hierarchical_repair/
|   |-- README.md
|   `-- results/
|
|-- validation/
|   |-- README.md
|   `-- results/
|
`-- figures/
```

Only independently developed material with clear release status should be added to the public repository.

---

## 15. Public-Release Boundary

### Intended for public release

- independently written project documentation;
- independently developed system-level source code approved for release;
- independently generated experimental results;
- independently generated figures and tables;
- reproducibility metadata that does not redistribute third-party protected material; and
- citations to relevant published research.

### Not redistributed here

- original authors' source code;
- original authors' datasets or checkpoints;
- original figures or tables;
- copied manuscript text; or
- other copyrighted material from the referenced research unless separately authorized by its applicable license.

Files whose ownership or redistribution status is uncertain should remain outside the public repository until reviewed.

---

## 16. Research Attribution

This project was developed with reference to previously published model-driven deep-learning research on hybrid beamforming under imperfect CSI and outage constraints.

The referenced work serves as a scientific baseline and research reference. **No original source code, datasets, checkpoints, figures, tables, or other copyrighted materials from the referenced authors are redistributed in this repository.**

All implementations, GPU engineering, real-time system studies, failure/outage analyses, early-warning studies, recovery mechanisms, validation workflows, and AI-aided engineering extensions presented here are independently developed as part of this research project, except where explicitly stated otherwise.

The complete bibliographic citation to the scientific reference will be included in the References section using the published paper metadata.

---

## 17. Research Integrity and Reproducibility

The project uses explicit versioning and frozen checkpoints to distinguish exploration from verified results.

Key principles include:

- freeze a baseline before testing an extension;
- preserve deterministic seeds/settings when performing controlled comparisons;
- separate instrumentation from algorithm changes;
- distinguish PRE-REPAIR failure from POST-REPAIR outcome;
- distinguish failure frames from failure-onset events;
- record rejected as well as accepted engineering interventions when relevant;
- avoid tuning final rules on final validation data; and
- report limitations and unresolved cases alongside successful results.

These practices are intended to make AI-aided engineering decisions auditable rather than opaque.

---

## 18. Current Status

```text
[Completed / Frozen]
  CPU reproduction and profiling
  Direct GPU-port baseline
  GPU-native Level-2 baseline work
  Real-time system foundation
  System V0.4 failure-state capture
  P10/P14/P20/P24 internal-audit phase
  P17 reference failure/onset audit

[Active]
  System V0.5
    - pre-failure history capture
    - precursor analysis
    - EASY recovery characterization
    - residual-failure / recoverability analysis
    - hierarchical repair design

[Next]
  freeze early-warning rule
  freeze repair hierarchy
  cross-condition validation
  20K+ statistical evaluation

[Future]
  recoverability-aware AI supervisor
  LLM exception supervision
  broader FR3 channel/system studies
  RF/PHY cross-layer AI-aided engineering
```

---

## 19. Broader Research Direction

This repository is one of two complementary AI-aided engineering research tracks:

```text
AI-Aided 6G Engineering
|
|-- RF Device / Front-End
|     `-- FBAW Filter Engineering
|
`-- Wireless PHY / System
      `-- AI-Aided Hybrid Beamforming — 6G FR3
```

A future direction is to connect these layers through AI-aided RF/PHY co-design while retaining deterministic verification at each engineering layer.

---

## 20. Citation

If this repository contributes to your research, please cite the corresponding publication or technical report associated with the specific released result.

A repository-level `CITATION.cff` will be added as public results mature.

---

## Disclaimer

This repository is an independent research project. References to published third-party research are for scientific attribution and technical context only and do not imply endorsement, affiliation, or authorship by the referenced researchers or institutions.

