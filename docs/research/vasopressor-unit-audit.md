# Vasopressor unit audit report (CURIE-051 / plan B1)

**Generated:** 2026-09-05 · **Branch:** `codex/curie-b-correctness`
**Sources:** credentialed MIMIC-IV 3.1 (`icu/inputevents.csv.gz`, `icu/chartevents.csv.gz`)
and eICU-CRD v2.0 (`infusionDrug.csv.gz`). Aggregate counts only; source files untouched.
**Scripts:** `scripts/audit_mimic_pressor_units.py`, `scripts/audit_eicu_pressor_units.py`.

## Why this audit

`ingestion/adapters/mimic/extract.py` previously read every numeric `rate` as if it were
`mcg/kg/min` and only recognized five itemids. The audit quantifies what that silently got wrong.

## MIMIC-IV 3.1 results (851,337 pressor rows, 28,884 stays)

### rateuom distribution (mapped pressor itemids)

| unit | rows | prior behavior | now |
|---|---|---|---|
| `mcg/kg/min` | 813,640 (95.6%) | read as-is | unchanged (known dose) |
| `units/hour` | 37,160 (4.4%) | **silently read as mcg/kg/min** | explicit unknown; vasopressin scores via unknown-dose fallback |
| `ng/kg/min` | 296 | **silently read as mcg/kg/min** | explicit unknown (×1000 conversion deferred; see unresolved) |
| `<missing>` | 234 | dose None (agent known) | unchanged (explicit unknown) |
| `units/min` | 3 | silently misread | explicit unknown |
| `mcg/min` | 2 | silently misread (no weight division) | converted with contemporaneous weight |
| `mg/kg/min` | 2 | silently misread (no ×1000) | converted ×1000 |

### Itemid cross-tab

- **Vasopressin (222315):** all 37,163 rows are `units/hour`/`units/min` — previously misread
  as mcg/kg/min doses; now "pressor present, dose unknown" (fallback 3 points).
- **Phenylephrine (221749):** 209,374 rows `mcg/kg/min` + 2 `mcg/min` — **previously unmapped
  (treated as "no pressor")**; now mapped as `other`.
- **Angiotensin II (229709/229764):** 399 rows `ng/kg/min` — previously unmapped; now `other`
  with explicit unknown dose.
- **Epinephrine old itemid (229617):** 234 rows with missing rate+unit → explicit unknown.
- **Milrinone (221986, 10,668 rows):** intentionally not mapped (inotrope, not a SOFA pressor).

### Weight availability (availability-time rule: latest charted weight ≤ pressor starttime)

- 839,058 / 851,337 rows (98.6%) have a prior weight; age at starttime: ≤1h 13.7%,
  1–6h 24.8%, 6–24h 39.0%, >24h 22.4%.
- 12,279 rows (1.4%) have no prior weight; 9,757 of those have only a *future* weight
  → explicit unknown ("weight_unavailable_or_only_future"). No population default substituted.

### Order category / status (unresolved cases)

- 234 rows are `05-Med Bolus` (bolus orders) — counted as pressor-present with dose unknown
  (never a fabricated continuous dose).
- Status distribution (not yet used by the activity window): ChangeDose/Rate 632,833,
  FinishedRunning 108,645, Paused 58,543, Stopped 51,257, Bolus 59. The start/end window is
  the activity rule; status-based filtering (esp. Paused with missing endtime) is a documented
  follow-up, not silently assumed away.

## eICU-CRD v2.0 results (1,066,069 pressor rows)

Agents: norepinephrine 579,127 · other (phenylephrine/vasopressin) 277,525 · dopamine 91,372 ·
dobutamine 63,967 · epinephrine 54,078.

| unit (from drugname parens) | rows | prior behavior | now |
|---|---|---|---|
| `ml/hr` | ≈537k (50%) | unknown (no concentration) | unchanged — explicit unknown |
| `mcg/min` | ≈213k | converted only with valid row weight | same; 99.9% of rows lack a valid row `patientweight` → explicit unknown |
| `mcg/kg/min` | ≈119.5k | passthrough | unchanged |
| `units/min` | 62,037 | unknown | unchanged |
| `mg/kg/min` | 232 | unknown (no silent conversion) | **now converted ×1000** (same policy as MIMIC) |
| `mg/min` | 61 | unknown | converted ×1000 ÷ weight when weight valid |
| `mcg/hr`, `mg/hr`, `ml`, `nanograms/kg/min`, `units/kg/hr(min)` | ≈250 | unknown | unchanged |

**No silent conversions existed in eICU before this change** (all non-`mcg/kg/min` units were
already unknown). The upgrade applies one policy to both datasets and normalizes the emitted
unit to `mcg/kg/min` whenever a dose is known.

## Unresolved cases (deliberately explicit)

1. **MIMIC status/order filtering:** Paused/Stopped rows with a missing endtime still count as
   active inside the start/end window (pre-existing behavior, now documented). Follow-up task.
2. **MIMIC bolus orders:** counted as pressor-present, dose unknown (conservative), not as
   continuous infusions.
3. **eICU `ml/hr` rows (half of eICU pressor rows):** no concentration column exists in
   infusionDrug; resolving them requires linking pharmacy/concentration data. Out of scope for B1.
4. **eICU `mcg/min` rows:** row weight is almost always absent; nursing-charted weights could
   resolve a subset. Out of scope for B1.
5. **MIMIC `ng/kg/min` (angiotensin II, 296 rows):** mechanically convertible (÷1000) but left
   unknown under the frozen v1 policy to avoid a policy change mid-branch. Trivial follow-up.
6. **Milrinone** excluded from the pressor map by design (inotrope). Documented in `item_map.py`.
