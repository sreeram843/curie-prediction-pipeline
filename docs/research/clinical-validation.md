# Clinical validation test plan

**Status:** Planning (not started as a clinical study)  
**Scope:** What evidence we need before any claim of clinical validity  
**Related:** [sofa-contract.md](../contracts/sofa-contract.md), [aki-contract.md](../contracts/aki-contract.md)

> **Current posture:** This repository is a **prototype**. Engineering tests (golden fixtures, T2 replay, Flink unit tests) prove *deterministic correctness*, not clinical validity. Do not claim FDA clearance, clinical validation, or readiness for patient care until the stages below are completed under appropriate IRB / institutional oversight.

---

## 1. Claim to validate (lock before running studies)

Pick one primary claim (recommended for Curie):

> **Primary claim:** Shared alert governance reduces interruptive alert volume versus threshold-only SOFA/AKI scoring, while preserving detection of labeled deterioration events within a clinically meaningful time window.

Optional secondary claims (each needs its own endpoint):

- Lead time: governed alerts fire ≥ N hours before labeled onset (when detection occurs).
- Multi-indicator reuse: AKI and sepsis share governance without separate infrastructure.
- Safety: missing/invalid data never silently imputes a reassuring score (fail closed / partial / DLQ).

**Non-claims until proven:** superiority to NEWS/qSOFA/vendor CDS; deployability as SaMD; fairness across all sites.

---

## 2. Stages of evidence

| Stage | Goal | Data | “Done” looks like |
|---|---|---|---|
| **A. Engineering gate** (done / ongoing) | Rules do what the contract says | Golden fixtures, T2 scenarios, Flink tests | CI green; Python ≡ Java on goldens |
| **B. Retrospective clinical eval** | Outcome-tied metrics on real ICU data | Full **MIMIC-IV** (PhysioNet), not demo-only | Pre-registered endpoints met on holdout |
| **C. External / temporal validation** | Generalization | Holdout years and/or second dataset (e.g. eICU) | Performance does not collapse |
| **D. Silent prospective** | Real workflow, no interrupts | Partner hospital shadow mode | Stable ops + metrics vs local labels |
| **E. Limited interruptive pilot** | Human factors + safety | Same site, CDS-style alerts | Dismiss rate, ack time, safety review |
| **F. Regulatory path** (if productized) | Legal/clinical use | QMS + clinical eval report | Per counsel / FDA CDS–SaMD guidance |

Stages B–E require **IRB / DUA / BAA** as applicable. Synthea does **not** substitute for B+.

---

## 3. Data requirements

### 3.1 PhysioNet MIMIC-IV (Stage B)

External data + tooling cheat sheet: [`mimic-data-sources.md`](./mimic-data-sources.md) (PhysioNet, [mimic-code](https://github.com/MIT-LCP/mimic-code/), [MIMIC-IV-Data-Pipeline](https://github.com/healthylaife/MIMIC-IV-Data-Pipeline), vs Curie demo/Challenge).

- [ ] PhysioNet credentialed access + signed DUA  
- [ ] Full MIMIC-IV (hosp + icu), not only `mimic-iv-demo`  
- [x] Document version target + pin policy (see [`mimic-iv-study-protocol.md`](./mimic-iv-study-protocol.md))  
- [x] Cohort definition: adult ICU stays, inclusion/exclusion, first stay vs all stays  
- [ ] Freeze rule-bundle versions used for the run (`sepsis-sofa`, `aki-kdigo`) at operating-point selection

### 3.1b PhysioNet Challenge 2019 (Stage B light — in progress)

Hourly ICU stays with `SepsisLabel` under `data/archive/` (~40k stays). Offline eval:

```bash
make challenge-2019          # sample
LIMIT=0 make challenge-2019  # full archive
```

**Results + improvement plan:** [`challenge-2019-eval.md`](./challenge-2019-eval.md).

- [x] Adapter + harness: `ingestion/adapters/challenge2019`, `eval/challenge2019/runner.py`  
- [x] Full-archive baseline (`strict` / bundle defaults) — 2026-08-11  
- [x] Gov profiles `balanced` / `sensitive`; tune on setA, hold out setB (see [`challenge-2019-eval.md`](./challenge-2019-eval.md) locked operating point)  
- [ ] Pre-specify paper endpoints (sensitivity floor + reduction cap)  
- [ ] Document partial-SOFA limitations in any public writeup (see eval doc)

### 3.2 Labels (ground truth)

Implement reproducible label pipelines (cite methods papers; version the code):

| Indicator | Candidate label | Notes |
|---|---|---|
| Sepsis | Sepsis-3 (infection suspicion + SOFA rise) | Need onset time, not just billing codes |
| AKI | KDIGO creatinine and/or UO staging | Align windows with [aki-contract.md](../contracts/aki-contract.md) |
| Optional severity | ICU mortality, vasopressor start, ventilation | Useful secondary endpoints |

- [ ] Label code reviewed and frozen  
- [ ] Inter-rater / sanity checks on a labeled subsample (if chart review used)  
- [ ] Explicit handling of ESRD, comfort care, OR transfers (exclusion or subgroup)

### 3.3 What the current `make mimic-demo` does *not* cover

- No outcome labels  
- Single snapshot (~24h), not streaming event-time replay  
- Demo cohort size only  

Stage B streaming path: **`make mimic-harness`** (CURIE-015) replays demo-schema
fixtures in availability-time order with leakage tests and content hashes. Full
PhysioNet extract wiring remains after DUA access.

---

## 4. Test matrix (clinical)

### 4.1 Detection performance (must-have)

For each indicator (sepsis, AKI), on **holdout** stays:

| ID | Test | Metric | Pass guideline (set numerically in protocol) |
|---|---|---|---|
| C-DET-1 | Event recall | Sensitivity within [0, T] hours of labeled onset | Pre-specify minimum (e.g. ≥ baseline − ε) |
| C-DET-2 | Burden | Alerts / 100 patient-days; PPV; **NNA** | Pre-specify max burden or NNA target |
| C-DET-3 | Lead time | Hours from first true-positive alert to onset | Report distribution; compare to naive |
| C-DET-4 | Miss analysis | False negatives by reason (missing data, threshold, governance) | Qualitative + counts |
| C-DET-5 | Partial data | Performance when `completeness=partial` | No silent false reassurance |

### 4.2 Governance value (core paper thesis)

| ID | Test | Metric |
|---|---|---|
| C-GOV-1 | Naive vs governed | Alert reduction ratio; ΔNNA; Δsensitivity |
| C-GOV-2 | Ablation: trajectory off | Same metrics |
| C-GOV-3 | Ablation: baseline off | Same metrics |
| C-GOV-4 | Ablation: refractory off | Same metrics |
| C-GOV-5 | Ablation: context suppression off | Same metrics (comfort care / protocol flags if available) |
| C-GOV-6 | Recovery / re-deterioration | Trajectory resets on below-threshold; re-alert behavior |

**Pass idea:** governance cuts interrupts **without** unacceptable drop in recall (thresholds fixed in writing *before* peeking at holdout).

### 4.3 Determinism & safety (engineering-clinical bridge)

| ID | Test | Metric |
|---|---|---|
| C-SAFE-1 | Replay determinism on MIMIC extract | 100% identical alerts on repeat |
| C-SAFE-2 | Invalid units/status | DLQ / reject; never scored as normal |
| C-SAFE-3 | FiO₂ policy | No ambient-air ratio without FiO₂ |
| C-SAFE-4 | Bundle version pin | Changing bundle version changes scores only as expected |

### 4.4 Subgroups / fairness (report even if exploratory)

| ID | Slice |
|---|---|
| C-SUB-1 | Age bands |
| C-SUB-2 | Admission type / service |
| C-SUB-3 | Illness severity (e.g. first-day SOFA) |
| C-SUB-4 | Sex (and race/ethnicity if ethically approved and available) |

### 4.5 Baselines to compare

- [ ] Threshold-only SOFA / AKI (naive path in this repo)  
- [ ] Optional: NEWS2 / qSOFA / published KDIGO electronic alerts (as feasible on MIMIC)  
- [ ] Optional: no-alert / random-time control for lead-time sanity  

### 4.6 Prospective stages (D–E) — checklist only until partner exists

- [ ] Shadow: alerts computed, not shown to clinicians; compare to local outcomes  
- [ ] Pilot: interruptive for agreed tiers only; capture ack / dismiss / override  
- [ ] Safety monitoring plan (unexpected harm, alert floods)  
- [ ] Human factors notes (wording, evidence panel, fatigue)  

---

## 5. Analysis protocol (keep honest)

1. **Pre-register** (even informally in this doc or a short protocol): cohort, labels, primary endpoint, governance config, train vs holdout split.  
2. **Split:** temporal (e.g. develop on earlier years, validate on later) preferred over random stay split.  
3. **No threshold fishing on holdout:** tune on development set only.  
4. **Report:** point estimates + CIs; absolute alert counts; missing-data rates.  
5. **Failures are results:** list FN/FP case themes.

---

## 6. Deliverables per stage

| Stage | Artifact |
|---|---|
| B | MIMIC eval report (tables for C-DET / C-GOV); frozen bundle SHAs; label code version |
| C | External/temporal replication appendix |
| D | Shadow-mode ops report (uptime, lag, DLQ rate) |
| E | Pilot clinical + HF report |
| — | Updated regulatory posture in README / PRD when claims change |

---

## 7. Mapping to current repo tests

| Already in repo | Clinical stage |
|---|---|
| Golden SOFA / T0 AKI fixtures | A only |
| T2 replay + alert_reduction_ratio | A (synthetic); method preview for C-GOV-1 |
| `make mimic-demo` | Plumbing for B — **not** clinical metrics |
| Flink/Python reliability tests | A / C-SAFE-* precursors |

**Net-new work for Stage B:** labeled MIMIC harness, streaming/replay over stays, metric notebook/report, ablation runner.

---

## 8. Effort sketch (order of magnitude)

| Work | Rough effort |
|---|---|
| Full MIMIC access + cohort + labels | Days–weeks (DUA + engineering) |
| Eval harness + primary tables | Weeks |
| Ablations + writeup-ready figures | Weeks |
| External validation | Additional weeks–months |
| Prospective partner study | Months (institutional) |

---

## 9. Open decisions (resolved by CURIE-014)

Frozen protocol: [`mimic-iv-study-protocol.md`](./mimic-iv-study-protocol.md) /
[`eval/mimic_study/frozen/protocol.v1.json`](../../eval/mimic_study/frozen/protocol.v1.json).

| Decision | Resolution |
|---|---|
| Primary endpoint | **PE-1** non-inferior governed sensitivity (naive − 10 pp or ≥ 70% absolute) on locked test |
| Co-primary | **PE-2** interruptive reduction ratio ≤ 0.25 |
| Onset window | `window_m12_p6` (−12h / +6h) |
| First paper indicators | SOFA deterioration + sepsis-3 primary; AKI secondary; respiratory exploratory |
| Governance config | Selected on calibration (OPS-1); frozen before test |
| Comfort care / ESRD | Subgroup / AKI denominator rules — see protocol cohort section |

---

## Revision history

| Date | Change |
|---|---|
| 2026-08-12 | CURIE-014: open decisions resolved via frozen MIMIC-IV protocol |
| 2026-08-11 | Initial clinical validation test plan |
