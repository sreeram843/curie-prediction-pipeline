# Streaming Review Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make delayed clinical data, Sepsis-3 baseline handling, late governance, FHIR blood-pressure mapping, and eICU respiratory-support extraction explicit and testable across the Python and Java runtimes.

**Architecture:** Keep clinical occurrence time separate from the availability/evaluation clock. Flink buffers and watermarks use the availability clock, while state freshness and value ordering use clinical time. Late governance remains fail-closed by default, with an explicit opt-in passive correction lane that never mutates trajectory state. Adapter derivations are accepted only when source evidence is explicit and temporally pairable.

**Tech Stack:** Python 3.11+, Pydantic, pytest, Ruff, Java 17, Apache Flink, Maven, Jackson.

**Spec:** User-provided follow-up streaming-engine review in the current conversation; repository contracts in `docs/contracts/`, `AGENTS.md`, and the existing rule bundles.

## Global Constraints

- Prototype only; no clinical validation, diagnosis, mortality, treatment, FDA, or production claims.
- LLM/GRP remains off the alert path and cannot create, suppress, or modify deterministic scores.
- Missing data fails closed with explicit missing fields; no silent normal imputation.
- Python and Java behavior must remain in parity where both runtimes implement the behavior.
- Frozen artifacts are never edited in place; new behavior receives new fixtures or sidecars.
- Every scorer or governance change has positive, negative, boundary, missing-data, and replay tests.
- Epic FLO/MAR identifiers are not invented; site-specific mappings remain an integration dependency.

---

### Task 1: Availability-aware streaming clocks

**Files:**
- Modify: `streaming/flink-jobs/sofa/src/main/java/com/curie/sofa/model/CanonicalEvent.java`
- Modify: `streaming/flink-jobs/sofa/src/main/java/com/curie/sofa/SofaJob.java`
- Modify: `streaming/flink-jobs/sofa/src/main/java/com/curie/sofa/aki/AkiJob.java`
- Modify: `streaming/flink-jobs/sofa/src/main/java/com/curie/sofa/operators/SofaAlertFunction.java`
- Modify: `streaming/flink-jobs/sofa/src/main/java/com/curie/sofa/aki/AkiAlertFunction.java`
- Modify: `eval/sofa/stream_scorer.py`
- Test: `streaming/flink-jobs/sofa/src/test/java/com/curie/sofa/state/EventTimeBufferTest.java`
- Test: `streaming/flink-jobs/sofa/src/test/java/com/curie/sofa/operators/SofaAlertFunctionTest.java`
- Test: `eval/sofa/test_stream_scorer.py`

**Interfaces:**
- Add `availability_time` to Java `CanonicalEvent`, preserving fallback order `availability_time → ingest_time → event_time`.
- Add `SofaAlertFunction.effectiveAvailabilityTimeMs(CanonicalEvent)` as the shared Java clock selector.
- Make Flink watermark assignment, timer registration, and `EventTimeBuffer.offer` use the effective availability clock.
- Apply feature values using clinical `event_time`; evaluate and emit alerts using the availability clock, retaining the clinical time in a `clinical_event_time` alert field.
- Mirror the same distinction in the Python reference scorer: `PatientState.apply` receives clinical time and `compute_sofa_score` receives effective availability time.

- [x] Add a regression event with clinical time 09:00 and availability time 10:00 after a vital at 09:55; assert the lab is not DLQ'd and the emitted evaluation time is 10:00.
- [x] Add invalid-availability and missing-availability tests proving fallback behavior and fail-closed timestamp handling.
- [x] Run the targeted Python and Maven tests and confirm the existing event-time ordering tests remain green.
- [x] Commit the RED and GREEN checkpoints separately.

### Task 2: Explicit Sepsis-3 baseline policy

**Files:**
- Modify: `eval/sepsis3/phenotype.py`
- Test: `eval/sepsis3/test_phenotype.py`
- Modify: `docs/contracts/signal-contract.md`

**Interfaces:**
- Add `baseline_policy: Literal["require_explicit", "assume_zero_if_no_known_dysfunction"]` with default `require_explicit`.
- Add `no_known_preexisting_dysfunction: bool` and `baseline_source: str | None` to `Sepsis3Input`.
- When policy is `assume_zero_if_no_known_dysfunction` and the explicit no-dysfunction flag is true, evaluate with baseline 0 and record `baseline_assumed_zero` plus a provenance entry.
- Otherwise preserve the current `insufficient_data` result for a missing baseline.

- [x] Test explicit baseline, missing baseline under strict policy, authorized zero baseline, and missing authorization.
- [x] Test that chronic dysfunction with no acute rise remains `not_met`.
- [x] Run phenotype and signal-contract tests.
- [x] Commit RED and GREEN checkpoints separately.

### Task 3: Late governance correction lane

**Files:**
- Modify: `eval/replay_harness/governance.py`
- Modify: `streaming/flink-jobs/governance/src/main/java/com/curie/governance/GovernancePolicy.java`
- Modify: `streaming/flink-jobs/sofa/src/main/java/com/curie/sofa/operators/GovernanceFilterFunction.java`
- Modify: `streaming/flink-jobs/sofa/src/main/java/com/curie/sofa/model/AlertEvent.java`
- Test: `eval/replay_harness/test_governance.py`
- Test: `streaming/flink-jobs/governance/src/test/java/com/curie/governance/GovernancePolicyTest.java`

**Interfaces:**
- Add `late_event_policy: Literal["suppress", "passive_correction"]` to Python and Java governance config, defaulting to `suppress` to preserve frozen behavior.
- For `passive_correction`, emit the late alert as `routing="passive"`, mark `late_correction=true`, return reason `late_correction`, and do not mutate trajectory, baseline, refractory, or component-delta state.
- For `suppress`, preserve the current `late_out_of_order` suppression and state immutability.
- Add the rule-bundle governance field with default suppression and wire it through Java bundle parsing without changing existing frozen bundle files.

- [x] Test both policies, including assertions that the correction lane cannot produce an interruptive page and cannot alter subsequent trajectory decisions.
- [x] Add matching Python/Java governance tests for both policy values; these configuration-only cases do not alter frozen scorer fixtures.
- [x] Run governance parity and Maven tests.
- [x] Commit RED and GREEN checkpoints separately.

### Task 4: Remaining evidence-backed adapter mappings

**Files:**
- Modify: `streaming/flink-jobs/sofa/src/main/java/com/curie/sofa/fhir/FhirSofaMapper.java`
- Modify: `ingestion/adapters/eicu/convert.py`
- Test: `streaming/flink-jobs/sofa/src/test/java/com/curie/sofa/fhir/FhirSofaMapperTest.java`
- Test: `ingestion/adapters/eicu/test_eicu.py`

**Interfaces:**
- Map FHIR blood-pressure panel `85354-9` only when SBP `8480-6` and DBP `8462-4` components occur in the same Observation; derive MAP `(SBP + 2*DBP)/3` with evidence from the panel.
- Reject invalid/non-pairable values and retain the existing direct MAP path.
- Parse eICU respiratory-charting support labels into explicit invasive-ventilation evidence only for unambiguous values such as invasive ventilation, ventilator, intubated, or ETT; map room air, nasal cannula, masks, and high-flow as non-invasive/false evidence, never as invasive ventilation.
- Do not infer ventilation from FiO2 alone and do not invent site-specific Epic mappings.

- [x] Add positive, negative, malformed, and missing-component fixtures for the FHIR BP panel.
- [x] Add eICU ventilation-label tests and ensure unknown labels remain missing rather than false.
- [x] Run adapter tests, Python parity, and Maven tests.
- [x] Commit RED and GREEN checkpoints separately.

### Final verification

- [x] Run `.venv/bin/pytest -q` (`532 passed`, 5 dependency/framework deprecation warnings).
- [x] Run `.venv/bin/ruff check .` and record any unrelated pre-existing finding; it reports only existing findings in `eval/manuscript/make_figures.py`, while changed files pass.
- [x] Run `git diff --check`.
- [x] Run `python -m eval.parity.gate` (`PARITY_OK=true fixtures=43 mismatches=0`).
- [x] Run `mvn -B -q test` in `streaming/flink-jobs`; Docker wrapper remains an environment limitation.
- [x] Update the review-fixes TDD evidence and relevant contracts without changing frozen study artifacts.
- [x] Commit the final implementation and report remaining integration-only gaps.

## Completion notes

- RED/GREEN checkpoints were committed separately for each implementation area.
- The remaining MIMIC-IV full-study execution and Epic Clarity/Caboodle mappings are integration
  work: they require the external dataset/DUA and hospital-specific identifiers, so no synthetic
  IDs or unsupported clinical claims were added here.
