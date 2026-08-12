# MIMIC / PhysioNet data sources (reference)

**Purpose:** Capture what each external MIMIC-related resource is for, so Stage B / later eval work does not re-derive this from chat history.  
**Status:** Planning notes — none of these replace PhysioNet credentialed access + DUA.  
**Related:** [clinical-validation.md](./clinical-validation.md), [challenge-2019-eval.md](./challenge-2019-eval.md), [physionet-project-form.md](./physionet-project-form.md) (paste-ready PhysioNet project fields)

---

## 1. Mental model

| Layer | What it is |
|---|---|
| **PhysioNet** | Source of truth: download or cloud access to MIMIC family datasets |
| **Tooling repos** | Code that *assumes you already have MIMIC* — build concepts, cohorts, ML tables |
| **Curie** | Streaming score + governance; local adapters/eval on demo / Challenge 2019 |

Nothing below **generates** MIMIC patients. They process or derive from data you are authorized to use.

---

## 2. Datasets (need PhysioNet access unless noted)

| Dataset | Access | Curie use today | Later use |
|---|---|---|---|
| **MIMIC-IV Clinical Database Demo** | Open (no credential) | `data/mimic-iv-demo/` → `make mimic-demo` | Smoke / plumbing only |
| **MIMIC-IV** (full hosp + icu) | Credentialed + DUA | Not yet | Stage B retrospective eval |
| **MIMIC-IV-Note**, **MIMIC-CXR**, ECG/echo/wave | Credentialed (per project) | Not used | Optional multimodal; out of core Curie path |
| **PhysioNet Challenge 2019** | Local `data/archive/` | Primary sepsis alert eval | Keep as labeled hourly proxy |

PhysioNet home: https://mimic.mit.edu · Challenge / MIMIC project pages on https://physionet.org

### Related non-PhysioNet ICU platforms

| Resource | What it is | Curie fit |
|---|---|---|
| **[KHDP](https://khdp.net)** (Korea Health Data Platform / SNUH) | Secure cloud platform for Korean healthcare research data; hosts / gates **K-MIMIC**-related ICU resources | Optional **external** eval later (different country, care patterns). Does **not** replace PhysioNet CITI for MIMIC-IV. |
| **Synthetic K-MIMIC (SYN-ICU)** via KHDP | Downloadable synthetic Korean ICU tables (see KHDP data catalog / [SYN-ICU](https://khdp.net/database/data-search-detail/SYN-ICU)) | Easiest KHDP on-ramp for plumbing experiments; not US MIMIC labels; needs a new Curie adapter if used |

**SYN-ICU download (what to get):** From the KHDP SYN-ICU page, download **all 15** `.xlsx` tables (MIMIC-IV–like schema, synthetic). Community ETL expects them together ([K-MIMIC-MEDS](https://github.com/ji-ch01/K-MIMIC-MEDS)):

```text
syn_patients.xlsx
syn_admissions.xlsx
syn_icustays.xlsx
syn_transfers.xlsx
syn_chartevents.xlsx
syn_labevents.xlsx
syn_d_items.xlsx
syn_d_labitems.xlsx
syn_inputevents.xlsx
syn_outputevents.xlsx
syn_procedureevents.xlsx
syn_procedures_icd.xlsx
syn_diagnoses_icd.xlsx
syn_emar.xlsx
syn_emar_detail.xlsx
```

For a Curie-style SOFA/AKI smoke path, the high-value subset is: `syn_patients`, `syn_admissions`, `syn_icustays`, `syn_chartevents`, `syn_labevents`, `syn_d_items`, `syn_d_labitems`, `syn_inputevents`, `syn_outputevents`. Still download all 15 if the portal gives one bundle — dictionaries and stays join the rest.

~1.3k synthetic patients; codes are Korean EDI/KCD-oriented, not identical to MIMIC itemids — mapping work required before governance claims.
| **Full K-MIMIC** | Multi-hospital Korean ICU (EMR + signals + imaging); access typically IRB + DUA + in-platform analysis | Strong external-validity candidate once Curie’s US/Challenge path is solid; heavier access than Challenge 2019 |

Do not commit KHDP/K-MIMIC extracts to git. Document version + access path if used in a paper.
---

## 3. External code hubs

### 3.1 [MIT-LCP/mimic-code](https://github.com/MIT-LCP/mimic-code/)

**What:** Central community hub for MIMIC analysis code (III, IV, ED, CXR, notes, …). Build scripts, SQL **derived concepts**, tutorials.

**Not:** A data download tool that invents MIMIC.

**Curie relevance:** Best source for **clinical label definitions** on full MIMIC-IV (e.g. Sepsis-3-aligned concepts) when moving past Challenge 2019 labels. See P4 in [challenge-2019-eval.md](./challenge-2019-eval.md).

**Typical workflow:**

1. Credentialed MIMIC-IV access (files or BigQuery/AWS).  
2. Run / adapt concepts under `mimic-iv/` (and cite dataset + Zenodo release as their README asks).  
3. Export stay-level timelines + labels → map into Curie envelopes → score + governance harness.

### 3.2 [healthylaife/MIMIC-IV-Data-Pipeline](https://github.com/healthylaife/MIMIC-IV-Data-Pipeline)

**What:** End-to-end **ML prep + modeling** pipeline on MIMIC-IV: cohort selection, cleaning/imputation, clinical grouping, fixed-interval time-series binning, optional multimodal alignment (structured, notes, CXR, ECG, echo, waveforms), plus train/eval/fairness modules. Wizard notebook: `mainPipeline.ipynb`.

**Papers:**

- Gupta et al., ML4H 2022 — [An Extensive Data Processing Pipeline for MIMIC-IV](https://proceedings.mlr.press/v193/gupta22a.html)  
- Multimodal extension — [arXiv:2601.11606](https://arxiv.org/abs/2601.11606)

**Not:** A Flink/Kafka streaming stack; not Curie’s alert-governance runtime.

**Curie relevance:** Useful if we want a **batch ML-ready cohort** or ideas for multimodal features. For Stage B governance eval, prefer **mimic-code labels** + Curie’s own event/replay format unless we deliberately adopt their binned tensors.

**Data layout they expect (after PhysioNet download):**

```text
mimiciv/
  1.0|2.0|3.1/   # hosp/, icu/, …
  notes/ cxr/ ecg/ echo/ wave/
```

---

## 4. What Curie already has locally

| Path / command | Role |
|---|---|
| `data/mimic-iv-demo/` (+ `CURIE_MIMIC_DEMO_DIR`) | Open demo CSVs |
| `make mimic-demo` | Score SOFA/AKI rules on demo stays — **not** clinical validity |
| `data/archive/` + `make challenge-2019` | Labeled hourly sepsis eval (~40k stays) |
| `ingestion/adapters/mimic/` | Demo extract → Curie inputs |
| `ingestion/adapters/challenge2019/` | Challenge stays → Curie inputs |

Do **not** commit PhysioNet dumps or derived patient-level extracts to git (`data/` is gitignored).

---

## 5. Recommended path when we pick Stage B back up

1. Keep Challenge 2019 as the locked **governance operating-point** benchmark.  
2. Obtain full MIMIC-IV DUA access.  
3. Use **mimic-code** for stay cohorts + sepsis (or AKI) labels; document MIMIC version + concept SHAs.  
4. Build a Curie “MIMIC eval harness” (stay timeline → envelopes → score → governance → metrics) — see [clinical-validation.md](./clinical-validation.md) Stage B.  
5. Optionally use **MIMIC-IV-Data-Pipeline** only if we need their cohort UI / multimodal tensors for a separate ML experiment — do not conflate with streaming alert claims.

---

## 6. Quick comparison

| Need | Prefer |
|---|---|
| Official-ish derived SQL concepts / sepsis labels | [mimic-code](https://github.com/MIT-LCP/mimic-code/) |
| Configurable ML time-series + multimodal + models | [MIMIC-IV-Data-Pipeline](https://github.com/healthylaife/MIMIC-IV-Data-Pipeline) |
| Fast labeled sepsis alert eval without full MIMIC | Challenge 2019 (`data/archive/`) |
| Live alerts | Curie Kafka → Flink (not these repos) |

---

## 7. Citation reminders (when we publish)

- Cite the **PhysioNet dataset version** you used (MIMIC-IV, Challenge 2019, etc.).  
- If using mimic-code concepts: cite their paper + Zenodo release per their README.  
- If using MIMIC-IV-Data-Pipeline: cite Gupta et al. 2022 (and multimodal arXiv if applicable).  
- Curie: frame as prototype / engineering eval until Stage B+ completes.
