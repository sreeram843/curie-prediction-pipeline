# ADR-0001: Shared alert governance is the product, not the score

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

A deterioration-detection system can be built around any number of risk scores (SOFA, KDIGO AKI, NEWS,
qSOFA). Each individual score is commodity clinical arithmetic; the hard, defensible part is deciding
*whether a computed risk is worth interrupting a clinician for*.

## Decision

Treat the shared **alert governance layer** — trajectory/persistence checks, patient-baseline-relative
scoring, context suppression, dedup + refractory windows, and acuity tiering — as the core, reusable
component. Every indicator, present and future, inherits it. The value proposition is governed alerting
(reducing interruptive volume while preserving detection), not any single score.

## Consequences

- Governance is a separate, shared module with a Python/Java mirror (`eval/replay_harness/governance.py` ↔
  `streaming/flink-jobs/governance/`), not code embedded per indicator.
- Evaluation is framed around alert-reduction ratio and number-needed-to-alert vs. a naive threshold
  baseline, not raw score accuracy.
- Adding an indicator must reuse governance rather than introduce its own routing/dedup logic.

## Related

- [`../governance/`](../governance/)
- [`../research/challenge-2019-eval.md`](../research/challenge-2019-eval.md)
- [`../research/clinical-validation.md`](../research/clinical-validation.md)
