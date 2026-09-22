# V1.3 --- Multi-LLM Autonomous Engineering Benchmark

## What Prevented Six LLMs from Reaching Golden-Level RF/FBAW Performance?

**Benchmark:** Blind 4Rx3 → 4Rx5 autonomous synthesis\
**Domain:** Lower-FR3 RF/FBAW filter engineering\
**Models:** Cohere, DeepSeek, OpenAI, Claude, xAI, Gemini\
**Runs:** 18 independent runs (3 per model), up to 10 sequential
engineering actions per run\
**Numerical authority:** Deterministic Python verification\
**Frozen result:** **0/18 Python-authorized FINAL PASS**

> **Engineering Goal → LLM Planning → Tool Execution → Python
> Verification → Accept / Reject / Rollback → Re-plan →
> Python-authorized STOP**

This benchmark evaluates whether an LLM can use verified engineering
feedback to make sequential, result-dependent decisions in a tightly
constrained multi-objective RF design problem. It is not a text-only
question-answer benchmark, and the LLM is not the numerical authority.

------------------------------------------------------------------------

## 1. Evolution of the Benchmark

The V1.3 result should be interpreted together with our earlier blind
higher-order synthesis experiments.

  --------------------------------------------------------------------------
  Benchmark          Models / Task     Constraint Regime   Result
  ------------------ ----------------- ------------------- -----------------
  Earlier blind      3 LLMs; 3Rx4 →    Broad,              **Successful**
  synthesis          blind 3Rx6 →      comparatively       
                     blind 3Rx8        permissive; focused 
                                       on autonomous       
                                       topology growth and 
                                       engineering-valid   
                                       synthesis, without  
                                       an equally tight    
                                       simultaneous        
                                       performance         
                                       envelope            

  V1.3               6 LLMs; blind     Explicit, tight     **0/18 FINAL
                     4Rx3 → 4Rx5       Nominal / Q80 / Q60 PASS**
                                       / BW / rejection    
                                       limits              

  Human-engineered   Verified 4Rx5     Same tight V1.3     **PASS**
  control            Golden            requirements        
  --------------------------------------------------------------------------

The earlier experiments demonstrated that LLMs can autonomously expand
filter topology and obtain valid higher-order designs when the
acceptable solution region is relatively broad.

V1.3 asks a substantially harder question: can the LLM construct and
optimize the filter until **all tightly coupled quantitative
requirements are satisfied simultaneously**?

**Autonomous synthesis success under broad engineering constraints does
not necessarily imply autonomous optimization success under a narrow,
simultaneous, quantitatively defined performance envelope.**

Most importantly, the V1.3 target is not infeasible. A verified
human-engineered 4Rx5 Golden design satisfies the same requirements.
Therefore, the 0/18 result cannot be explained simply by an impossible
target.

------------------------------------------------------------------------

## 2. Frozen V1.3 Performance Requirements

  Metric                      PASS Requirement   Verified Golden
  ------------------------- ------------------ -----------------
  Nominal passband ripple        ≤ 0.598967 dB       0.598967 dB
  Q80/Cp40 ripple                ≤ 0.684248 dB       0.684248 dB
  Q60/Cp60 ripple                ≤ 0.915071 dB       0.915071 dB
  Q60 3-dB bandwidth              ≥ 0.7500 GHz        0.7705 GHz
  Minimum rejection                  ≥ 80.0 dB      80.152803 dB

The Golden design is a feasibility control: it demonstrates that the
simultaneous constraint intersection exists.

------------------------------------------------------------------------

## 3. Frozen 18-Run FINAL Results

  -----------------------------------------------------------------------------------
  Model            Run    Nominal        Q80        Q60  BW (GHz)   Rejection FINAL
                                                                         (dB) 
  ---------- --------- ---------- ---------- ---------- --------- ----------- -------
  Cohere             1   1.061643   0.806529   0.955568    0.7710   80.816000 FAIL

  Cohere             2   1.563043   1.010164   1.213329    0.7570   79.997000 FAIL

  Cohere             3   0.824621   0.583270   0.750675    0.7780   80.431000 FAIL

  DeepSeek           1   0.886665   0.543207   0.806181    0.7730   80.439940 FAIL

  DeepSeek           2   0.759213   0.605925   0.820821    0.7755   80.484338 FAIL

  DeepSeek           3   0.579587   0.699226   1.026676    0.7650   79.997477 FAIL

  OpenAI             1   0.717548   0.573627   0.848565    0.7715   80.144921 FAIL

  OpenAI             2   0.717548   0.573627   0.848565    0.7715   80.144921 FAIL

  OpenAI             3   0.817309   0.633196   0.908182    0.7685   80.414886 FAIL

  Claude             1   0.815564   0.586113   0.794681    0.7780   80.720259 FAIL

  Claude             2   0.579395   0.739766   1.047853    0.7645   79.995956 FAIL

  Claude             3   0.663949   0.572274   0.887010    0.7695   80.019119 FAIL

  xAI                1   0.793289   0.604800   0.802588    0.7750   80.509298 FAIL

  xAI                2   0.590700   0.654928   0.964936    0.7680   79.995741 FAIL

  xAI                3   0.827662   0.632289   0.911345    0.7695   80.861741 FAIL

  Gemini             1   0.744257   0.815287   1.117379    0.7635   79.975851 FAIL

  Gemini             2   1.426029   1.370838   1.517756    0.7815   80.502897 FAIL

  Gemini             3   0.731469   0.654888   0.892040    0.7720   80.481214 FAIL
  -----------------------------------------------------------------------------------

**FINAL delivery capability: 0/18 PASS.**

This does not mean that useful engineering reasoning was absent. Several
runs reached strong nominal-favorable or robustness-favorable verified
states. The central problem was failure to reliably reach and retain the
**simultaneous feasible intersection**.

------------------------------------------------------------------------

## 4. Main Reasoning Finding

Across the six evaluated LLMs, the principal limitation was not the
absence of local reasoning.

The models frequently identified the currently failing metric, selected
a plausible engineering action, recognized severe regressions, used
rollback, and sometimes identified repeated optimization cycles.

The deeper limitation was:

> **The models did not consistently accumulate local verified evidence
> into a coherent global engineering strategy.**

In particular, the benchmark repeatedly exposed a gap between:

**Search Capability → State Recognition → State Retention → Final
Delivery**

These are different capabilities.

The models repeatedly reached different faces of the feasible region,
but did not reliably navigate along those faces into their intersection.

------------------------------------------------------------------------

## 5. Project-Derived Reasoning Deficiencies

The following deficiencies are derived from the actual 4Rx3 → 4Rx5
benchmark trajectories rather than from generic LLM reasoning theory.

### 5.1 Local Optimization Without Global Coordination

A common pattern was movement between nominal-favorable and
robustness-favorable states. Fixing the currently worst metric often
damaged another constraint.

### 5.2 Weak Constraint-Margin Exchange Reasoning

Models could recognize available margin but did not reliably predict how
much Q80/Q60/rejection margin would be consumed by a nominal-focused
action.

**Available margin ≠ safely spendable margin.**

### 5.3 Weak Action-to-Response Causal Learning

Each Python verification is effectively an engineering experiment. The
models did not consistently convert repeated experiments into an
explicit local model:

`Action → ΔNominal / ΔQ80 / ΔQ60 / ΔBW / ΔRejection`

### 5.4 Nominal--Robust Optimization Attractors

Several trajectories oscillated between:

`Robust-favorable → Nominal polish → Nominal-favorable → Robust polish → Robust-favorable`

Repeated return to similar states suggests a non-PASS attractor or limit
cycle.

### 5.5 Weak Constraint-Intersection Navigation

The correct objective is not merely "repair the currently failing
metric." It is to identify a direction that moves the design toward the
intersection of all five constraints.

### 5.6 Basin Recognition Is Not Basin Navigation

Recognizing that the current basin is exhausted is useful, but choosing
a productive new basin requires separate causal evidence.

### 5.7 Optimizer Composition Was Sometimes Assumed Rather Than Learned

A plausible sequence such as "nominal polish, then robust polish" does
not guarantee that the first improvement will survive the second action.

### 5.8 Rollback Did Not Always Become Persistent Engineering Knowledge

Rollback can restore a state, but the failed experiment should also
modify the model's future belief and action policy.

### 5.9 Weak State-Value Recognition and Retention

A single scalar "best" state is insufficient. Best-nominal, best-robust,
best-balanced, rejection-safe, and Pareto-nondominated states can have
different strategic value.

### 5.10 Insufficient Budget-Aware Endgame Reasoning

A risky action may be reasonable at Action 3 but irrational at Action 10
when no recovery action remains.

------------------------------------------------------------------------

## 6. Concrete Improvements Derived from This Project

### 6.1 Maintain a Five-Dimensional Constraint-Margin Vector

After every verification, explicitly maintain:

`M = [MNom, MQ80, MQ60, MBW, MRejection]`

The planner should reason about both violation and safety margin.

### 6.2 Build a Local Sensitivity Map

Store verified action deltas and progressively learn which parameter
families affect which engineering metrics.

### 6.3 Require Prediction Before Execution

Before each significant action, predict expected metric changes and
uncertainty ranges. Compare the prediction with the Python result.

The reasoning loop should become:

`Hypothesis → Prediction → Action → Verification → Prediction Error → Belief Update → Next Hypothesis`

### 6.4 Use Prediction Error as a Reasoning Diagnostic

A stronger engineering model should show decreasing action-consequence
prediction error as verified evidence accumulates.

### 6.5 Compare Counterfactual Actions

At critical states, compare 2--3 candidate actions before committing.
Estimate expected benefit, margin consumption, uncertainty, attractor
risk, recovery cost, and remaining budget.

### 6.6 Detect Limit Cycles Explicitly

If two nominal/robust cycles return to similar states, declare the
current action family exhausted and switch engineering degrees of
freedom.

### 6.7 Navigate the Constraint Intersection

Replace:

`Which metric should I repair next?`

with:

`Which parameter direction is most likely to move the current design along the feasible boundary toward the simultaneous constraint intersection?`

### 6.8 Use Evidence-Guided Basin Switching

Before a basin-changing action, require evidence that the current basin
is exhausted and evidence supporting the proposed new direction.

### 6.9 Learn Nonlinear Margin Exchange

Do not assume that 0.1 dB of apparent Q60 margin can safely be traded
for nominal improvement. Estimate the exchange from verified local
history and include uncertainty.

### 6.10 Preserve Multiple Strategic States

Maintain:

-   Best Nominal
-   Best Robust
-   Best Balanced
-   Best Rejection-Safe
-   Pareto-Nondominated States

### 6.11 Make Remaining Budget Part of the Engineering State

Reason over:

`Engineering State + Constraint Margins + Remaining Actions + Recovery Cost`

### 6.12 Separate Exploration, Exploitation, and Endgame

Early actions can explore. Middle actions should learn causal structure
and converge. Final actions should prioritize low-risk closure and
margin protection.

### 6.13 Turn Failure Into Causal Attribution

Classify failed actions as, for example:

-   wrong direction;
-   excessive step;
-   wrong parameter family;
-   topology mismatch;
-   optimizer conflict;
-   tool-semantics error.

The classification should affect future actions.

### 6.14 Improve Recovery Efficiency

Measure not only whether the model can recover, but how many actions
recovery consumes.

`Recovery Efficiency = engineering progress recovered / actions consumed`

### 6.15 Use Explicit Multi-Step Engineering Plans

Instead of choosing only the next action, form a short strategy such as:

`build robust margin → exchange selected margin for nominal improvement → preserve one recovery action`

The plan should be revised when verified evidence contradicts its
assumptions.

### 6.16 Make Belief Update Mandatory

A verified result should not merely change the numerical state. It
should change the model's engineering belief when the observation
contradicts its prediction.

**Evidence → Belief Update → Changed Decision**

------------------------------------------------------------------------

## 7. Project-Level Interpretation

The comparison between the earlier and current benchmarks suggests a
useful hierarchy of autonomous engineering capability.

### Level 1 --- Autonomous Topology Growth

Can the LLM construct a valid higher-order design from a lower-order
anchor?

The earlier 3Rx4 → blind 3Rx6 → blind 3Rx8 experiments showed successful
behavior at this level under broader acceptance conditions.

### Level 2 --- Verified Iterative Optimization

Can the LLM react to deterministic simulation results and improve the
design through sequential actions?

V1.3 demonstrates substantial partial capability here.

### Level 3 --- Tight Multi-Objective Constraint Closure

Can the LLM accumulate verified evidence, model nonlinear tradeoffs,
preserve strategically valuable states, and navigate into a narrow
feasible intersection defined by multiple simultaneous requirements?

The V1.3 0/18 FINAL result shows that this level remains substantially
more difficult for the evaluated models in this specific RF/FBAW
benchmark.

The human-engineered Golden design is important because it establishes
that Level 3 is achievable for the underlying engineering problem.

------------------------------------------------------------------------

## 8. Central Conclusion

> **A stronger engineering LLM should not merely react to verification
> results. It should build, update, and exploit an internal causal model
> of the local engineering design space.**

For this specific RF/FBAW project, that means learning how nominal
ripple, Q80/Cp40 robustness, Q60/Cp60 robustness, bandwidth, rejection,
topology, boundary embedding, and individual cell parameters
interact---and then using accumulated verified evidence to navigate
deliberately toward their known feasible intersection.

> **The next improvement in autonomous engineering reasoning should
> therefore come not primarily from allowing more actions, but from
> extracting more engineering knowledge from each verified action.**

------------------------------------------------------------------------

## 9. Evidence and Data Access

This public report presents the benchmark methodology, frozen numerical
results, representative engineering-reasoning findings, and principal
limitations observed across the six evaluated LLMs.

The underlying benchmark contains substantially more detailed material,
including action-by-action trajectories, planner decisions,
deterministic Python verification results, intermediate verified states,
rollback/recovery sequences, nominal-versus-robust transitions, and
representative failure cases.

To avoid unnecessarily publishing large volumes of model-specific raw
interaction data, complete reasoning and verification records are not
included publicly.

LLM developers, research teams, or companies interested in examining
detailed benchmark data and engineering-reasoning trajectories are
welcome to contact us privately. Access to relevant data, technical
discussion, and potential research collaboration can be considered **by
mutual agreement**.

The purpose is not simply model comparison. The broader objective is to
identify reasoning limitations in autonomous engineering systems and
explore how future LLMs and agent harnesses can improve multi-objective
reasoning, evidence-based decision making, state management, failure
recovery, and reliable execution under deterministic verification.

------------------------------------------------------------------------

## Reporting Scope

-   Results reported here are specific to this RF/FBAW benchmark, its
    frozen topology, action interface, verifier, constraints, and action
    budget.
-   A FINAL failure is not a claim that a model lacks general reasoning
    ability.
-   A successful earlier blind-synthesis result is not evidence that the
    same model will satisfy a much narrower multi-objective performance
    envelope.
-   The deterministic Python engineering core remains the numerical
    authority.
-   Model-specific raw trajectories should be checked against frozen run
    headers before public attribution of individual reasoning examples.
