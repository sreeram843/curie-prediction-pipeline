# MIMIC/eICU correctness matrix (plan B2)

Every row names the layer, the case, the expected behavior, and the tests that pin it.
"Parity fixture needed" = the case changes the shared scorer contract (Python ↔ Java);
B1 did not change the scorer, so no new golden fixtures were required (verified with
`python -m eval.parity.gate`).

Layers: **CONV** = `ingestion/adapters/mimic/vasopressors.py` · **EXT** = `extract.py` ·
**DEMO** = `to_demo_schema.py` · **HARNESS** = `eval/mimic_harness/replay.py` ·
**EICU** = `ingestion/adapters/eicu/convert.py`.

| # | Case | Layer | Expected | Test | Parity fixture |
|---|---|---|---|---|---|
| 1 | `mcg/kg/min` rate | CONV | dose = rate, known | `test_mcg_kg_min_passthrough` | no |
| 2 | `mcg/min` with prior valid weight | CONV/EXT | dose = rate ÷ kg | `test_mcg_min_divides_by_weight`, `test_pressor_at_known_dose_with_contemporaneous_weight` | no |
| 3 | `mg/kg/min` | CONV | dose = rate × 1000 | `test_mg_kg_min_multiplies_by_1000` | no |
| 4 | `mg/min` | CONV | dose = rate × 1000 ÷ kg | `test_mg_min_multiplies_then_divides` | no |
| 5 | `mL/hour` / volume rate | CONV | unknown (`volume_rate_without_concentration`) | `test_volume_rate_without_concentration_is_unknown` | no |
| 6 | `units/hour`, `units/min`, `ng/kg/min`, misc | CONV | unknown (`unsupported_unit:*`) | `test_unsupported_units_are_unknown` | no |
| 7 | missing unit | CONV | unknown (`missing_unit`) | `test_missing_unit_is_unknown` | no |
| 8 | missing rate | CONV | unknown (`missing_rate`) | `test_missing_rate_is_unknown` | no |
| 9 | NaN/±inf rate | CONV | unknown (`non_finite_rate`) | `test_non_finite_and_non_positive_rate_is_unknown` | no |
| 10 | zero/negative rate | CONV | unknown (`non_positive_rate`) | same | no |
| 11 | weight missing / <1kg / >500kg / non-finite | CONV | unknown (`invalid_or_missing_weight`) | `test_missing_weight_is_unknown`, `test_invalid_weight_is_unknown` | no |
| 12 | only future weight at pressor start | CONV/EXT | unknown (`weight_unavailable_or_only_future`); never used | `test_future_only_weight_is_unknown`, `test_pressor_at_future_only_weight_is_unknown_dose`, `test_weight_only_future_is_reported_not_used` | no |
| 13 | lbs weight (226531) | CONV | converted to kg (×0.45359237) | `test_lbs_weight_converted_to_kg` | no |
| 14 | invalid charted weight | CONV | status `invalid`, no dose | `test_invalid_charted_weight_is_reported` | no |
| 15 | overlapping pressors, different agents | EXT | highest SOFA band wins; all evidence IDs preserved | `test_pressor_at_overlapping_agents_prefers_highest_band` | no |
| 16 | overlapping pressors, same band, one unknown dose | EXT | known dose preferred (deterministic tie-break) | `test_pressor_at_overlapping_agents_prefers_highest_band` (ordering) | no |
| 17 | pressor row outside start/end window | EXT | inactive | `test_pressor_at_inactive_rows_ignored` | no |
| 18 | bolus order (`05-Med Bolus`) | EXT | present, dose unknown (`bolus_order_dose_not_applicable`) | `test_pressor_at_bolus_present_but_dose_not_applicable` | no |
| 19 | pressor present, dose unknown → SOFA fallback | EXT/HARNESS | 3 points (`unknown_pressor_points`) | `test_unknown_vasopressor_dose_is_explicit_and_uses_fallback_points` | covered by existing goldens |
| 20 | non-normalized unit event in harness (e.g. `mcg/min`) | HARNESS | valuenum **never** read as mcg/kg/min → dose unknown | `test_non_normalized_pressor_unit_never_reads_dose` | no |
| 21 | normalized unit event (`mcg/kg/min`) | HARNESS | dose read | `test_normalized_pressor_unit_reads_dose` | no |
| 22 | eICU `mg/kg/min` row | EICU | ×1000, emitted unit `mcg/kg/min` | `test_mg_kg_min_pressor_converted_x1000` | no |
| 23 | eICU `mg/min` without row weight | EICU | unknown | `test_mg_min_pressor_without_valid_weight_is_unknown` | no |
| 24 | eICU `ml/hr` | EICU | unknown + reason preserved in extras | `test_volume_rate_pressor_unknown_without_concentration` | no |
| 25 | eICU `mcg/min` with valid weight | EICU | converted, unit normalized | `test_mcg_min_pressor_with_valid_weight_converted_and_normalized_unit` | no |
| 26 | urine < 24h of stay | EXT | `urine_output_ml_day=None` (never a partial-day total) | `test_urine_output_ineligible_before_24h_window` | no |
| 27 | urine < 24h of stay | HARNESS | `(None, [])` until 24h | `test_urine_is_missing_until_full_24_hour_stay_window` | no |
| 28 | PaO2/FiO2 vs SpO2/FiO2 preference | EXT/HARNESS | PaO2 preferred; SpO2 pairs with latest FiO2; no ambient-air 0.21 assumption | `ingestion/adapters/test_respiration.py`, `test_late_fio2_pairs_with_prior_spo2`, `test_pao2_with_fio2_scores_respiration` | covered by resp goldens |
| 29 | discharge diagnosis as feature | HARNESS | never enters scoring evidence | `test_discharge_diagnosis_never_in_scoring_evidence` | no |
| 30 | evidence IDs for pressor rows | EXT/DEMO/EICU | source row identity preserved (`MIMIC/inputevents/{itemid}/{starttime}`; eICU `infusiondrugid` in extras) | `test_provenance_fields_preserved`, `test_pressor_details_preserve_evidence_and_reasons` (via details), eICU extras asserts | no |
| 31 | itemid map | CONV | phenylephrine/vasopressin/angiotensin-II = `other`; milrinone excluded | `test_itemid_map_includes_other_pressors_not_milrinone` | no |
| 32 | replay determinism | HARNESS | repeated runs → identical content hash | `test_repeated_runs_identical_content_hash` | no |
| 33 | Python ↔ Java scorer parity | — | unchanged contract; all goldens green | `python -m eval.parity.gate` (fixtures=34, mismatches=0) | existing |
