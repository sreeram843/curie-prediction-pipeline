# AKI (KDIGO-inspired) scoring contract v0.1

Prototype only — not clinically validated.

## Inputs

| Field | Source | Notes |
|---|---|---|
| `creatinine_mg_dl` | FHIR Observation LOINC 2160-0 | Current creatinine |
| `baseline_creatinine_mg_dl` | Prior Observation or explicit baseline | Missing → cannot stage relative rise |

## Staging → score mapping

| Stage | Rule (simplified) | Score |
|---|---|---|
| 0 | No criteria met | 0 |
| 1 | Cr ≥ 1.5× baseline **or** ΔCr ≥ 0.3 mg/dL | 2 |
| 2 | Cr ≥ 2.0× baseline | 4 |
| 3 | Cr ≥ 3.0× baseline **or** Cr ≥ 4.0 mg/dL | 6 |

## Missing-data policy

- No current creatinine → `insufficient_data` (do not impute).
- Current creatinine without baseline → `partial` stage-1 candidate only via absolute Cr ≥ 4.0; otherwise list `baseline_creatinine` in `missing_components`.

## Governance

Uses the **same** shared governance operators as sepsis (trajectory, baseline-relative, suppression, dedup, tiering) configured via this rule bundle — no Kafka/ingest/governance-core changes.
