# AKI (KDIGO-inspired) scoring contract v0.4

Prototype only — not clinically validated.

**Citation:** KDIGO Clinical Practice Guideline for Acute Kidney Injury (Kidney Int Suppl. 2012).

## Signal

`indicator`: `aki` — acute kidney injury staging. Rule bundle `aki-kdigo` **v0.4.0**.

Stateful timelines: `eval/aki/timeline.py` / Java `AkiTimeline` (`TIMELINE_VERSION` **1.0.0**).

## Baseline selection (CURIE-009)

At evaluation time `t`:

| Quantity | Definition |
|---|---|
| Current Cr | Latest usable creatinine with `event_time <= t` (corrections replace same `evidence_id`) |
| 48h reference | `min(Cr)` in `[t − 48h, t]` — absolute rise if `current − ref ≥ 0.3` |
| 7d baseline | `min(Cr)` in `[t − 7d, t]` excluding the current sample when older values exist — ratio rules |

Caller-provided baseline remains supported by the legacy `compute_aki_score` / `AkiScorer` path for fixtures; runtime Flink uses the timeline.

## Inputs

| Field | Source | Notes |
|---|---|---|
| `creatinine_mg_dl` | FHIR Observation LOINC 2160-0 | Appended to 48h/7d histories |
| `urine_volume_ml` + `duration_hours` | Urine Observation | Preferred UO path; requires `weight_kg` |
| `weight_kg` | Body weight Observation | Required for volume-normalized UO |
| `urine_ml_kg_h` + `duration_hours` | LOINC 9187-6 | Legacy pre-normalized segments |
| `anuria` | `anuria` / `urine-anuria` | Stage 3 if duration ≥ 12h |
| flags `esrd`, `rrt_initiated` | Context | ESRD alone → excluded; RRT → stage 3 |

## Staging → score mapping

Final **stage = max(creatinine_stage, urine_stage, rrt)**.

### Creatinine

| Stage | Rule | Score |
|---|---|---|
| 0 | No criteria met | 0 |
| 1 | Cr ≥ 1.5× 7d baseline **or** ΔCr ≥ 0.3 vs 48h reference | 2 |
| 2 | Cr ≥ 2.0× 7d baseline | 4 |
| 3 | Cr ≥ 3.0× 7d baseline **or** Cr ≥ 4.0 mg/dL **or** RRT | 6 |

### Urine output

Windows of 6h / 12h / 24h require **coverage ≥ window length**. Unobserved gaps are not treated as zero urine.

| Stage | Rule |
|---|---|
| 1 | Mean &lt; 0.5 mL/kg/h with ≥ 6h coverage |
| 2 | Mean &lt; 0.5 mL/kg/h with ≥ 12h coverage |
| 3 | Mean &lt; 0.3 mL/kg/h with ≥ 24h coverage **or** anuria ≥ 12h |

## Missing-data policy

- No current creatinine **and** no evaluable UO → `insufficient_data` (do not impute).
- Volume UO without weight → list `weight_kg`; creatinine path still scores; **no** reassuring UO stage.
- Partial UO fields → list `urine_output`.
- `esrd` without `rrt_initiated` → `excluded` (never stage 0 from ESRD alone).

## Outputs

Score payload plus timeline fields: `criteria_met`, `baseline_7d_mg_dl`, `reference_48h_mg_dl`, `onset_time`, evidence IDs per criterion.

## Governance

Same shared governance operators as SOFA (`sofa-deterioration`), configured via this rule bundle.

Fixtures: `eval/fixtures/golden/aki_timeline_cases.v1.json`.
