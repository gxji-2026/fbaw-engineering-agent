# Technical Background

The DSH FBAW Engineering Agent is the third stage of a continuing FBAW engineering workflow. It does not replace the underlying RF synthesis or deterministic numerical optimization; it adds an autonomous LLM-driven tool-use layer above them.

## Stage 1 — RF-physics foundation

**X. Ji and R. Zhu, "SFR-Based Transmission Zero Synthesis and DFR Realization of Wideband FBAW Filters for 6G FR3 (6.425–7.125 GHz)," 2026.**

This work establishes the SFR-TZS-DFRR methodology. A single-frequency-resonator network is used as a transmission-zero synthesis engine, embedded-impedance analysis identifies the lower and upper transmission-zero targets, and those targets are mapped to dual-frequency acoustic resonators for DFR realization.

For the 6.425–7.125 GHz design, the synthesis produces spectral targets near 6.22 GHz and 7.40 GHz. Higher-order DFR realizations then extend the method through modular cascading and practical robustness evaluation.

## Stage 2 — AI-assisted deterministic closed loop

**X. Ji and R. Zhu, "AI-Assisted Physics-Constrained Closed-Loop Optimization of Robust DFR-Based Wideband FBAW Filters for 6G FR3," 2026.**

This work adds an LLM-assisted Python design layer above the established DFR physics. The LLM helps formulate and refine the optimization program and engineering strategy, while numerical S-parameter calculations remain deterministic in Python and are independently checked against ADS.

The workflow performs nominal ripple optimization, cell-by-cell tuning, terminal matching refinement, and finite-Q/parasitic robustness optimization under multiple operating conditions. The distinction between AI assistance and numerical authority is central: the LLM does not generate the final RF response numerically.

## Stage 3 — DSH autonomous engineering agent

This repository advances the workflow from AI-assisted program development to an autonomous tool-using engineering agent:

```text
Engineering goal
      |
      v
DeepSeek V4-Flash (LLM planner)
      |
      v
DeepSeek Harness (DSH)
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
      +--> ACCEPT / REJECT / rollback
      +--> verified design state
      |
      v
result returned to DSH / LLM
      |
      v
Python-authorized STOP
```

The key architectural change is therefore not a replacement of RF physics by an LLM. Instead, DSH hosts the multi-step agent loop, DeepSeek V4-Flash performs engineering planning and tool selection, and the Python RF core retains numerical authority.

## Research progression

```text
SFR-TZS-DFRR physical synthesis
        -> AI-assisted Python closed-loop optimization
        -> DSH-native autonomous engineering-agent execution
```

The two 2026 studies are cited as technical background rather than as publications describing the DSH implementation itself. The DSH agent is a subsequent engineering implementation built on that foundation.
