# System Architecture

## Operating concept

The trained/model-driven beamforming system remains the nominal operating engine. System-level mechanisms observe QoS state and escalate repair only when needed.

```text
NOMINAL BEAMFORMING
        |
        v
STATE / QoS MONITORING
        |
        v
PRE-FAILURE RISK ASSESSMENT
        |
        +-- safe ----------------------> continue
        |
        v
FAST / LOW-COST REPAIR
        |
        +-- verified success ----------> continue
        |
        v
DIGITAL / POWER REPAIR
        |
        +-- verified success ----------> continue
        |
        v
RF / BEAM RESELECTION
        |
        +-- verified success ----------> continue
        |
        v
HARD / EXCEPTION CASE
```

## Deterministic authority

Every accepted repair must be checked by the numerical beamforming/QoS evaluation path. AI components may predict risk or propose/prioritize bounded actions, but do not replace deterministic verification.

## V0.5 research boundary

Current V0.5 work studies historical state before failure onset and the recoverability of captured failures. A final early-warning threshold and final repair hierarchy are not yet frozen.

## Future exception supervisor

A future AI/LLM supervisor may be evaluated for MODERATE or ambiguous cases after deterministic low-cost repair has been exhausted. It is intentionally outside the fast numerical loop and any proposed action remains subject to ACCEPT/REJECT verification.
