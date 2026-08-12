# AKI (KDIGO-inspired) scoring contract v0.2

Prototype only — not clinically validated.

**Citation:** KDIGO Clinical Practice Guideline for Acute Kidney Injury (Kidney Int Suppl. 2012).

## Inputs

| Field | Source | Notes |
|---|---|---|
| `creatinine_mg_dl` | FHIR Observation LOINC 2160-0 | Current creatinine |
| `baseline_creatinine_mg_dl` | Prior Observation or explicit baseline | Missing → cannot stage relative rise |
| `urine_ml_kg_h` | FHIR Observation LOINC **9187-6** with unit `mL/kg/h` | Optional UO path (Flink `AkiAlertFunction`) |
| `urine_duration_hours` | Observation.component code `duration-hours` | Required with `urine_ml_kg_h` |
| `anuria` | Observation code `anuria` / `urine-anuria`, or UO component | Stage 3 if anuria ≥ 12h |

## Staging → score mapping

Final **stage = max(creatinine_stage, urine_stage)**.

### Creatinine

| Stage | Rule (simplified) | Score |
|---|---|---|
| 0 | No criteria met | 0 |
| 1 | Cr ≥ 1.5× baseline **or** ΔCr ≥ 0.3 mg/dL | 2 |
| 2 | Cr ≥ 2.0× baseline | 4 |
| 3 | Cr ≥ 3.0× baseline **or** Cr ≥ 4.0 mg/dL | 6 |

### Urine output

| Stage | Rule (simplified) |
|---|---|
| 1 | &lt; 0.5 mL/kg/h for ≥ 6h |
| 2 | &lt; 0.5 mL/kg/h for ≥ 12h |
| 3 | &lt; 0.3 mL/kg/h for ≥ 24h **or** anuria ≥ 12h |

Timing windows (48h ΔCr / 7d ratio) are documented in the rule bundle; this prototype treats baseline vs current as caller-provided.

## Missing-data policy

- No current creatinine **and** no evaluable UO → `insufficient_data` (do not impute).
- Current creatinine without baseline → `partial`; only absolute Cr ≥ 4.0 can reach stage 3; otherwise list `baseline_creatinine` in `missing_components`.
- Partial UO fields (rate without duration or vice versa) → list `urine_output` in `missing_components`; creatinine path still scores if present.

## Governance

Uses the **same** shared governance operators as sepsis (trajectory, baseline-relative, suppression, dedup, tiering) configured via this rule bundle — no Kafka/ingest/governance-core changes.

Rule bundle: `aki-kdigo` **v0.2.0**.
