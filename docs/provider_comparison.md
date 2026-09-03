# Provider and Runtime Comparison

## Purpose

The repository contains three implementations of the same FBAW
engineering-agent concept. They should not be interpreted as five
unrelated versioned programs.

The public distinction is by **runtime/provider** and, for the
direct-API implementations, by **execution mode**.

## Implementation Map

  -----------------------------------------------------------------------------------
  Public implementation   Internal development lineage        Public role
  ----------------------- ----------------------------------- -----------------------
  DSH-native FBAW         `fbaw_dsh_native_bridge_v4_3c.py`   Primary/reference
  Engineering Agent                                           implementation

  DeepSeek FBAW           V4.3 lineage                        Direct-API serial
  Engineering Agent ---                                       baseline
  Serial                                                      

  DeepSeek FBAW           V4.3-P3 lineage                     Direct-API parallel
  Engineering Agent ---                                       reference
  Parallel                                                    

  Cohere FBAW Engineering V4.1 realistic-failure lineage      Cross-provider serial
  Agent --- Serial                                            baseline

  Cohere FBAW Engineering V4.1-P3 lineage                     Cross-provider parallel
  Agent --- Parallel                                          reference
  -----------------------------------------------------------------------------------

## What Is Common

The implementations share the same high-level engineering philosophy:

-   physics-constrained FBAW/DFR optimization;
-   Python-based RF simulation and verification;
-   agent/tool actions around the numerical engineering core;
-   candidate evaluation followed by deterministic engineering
    acceptance or rejection;
-   final numerical results determined by Python verification rather
    than by an LLM's unsupported numerical assertion.

The FBAW circuit model uses the ADS-confirmed L6 placement and the
external-inductor Q/Cp modeling used by the current engineering core.

## What Changes Between Implementations

### DSH-native

The DSH-native implementation is the primary/reference implementation.
It expresses the FBAW engineering workflow through the DSH runtime and
its agent/tool interaction model.

Public source name:

``` text
agent/fbaw_dsh_native_agent.py
```

The historical filename `fbaw_dsh_native_bridge_v4_3c.py` can remain
visible in release history or changelog records.

### DeepSeek direct API

The DeepSeek implementation exercises the engineering agent through
direct DeepSeek model/API interaction rather than the DSH-native
runtime.

Public source names:

``` text
providers/deepseek/deepseek_fbaw_agent_serial.py
providers/deepseek/deepseek_fbaw_agent_parallel.py
```

The parallel variant accelerates independent local RF candidate
verification. It does not make the model/API decision sequence itself
parallel.

### Cohere direct API

The Cohere implementation provides a cross-provider test of the same
engineering-agent pattern.

Public source names:

``` text
providers/cohere/cohere_fbaw_agent_serial.py
providers/cohere/cohere_fbaw_agent_parallel.py
```

The serial implementation is the baseline. The parallel implementation
preserves the Cohere planner/advisory sequence while parallelizing
independent Python RF candidate evaluations.

## Serial vs. Parallel

The distinction is computational, not architectural.

**Serial**

``` text
candidate 1 -> verify
candidate 2 -> verify
candidate 3 -> verify
...
candidate N -> verify
-> rank -> accept/rollback
```

**Parallel**

``` text
candidate 1 --+
candidate 2 --+
candidate 3 --+--> local RF verification -> ordered results -> rank -> accept/rollback
...           |
candidate N --+
```

The parallel implementation is designed so that candidate results are
returned in input order and the parent process performs the engineering
ranking/acceptance logic.

## Current Cross-Implementation Regression Target

The validated checkpoint is:

  Scenario     Ripple (dB)   Far rejection (dB)          TZ (GHz)
  ---------- ------------- -------------------- -----------------
  Nominal         0.539940      51.177 / 55.633   6.2221 / 7.3995
  Q80/Cp40        0.618137      50.583 / 56.093   6.2221 / 7.3995
  Q60/Cp60        0.745393      50.240 / 56.311   6.2221 / 7.3995

Target constraints:

``` text
Nominal ripple <= 0.55 dB
Q80/Cp40 ripple <= 0.63 dB
Q60/Cp60 ripple <= 0.75 dB
Far-stopband rejection >= 45 dB
```

## Cohere Parallel Benchmark

A six-worker cold run produced:

``` text
elapsed_s   = 248.29
elapsed_min = 4.138
workers     = 6
```

The RF checkpoint remained unchanged. The serial Cohere V4.1 development
run had required more than 10 minutes on the same development system.

This benchmark is useful because it demonstrates that the P3-style
parallelization is an execution optimization rather than a change to the
engineering target or final verified result.

## Versioning Policy

To avoid confusing users, use three separate concepts:

``` text
Project release       v1.0.0, v1.1.0, ...
Runtime/provider      DSH-native, DeepSeek, Cohere
Execution mode        native, serial, parallel
```

Internal identifiers such as `V4.3c`, `V4.3-P3`, `V4.1`, and `V4.1-P3`
should remain in development history, source comments, or changelog
entries when traceability is useful.

They should not be presented as five peer-level products on the
repository front page.

## Recommended Presentation Order

1.  **DSH-native FBAW Engineering Agent** --- primary/reference
    implementation.
2.  **DeepSeek FBAW Engineering Agent --- Parallel** --- direct-API
    reference.
3.  **Cohere FBAW Engineering Agent --- Parallel** --- cross-provider
    reference.
4.  DeepSeek Serial --- baseline/reference.
5.  Cohere Serial --- baseline/reference.

This presentation makes the architectural message explicit: one
engineering-agent framework, multiple runtime/provider realizations.
