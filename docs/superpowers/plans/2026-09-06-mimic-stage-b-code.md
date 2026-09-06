# MIMIC/eICU Stage B Code Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the repository-side infrastructure needed to run a reproducible MIMIC-IV/eICU Stage B study without fabricating external-data results.

**Architecture:** Keep the frozen v1 demo study immutable. Add a v2 protocol that assigns MIMIC stays by `anchor_year_group`, then connect separately materialized, pinned label artifacts to the existing Parquet index and availability-time replay. Operating-point and run manifests will be generated only from supplied development/calibration/test outputs and will record hashes and protocol identity.

**Tech Stack:** Python 3.11+, Pydantic/dataclasses already used by the repository, pytest, Ruff, JSON/CSV, optional PyArrow index, and external PostgreSQL/BigQuery execution supplied by the operator.

**Spec:** User-provided Stage B publication roadmap in the current conversation; existing readiness plan at `docs/superpowers/plans/2026-09-05-mimic-eicu-paper-readiness.md`.

## Global Constraints

- Prototype only; no clinical validation, diagnosis, mortality, treatment, FDA, or production claims.
- Do not edit or replace `eval/mimic_study/frozen/protocol.v1.json`, `operating_point.v1.json`, or `study_manifest.v1.json`.
- Do not read, write, or commit PhysioNet extracts under `data/`.
- Labels remain separate from feature replay and are never placed on the alert path.
- Replay orders observations by availability time and fails closed on future evidence.
- A Stage B command must fail clearly when the required external label artifact or index is absent.
- No protocol selection, threshold tuning, or operating-point selection may run on the test split.
- Generated v2 artifacts are written only when supplied inputs and hashes validate; no synthetic full-cohort result is accepted as publication evidence.

---

### Task 1: Freeze protocol v2 and anchor-year-group split assignment

**Files:**
- Create: `eval/mimic_study/frozen/protocol.v2.json`
- Modify: `eval/mimic_study/protocol.py`
- Modify: `eval/mimic_study/cohort_flow.py`
- Test: `eval/mimic_study/test_protocol.py`
- Test: `eval/mimic_study/test_cohort_flow.py`

**Interfaces:**
- `load_protocol(path=None, version=None) -> dict[str, Any]` preserves v1 as the historical default while accepting explicit v1/v2 paths; Stage B callers pass `version="v2"`.
- `split_for_anchor_year_group(anchor_year_group: str, protocol: dict[str, Any] | None = None) -> str` returns `development`, `calibration`, `test`, or `outside_protocol`.
- `apply_cohort(root: Path, *, protocol: dict[str, Any] | None = None) -> dict[str, Any]` records the protocol ID and v2 split assignment without changing inclusion/exclusion denominators.

- [ ] Write failing tests proving v2 uses `2008 - 2010` and `2011 - 2013` for development, `2014 - 2016` for calibration, `2017 - 2019` for test, and rejects unknown groups.
- [ ] Run the protocol/cohort tests and verify the failure is caused by missing v2 support.
- [ ] Add the v2 JSON by copying the v1 study definitions and changing only protocol identity, anchor-year-group split rules, and v2 output artifact paths.
- [ ] Update protocol loading and cohort assignment; retain an explicit v1 path for historical fixture tests.
- [ ] Run the same tests green and commit RED/GREEN checkpoints separately.

### Task 2: Correct label-source paths and materialize immutable label artifacts

**Files:**
- Modify: `eval/mimic_study/labels/sources.json`
- Modify: `eval/mimic_study/labels/__init__.py`
- Modify: `eval/mimic_study/labels/pins.py`
- Create: `eval/mimic_study/labels/materialize.py`
- Create: `scripts/materialize_mimic_labels.py`
- Test: `eval/mimic_study/test_labels.py`

**Interfaces:**
- `build_label_artifact(*, sepsis_rows: Iterable[dict[str, Any]], kdigo_rows: Iterable[dict[str, Any]], protocol_id: str, dataset_pin: dict[str, Any], source_pin: dict[str, Any]) -> dict[str, Any]` produces deterministic, per-stay labels with source provenance and `content_hash`.
- `write_label_artifact(artifact: dict[str, Any], output: Path) -> Path` validates and writes one canonical JSON artifact.
- CLI: `python scripts/materialize_mimic_labels.py --sepsis3-csv ... --kdigo-csv ... --source-pin ... --protocol-id ... --dataset-version ... --out ...`.

- [ ] Write failing tests for corrected six-file source paths, missing source pin rejection, deterministic row ordering/hash, duplicate stay consolidation, earliest positive sepsis onset, maximum KDIGO stage, and malformed timestamps.
- [ ] Run the label tests to establish RED.
- [ ] Update the six remote paths to `concepts_postgres/sepsis`, `organfailure`, and `score`; include all six definitions in the pin registry.
- [ ] Implement CSV/JSON row loading and strict materialization. Sepsis labels use the earliest row with `sepsis3` truthy and `sofa_time`/`suspected_infection_time`; KDIGO labels use the maximum valid stage and earliest stage-onset time.
- [ ] Keep label generation execution-neutral: the operator runs pinned SQL in PostgreSQL/BigQuery and supplies exports; the script does not invent credentials or execute untrusted SQL.
- [ ] Run tests green and commit RED/GREEN checkpoints separately.

### Task 3: Attach v2 labels and protocol splits to indexed replay

**Files:**
- Modify: `eval/mimic_study/index_replay.py`
- Modify: `eval/mimic_study/manifest.py`
- Modify: `eval/mimic_study/study_replay.py`
- Test: `eval/mimic_study/test_index_replay.py`
- Test: `eval/mimic_study/test_manifest.py`

**Interfaces:**
- `load_label_artifact(path: Path) -> dict[str, dict[str, Any]]` validates the artifact hash and returns labels keyed by `stay_id`.
- `replay_indexed_stays(..., labels_path: Path | None = None, protocol: dict[str, Any] | None = None) -> dict[str, Any]` attaches labels and assigns v2 split IDs before replay.
- `build_run_manifest(..., labels_path: Path | None = None, protocol_id: str | None = None) -> dict[str, Any]` records label artifact hash/status and protocol identity.
- CLI adds `--labels` and `--protocol-version`; absent labels are allowed only for explicitly unlabeled completeness runs and are marked `labels.status = "not_supplied"`.

- [ ] Write failing tests proving valid labels attach to the correct stay, tampered labels fail closed, missing labels are explicitly marked, and a v2 protocol assigns the expected split.
- [ ] Run the focused replay/manifest tests to establish RED.
- [ ] Implement label loading, protocol-aware split assignment, and manifest provenance without importing label code into the feature-only replay module boundary beyond the explicit artifact loader.
- [ ] Run tests green and commit RED/GREEN checkpoints separately.

### Task 4: Make study selection and v2 artifact generation data-source agnostic

**Files:**
- Modify: `eval/mimic_study/study.py`
- Modify: `eval/mimic_study/metrics.py`
- Modify: `eval/mimic_study/ablations.py`
- Test: `eval/mimic_study/test_study.py`
- Test: `eval/mimic_study/test_paper_scaffolding.py`

**Interfaces:**
- `run_study_rows(stays: list[dict[str, Any]], *, protocol: dict[str, Any], write_frozen: bool, frozen_dir: Path, study_version: str) -> dict[str, Any]` runs development sweep, calibration selection, locked test evaluation, and pre-specified ablations over indexed replay rows.
- `select_operating_point(..., protocol=...)` must read the protocol’s v2 success rule and output `operating_point.v2.json` only when explicitly requested.
- Metrics must preserve stay-level sensitivity, burden, NNA, lead time, false episodes, and bootstrap-ready row data without adding clinical claims.

- [ ] Write failing tests proving v2 output paths and protocol IDs propagate, test selection is rejected, and empty/missing-label rows do not become positives.
- [ ] Run study tests to establish RED.
- [ ] Add protocol/path parameters and preserve v1 defaults for demo compatibility; do not change frozen v1 results.
- [ ] Run tests green and commit RED/GREEN checkpoints separately.

### Task 5: Wire reproducible Stage B commands and documentation

**Files:**
- Modify: `Makefile`
- Modify: `.env.example`
- Modify: `docs/research/mimic-iv-study-protocol.md`
- Modify: `docs/research/mimic-eicu-claims-ledger.md`
- Create: `docs/testing/mimic-stage-b-code.tdd.md`
- Test: `eval/mimic_study/test_protocol.py`

**Interfaces:**
- `make mimic-labels` invokes the label materializer with explicit input/output paths and never overwrites frozen artifacts.
- `make mimic-study-v2` invokes indexed replay/study code with `PROTOCOL_VERSION=2`, external index, and label artifact paths.
- Documentation states that full-cohort execution requires credentialed data and that eICU remains portability/completeness-only.

- [ ] Write failing command/help tests for the new targets and explicit protocol version.
- [ ] Implement the minimal Makefile/environment wiring and documentation links.
- [ ] Run targeted tests, full Python tests, parity, Ruff on changed files, diff checks, and local Maven tests.
- [ ] Record actual RED/GREEN and final validation output in the TDD evidence report.
- [ ] Commit the final code/documentation changes and leave `main` clean.

## Explicit non-goals

- This implementation does not download PhysioNet data, execute BigQuery/PostgreSQL, or create a full-cohort result.
- This implementation does not freeze a fabricated operating point, label output, or study manifest; those are generated only after the operator supplies and hashes the external data/results.
- Epic Clarity/Caboodle identifiers remain site-specific integration work.
