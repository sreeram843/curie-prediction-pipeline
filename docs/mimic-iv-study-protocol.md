# MIMIC-IV governance study protocol v1 (CURIE-014)

**Status:** Frozen 2026-08-12 — pre-registered before temporal holdout inspection  
**Machine-readable:** [`eval/mimic_study/frozen/protocol.v1.json`](../eval/mimic_study/frozen/protocol.v1.json)  
**Guards:** `python -m eval.mimic_study.sweep show`  
**Related:** [clinical-validation.md](./clinical-validation.md), [mimic-data-sources.md](./mimic-data-sources.md), [challenge-2019-eval.md](./challenge-2019-eval.md)

> Prototype study design only. Not IRB-approved clinical research, not FDA evidence, not for patient care. Full MIMIC-IV requires PhysioNet credentialed access + DUA. Demo schema is for harness plumbing (CURIE-015), never the primary cohort.

---

## 1. Objective

Evaluate whether **shared alert governance** reduces interruptive alert volume versus threshold-only scoring while **preserving detection** of labeled deterioration on MIMIC-IV, using Curie SOFA / sepsis-3 (primary) and AKI (secondary) indicators.

---

## 2. Dataset and code pins

| Item | Pin policy |
|---|---|
| MIMIC-IV | Target **3.1** (`hosp` + `icu`); record exact PhysioNet version + extract date + stay-list hash at first Stage B extract |
| mimic-code | Record git SHA (+ Zenodo if used) for sepsis/AKI concepts before label generation; do not change for primary analysis |
| Rule bundles | Pin active `sepsis-sofa` / `aki-kdigo` versions into the operating-point freeze artifact at selection time |
| Demo | `CURIE_MIMIC_DEMO_DIR` / `make mimic-demo` — plumbing only |

---

## 3. Cohort

- **Unit:** ICU stay (`stay_id`)
- **Include:** age ≥ 18; first ICU stay per `hadm_id`; length ≥ 4 h
- **Exclude (primary):** pediatric; stay &lt; 4 h; missing intime/outtime
- **Subgroup / special handling:** comfort care; ESRD (exclude from AKI denominator); OR transfer gaps (missingness, no impute)
- **Bootstrap unit:** ICU stay

---

## 4. Labels

| Role | Event | Definition |
|---|---|---|
| Primary | `sepsis3_onset` | Sepsis-3-aligned (infection suspicion + acute SOFA rise); onset = availability-time when phenotype first completes |
| Secondary | `aki_kdigo_stage_ge_1` | KDIGO stage ≥ 1 (creatinine and/or covered UO) |
| Exploratory | respiratory proxy | `resp-deterioration` v0.1 — not primary |

Discharge ICD sepsis codes are **not** primary onset.

---

## 5. Availability-time policy

Replay in **availability-time** order. Forbidden as features before availability: discharge diagnoses, future corrections, later notes, post-discharge labels. Amended values apply only at their own availability time. Leakage tests land in CURIE-015.

**Cadence:** event-driven score updates (primary). Optional hourly re-bin for Challenge-comparable sensitivity tables only.

---

## 6. Splits (temporal by ICU intime)

| Split | Intime (planned) | Role | Allowed |
|---|---|---|---|
| `development` | 2008-01-01 → 2016-12-31 | tune | sweep / ablation design |
| `calibration` | 2017-01-01 → 2018-12-31 | select | operating-point selection |
| `test` | 2019-01-01 → 2019-12-31 | evaluate **once** | locked primary / ablation / bootstrap only |

If the pinned MIMIC calendar span differs, rescale ranges but keep the three roles.

**Hard rule:** sweep, tune, grid/threshold search, and operating-point selection are **forbidden** on `test` (enforced in `eval.mimic_study.protocol`).

```bash
python -m eval.mimic_study.sweep sweep --split development   # ok (dry-run until harness)
python -m eval.mimic_study.sweep sweep --split test          # exits 2 — PROTOCOL_VIOLATION
```

---

## 7. Primary endpoint and operating-point rule

### PE-1 (primary) — non-inferior governed sensitivity

Among labeled-positive stays on **test**:

`governed_sensitivity >= naive_sensitivity − 0.10` **OR** `governed_sensitivity >= 0.70`

Detection window: **`window_m12_p6`** — any alert in `[onset − 12h, onset + 6h]` (inherited from Challenge timing freeze).

Non-inferiority margin: **10 percentage points**.

### PE-2 (co-primary) — interruptive burden

`interruptive_reduction_ratio = governed_interruptive / naive_interruptive ≤ 0.25`

Also report interruptive alerts per 100 patient-days.

### OPS-1 — operating-point selection

1. Sweep knobs on **development** (bundles fixed).  
2. On **calibration**, pick the candidate that **minimizes** interruptive reduction ratio **subject to PE-1**.  
3. Freeze to `eval/mimic_study/frozen/operating_point.v1.json`.  
4. **Never** re-select using **test**. One-shot primary evaluation on test.

Tie-breakers: lower interruptive NNA → higher sensitivity → lexicographic `candidate_id`.

---

## 8. Ablations, subgroups, missingness

**Ablations (pre-specified):** threshold-only; full governance; drop persistence / crossings / baseline / refractory / context suppression / page gate / episode arbitration / late-event buffer.

**Subgroups:** age band, sex, admission type, first-day SOFA tertile, partial vs complete scores, comfort-care flag.

**Missing data:** completeness by split; performance when partial; FiO₂ / Cr / UO missing rates; no ambient FiO₂ without `room_air`.

**Bootstrap:** 1000 stay-level percentile 95% CIs, seed 42.

---

## 9. Product claims → evidence

| ID | Claim | Evidence required | Status |
|---|---|---|---|
| C1 | Governance cuts interruptive volume while preserving in-window detection | PE-1 + PE-2 on test + CIs | pending Stage B |
| C2 | Episode arbitration → one actionable episode | Episode vs alert rates; CURIE-012; concurrent-signal subgroup | eng. done / clinical pending |
| C3 | New indicator = plugin/bundle, not new platform | CURIE-010/011/013 gates | eng. done |
| C4 | Availability-time replay has no future leakage | CURIE-015 leakage tests + hash identity | eng. done (demo schema) |
| NON | Clinical validation / FDA / NEWS superiority / SaMD | Out of scope until Stages C–F | **non-claim** |

---

## 10. What this freeze does *not* authorize

- Peeking at test metrics to choose knobs  
- Claiming clinical validity from demo or Challenge alone  
- Committing PhysioNet patient extracts to git  

Next implementation after harness: **CURIE-016** ablation study — see
[`mimic-ablation-study.md`](./mimic-ablation-study.md) (`make mimic-study`).
