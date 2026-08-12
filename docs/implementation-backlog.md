# Implementation backlog: research-grade deterministic prototype

**Status:** Active  
**Primary objective:** Make Curie reproducible, clinically defensible, and ready for a locked
MIMIC-IV evaluation before expanding the product surface.

This is the working engineering backlog. The clinical study design remains in
[`clinical-validation.md`](clinical-validation.md).

## How to use this backlog

- Complete tasks in milestone order unless a task explicitly says it can run in parallel.
- Use one task per branch/PR where practical and include the task ID in the branch or PR title.
- Do not tune thresholds on Challenge 2019 `training_setB`; it has already been inspected.
- Never replace a frozen study artifact in place. Create a new version and retain its hash.
- Mark a task complete only after its acceptance criteria and verification commands pass.
- Every clinical-rule change needs Python tests, Java tests when applicable, and a replay result.

## Definition of done for every code task

- [ ] Behavior is covered by positive, negative, boundary, missing-data, and replay tests.
- [ ] Python and Java behavior match when both runtimes implement the feature.
- [ ] Rule/config versions and output provenance are explicit.
- [ ] `pytest -q`, `ruff check .`, `git diff --check`, and relevant Maven tests pass.
- [ ] Documentation and benchmark claims are updated without overstating clinical validity.

---

## Milestone 0 — Benchmark integrity and determinism

These tasks block publication claims, MIMIC threshold tuning, and additional indicators.

### CURIE-001 — Materialize a reproducible Challenge operating point [P0]

**Objective:** Ensure the evaluated artifact can be loaded unchanged by replay and runtime code.

**Work**

- Generate a fully resolved, immutable rule bundle from
  `eval/challenge2019/frozen/p1_setA_winner.json`, including score, alert, governance, page-gate,
  and missing-data settings.
- Keep the general product bundle separate from the study-specific resolved artifact.
- Store the resolved artifact's SHA-256 in every evaluation report.
- Remove or qualify any statement that `sepsis-sofa.v0.3.0` exactly matches the frozen study
  configuration unless all fields match, including `min_components_required`.
- Add a test that fails when the resolved study artifact drifts from its recorded hash.

**Likely files**

- `eval/challenge2019/frozen/`
- `eval/challenge2019/runner.py`
- `eval/replay_harness/gov_profiles.py`
- `streaming/rule-registry/bundles/`
- `docs/challenge-2019-eval.md`

**Acceptance criteria**

- [x] The resolved study bundle uses `min_components_required=2` as recorded by the frozen run.
- [x] A report identifies both the bundle version and content hash.
- [x] Loading the resolved artifact needs no implicit profile override.
- [x] Product and study configurations cannot be confused in API or report output.

### CURIE-002 — Require explicit semantic rule versions [P0]

**Objective:** Eliminate silent or lexicographically incorrect "latest bundle" selection.

**Work**

- Parse versions with semantic-version ordering instead of filename sorting.
- Require an explicit version in production/runtime entry points.
- If development code supports `latest`, resolve it through a versioned activation manifest.
- Reject duplicate versions, invalid versions, unknown schemas, and version rollback unless an
  explicit rollback command is used.
- Add tests covering `0.9.0` versus `0.10.0` and an invalid bundle.

**Likely files**

- `eval/indicators/registry.py`
- `scripts/publish_rules.sh`
- `streaming/rule-registry/`
- Flink rule-broadcast handlers

**Acceptance criteria**

- [x] No evaluation or runtime silently selects a bundle by lexical filename order.
- [x] Every alert contains the exact rule version and bundle hash.
- [x] An older broadcast cannot accidentally replace an active newer version.

### CURIE-003 — Correct alert metrics and naming [P0]

**Objective:** Make every reported metric mathematically correct and unambiguous.

**Work**

- Change interruptive NNA to `interruptive_alerts / interruptive_tp`.
- If the existing governed-TP denominator is useful, retain it under a different explicit name.
- Distinguish event-level PPV, episode-level PPV, and stay-level PPV.
- Report raw numerator and denominator beside every ratio.
- Add regression tests for zero-alert and zero-true-positive cohorts.

**Likely files**

- `eval/challenge2019/bootstrap.py`
- `eval/challenge2019/runner.py`
- `eval/challenge2019/test_utility.py`
- `docs/challenge-2019-eval.md`

**Acceptance criteria**

- [x] The current set-B page NNA is approximately `41158 / 437 = 94.2`.
- [x] Metric labels state their unit of analysis.
- [x] Bootstrap output uses the corrected metric.

### CURIE-004 — Make bounded time-to-onset metrics primary [P0]

**Objective:** Stop counting arbitrarily early first alerts as successful detection.

**Work**

- Define configurable windows such as `[-12h, +6h]` relative to label start.
- Calculate detection from any alert in the window, not only an unbounded first alert.
- Keep the official Challenge utility as a co-primary Challenge metric.
- Report too-early, in-window, late, and missed cases separately.
- Retain the old grace metric only as a labeled legacy/sensitivity analysis.

**Acceptance criteria**

- [ ] The report clearly states that Challenge labels begin six hours before clinical onset.
- [ ] No primary metric rewards an alert with unlimited early lead time.
- [ ] Timing definitions are frozen before MIMIC holdout evaluation.

### CURIE-005 — Complete Python/Java governance configuration parity [P0]

**Objective:** Ensure every runtime consumes the same bundle fields and defaults.

**Work**

- Extend `governance_config_from_bundle` to include page gates, baseline lookback, resolution gap,
  and any remaining Java-supported fields.
- Remove hard-coded replay overrides unless the scenario explicitly declares them.
- Include `positive_components` in AKI and SOFA replay alerts when page gates use it.
- Build one shared parity fixture containing all governance fields.

**Likely files**

- `eval/indicators/registry.py`
- `eval/replay_harness/runner.py`
- `eval/replay_harness/aki_runner.py`
- `streaming/flink-jobs/sofa/src/main/java/com/curie/sofa/operators/GovernanceFilterFunction.java`

**Acceptance criteria**

- [x] Python and Java derive identical governance configs from the same JSON.
- [x] AKI and SOFA replays exercise v0.3 page gates by default.
- [x] Missing bundle fields have documented, identical defaults.

### CURIE-006 — Implement deterministic event-time ordering [P0]

**Objective:** Make outputs a deterministic function of the allowed input event set, independent
of Kafka arrival order.

**Work**

- Buffer per-patient events until the event-time watermark or another documented close condition.
- Sort by event time and a stable tie-breaker such as idempotency key/resource ID.
- Define allowed lateness and route events beyond it to a late-data audit/DLQ path.
- Decide whether late corrections retract/recompute prior alerts or affect future state only.
- Apply the policy before both feature-state mutation and governance-state mutation.
- Add permutation, duplicate, restart, equal-timestamp, and encounter-transition tests.

**Acceptance criteria**

- [x] All permutations within allowed lateness produce byte-equivalent normalized alerts.
- [x] Events beyond allowed lateness have a deterministic disposition and reason.
- [x] Restart/replay produces the same state and outputs as uninterrupted processing.

### CURIE-007 — Add a cross-runtime parity gate to CI [P0]

**Objective:** Prevent Python reference behavior and Java production behavior from drifting.

**Work**

- Run resolved SOFA, AKI, and governance fixtures through both implementations.
- Normalize non-semantic serialization differences and compare full decision payloads.
- Include score, components, missingness, suppression reason, routing, evidence, and version.
- Fail CI on any mismatch.

**Acceptance criteria**

- [x] CI reports fixture count and zero mismatches.
- [x] v0.3.1 cannot be published unless the parity job passes.

---

## Milestone 1 — Clinically defensible indicator definitions

### CURIE-008 — Separate SOFA deterioration from sepsis identification [P0]

**Objective:** Avoid presenting absolute organ-dysfunction scoring as a sepsis diagnosis.

**Work**

- Rename the existing signal to `sofa-deterioration` in user-facing output.
- Implement a separate Sepsis-3 phenotype requiring suspected infection and acute SOFA change.
- Define infection-suspicion timing using cultures, antimicrobials, and documented timing rules.
- Preserve every evidence ID and explain which criterion was met.
- Add exclusions and explicit handling for pre-existing organ dysfunction.

**Acceptance criteria**

- [ ] No screen or API labels SOFA threshold alone as confirmed sepsis.
- [ ] Sepsis phenotype logic has versioned positive, negative, boundary, and missing-data cases.

### CURIE-009 — Implement stateful KDIGO timelines [P0]

**Objective:** Replace caller-provided AKI windows with reproducible temporal computation.

**Work**

- Maintain 48-hour and seven-day creatinine histories.
- Document and implement baseline-creatinine selection.
- Aggregate weight-normalized urine output over 6h, 12h, and 24h windows.
- Handle anuria, dialysis/RRT, ESRD, missing weight, duplicate labs, and corrected results.
- Emit criteria-specific evidence and onset time.

**Acceptance criteria**

- [ ] KDIGO stages match reviewed fixtures at all temporal boundaries.
- [ ] Restart, duplicate, and out-of-order tests preserve staging.
- [ ] The algorithm does not infer a reassuring stage when required inputs are missing.

### CURIE-010 — Define a common clinical-signal output contract [P1]

**Objective:** Standardize outputs before adding more conditions.

The contract should include signal type, phenotype/risk distinction, score, confidence or
completeness, severity, onset estimate, required/missing inputs, evidence, exclusions, rule
version/hash, and resolution state.

**Acceptance criteria**

- [ ] SOFA/sepsis and AKI emit the same top-level schema.
- [ ] The API and dashboard render an unknown future signal without condition-specific code.

---

## Milestone 2 — Genuine multi-indicator platform

### CURIE-011 — Create an indicator plugin SDK [P1]

**Objective:** Make adding an indicator a bounded plugin task rather than a new platform path.

**Plugin contract**

- Required clinical concepts, codes, units, windows, eligibility, exclusions, scorer, tiers,
  missing-data policy, resolution rule, fixtures, and bundle schema.
- Explicit runtime implementation mapping; a JSON bundle alone must not claim to implement a
  scorer that does not exist.

**Acceptance criteria**

- [ ] SOFA/sepsis and AKI are registered and dispatched through the same interface.
- [ ] Listing an indicator proves that a compatible scorer is installed.
- [ ] Unsupported score types fail at activation rather than during patient processing.

### CURIE-012 — Add patient episode aggregation and cross-condition arbitration [P1]

**Objective:** Produce one actionable patient episode instead of independent alert floods.

**Work**

- Group correlated signals within a configurable episode window.
- Maintain episode state: open, updated, escalated, acknowledged, resolved, reopened.
- Select a dominant problem while retaining supporting signals/differential context.
- Page on meaningful escalation or new actionability, not every component update.
- Preserve condition-specific evidence and suppression decisions in the audit trail.

**Acceptance criteria**

- [ ] Concurrent sepsis, AKI, and hypotension signals generate one interruptive episode alert.
- [ ] Passive updates remain visible without generating repeat pages.
- [ ] Resolution and re-deterioration behavior is deterministic and tested.

### CURIE-013 — Add respiratory deterioration as indicator three [P2]

**Dependency:** CURIE-010 through CURIE-012.

Start with deterministic hypoxemic/ventilatory deterioration using oxygen support, SpO2/FiO2 or
PaO2/FiO2 when valid, respiratory rate, blood gas context, and ventilation escalation. Do not add
this as another bespoke job.

**Acceptance criteria**

- [ ] The new indicator needs no dashboard-specific rendering path.
- [ ] It participates in the shared episode arbiter and governance layer.

---

## Milestone 3 — MIMIC-IV retrospective study

Tasks CURIE-014 and CURIE-015 can begin against the demo schema while access is pending.

### CURIE-014 — Freeze the MIMIC-IV study protocol [P0]

**Objective:** Predefine the study before inspecting the temporal holdout.

Specify dataset and `mimic-code` versions, cohort, exclusions, labels, prediction cadence,
availability-time policy, development/calibration/test split, primary endpoint, non-inferiority
margin, ablations, subgroup analyses, bootstrap unit, and missing-data analyses.

**Acceptance criteria**

- [ ] The protocol identifies one primary endpoint and operating-point selection rule.
- [ ] The test split cannot be used by sweep/tuning commands.
- [ ] Product claims are mapped to the evidence required to support them.

### CURIE-015 — Build a leakage-safe MIMIC timeline harness [P0]

**Work**

- Convert MIMIC events into the canonical envelope and replay them in availability-time order.
- Never use discharge diagnoses, future measurements, or later corrections before availability.
- Pin derived concept SQL and record dataset/code hashes.
- Cache only versioned derived artifacts without patient data entering Git.
- Produce per-stay signals, episodes, labels, and error/missingness summaries.

**Acceptance criteria**

- [ ] A demo-schema run completes end to end before full access arrives.
- [ ] Automated leakage tests fail when future information is introduced.
- [ ] Repeated runs produce identical output hashes.

### CURIE-016 — Run the locked MIMIC ablation and robustness study [P1]

Compare threshold-only detection, full governance, and one-at-a-time removal of persistence,
crossings, baseline, refractory period, context suppression, page gate, episode arbitration, and
late-event buffering.

Report sensitivity, AUPRC/PPV where applicable, bounded lead time, calibration for probabilistic
models, alerts per 100 patient-days, false episodes, repeats, NNA/NNE, missingness, subgroup
performance, and patient-level confidence intervals.

**Acceptance criteria**

- [ ] Thresholds are selected only on development/calibration data.
- [ ] The locked temporal holdout is executed once for the primary result.
- [ ] All tables can be regenerated from one versioned command or manifest.

---

## Milestone 4 — Durable shadow-mode product

### CURIE-017 — Replace the in-memory alert store [P1]

Add durable alert, episode, acknowledgement, rule-version, and audit tables. Consume Kafka with
manual commit after a successful idempotent transaction. Add migrations, unique keys, restart
tests, retention rules, and bounded query pagination.

**Acceptance criteria**

- [ ] A process restart loses neither alerts nor acknowledgements.
- [ ] Duplicate Kafka delivery cannot create a duplicate alert or episode transition.
- [ ] Metrics are not silently truncated at 10,000 records.

### CURIE-018 — Add production security and observability boundaries [P1]

Add OIDC/RBAC, restrictive CORS, encrypted transport, secret management, tenant/site boundaries,
PHI-safe structured logging, health/readiness endpoints, Kafka/Flink lag, watermark and lateness
metrics, DLQ monitoring, rule-activation audit, alert-volume alarms, and kill switches.

**Acceptance criteria**

- [ ] No prototype service is internet-accessible with wildcard CORS and no authentication.
- [ ] Operators can identify the active bundle, processing lag, missing-data rate, and alert rate.
- [ ] A rule or alert lane can be disabled without redeploying code.

### CURIE-019 — Add standards-based integration boundary [P2]

Expose FHIR-compatible evidence references and a CDS Hooks-compatible presentation/feedback
boundary. Keep EHR-specific integration outside the scoring and governance core.

---

## Milestone 5 — Paper and VC deliverables

### CURIE-020 — Produce the research manuscript package [P1]

- Methods and protocol with exact code/data versions.
- Cohort flow diagram, operating-point/Pareto plot, timing plot, calibration plot where relevant,
  ablation table, subgroup table, and failure analysis.
- Clear separation of retrospective detection, alert-policy utility, and unproven clinical outcome
  effects.
- Reproducibility manifest that does not expose protected MIMIC data.

### CURIE-021 — Build the investor demonstration and claims matrix [P1]

The demo should replay a patient timeline, show multiple signals becoming one episode, compare
naive/passive/interruptive volume, expose evidence and rule hashes, and survive duplicate,
out-of-order, and restart scenarios.

Maintain a claims matrix with `demonstrated`, `under evaluation`, and `not claimed` categories.
Do not claim diagnosis, outcome improvement, clinical validation, or regulatory clearance without
the corresponding evidence.

---

## Recommended first five Cursor tasks

Run these as separate changes in this order:

1. **CURIE-003:** Correct NNA and metric names; add regression tests.
2. **CURIE-002:** Add semantic version parsing and explicit bundle resolution.
3. **CURIE-001:** Generate and hash a fully resolved Challenge study bundle.
4. **CURIE-005:** Complete Python/Java governance-config parity.
5. **CURIE-006:** Implement deterministic event-time buffering and permutation tests.

After each task, run:

```bash
pytest -q
ruff check .
git diff --check
make flink-test
```

Then rerun the frozen configuration only as a regression report—not as another opportunity to tune
against Challenge set B.

