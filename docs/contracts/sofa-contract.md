# SOFA deterioration + Sepsis-3 phenotype (v0.3)

Prototype only — not clinically validated. Missing components are never silently imputed.

**Citations:** Vincent et al., Crit Care Med 1998 (SOFA); Singer et al., JAMA 2016 (Sepsis-3).

## Signal naming (CURIE-008)

| Signal | `indicator` | Meaning |
|---|---|---|
| SOFA organ dysfunction | `sofa-deterioration` | Absolute / threshold SOFA scoring with governance. **Not** a sepsis diagnosis. |
| Sepsis-3 phenotype | `sepsis-3` | Suspected infection **and** acute SOFA Δ≥2 (see `eval/sepsis3/`). Separate from the streaming SOFA alert path. |

Product rule bundle `sepsis-sofa` **v0.3.0** emits `sofa-deterioration`. Challenge stay field `sepsis` (binary label) is unchanged and unrelated to this indicator rename.

## Components (0–4 each; total 0–24)

| Component | Typical inputs (FHIR Observation codes — LOINC preferred) | Notes |
|---|---|---|
| respiration | PaO2/FiO2 or SpO2/FiO2 proxy; ventilation flag | Points 3–4 require mechanical ventilation |
| coagulation | Platelets (10^9/L) | |
| liver | Bilirubin (mg/dL) | |
| cardiovascular | MAP (mmHg); vasopressor agent + dose (µg/kg/min) | Vincent ladder; unknown dose → 3 |
| cns | GCS total | |
| renal | Creatinine (mg/dL) and/or urine output (mL/day) | `max(Cr, UO)` |

## Cardiovascular ladder (v0.2+)

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
- `insufficient_data` when fewer than 3 of 6 components are present (configurable via rule bundle; Challenge study freeze uses 2).

## Alert payload (deterministic)

Must include: `score`, `severity`/`tier`, `component_breakdown`, `missing_components`, `evidence_ids`, `rule_bundle_id`, `rule_version`, `patient_id`, `encounter_id`, `event_time`, `indicator` (`sofa-deterioration`).

Rule bundle: `sepsis-sofa` **v0.3.0** (thresholds in JSON `score.component_thresholds`).

## Sepsis-3 phenotype (v1.0.0)

Implemented in `eval/sepsis3/phenotype.py` with fixtures `eval/fixtures/golden/sepsis3_cases.v1.json`.

- Infection suspicion: culture collection/order **or** systemic antimicrobial admin/order within ±24h of evaluation time.
- Acute organ dysfunction: `current_sofa - baseline_sofa ≥ 2`.
- Pre-existing high baseline without acute rise → **not met**.
- Missing SOFA or infection inputs → `insufficient_data` (never silently met).
- Exclusions: `comfort_care`, `already_on_sepsis_protocol`.

Every evidence ID from the chosen infection event is preserved on the result.
