# Challenge 2019 sepsis alert evaluation

**Status:** Operating point locked on holdout setB (2026-08-11) — eval task track complete  
**Harness:** `make challenge-2019` / `challenge-2019-sweep` / `challenge-2019-robustness`  
**Data:** PhysioNet Challenge 2019 under `data/archive/` (ODbL; cite PhysioNet)  
**Frozen config:** [`eval/challenge2019/frozen/p1_setA_winner.json`](../eval/challenge2019/frozen/p1_setA_winner.json)  
**Related:** [clinical-validation.md](./clinical-validation.md), [sofa-contract.md](./sofa-contract.md)

> This is a **retrospective offline** evaluation of Curie SOFA + governance against Challenge `SepsisLabel`. It is **not** clinical validation, FDA evidence, or the official Challenge utility score.

---

## Operating point (locked)

| Item | Value |
|---|---|
| Config | `grid_p0_r90_b0` → `p1_setA_winner.json` + resolved study bundle `sepsis-sofa.challenge2019-p1.v1.json` |
| Knobs | persist **0**, crossings **1**, baseline **off**, refractory **90** min, min_comp **2**, **page gate on** (↑score, ≥2 crossings, ≥2 components, page persist **30** m) |
| Tune / holdout | setA → freeze → **setB** (blinded) |
| Detection | **Primary:** any alert in `[label_start−12h, label_start+6h]` (`window_m12_p6`, CURIE-004). Legacy grace≤6h is sensitivity analysis only. |
| Burden | **Interruptive** (urgent/critical) pages only |
| Label | Challenge `SepsisLabel` begins **~6h before clinical onset**; `onset_iculos` = **label_start** |
| Timing freeze | [`eval/challenge2019/frozen/timing_primary.v1.json`](../eval/challenge2019/frozen/timing_primary.v1.json) |

### Holdout setB (n = 20,000) — primary `window_m12_p6`

Pinned artifact:
[`eval/challenge2019/frozen/holdout_primary_window_m12_p6.v1.json`](../eval/challenge2019/frozen/holdout_primary_window_m12_p6.v1.json).
Miss attribution stub:
[`eval/challenge2019/frozen/miss_analysis.v1.json`](../eval/challenge2019/frozen/miss_analysis.v1.json).

| Metric | Point | Notes |
|---|---|---|
| **Governed sensitivity (primary)** | **79.5%** | Any governed alert in `[onset−12h, onset+6h]` |
| **Interruptive sensitivity (emissions)** | **34.0%** | Interruptive emissions in-window — not episode pages |
| **Interruptive NNA (emissions)** | **106.1** | Interruptive emissions / interruptive TP |
| **In-window mean lead hours** | **5.97 h** | First in-window governed alert → onset |

### Legacy grace≤6h (sensitivity analysis only)

> Do **not** quote 81.1% as the primary timing result. Legacy figures remain for robustness tables.

| Metric | Point | 95% CI |
|---|---|---|
| Detection sensitivity (gov = naive), **legacy grace≤6h** | **81.1%** | [0.79, 0.83] |
| Interruptive reduction vs naive | **0.132** (~7.6× fewer pages) | [0.13, 0.14] |
| Interruptive NNA (pages / interruptive TP) | **~94.2** | — |
| Legacy pages / any-governed TP | **~44** | [42, 48] |
| Mean lead hours (governed, **unbounded first alert**) | **~42** | [38, 46] |

**Goals:** primary window sensitivity documented above; co-primary interruptive reduction ≤ 0.25 (legacy table).
Secondary page NNA was previously quoted as ~44 using pages / **any-governed** TP;
the corrected definition (pages / **interruptive** TP) is **~94.2** (`41158 / 437`).
All-alert governed NNA remains ~173 because watch volume is high by design.

Reproduce holdout:

```bash
GOV_CONFIG=eval/challenge2019/frozen/p1_setA_winner.json SET=training_setB LIMIT=0 make challenge-2019
```

---

## 1. What we ran (historical baseline)

| Item | Value |
|---|---|
| Command | `python -m eval.challenge2019.runner --limit 0 --json-out data/archive/challenge2019_eval_full.json` |
| Stays scored | **40,336** (training_setA + training_setB) |
| Wall time | **~79 s** on local machine |
| Rule bundle | `sepsis-sofa` **v0.2.0** |
| Governance | Bundle defaults: `min_crossings=2`, persistence **30** min, baseline **on** (Δ≥2), refractory **120** min |
| Detection rule | True positive if first alert ICULOS ≤ onset + **6** hours |
| Artifact | `data/archive/challenge2019_eval_full.json` (gitignored under `data/`) |

### Method (short)

1. Read each stay `.psv` hour-by-hour.  
2. Forward-fill SOFA-relevant fields: MAP, platelets, bilirubin, creatinine, O2Sat/SaO2, FiO2.  
3. Score with Curie SOFA (partial — see limitations).  
4. **Naive:** alert when tier ≠ `none`.  
5. **Governed:** shared governance `evaluate` (same as replay harness).  
6. Onset = first hour with `SepsisLabel == 1`.  
7. **Bootstrap CIs** (default `n_boot=1000`, seed 42): stay-level percentile intervals on sensitivity, reduction ratios, NNA, lead time — no re-scoring (`--bootstrap 0` to disable).  
8. **Dual-lane:** page gate may downgrade urgent/critical → watch; detection uses any emit, burden uses pages.

---

## 2. Baseline results (full archive)

### Cohort

| Cohort | Stays |
|---|---|
| Sepsis (any `SepsisLabel=1`) | **2,932** |
| Non-sepsis | **37,404** |

### Profile comparison (all 40,336 stays, grace = 6h)

| Profile | Gov sens. | Naive sens. | Gov alerts | Reduction | Gov NNA | Notes |
|---|---|---|---|---|---|---|
| **`strict`** (bundle default) | **18.9%** | 80.2% | 18,043 | **0.023** | ~32 | Old baseline — too quiet |
| **`accuracy`** (default now) | **85.6%** | 85.6% | 430,214 | **0.51** | ~171 | Matches naive catch; ~half the alerts |
| `sensitive` | 85.6% | 85.6% | 430,214 | 0.51 | ~171 | Same operating point on hourly data as `accuracy` |

`accuracy` knobs: `min_crossings=1`, persistence **0**, baseline **off**, refractory **90** min, `min_components_required=2`.

### `strict` detail (historical)

| Path | Total alerts | vs naive |
|---|---|---|
| Naive | **771,189** | 100% |
| Governed | **18,043** | **~2.3%** (reduction ratio ≈ **0.023**) |

| Metric | Naive | Governed |
|---|---|---|
| True positives (stays) | 2,351 | 556 |
| Sensitivity | **80.2%** | **18.9%** |
| FP stays (alerted, no sepsis) | 22,814 | 3,107 |
| NNA (alerts / TP) | ~328 | **~32** |

### `accuracy` detail (recommended for detection-first)

| Metric | Naive | Governed |
|---|---|---|
| Alerts | 841,755 | **430,214** |
| True positives | 2,509 | **2,509** |
| Sensitivity | **85.6%** | **85.6%** |
| FP non-sepsis stays | 23,165 | 23,165 |
| NNA | ~335 | **~171** |
| Mean lead hours | ~45.0 | ~45.0 |

Naive alert totals differ slightly vs `strict` because `min_components_required` is **2** (more hours become scoreable).

### Interpretation

1. **`strict`:** strong burden cut, poor recall on this dataset.  
2. **`accuracy`:** **same sepsis catch as threshold-only**, with ~**49%** fewer repeat alerts via hourly refractory dedup.  
3. FP *stays* do not drop under `accuracy` (first alert still fires); volume drops from dedup within stay.  
4. Challenge rows are **hourly** — refractory &lt; 60m is effectively a no-op between consecutive hours.

---

## 3. Limitations (must state in any writeup)

- **Partial SOFA:** Challenge 2019 has no GCS, urine output, or vasopressor dose ladder → many scores are partial; respiration rarely reaches points 3–4 (no reliable mechanical-vent flag).  
- **Label ≠ Sepsis-3 chart review:** `SepsisLabel` is the Challenge definition (onset-aligned).  
- **Not a Challenge leaderboard entry:** we report Curie metrics plus an offline
  Challenge utility (`challenge_utility`) with emit-hour positives — not a
  submitted entry.
- **Holdout protocol:** knobs tuned on setA only; setB reported once with frozen sidecar (see Operating point). Historical §2 baselines scored setA+setB together.  
- **Forward-fill** last observation — simple; may differ from bedside charting practice.  
- **Watch vs page:** detection sensitivity includes passive watch emits; interruptive metrics are the page-burden numbers to quote for “optimal alerts.”

---

## 4. Improvement plan

### Goal (locked operating point)

| Priority | Target | Holdout result |
|---|---|---|
| Primary | Governed sensitivity ≥ **naive − 10 pp** (or ≥ **70%** absolute) on **holdout setB** | **81.1% = naive** ✓ |
| Co-primary | **Interruptive** reduction ≤ **0.25** (pages vs naive) | **0.132** ✓ |
| Secondary | Interruptive NNA ≤ **50** (pages / interruptive TP) | **~94.2** (legacy pages/gov TP ~44) |

### Phase P0 — Eval profiles (done)

Named profiles in `eval/replay_harness/gov_profiles.py`:

| Profile | Intent | Knobs |
|---|---|---|
| `strict` | Interrupt hygiene | Bundle defaults |
| `balanced` | Mid tradeoff + page gate | crossings=1, persist 15m, baseline on, refractory 60m, min_comp=2, **page gate on** |
| `sensitive` / **`accuracy`** | Best detection | crossings=1, persist 0, baseline off, refractory 90–120m, min_comp=2 |
| **`dual`** | Detection + quieter pages | accuracy watch lane + page gate (↑score, ≥2 crossings, ≥2 components, 60m persist) |

`make challenge-2019` defaults to **`accuracy`**.

### Phase P1 — Tune on setA, freeze, hold out setB (done)

1. Sweep profiles (+ small grid around `balanced`) **only on training_setA** (`--jobs` parallel).  
2. Freeze winning config → `eval/challenge2019/frozen/p1_setA_winner.json`.  
3. Single blinded-style run on **training_setB**.  
4. Record results in this doc §5.

**Winner:** `grid_p0_r90_b0` (persist 0, refractory 90, baseline off, page gate on).  
**Holdout:** goals **met** — detection sens = naive (81.1%); interruptive reduction **0.132** (≤0.25).

Reproduce:

```bash
JOBS=11 LIMIT=0 make challenge-2019-sweep
# or score frozen config only:
GOV_CONFIG=eval/challenge2019/frozen/p1_setA_winner.json SET=training_setB LIMIT=0 make challenge-2019
```

**Exit:** holdout meets §4 goals, or document failure and next knob. ✓

### Phase P2 — Detection definition robustness (done)

Report side-by-side on **setB** with frozen winner + `strict`/`accuracy`/`dual`/`balanced`:

| Mode | Frozen sens N/G | Notes |
|---|---|---|
| grace **0** | 56.3% / 56.3% | First alert ≤ onset |
| grace **6** (legacy analysis) | **81.1% / 81.1%** | Not primary — see `window_m12_p6` |
| grace **12** | 84.6% / 84.6% | |
| early-only | 54.8% / 54.8% | First alert **&lt;** onset |
| window ±12h | 83.3% / 83.3% | Any alert in [onset−12, onset+12] |

**Ranking stable** across all modes: `frozen ≈ dual ≈ accuracy > balanced > strict`.  
Artifact: `data/archive/challenge2019_robustness_setB.json`  
Reproduce: `JOBS=5 LIMIT=0 make challenge-2019-robustness`

**Exit:** ranking of profiles stable across definitions. ✓

### Phase P3 — Feature / mapping upgrades (optional, week)

- [ ] Better vent proxy from Challenge columns  
- [ ] Miss analysis: sample FN stays (governed) — trajectory vs baseline vs refractory vs insufficient components  
- [x] Dual-tier: count **watch** as detection for sensitivity, **urgent/critical** for interruptive NNA  (`alerts.watch_total` / `interruptive_*` in runner) 

### Phase P4 — Path to stronger validity (later)

- [ ] Align labels with Sepsis-3 via [mimic-code](https://github.com/MIT-LCP/mimic-code) on full MIMIC-IV  
- [ ] Compare Challenge-tuned governance on MIMIC labels (external-style check)  
- [ ] See [clinical-validation.md](./clinical-validation.md) Stages B–E
- [ ] Data/tooling map: [mimic-data-sources.md](./mimic-data-sources.md)
- [x] Deploy frozen page-gate governance into Flink rule bundle (`sepsis-sofa.v0.3.0`) — see [runtime-gov-parity.md](./runtime-gov-parity.md)
- [x] Resolved Challenge study artifact (`sepsis-sofa.challenge2019-p1.v1`) with SHA-256 gate — **product v0.3.0 is not identical** (product `min_components_required=3`; study uses **2**)

---

## 5. Results log

| Date | Scope | Profile | Sens N/G | Reduction | NNA G | Notes |
|---|---|---|---|---|---|---|
| 2026-08-11 | All 40,336 | `strict` | 80.2% / 18.9% | 0.023 | ~32 | First baseline |
| 2026-08-11 | All 40,336 | **`accuracy`** | **85.6% / 85.6%** | **0.51** | ~171 | Detection-first; `challenge2019_eval_accuracy.json` |
| 2026-08-11 | All 40,336 | `sensitive` | 85.6% / 85.6% | 0.51 | ~171 | Same as accuracy on hourly spacing |
| 2026-08-11 | setA 20,336 | **`grid_p0_r90_b0`** (frozen) | 88.4% / 88.4% | int. **0.123** | int. NNA ~41 | Page-gate winner; watch carries detection |
| 2026-08-11 | **setB 20,000 holdout** | frozen `p1_setA_winner` | **81.1% / 81.1%** | int. **0.132** | int. NNA ~44† | **Goals met** on sens/burden; 95% CI sens [0.79, 0.83], int. red. [0.13, 0.14] |
| 2026-08-12 | metric fix CURIE-003 | — | — | — | int. NNA **~94.2** | Corrected: pages/interruptive_tp; †prior ~44 was pages/governed_tp |
| 2026-08-11 | setB robustness | frozen + 4 profiles | grace6 81.1%; early 54.8%; ±12h 83.3% | — | — | Ranking **stable** across 5 detection defs |

---

## 6. How to reproduce

```bash
# Baseline (all stays)
LIMIT=0 make challenge-2019
# or:
python -m eval.challenge2019.runner --limit 0 --json-out data/archive/challenge2019_eval_full.json

# One set
SET=training_setA LIMIT=0 make challenge-2019
SET=training_setB LIMIT=0 make challenge-2019

# Parallel setA sweep → freeze → setB holdout
JOBS=11 LIMIT=0 make challenge-2019-sweep

# Detection-window robustness (grace 0/6/12, early-only, ±12h)
JOBS=5 LIMIT=0 make challenge-2019-robustness

# Frozen operating point on setB
GOV_CONFIG=eval/challenge2019/frozen/p1_setA_winner.json SET=training_setB LIMIT=0 make challenge-2019

# Sample
LIMIT=200 make challenge-2019
```

Unit tests (fixture only, no archive required):

```bash
pytest eval/fixtures/test_challenge2019.py \
  eval/fixtures/test_challenge2019_sweep.py \
  eval/fixtures/test_challenge2019_robustness.py
```

---

## 7. Citation reminder

If publishing numbers derived from this archive, cite PhysioNet Challenge 2019 / Reyna et al. (as required by the project page) and state Curie rule-bundle version + governance profile used.
