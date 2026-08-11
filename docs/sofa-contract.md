# SOFA-style sepsis scoring contract (v1)

Prototype only — not clinically validated. Missing components are never silently imputed.

## Components (0–4 each; total 0–24)

| Component | Typical inputs (FHIR Observation codes — LOINC preferred) | Notes |
|---|---|---|
| respiration | PaO2/FiO2 or SpO2/FiO2 proxy; ventilation flag | Prefer arterial P/F; document proxy use |
| coagulation | Platelets (10^9/L) | |
| liver | Bilirubin (mg/dL) | |
| cardiovascular | MAP (mmHg) and/or vasopressor exposure | MedicationAdministration may contribute |
| cns | GCS total | |
| renal | Creatinine (mg/dL) and/or urine output | |

## Missing-data policy

- If a component has no valid observation inside its validity window → component is `null` and listed in `missing_components`.
- Score is emitted as `partial` when any required component is missing.
- `insufficient_data` is a first-class outcome when too few components are present to score meaningfully (configurable; default: fewer than 3 of 6).

## Alert payload (deterministic)

Must include: `score`, `severity`/`tier`, `component_breakdown`, `missing_components`, `evidence_ids`, `rule_bundle_id`, `rule_version`, `patient_id`, `encounter_id`, `event_time`.
