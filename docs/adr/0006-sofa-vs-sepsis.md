# ADR-0006: Separate SOFA deterioration from sepsis identification

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

An absolute SOFA rise is often conflated with a sepsis diagnosis. Sepsis-3 requires suspected infection
**and** an acute SOFA Δ≥2; absolute SOFA scoring alone is not a diagnosis and must not be labeled as one.

## Decision

Split into two signals: `sofa-deterioration` (absolute/threshold SOFA scoring with governance, on the
streaming alert path) and `sepsis-3` (a separate phenotype: infection suspicion ± 24h of evaluation time
**and** `current_sofa − baseline_sofa ≥ 2`, implemented in `eval/sepsis3/`). The Challenge `sepsis` binary
label is unchanged and unrelated.

## Consequences

- No screen or API labels SOFA threshold alone as confirmed sepsis.
- The Sepsis-3 phenotype has its own versioned positive/negative/boundary/missing-data fixtures and
  exclusions (`comfort_care`, `already_on_sepsis_protocol`).
- Pre-existing high baseline without an acute rise is **not** met; missing inputs yield
  `insufficient_data`.

## Related

- [`../contracts/sofa-contract.md`](../contracts/sofa-contract.md)
