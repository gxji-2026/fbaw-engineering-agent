# Research Roadmap

## Research objective

Preserve the reference statistical outage formulation while investigating whether frame-level operational failures can be anticipated and recovered with bounded, deterministic interventions.

```text
Scientific reference
      -> independent reproduction
      -> GPU implementation
      -> real-time system
      -> failure-state capture
      -> pre-failure early warning
      -> recoverability-aware hierarchical repair
      -> frozen-rule 20K+ validation
      -> future AI/LLM exception supervision
```

## Frozen foundations

- CPU reproduction/profiling baseline.
- Direct GPU-port reproducibility baseline.
- Level-2 GPU-native implementation work without intentional changes to algorithm mathematics.
- System V0.4 failure-state capture workflow.
- P10/P14/P20/P24 internal-audit phase is closed unless explicitly reopened.

## Current phase — System V0.5

The current study focuses on pre-failure observability and hierarchical repair. Existing failure-capture data is used first; the early-warning study is instrumentation/analysis rather than a new training stage.

The working system distinction is:

```text
statistical outage formulation
          !=
final operational failure rate
```

The research goal is to reduce unrecovered operational failure without claiming that the underlying statistical outage setting has been removed.

## Validation discipline

Rules discovered during exploratory runs must be frozen before final large-scale evaluation. Final validation should report warning quality, repair success, unrecovered failure, intervention cost/latency, escalation frequency, and performance across operating conditions.
