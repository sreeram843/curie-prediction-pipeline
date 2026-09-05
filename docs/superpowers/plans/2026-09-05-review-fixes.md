# Review Fixes Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with tests before implementation and preserve the existing dirty worktree changes.

**Goal:** Remove the review-identified correctness and layering defects while preserving deterministic scoring, provenance, and Python/Java parity.

**Architecture:** Keep dataset-specific file discovery in adapters, move shared cohort logic into a neutral ingestion module, and centralize respiration pairing behind one pure resolver. Keep replay state event-time/availability-time safe, with explicit unknown values rather than sentinels. Documentation will distinguish preview evidence from completed holdout-scale evidence.

**Tech Stack:** Python 3.11+, pytest, Ruff, existing demo-schema replay harness, existing Java/Flink parity tests.

**Spec:** Review findings supplied in the current task and repository `AGENTS.md`.

## Global Constraints

- Prototype only; never describe this work as clinical validation, production-ready, FDA-cleared, or a diagnosis system.
- The LLM remains downstream of deterministic alerts and cannot create, suppress, or alter a score or route.
- Missing data stays explicit; unknown vasopressor dose is `None`, never a reassuring numeric sentinel.
- Frozen artifacts are not edited in place.
- Existing uncommitted user changes are preserved; only review-fix hunks are changed.

---

### Task 1: Neutral cohort helpers and credentialed eICU paths

**Files:**
- Create: `ingestion/completeness.py`
- Modify: `ingestion/adapters/eicu/paths.py`
- Modify: `ingestion/adapters/eicu/convert.py`
- Modify: `ingestion/adapters/mimic/to_demo_schema.py`
- Modify: `eval/mimic_study/completeness_check.py`
- Test: `eval/mimic_study/test_completeness_check.py`

**Interfaces:**
- `ingestion.completeness` owns `seeded_sample`, eICU/MIMIC protocol filters, and sample loaders.
- `eicu_dir()` reads `CURIE_EICU_DIR` or `EICU_DIR` and has no personal-path fallback; `require_eicu_dir()` validates full credentialed files.
- Evaluation code imports the neutral helpers for compatibility; ingestion never imports evaluation code.

- [ ] Add tests proving full eICU path resolution requires an environment variable and validates required files.
- [ ] Move shared cohort functions to `ingestion/completeness.py` and preserve evaluation-module imports as compatibility re-exports.
- [ ] Replace the conversion module’s evaluation import and hardcoded path usage with neutral helpers and `require_eicu_dir()`.
- [ ] Change unknown eICU vasopressor emission from `0.0` to `None` and update the MIMIC demo adapter similarly.
- [ ] Run the focused cohort, adapter, and import-direction tests.

### Task 2: Explicit vasopressor state and regression tests

**Files:**
- Modify: `eval/mimic_harness/replay.py`
- Modify: `ingestion/adapters/eicu/convert.py`
- Modify: `ingestion/adapters/mimic/extract.py`
- Modify: `eval/mimic_harness/test_harness.py`
- Test: `ingestion/adapters/eicu/test_eicu.py`

**Interfaces:**
- `VasopressorState` exposes `agent`, `dose`, `evidence_id`, and `on_pressor` for replay decisions.
- `_active_vasopressor()` returns `VasopressorState`; adapter parsing uses a named parsed representation where unit metadata is required.

- [ ] Add a failing unknown-dose test asserting `vaso_dose_known` is false and SOFA uses the unknown-dose pressor band.
- [ ] Replace tuple unpacking at replay and adapter parsing seams with named dataclasses.
- [ ] Fix the duplicated keyword-only marker in `replay.py` if still present.
- [ ] Run harness and eICU adapter tests.

### Task 3: Shared respiration resolution

**Files:**
- Create: `ingestion/adapters/respiration.py`
- Modify: `eval/mimic_harness/replay.py`
- Modify: `ingestion/adapters/mimic/extract.py`
- Modify: `ingestion/adapters/syn_icu/convert.py`
- Test: `eval/mimic_harness/test_harness.py`
- Test: `ingestion/adapters/syn_icu/test_syn_icu.py`

**Interfaces:**
- `resolve_spo2_fio2_pao2(...)` is a pure helper that selects PaO2 before SpO2, requires valid FiO2, enforces the shared lookback, and returns selected values plus evidence IDs.
- All three adapters/replay paths use the same selection and pairing rules.

- [ ] Add focused tests for PaO2 preference, SpO2 fallback, no-FiO2 abstention, and lookback boundaries.
- [ ] Implement the helper with a small result dataclass and migrate the three call sites.
- [ ] Run respiration adapter, replay, and parity tests.

### Task 4: Full 24-hour urine availability and documentation status

**Files:**
- Modify: `eval/mimic_harness/replay.py`
- Modify: `eval/mimic_harness/test_harness.py`
- Modify: `eval/mimic_study/completeness_check.py`
- Modify: `docs/implementation-backlog.md`
- Create: `docs/testing/review-fixes.tdd.md`

- [ ] Add a failing replay test proving urine output before 24 hours remains missing and becomes eligible at 24 hours.
- [ ] Track stay start in replay state and gate the rolling urine total until a full 24 hours has elapsed.
- [ ] Correct the eICU age docstring from 90 to 89.
- [ ] Restore CURIE-042, mark CURIE-045 `P0 · IN PROGRESS`, label n=500 as preview, and keep PaO2/FiO2 work in its own explicit CURIE-050 entry.
- [ ] Run focused tests, lint, diff checks, and the available full/parity/Flink gates; record only actual results in the TDD evidence report.

