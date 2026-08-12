# PhysioNet-style project form copy

Paste into the project submission UI. Title field: `curie-prediction-pipeline`.

**Important:** This describes a **software / evaluation codebase**, not a release of MIMIC or Challenge raw files. Do not upload credentialed PhysioNet dumps with the project.

---

## Abstract *

Curie Prediction Pipeline is a prototype streaming platform for real-time clinical deterioration alerting. It ingests FHIR-style clinical events (via Apache Kafka), scores indicators such as sepsis (SOFA-style) and AKI (KDIGO-style) in Apache Flink, and applies a shared **alert governance** layer (trajectory, baseline-relative scoring, suppression, deduplication, refractory windows, and acuity tiering) before surfacing alerts to a review API/dashboard.

The core research/engineering claim is not a novel bedside score, but **governed alerting**: reducing interruptive page volume while preserving detection of labeled events, relative to a naive threshold-only baseline. Offline evaluation uses the PhysioNet Computing in Cardiology Challenge 2019 archive (hourly ICU stays with `SepsisLabel`) and optional scoring against the open MIMIC-IV Clinical Database Demo. Full MIMIC-IV retrospective validation is planned and requires separate credentialed access.

This software is a prototype only: synthetic and public challenge/demo data, no real PHI in the default path, **not clinically validated**, not FDA-cleared, and not intended for patient care.

---

## Background *

Clinician alert fatigue remains a barrier to useful early-warning systems: raw threshold crossings on incomplete or noisy ICU streams generate high interruptive burden with limited actionable precision. Many systems focus on improving a single risk model; fewer treat **when and how to interrupt** as a first-class, reusable policy across indicators.

Curie explores a modular architecture where:

1. Versioned JSON **rule bundles** define deterministic scores (sepsis SOFA components; AKI creatinine staging).
2. A shared **governance** policy decides watch vs interruptive tiers and suppresses repeats.
3. Stream processing (Kafka + Flink) supports event-time replay suitable for both live demos and offline backtests.
4. Optional LLM narrative (Guarded Reasoning Pipeline) may explain an alert **after** it fires, but cannot create, suppress, or change scores.

Public PhysioNet resources (Challenge 2019; MIMIC family for future Stage B work) provide labeled or clinically realistic inputs for engineering evaluation. Related community tooling for MIMIC-derived concepts and ML prep includes [MIT-LCP/mimic-code](https://github.com/MIT-LCP/mimic-code/) and [healthylaife/MIMIC-IV-Data-Pipeline](https://github.com/healthylaife/MIMIC-IV-Data-Pipeline); see project docs `docs/mimic-data-sources.md`.

---

## Methods *

**Architecture.** Source adapters emit canonical JSON event envelopes to Kafka topics (`observations`, `conditions`, `medications`, `rules`). Flink jobs (`SofaJob`, `AkiJob`) maintain per-patient keyed state, apply broadcast rule bundles, compute scores with explicit missing-component handling, run governance filters, and publish to `alerts` (failures to `dlq`). A FastAPI service and static dashboard support alert review and acknowledge (demo store and/or future Kafka consumer).

**Governance.** Policies include persistence/trajectory gates, baseline-relative logic, context flags (encounter-scoped), dedup and refractory windows, and dual-lane routing (passive **watch** vs interruptive **urgent/critical**). Profiles (`strict`, `balanced`, `sensitive`, `accuracy`, `dual`) and frozen operating points are used for reproducible eval.

**Evaluation.**

- **Challenge 2019:** Adapter maps hourly stays to envelopes; runner compares naive vs governed alerts with detection sensitivity, interruptive reduction, NNA, and bootstrap CIs. Operating point tuned on `training_setA`, held out on `training_setB` (see `docs/challenge-2019-eval.md`).
- **MIMIC-IV demo:** Local open demo CSVs scored for plumbing (`make mimic-demo`) — not clinical validity.
- **Unit/integration:** Python pytest suite; Flink module tests; Synthea FHIR replay for E2E mechanical checks.

**Reproducibility.** Make targets (`challenge-2019`, `challenge-2019-sweep`, `up` / `up-full`) and frozen JSON configs under `eval/challenge2019/frozen/`.

---

## Data Description *

This project **does not redistribute** credentialed MIMIC-IV or other restricted PhysioNet files. Users obtain data from PhysioNet under applicable agreements.

| Resource | Role in Curie | Notes |
|---|---|---|
| [PhysioNet Challenge 2019](https://physionet.org/content/challenge-2019/) | Primary labeled sepsis alert eval | Place archive under `data/archive/` (gitignored) |
| [MIMIC-IV Clinical Database Demo](https://physionet.org/content/mimic-iv-demo/) | Optional open smoke scoring | `data/mimic-iv-demo/` or `CURIE_MIMIC_DEMO_DIR` |
| MIMIC-IV (full) | Planned Stage B | Credentialed; use with mimic-code concepts — not shipped here |
| Synthea-generated FHIR | Integration / replay only | Mechanical E2E; not clinical validation |

Derived eval artifacts (metrics JSON, frozen governance configs) may be included in the software repo; patient-level challenge/MIMIC extracts stay local.

---

## Usage Notes *

1. **Prototype only** — not for clinical decision-making or patient care.
2. Clone the repository; Python 3.11+, Docker (Kafka/Flink/Kafka UI), optional Java/Maven for Flink packaging.
3. Install: `pip install -e ".[dev]"` (add `[api]`, `[kafka]` as needed).
4. Infra: `make up` (Kafka, Flink, Kafka UI at http://localhost:8080) or `make up-full` (also API on :8000, rule seed, submit Sofa/AKI jobs).
5. Challenge eval (after placing the Challenge 2019 archive under `data/archive/`): `make challenge-2019` or `LIMIT=0 make challenge-2019`.
6. MIMIC demo: place open demo files, then `make mimic-demo`.
7. Dashboard demo uses an in-memory store with synthetic alerts unless a Kafka→API consumer is added; do not expose the API publicly (`allow_origins=["*"]` is for local prototype only).
8. Cite PhysioNet datasets you download separately; cite Curie as software when reporting engineering results. Clinical validity claims require completing the plan in `docs/clinical-validation.md`.

---

## Release Notes

**v0.1 (prototype)**

- Kafka + Flink vertical slice: SOFA sepsis and AKI jobs with shared Java/Python-aligned governance.
- Versioned rule bundles (`sepsis-sofa`, `aki-kdigo`).
- Challenge 2019 eval harness, dual-tier (watch vs interruptive) metrics, setA sweep → frozen setB operating point, detection-window robustness checks.
- Compose profile `full`: containerized API, rule publish, shaded JAR package/submit; Provectus Kafka UI on port 8080.
- Docs: challenge eval report, clinical validation plan, MIMIC data-source map (`docs/mimic-data-sources.md`).
- Explicit non-goals: no PHI default path, no FDA/SaMD clearance, LLM not on the alert-firing path.

---

## Acknowledgements *

We thank the PhysioNet / MIT Laboratory for Computational Physiology community for making critical-care research datasets and challenge archives publicly available under appropriate credentialing and data use agreements. Evaluation in this prototype relies on data obtained separately by the user from PhysioNet, including the [Early Prediction of Sepsis from Clinical Data — the PhysioNet Computing in Cardiology Challenge 2019](https://physionet.org/content/challenge-2019/) and, optionally, the [MIMIC-IV Clinical Database Demo](https://physionet.org/content/mimic-iv-demo/). Future planned work may use full [MIMIC-IV](https://physionet.org/content/mimiciv/) and community-derived concepts from [MIT-LCP/mimic-code](https://github.com/MIT-LCP/mimic-code/); multimodal MIMIC prep tooling such as [healthylaife/MIMIC-IV-Data-Pipeline](https://github.com/healthylaife/MIMIC-IV-Data-Pipeline) is acknowledged as related prior work.

Synthetic FHIR integration tests use [Synthea](https://synthetichealth.github.io/synthea/). Stream processing builds on Apache Kafka and Apache Flink. This software is an independent prototype and is not affiliated with or endorsed by PhysioNet, MIT-LCP, or the Challenge organizers.

*(Edit if you have institutional funding, mentors, or compute sponsors to name.)*

---

## Conflicts of Interest *

The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this software prototype.

This project is provided for research and engineering exploration only. It is not a commercial medical device, is not clinically validated, and is not intended for use in patient care. Any future commercialization, hospital partnership, or regulatory path would require updated conflict-of-interest disclosures.

*(If you or co-authors have equity, consulting, grants, or employment tied to alerting/CDS vendors, replace the first paragraph with an explicit disclosure.)*

---

## Access policy & license (PhysioNet UI)

**Recommended for this project**

| Field | Choose | Why |
|---|---|---|
| **Access policy** | **Open** | You are publishing **software / docs / eval configs**, not credentialed patient databases. Anyone following the license can use the files. |
| **License** | **Creative Commons Attribution 4.0 International (CC BY 4.0)** | Closest fit among the listed options for an open engineering project that must be attributed. Matches an open, attribution-required posture. |

**Do not pick**

| Option | Why not |
|---|---|
| Restricted / Credentialed / Contributor Review | Those are for sensitive **databases** (DUA + PhysioNet credentialing). Wrong unless you upload restricted MIMIC extracts (you should not). |
| Open Data Commons Attribution / ODbL | Aimed at **databases**, not application source code. |
| CC BY-NC-SA 4.0 | Blocks commercial reuse; awkward if Curie later becomes a product. |
| CC0 | Fine legally, but drops a clear attribution requirement; CC BY is safer for academic credit. |

**Note:** `pyproject.toml` declares **Apache-2.0** for the Python package. PhysioNet’s dropdown here is mostly **data** licenses. Prefer CC BY 4.0 on PhysioNet for the uploaded project files, and keep Apache-2.0 on GitHub/code; state in Usage Notes that the GitHub repo is Apache-2.0 if both apply. If PhysioNet later offers Apache-2.0 / MIT for software projects, switch the PhysioNet license to match the repo.

---

## Project Discovery (PhysioNet UI §4)

### Version *
```
0.1.0
```

### Short Description *
```
Prototype streaming clinical deterioration platform: Kafka + Flink scoring (SOFA sepsis, KDIGO AKI) with shared alert governance (trajectory, baseline, suppression, dedup, tiering). Evaluated offline on PhysioNet Challenge 2019; optional MIMIC-IV demo plumbing. Not clinically validated; not for patient care.
```

### Project Home Page
```
https://github.com/sreeram843/curie-prediction-pipeline
```

### Parent Projects
Link PhysioNet **projects this software uses for evaluation** (not GitHub tooling repos):

- `challenge-2019` — Early Prediction of Sepsis (CinC Challenge 2019) — primary labeled eval  
- `mimic-iv-demo` — MIMIC-IV Clinical Database Demo — optional smoke scoring  

*(If the UI is a search box, type those slugs/titles and select the official PhysioNet entries. Do **not** list mimic-code or MIMIC-IV-Data-Pipeline as parents unless they exist as PhysioNet projects you depend on for distributed files.)*

### Publication
Leave empty for now, or add later:

- None yet for Curie itself  
- Optional related citations (not Curie papers): Gupta et al. ML4H 2022 MIMIC-IV pipeline; Johnson et al. MIMIC Code Repository JAMIA 2018 — only if you want “related work” discoverability  

### Topics
Add with **+** (suggested tags):

- sepsis  
- alert-fatigue  
- clinical-decision-support  
- stream-processing  
- apache-flink  
- apache-kafka  
- sofa  
- aki  
- physionet-challenge-2019  
- mimic-iv  
- fhir  
- open-source  

Click **Save Information** when done.

---

## Ethics Statement * (PhysioNet UI §5)

Paste:

```
This project is a software and engineering evaluation prototype. It does not enroll human subjects, collect new clinical data, or deliver alerts in a care setting.

All patient-derived evaluation data are obtained by the user from PhysioNet under the applicable PhysioNet Credentialed Health Data Use Agreement and project-specific terms. Primary offline evaluation uses the publicly distributed PhysioNet Computing in Cardiology Challenge 2019 archive (deidentified ICU time series with sepsis labels). Optional plumbing checks may use the open MIMIC-IV Clinical Database Demo. Full MIMIC-IV or other credentialed databases are not redistributed with this project; any future use requires the user’s own PhysioNet access and compliance with those DUAs.

The Beth Israel Deaconess Medical Center (BIDMC) and MIT Institutional Review Boards approved the collection of MIMIC and related PhysioNet critical-care databases and waived the requirement for individual informed consent for secondary research use of the deidentified data, as described on the respective PhysioNet project pages. This software work performs only secondary analysis / system evaluation on those deidentified resources (or synthetic Synthea FHIR for integration tests) and does not constitute a clinical trial or clinical validation study.

This software is not intended for diagnosis, treatment, or clinical decision-making. No protected health information (PHI) is included in the default repository contents.
```

**Supporting Documents:** usually none required for this software-only project if you are not releasing restricted data. Upload only if PhysioNet editors ask (e.g. your signed DUA PDF) — those stay private to editorial staff.

Click **Save Ethics Statement** when done.
