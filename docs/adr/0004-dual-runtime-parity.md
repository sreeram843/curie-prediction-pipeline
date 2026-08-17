# ADR-0004: Dual-runtime parity (Python reference + Java/Flink)

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

Evaluation is written in Python (`eval/`), but the streaming runtime is Java/Flink
(`streaming/flink-jobs/`). If the two implementations diverge, an eval can report a result the production
runtime does not reproduce — undermining every downstream claim.

## Decision

Every indicator has a **Python reference scorer** and a **Java/Flink implementation** that must produce
identical results. Shared governance has the same mirror. `make parity` (or `python -m eval.parity.gate`)
verifies the Python side against golden fixtures; the Java side is Maven surefire tests. CI fails on any
mismatch, and `make rules` refuses to publish unless the gate passes.

## Consequences

- Adding or changing a scorer requires fixtures in `eval/fixtures/golden/` **and** the matching Java test.
- Golden fixtures change only alongside a scorer change.
- A bundle cannot be published while parity is red.

## Related

- [`../governance/runtime-gov-parity.md`](../governance/runtime-gov-parity.md)
- [`../contracts/`](../contracts/)
