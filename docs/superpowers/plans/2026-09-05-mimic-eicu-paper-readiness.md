# MIMIC/eICU Paper-Readiness Plan

**Date:** 2026-09-05  
**Branch:** `codex/review-fixes`  
**Status:** Planned; no full-cohort results are accepted by this plan until the gates below pass.

## Goal

Build a reproducible, completeness-aware analytical validation package for the Curie deterministic scoring and alert-governance prototype, then publish a methods/clinical-informatics paper with claims limited to the evidence actually frozen.

The workstreams requested in the review are:

- **A — Data completeness:** quantify missingness and partial-score coverage under a declared cohort and availability-time protocol.
- **B — Correctness:** make the adapters and deterministic replay semantically correct, especially medication units and time windows.
- **C — Infrastructure:** make full-cohort extraction, replay, labels, and comparisons scalable and reproducible.
- **D — Process/publication:** freeze code/data/config identities, maintain a claims ledger, and build the manuscript package.

The workstreams are named A–D, but the safe execution order is **B → C → A → D**. Measuring completeness or comparing outcomes before medication-unit correctness and scalable replay are fixed would create results that need to be discarded.

## Scope and claim boundary

The first MIMIC/eICU paper should be an analytical methods paper, not a clinical-validation paper. Until a separate clinical study exists, do not claim:

- clinical SOFA accuracy or superiority;
- improved patient outcomes, mortality prediction, or treatment benefit;
- clinical validation on MIMIC/eICU;
- FDA/SaMD readiness or production readiness;
- external validation from unlabeled dumps or demo data.

The permissible MIMIC claim is narrower: under the declared data-quality and replay protocol, the implementation’s deterministic SOFA/AKI inputs and governance behavior are characterized, and where a reference implementation is available, component/label concordance is reported. eICU is an external completeness and portability analysis unless a separately implemented and verified outcome-label protocol is completed.

The existing Challenge 2019 paper remains a separate result cohort. Do not merge its frozen setB governance claim with MIMIC/eICU results or describe MIMIC as a second confirmation of that claim.

## Current review reconciliation

### Already addressed on the current branch

- Full eICU path resolution uses `CURIE_EICU_DIR`/`EICU_DIR` rather than a personal fallback path.
- Unknown vasopressor dose is represented as `None`, with a test path for unknown dose.
- Shared completeness helpers no longer require `eval/` to be imported by ingestion code.
- Shared SpO₂/FiO₂/PaO₂ resolution exists in `ingestion/adapters/respiration.py`.
- Urine output is not treated as a complete 24-hour daily measurement before 24 hours have elapsed.
- CURIE-042 was restored and CURIE-045 is no longer presented as complete.

These changes still need to be included in the final validation run and frozen artifact hashes.

### Still open or untrusted

- MIMIC `rateuom` is not interpreted in `ingestion/adapters/mimic/extract.py`; the current code treats every numeric `rate` as if it were `mcg/kg/min`.
- Existing MIMIC “n=8000” completeness text must be re-run and reconciled with the actual input manifest. It is not publication evidence merely because it is present in a document.
- The full MIMIC/eICU path is not yet an indexed, stay-partitioned, measured end-to-end replay.
- MIMIC Sepsis-3/KDIGO reference labels and comparator versions are not yet frozen as a reproducible run artifact.
- There is no complete per-run bundle/config/data hash manifest tied to every reported table and figure.

## Phase B — Correctness blockers

### B1. Audit and normalize MIMIC vasopressor units

**Files:**

- `ingestion/adapters/mimic/extract.py`
- `ingestion/adapters/mimic/item_map.py`
- `ingestion/adapters/mimic/test_extract.py` or the existing MIMIC adapter test module
- add a focused module only if the conversion policy is large enough to deserve a deep interface, preferably `ingestion/adapters/mimic/vasopressors.py`

**Work:**

1. Add a read-only audit that reports the unique `rateuom` values, row counts, missing rates, and weight availability for mapped pressor rows before changing conversion behavior.
2. Define one typed conversion function with an explicit result (`dose_ug_kg_min`, `known`, `reason`, and source unit). Do not return a bare number for an unknown conversion.
3. Normalize only units that can be justified by the source schema:
   - `mcg/kg/min` → numeric rate unchanged;
   - `mcg/min` → divide by valid contemporaneous weight in kg;
   - `mg/kg/min` → multiply by 1000;
   - `mg/min` → multiply by 1000, then divide by valid weight;
   - `mL/hour` or other volume rates → unknown unless a documented concentration is available at the same event time;
   - missing, non-finite, zero/negative, or unsupported values → unknown with an explicit reason.
4. Resolve weight by a declared availability-time rule. Never use a future weight or silently substitute a population default.
5. Preserve the source unit, conversion reason, and evidence ID in the emitted metadata so a 3-versus-4 SOFA-point decision is auditable.
6. Keep the existing deterministic fallback for `on_vasopressors=True` with unknown dose; distinguish “pressor present, dose unknown” from “no pressor”.

**Tests:** supported units, case/spacing variants, missing unit, missing weight, future-only weight, volume rate without concentration, non-finite/negative input, dose boundary, overlapping agents, and unknown-dose SOFA fallback. Add golden fixtures and the matching Java test only if the normalized dose changes the shared scorer contract or Java receives the same dose field.

**Acceptance:** no mapped MIMIC pressor row is silently interpreted in the wrong unit; every unsupported conversion is explicit; Python tests cover the policy; parity remains green; a small audit report records the observed unit distribution.

### B2. Build a correctness matrix for all fixed review findings

**Files:**

- `eval/mimic_harness/replay.py`
- `ingestion/adapters/respiration.py`
- `ingestion/adapters/mimic/extract.py`
- `ingestion/adapters/eicu/convert.py`
- `eval/mimic_harness/test_harness.py`
- `ingestion/adapters/test_respiration.py`
- `eval/fixtures/golden/`

**Work:** create a single matrix covering availability time, missingness, partial scores, overlapping pressors, 24-hour urine eligibility, PaO₂/FiO₂ preference, SpO₂ fallback, ambient-air handling, and evidence IDs. Each row must identify the expected Python score/status and whether a Java parity fixture is required.

**Acceptance:** positive, negative, boundary, missing-input, and replay cases pass; no “missing” input becomes a reassuring normal value; changed frozen fixtures receive a new version rather than an in-place replacement.

### B3. Lock the semantic contract before scale work

**Files:**

- `docs/contracts/signal-contract.md`
- `docs/contracts/indicator-plugin-sdk.md`
- `docs/research/mimic-iv-study-protocol.md`
- `eval/mimic_study/frozen/protocol.v1.json`

**Work:** document the units and missingness semantics for each SOFA component, especially pressors, urine, FiO₂, PaO₂, and weight. Record which values are “not observed”, “observed but not convertible”, “not eligible yet”, and “not applicable”.

**Acceptance:** a reviewer can determine from the contract why a component is scored, partial, or missing without reading adapter internals.

## Phase C — Scalable, reproducible study infrastructure

### C1. Create an indexed local representation

**Files:**

- add `scripts/build_mimic_index.py` or an equivalent module under `eval/mimic_study/`
- add `scripts/validate_mimic_index.py`
- update `Makefile`
- update `docs/research/mimic-data-sources.md`
- update `.env.example`

**Work:** build a local, gitignored, reproducible representation partitioned or indexed by `stay_id` and event family. Pin the implementation dependency in the project’s optional study dependency group after checking the installed environment. The preferred format is Parquet with predicate pushdown; if the source environment cannot support that reliably, use a documented indexed alternative rather than repeatedly scanning compressed source files.

The index must retain source provenance, event time, availability/chart time, unit fields, and source row identity. It must not alter or overwrite the downloaded PhysioNet files.

**Acceptance:** a single-stay and a bounded multi-stay extraction produce identical rows from source and index; the validator checks row counts, stay coverage, timestamp parse failures, unit distributions, and source hashes; rerunning the build is deterministic.

### C2. Implement the full MIMIC adapter → replay path

**Files:**

- `ingestion/adapters/mimic/`
- `eval/mimic_harness/`
- `eval/mimic_study/study_replay.py`
- `eval/mimic_study/completeness_check.py`
- `eval/mimic_study/metrics.py`
- `Makefile`

**Work:** add a full-data command that consumes the indexed representation, applies the frozen cohort, replays in availability-time order, and writes per-stay/per-event metrics plus a run manifest. Keep the demo runner as a plumbing test; do not use it as MIMIC evidence.

The run must support bounded dry runs, then `LIMIT=0` full runs, without changing semantics. It must expose the chosen protocol ID, rule-bundle versions, split, cohort counts, event counts, missingness counts, and runtime/resource summary.

**Acceptance:** a 5-stay run, a bounded run, and a full run use the same code path; repeated runs with the same inputs/config produce the same hashes and metrics; no future event is visible at replay time.

### C3. Freeze label generation and reference comparators

**Files:**

- `eval/mimic_study/labels/` (new package if needed)
- `eval/mimic_study/comparators/` (new package if needed)
- `docs/research/mimic-iv-study-protocol.md`
- `eval/mimic_study/frozen/`
- `Makefile`

**Work:**

1. Pin the exact `mimic-code` revision or release used for MIMIC Sepsis-3 and AKI concepts.
2. Record source SQL/query files and their SHA-256 hashes in the run manifest.
3. Generate labels using only information available under the declared label policy; keep outcome/onset generation separate from feature replay.
4. Compare Curie component scores and onset events with the pinned reference implementation at the component, stay, and time-window levels.
5. Treat disagreement as an analysis result. Do not silently “correct” Curie to match the reference.

For eICU, stop at completeness/portability unless a defensible, reproducible label definition is implemented and verified. Do not imply eICU Sepsis-3 validation from raw tables alone.

**Acceptance:** every label row points to a versioned source definition; comparator output is reproducible; disagreement categories include unit, timing, missingness, mapping, and definition differences.

## Phase A — Evidence generation

### A1. Re-run cohort and completeness with a pre-specified protocol

**Files:**

- `eval/mimic_study/completeness_check.py`
- `eval/mimic_study/test_completeness_check.py`
- `eval/mimic_study/frozen/`
- `docs/research/mimic-iv-study-protocol.md`
- add `docs/research/eicu-study-protocol.md` if the eICU analysis is retained

**Work:** apply the declared adult/first-ICU/length rule and explicitly report comfort-care, ESRD, OR-transfer, missing-time, and incomplete-stay handling. Report denominators at each exclusion step. Run MIMIC first as the primary dataset and eICU as an external completeness/portability analysis.

Report, by split and dataset:

- cohort flow and stay counts;
- component observation and eligibility rates;
- complete versus partial SOFA coverage;
- unit-conversion success and unknown-dose rates;
- missingness by event time and first ICU day;
- source-to-index row reconciliation;
- runtime and peak storage for the indexed path.

**Acceptance:** all numbers are generated from the current input manifest, protocol ID, and code revision; no old “n=8000” text is reused without a matching manifest and rerun log; every table has a denominator.

### A2. Run concordance and governance analyses without retuning the holdout

**Files:**

- `eval/mimic_study/metrics.py`
- `eval/mimic_study/ablations.py`
- `eval/mimic_study/study.py`
- `eval/mimic_study/frozen/`
- `paper/tables/` (generated only)

**Work:** use development for tuning, calibration for operating-point selection, and the frozen temporal test split exactly as specified in `docs/research/mimic-iv-study-protocol.md`. Report:

- governed versus naive interruptive burden;
- sensitivity only for the declared derived label and window;
- alert/watch/page separation;
- component-level and stay-level reference concordance;
- partial versus complete score strata;
- pre-specified governance ablations;
- stay-level bootstrap confidence intervals with the protocol seed.

Do not call concordance “accuracy” unless a true reference standard and an appropriate unit of analysis are defined. Do not use the test split to choose thresholds, governance knobs, exclusions, or post hoc label rules.

**Acceptance:** the protocol guard rejects test-set tuning; every primary number can be traced to one run manifest and one frozen bundle/config hash; the manuscript tables are generated from JSON sidecars.

### A3. Robustness and sensitivity checks

**Files:**

- `eval/mimic_study/metrics.py`
- `eval/mimic_study/ablations.py`
- `eval/mimic_study/frozen/`
- `docs/research/mimic-iv-study-protocol.md`

Run only pre-specified analyses:

- urine grace/eligibility windows;
- detection windows of −12/0/+12 hours as applicable;
- partial-score handling;
- pressor unit-conversion exclusions versus explicit unknown-dose fallback;
- FiO₂/PaO₂ preference and SpO₂ fallback;
- cohort policy variants for ESRD, comfort care, and OR-transfer gaps;
- temporal split stability;
- 1000 stay-level bootstrap, seed 42.

The primary operating point remains locked. Sensitivity analyses explain fragility; they do not become new tuning opportunities.

**Acceptance:** ranking stability and effect direction are reported with uncertainty; any materially changed conclusion is promoted to a protocol decision before manuscript writing.

## Phase D — Governance, artifacts, and publication

### D1. Add a claims-and-evidence ledger

**Files:**

- add `docs/research/mimic-eicu-claims-ledger.md`
- `docs/research/clinical-validation.md`
- `docs/research/mimic-iv-study-protocol.md`
- `docs/research/challenge-2019-eval.md`

For each proposed sentence in the paper, record the dataset, split, metric, run ID, artifact path, code revision, and whether the sentence is an engineering characterization, analytical validation, or prohibited clinical claim. Mark unsupported legacy statements as unverified rather than deleting provenance.

**Acceptance:** an independent reviewer can identify the exact evidence for every Results sentence and can see which claims are explicitly out of scope.

### D2. Freeze reproducibility artifacts

**Files:**

- `eval/mimic_study/frozen/`
- `eval/challenge2019/frozen/`
- `eval/manuscript/frozen/`
- `eval/manuscript/generated/`
- `scripts/` and `Makefile`

Create a new version for each changed protocol, operating point, study manifest, and table/figure specification. Never replace an existing frozen artifact. Each study manifest must include:

- git commit and branch;
- source dataset release, extract date, and source-file hashes;
- index-builder version and index hash;
- cohort/protocol ID;
- label/comparator revision and hashes;
- rule-bundle IDs, versions, and content hashes;
- Python dependency lock/environment identity;
- random seed and bootstrap settings;
- command line and output hashes;
- PHI/sensitive-data handling check.

**Acceptance:** `make manuscript` and the MIMIC/eICU study commands rebuild the same generated tables/figures from the frozen sidecars, or fail with a clear identity mismatch.

### D3. Manuscript build

**Files:**

- `paper/` or the existing manuscript source location
- `docs/architecture.md`
- `eval/manuscript/`
- `Makefile`

Use this paper shape:

1. Introduction: alarm fatigue; score is not page; governance is the design unit.
2. System: Kafka/Flink, versioned bundles, and LLM off the alert path; one architecture figure.
3. Methods: source data, adapter, Curie SOFA/AKI, naive/governed/interruptive paths, availability-time replay, protocol and hashes.
4. Results: cohort flow, completeness, concordance, governance burden, timing, ablations, and robustness.
5. Limitations: proxy/reference definitions, partial SOFA, missingness, single-center or public-dataset constraints, no clinical validation.
6. Reproducibility: commands, versions, frozen artifacts, and data-access restrictions.

The paper must state that credentialed datasets cannot be redistributed and that all reported data-derived artifacts are aggregate/non-sensitive. Demo data, synthetic data, and unlabeled coverage checks belong in plumbing or appendix context, not as outcome evidence.

### D4. Publication gate

Before submission, require all of the following:

- B1 unit audit and conversion tests pass;
- Python parity and Java tests pass for all affected scoring paths;
- indexed-source reconciliation passes;
- full MIMIC primary run completes with a frozen manifest;
- eICU analysis is explicitly labeled completeness/portability or has its own verified label protocol;
- no test-set retuning or frozen-artifact replacement occurred;
- all manuscript tables/figures rebuild from sidecars;
- claims ledger has no unsupported clinical language;
- `pytest -q`, `ruff check .`, `git diff --check`, parity, and Maven tests are recorded, with Docker-dependent failures documented rather than hidden;
- a second reviewer can reproduce the bounded run and inspect the full-run manifest.

## Recommended execution sequence

| Order | Work | Exit condition |
|---|---|---|
| 1 | B1/B2: pressor units and correctness matrix | No silent unit assumptions; focused tests and parity pass |
| 2 | C1/C2: indexed source and full availability-time replay | Bounded/source reconciliation and deterministic rerun pass |
| 3 | C3: pinned MIMIC labels and comparators | Label/query/code hashes are in a run manifest |
| 4 | A1: MIMIC completeness and cohort flow | All denominators and missingness results are regenerated |
| 5 | A2/A3: concordance, governance, and robustness | Primary and pre-specified secondary results are frozen |
| 6 | D1/D2: claims ledger and artifact freeze | Every result maps to a frozen artifact |
| 7 | D3/D4: manuscript and reproducibility gate | Paper builds cleanly and claims stay within evidence |

## First three implementation tasks

1. Add the MIMIC `rateuom` audit and unit-normalization tests before touching any full-cohort result.
2. Implement the typed pressor conversion policy, including weight availability and explicit unknown reasons; update the MIMIC adapter output and fixtures.
3. Add the indexed bounded-run command and source/index reconciliation check, then use it to rerun the 5-stay smoke before scaling to the full cohort.

Only after those three tasks pass should the existing completeness numbers be considered candidates for regeneration. The paper should be drafted from the regenerated frozen package, not from current narrative docs.
