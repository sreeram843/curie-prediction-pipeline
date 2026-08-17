# ADR-0007: Indicators are plugins, not new infrastructure

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

A second indicator (AKI) could have been added as a bespoke Flink job, a new dashboard renderer, and a new
governance path. That would make each condition an O(n) platform expansion instead of a bounded task.

## Decision

Adding an indicator is a **plugin task**: declare an `IndicatorPlugin` (`eval/indicators/plugin.py`), ship a
rule bundle whose `score.type` matches, and provide Python + Java runtimes. All indicators project onto one
shared signal contract (`docs/contracts/signal-contract.md`) with condition-specific fields in
`extensions`. A JSON bundle alone cannot activate without an installed scorer.

## Consequences

- The dashboard renders unknown signal types using only contract fields — no per-condition branches.
- Unsupported `score.type` fails at activation (`validate_activation()`), not at runtime.
- `runtime_impl` maps each plugin to its Python/Java/Flink implementation; parity fixtures are required.

## Related

- [`../contracts/indicator-plugin-sdk.md`](../contracts/indicator-plugin-sdk.md)
- [`../contracts/signal-contract.md`](../contracts/signal-contract.md)
- [`../contracts/indicator-four-selection.md`](../contracts/indicator-four-selection.md)
