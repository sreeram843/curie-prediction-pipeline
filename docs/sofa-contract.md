# SOFA-style sepsis scoring contract (v0.2)

Prototype only — not clinically validated. Missing components are never silently imputed.

**Citations:** Vincent et al., Crit Care Med 1998 (SOFA); Singer et al., JAMA 2016 (Sepsis-3 context — infection gate not implemented here).

## Components (0–4 each; total 0–24)

| Component | Typical inputs (FHIR Observation codes — LOINC preferred) | Notes |
|---|---|---|
| respiration | PaO2/FiO2 or SpO2/FiO2 proxy; ventilation flag | Points 3–4 require mechanical ventilation |
| coagulation | Platelets (10^9/L) | |
| liver | Bilirubin (mg/dL) | |
| cardiovascular | MAP (mmHg); vasopressor agent + dose (µg/kg/min) | Vincent ladder; unknown dose → 3 |
| cns | GCS total | |
| renal | Creatinine (mg/dL) and/or urine output (mL/day) | `max(Cr, UO)` |

## Cardiovascular ladder (v0.2)

| Points | Rule |
|---|---|
| 4 | dopamine > 15 **or** epi/norepi > 0.1 µg/kg/min |
| 3 | dopamine > 5 **or** epi/norepi ≤ 0.1 **or** pressors present with unknown dose |
| 2 | dopamine ≤ 5 **or** any dobutamine |
| 1 | MAP < 70 (no pressors) |
| 0 | MAP ≥ 70 (no pressors) |

## Missing-data policy

- If a component has no valid observation → component is `null` and listed in `missing_components`.
- Score is emitted as `partial` when any required component is missing.
- `insufficient_data` when fewer than 3 of 6 components are present (configurable via rule bundle).

## Alert payload (deterministic)

Must include: `score`, `severity`/`tier`, `component_breakdown`, `missing_components`, `evidence_ids`, `rule_bundle_id`, `rule_version`, `patient_id`, `encounter_id`, `event_time`.

Rule bundle: `sepsis-sofa` **v0.2.0** (thresholds also documented in JSON `score.component_thresholds`).
