# V1.4 Multi-LLM Persistent Verified Evolution

## 30-Decision Comparative Analysis of Long-Horizon Autonomous Engineering

### Overview

V1.4 extends the earlier independent-run benchmark into a harder
long-horizon experiment:

> **Can an LLM accumulate verified engineering progress, preserve
> successful designs, discard failures, reuse prior experience, and
> improve persistently across a sequence of engineering decisions?**

Four LLMs were evaluated over the same **30-decision horizon**:

**Cohere · xAI · DeepSeek · Claude**

All four operated inside the same engineering-embedded evaluation
architecture:

**Engineering Goal → LLM Decision → Tool Execution → Deterministic
Python Verification → Accept / Reject / Rollback → Persistent Memory →
Re-plan**

The **Golden 4Rx5 solution was hidden during evolution**. It was
disclosed only after the runs and used as a common post-run reference.

V1.4 therefore does **not** ask whether an LLM can imitate a known
Golden solution. It asks whether verified engineering experience can
accumulate into useful autonomous progress when the target solution is
unknown.

------------------------------------------------------------------------

## 1. Benchmark Contract

The benchmark used a real Lower-FR3 FBAW/DFR filter-synthesis task.

The persistent agent was allowed to preserve verified checkpoints,
maintain Pareto and repairable branches, select previously verified
parents, explore alternative engineering actions, and recover after
unsuccessful candidates.

Python remained the numerical authority throughout the experiment.

Key rules:

-   Common engineering problem and deterministic RF verification.
-   Common 30-decision horizon for the formal cross-model comparison.
-   Golden parameters and Golden performance metrics hidden during
    evolution.
-   Candidate designs verified before they could replace a preserved
    solution.
-   Failed or dominated candidates could be rejected without destroying
    verified progress.
-   Useful nondominated candidates could enter Pareto memory.
-   Hard 5-cell feasibility guards included:
    -   **Q60 bandwidth ≥ 0.750 GHz**
    -   **Rejection ≥ 80 dB** under Nominal, Q80, and Q60 conditions.
-   Passband ripple was treated as a multi-objective engineering
    quantity rather than a disclosed Golden target.

The central purpose was not simply to minimize one scalar number. It was
to observe how an LLM uses verified engineering history over time.

------------------------------------------------------------------------

## 2. Closest Verified Solutions to the Hidden Golden

The most informative V1.4 comparison is not necessarily the Decision #30
endpoint.

Because V1.4 preserves multiple verified/Pareto branches, an important
solution may occur before the final decision. After the Golden reference
was unblinded, representative verified or feasible checkpoints closest
to the Golden solution were selected for comparison.

![V1.4 Multi-LLM Persistent Verified Evolution --- Closest Verified
Solutions to Golden](V1_4_Closest_Verified_to_Golden_LARGE_FONT.png)

### Representative checkpoints

  ---------------------------------------------------------------------------------------
  Model           Selected Nominal ripple     Q80 ripple     Q60 ripple Interpretation
                checkpoint           (dB)           (dB)           (dB) 
  ----------- ------------ -------------- -------------- -------------- -----------------
  Cohere              CP29       0.750158       0.557516       0.830534 Robust-oriented
                                                                        verified basin

  xAI                 CP20       0.662798       0.573975       0.779202 Strong
                                                                        nominal/robust
                                                                        balance

  DeepSeek            CP21   **0.591294**   **0.609387**   **0.913809** Low-nominal
                                                                        Pareto point very
                                                                        close to Golden
                                                                        ripple targets

  Claude              CP26       0.738267       0.573037       0.842695 Balanced robust
                                                                        verified solution

  Golden               ---   **0.598967**   **0.684248**   **0.915071** Hidden during
  reference                                                             V1.4 evolution
  ---------------------------------------------------------------------------------------

The figure is a **post-run comparison**, not information that was
available to the planners during evolution.

A particularly important result is **DeepSeek CP21**. Its Nominal, Q80,
and Q60 ripple values are all at or below the later-unblinded Golden
ripple references. CP21 also satisfies the V1.4 engineering bandwidth
and ≥80-dB rejection guards. However, it does **not** reproduce every
stricter Golden bandwidth/rejection value, so it should not be described
as a full Golden PASS.

This distinction is important: V1.4 discovered a solution with
Golden-level ripple performance without giving the model the Golden
target.

------------------------------------------------------------------------

## 3. Verified Engineering Evolution Videos

To complement the numerical benchmark results, four publication videos
visualize the observable engineering evolution produced by the V1.4
planners inside the deterministic benchmark harness.

These videos show the externally observable benchmark process, including
engineering actions, verified performance changes, checkpoint preservation,
repair attempts, strategy changes, and convergence or saturation behavior.
They are **not** visualizations of hidden chain-of-thought. Numerical
performance remains determined exclusively by the deterministic Python
verifier.

- [DeepSeek — V1.4 Verified Engineering Evolution](videos/DeepSeek_V1_4_Verified_Engineering_Evolution.mp4)
- [Cohere — V1.4 Verified Engineering Evolution](videos/Cohere_V1_4_Verified_Engineering_Evolution.mp4)
- [xAI Grok — V1.4 Verified Engineering Evolution](videos/xAI_Grok_V1_4_Verified_Engineering_Evolution.mp4)
- [Claude — V1.4 Verified Engineering Evolution](videos/Claude_V1_4_Verified_Engineering_Evolution.mp4)

The videos are supporting visual records of the experiment; the verified
numerical results and benchmark contract remain the primary evidence.

------------------------------------------------------------------------

## 4. Cohere --- Persistent Memory with Long-Horizon Saturation

Cohere demonstrated that verified engineering progress could survive
across phases. It preserved successful checkpoints, retained repairable
branches, recovered from failed actions, and moved between optimization
basins.

Its trajectory can be summarized as:

**Topology construction → robust basin → low-nominal repair branch →
repeated repair → strategy switch → Pareto exploration → new robust
solution**

The formal 30-decision run produced a robust-oriented solution family. A
representative later verified basin, CP29, reached approximately:

-   Nominal ripple: **0.750158 dB**
-   Q80 ripple: **0.557516 dB**
-   Q60 ripple: **0.830534 dB**

Cohere was also extended separately from Decision #31 to #40. Those
extra decisions produced only small additional movement while repeatedly
revisiting similar repair behavior.

That extension is scientifically useful, but it is **not included in the
equal-horizon four-model comparison**.

It suggests an important distinction:

> **Persistent memory does not automatically produce persistent
> intelligence improvement.**

An agent may preserve engineering history correctly while still failing
to convert repeated outcomes into a sufficiently different next
strategy.

------------------------------------------------------------------------

## 5. xAI --- Strategy Switching and Pattern Transfer

xAI showed a different persistent-engineering pattern.

Its trajectory can be summarized as:

**Rapid feasible construction → robust polish → saturation recognition →
nominal exploration → repair → pattern transfer → new verified basin**

A representative verified checkpoint, CP20, reached:

-   Nominal ripple: **0.662798 dB**
-   Q80 ripple: **0.573975 dB**
-   Q60 ripple: **0.779202 dB**

with:

-   Nominal BW: **0.8235 GHz**
-   Q80 BW: **0.7900 GHz**
-   Q60 BW: **0.7780 GHz**
-   Nominal rejection: **80.992198 dB**
-   Q80 rejection: **80.369926 dB**
-   Q60 rejection: **80.015400 dB**

One of the more interesting behaviors was that xAI did not only retrieve
previous states. It attempted to reuse an earlier successful repair
pattern when a later branch exhibited a related engineering problem.

This motivates a distinction between:

**memory retrieval** and **experience abstraction**.

The second is a more demanding capability for autonomous engineering.

------------------------------------------------------------------------

## 6. DeepSeek --- Productive Persistence Along a Constraint Boundary

DeepSeek produced one of the clearest examples of **productive
persistence** in V1.4.

During Phase II, repeated `BALANCED_REPAIR` actions progressively moved
a repair lineage toward the hard 80-dB Q60 rejection boundary.

The Q60 rejection evolved approximately as:

**79.995648 → 79.997675 → 79.997700 → 79.999873 → 79.999704 → 80.000221
dB**

while nominal ripple also improved.

These repeated actions were therefore not merely duplicate behavior.
They produced measurable movement along a constraint boundary until a
previously infeasible branch became verified feasible.

Phase III then produced the especially important **CP21**:

-   Nominal ripple: **0.591294 dB**
-   Q80 ripple: **0.609387 dB**
-   Q60 ripple: **0.913809 dB**

Compared with the later-unblinded Golden ripple values:

-   Golden Nominal: **0.598967 dB**
-   Golden Q80: **0.684248 dB**
-   Golden Q60: **0.915071 dB**

CP21 improves all three ripple values while satisfying the V1.4
engineering feasibility guards.

DeepSeek also exposed multiple distinct solution families:

**low-nominal frontier → balanced frontier → robust frontier**

Its later robust solution was approximately:

**0.695 / 0.573 / 0.861 dB**

The coexistence of CP21 and the robust frontier demonstrates why the
benchmark should retain a **Pareto archive** rather than report only one
final scalar-best checkpoint.

------------------------------------------------------------------------

## 7. Claude --- Broad Exploration Followed by Robust Convergence

Claude entered Phase III from a verified state around:

**0.737994 / 0.573500 / 0.842828 dB**

for Nominal/Q80/Q60 ripple.

Its Phase-III exploration included several explicit engineering
strategies:

**TUNE_CELL → alternative Pareto TUNE_CELL → BEST TUNE_CELL →
BALANCED_REPAIR → TUNE_BOUNDARY**

Most of these attempts did not improve the incumbent.

A useful but infeasible branch appeared at CP23:

**0.713816 / 1.065128 / 1.277051 dB**

with Q60 rejection falling to **79.675428 dB**.

A subsequent repair restored Q60 rejection to **79.997420 dB**, very
close to the 80-dB feasibility guard but still below it.

Claude then returned to deterministic `JOINT_ROBUST_POLISH` and obtained
**CP26**:

-   Nominal ripple: **0.738267 dB**
-   Q80 ripple: **0.573037 dB**
-   Q60 ripple: **0.842695 dB**
-   BW: **0.8230 / 0.7845 / 0.7725 GHz**
-   Rejection: **81.2321 / 80.5718 / 80.1981 dB**

CP26 became Claude's Best Verified checkpoint.

Claude also generated other Pareto branches, including CP28 and the
near-feasible CP29. It ultimately preserved the verified incumbent
rather than replacing it with an infeasible branch.

------------------------------------------------------------------------

## 8. Cross-Model Engineering-Behavior Comparison

V1.4 is primarily a study of persistent engineering behavior, not a
model ranking.

  ---------------------------------------------------------------------------
  Engineering     Cohere         xAI            DeepSeek       Claude
  behavior                                                     
  --------------- -------------- -------------- -------------- --------------
  Verified        Strong         Strong         Strong         Strong
  checkpoint                                                   
  retention                                                    

  Repair-memory   Extensive      Effective      Extensive      Moderate
  use                                                          

  Strategy        Demonstrated   Clearly        Demonstrated   Demonstrated
  switching                      demonstrated                  

  Productive      Limited in     Some           Strong example Limited
  repeated repair later horizon                                

  Saturation      Weakest in     Clear          Clear in Phase Partial
  recognition     extended run                  III            

  Experience /    Present        Explicit       Strong lineage More local
  pattern reuse                                 reuse          

  Pareto          Strong         Strong         Strong         Strong
  exploration                                                  

  Near-feasible   Yes            Yes            Yes            Yes
  branch                                                       
  discovery                                                    

  Near-feasible → Demonstrated   Demonstrated   Clearly        Not in Phase
  feasible                                      demonstrated   III
  conversion                                                   

  Safe            Yes            Yes            Yes            Yes
  preservation                                                 
  after failures                                               
  ---------------------------------------------------------------------------

These descriptions refer only to behavior observed inside this benchmark
configuration.

------------------------------------------------------------------------

## 9. The Central V1.4 Finding

V1.4 suggests that **persistent autonomous engineering should not be
measured only by whether an LLM remembers previous checkpoints**.

Three distinct phenomena appeared.

### Productive persistence

Repeated actions continue moving a design toward feasibility.

DeepSeek's constraint-boundary repair sequence is the clearest V1.4
example.

### Adaptive strategy switching

The planner recognizes diminishing returns and changes optimization
direction.

This was visible particularly in xAI and later DeepSeek behavior.

### Unproductive saturation

The system retains memory, but similar strategies repeatedly regenerate
essentially the same engineering basin.

This became especially visible in Cohere's separate #31--#40
extended-horizon experiment.

The central conclusion is therefore:

> **Persistent memory is necessary for long-horizon autonomous
> engineering, but it is not sufficient. The more demanding capability
> is converting accumulated verified experience into better future
> engineering decisions.**

------------------------------------------------------------------------

## 10. Proposed Long-Horizon Benchmark Metrics

V1.4 indicates that FINAL PASS rate and endpoint RF performance alone
are insufficient for evaluating a persistent engineering agent.

The following metrics are proposed for future benchmark versions:

1.  **Verified Progress Retention (VPR)** --- whether previously
    verified progress survives later unsuccessful exploration.
2.  **Productive Action Ratio (PAR)** --- fraction of decisions
    producing meaningful verified or Pareto progress.
3.  **Duplicate / Saturation Ratio (DSR)** --- fraction of actions
    returning identical or near-identical engineering states.
4.  **Near-Feasible Conversion Rate (NFCR)** --- ability to convert
    promising constraint-violating states into verified feasible
    designs.
5.  **Strategy-Switch Effectiveness (SSE)** --- whether changing
    engineering strategy after saturation produces a useful new basin.
6.  **Pareto Expansion** --- number and diversity of nondominated
    verified engineering solutions accumulated over time.
7.  **Constraint-Boundary Progress** --- quantitative movement toward
    feasibility along repair trajectories.
8.  **Best Verified Progress vs. Decision Number** --- long-horizon
    evolution of the best preserved engineering state.

These metrics shift the benchmark question from:

> *Which model produced the lowest final ripple?*

toward:

> **How effectively does an LLM use accumulated, deterministically
> verified engineering experience while operating inside a real
> tool-using workflow?**

------------------------------------------------------------------------

## 11. Frozen V1.4 Study Structure

V1.4 should be interpreted in two parts.

### Part A --- Equal-Horizon Multi-LLM Comparison

**Cohere / xAI / DeepSeek / Claude --- Decisions #1→#30**

This is the formal cross-model comparison.

### Part B --- Extended-Horizon Persistence Study

**Cohere --- Decisions #31→#40**

This separate extension examines what happens after a persistent agent
has already accumulated substantial verified engineering history and
approaches a mature optimization basin.

Keeping the two parts separate preserves fairness in the common
30-decision comparison while retaining the scientifically useful
saturation experiment.

------------------------------------------------------------------------

## 12. Limitations

V1.4 should not be interpreted as a general ranking of LLM intelligence
or engineering capability.

The observed behavior depends on:

-   the specific RF/FBAW synthesis problem,
-   the deterministic operator set exposed to the planner,
-   the checkpoint/Pareto/repair memory architecture,
-   the optimization budget,
-   the model/API configuration used during the experiment,
-   and the 30-decision horizon.

The LLM proposes engineering actions, but **Python remains the numerical
authority**. Therefore the benchmark evaluates the combined behavior of
an LLM planner operating inside a constrained deterministic engineering
environment.

The results also show that the available action space can influence what
the planner is able to achieve. A model may identify a useful direction
while the deterministic operator available for that direction remains
too coarse to reach the desired neighboring basin.

------------------------------------------------------------------------

## 13. From V1.4 to V1.5: Selecting the Common Starting Point

V1.4 establishes the **Golden-hidden persistent evolution** baseline.

Its key question is:

> **Can an LLM autonomously evolve toward strong engineering solutions
> when the Golden reference is hidden?**

After all V1.4 runs were completed, the previously hidden Golden
reference was unblinded and the preserved verified solutions were
compared against it. The transition to V1.5 did **not** mechanically use
each model's Decision #30 endpoint. Instead, the preserved verified
checkpoint closest to the Golden reference was selected as the common
starting design for the next benchmark stage.

The selected design was **DeepSeek CP21**:

- Nominal ripple: **0.591294 dB**
- Q80 ripple: **0.609387 dB**
- Q60 ripple: **0.913809 dB**

The corresponding Golden ripple values are:

- Nominal: **0.598967 dB**
- Q80: **0.684248 dB**
- Q60: **0.915071 dB**

CP21 therefore matched or improved all three Golden ripple references
while satisfying the V1.4 engineering feasibility guards. It did not,
however, reproduce every stricter Golden bandwidth and rejection value,
so it was **not** a full Golden PASS.

This combination made CP21 an especially informative transition point:
it was already close to the hidden Golden solution, but still left
specific multi-metric deficits that could be attacked in a controlled
follow-on experiment.

V1.5 deliberately changes the experimental condition:

- the topology remains fixed at **4Rx5**;
- **all evaluated LLMs start from the same verified DeepSeek CP21
  design**;
- the Golden reference is explicitly disclosed to every planner; and
- success requires simultaneously meeting or exceeding **all nine
  Golden performance metrics** under the strict **BEAT_GOLDEN**
  criterion.

The V1.5 question therefore becomes:

> **Starting from the same near-Golden verified design, can an LLM use
> the disclosed Golden reference to close the remaining deficits and
> beat the Golden solution across all nine metrics simultaneously?**

Using one common CP21 starting point is important for experimental
fairness. It removes differences in V1.4 terminal state from the V1.5
comparison and ensures that subsequent cross-model differences arise
from the Golden-informed evolution stage rather than from different
starting designs.

This creates a clean benchmark progression:

**V1.3 — Independent repeated engineering**  
→ **V1.4 — Golden-hidden persistent verified evolution**  
→ **Select closest verified V1.4 checkpoint: DeepSeek CP21**  
→ **V1.5 — Common CP21 start + Golden-informed BEAT_GOLDEN evolution**

------------------------------------------------------------------------

## Conclusion

V1.4 demonstrates that long-horizon LLM engineering behavior cannot be
characterized adequately by a single final RF number.

Across 30 verified decisions, the four planners displayed different
combinations of checkpoint retention, repair reuse, Pareto exploration,
strategy switching, constraint-boundary progress, and saturation.

The strongest scientific observation is not that one model produced one
particular endpoint. It is that **verified experience can be preserved
across long engineering trajectories, yet preservation alone does not
guarantee continued improvement**.

For autonomous engineering agents, the key capability is therefore not
simply memory.

It is the ability to transform accumulated, verified engineering
experience into increasingly effective future decisions.
