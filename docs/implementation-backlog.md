# Implementation backlog: research-grade deterministic prototype

**Status:** Active  
**Primary objective:** Make Curie reproducible, clinically defensible, ready for a locked
MIMIC-IV evaluation, and safe to operate as a commercial shadow-mode prototype before expanding
the product surface.

This is the working engineering backlog. The clinical study design remains in
`[research/clinical-validation.md](research/clinical-validation.md)`.

## How to use this backlog

- Complete tasks in milestone order unless a task explicitly says it can run in parallel.
- Use one task per branch/PR where practical and include the task ID in the branch or PR title.
- Do not tune thresholds on Challenge 2019 `training_setB`; it has already been inspected.
- Never replace a frozen study artifact in place. Create a new version and retain its hash.
- Mark a task complete only after its acceptance criteria and verification commands pass.
- Every clinical-rule change needs Python tests, Java tests when applicable, and a replay result.

Task execution labels used below:

- **READY** — can be completed in this repository with synthetic, frozen, or public artifacts.
- **ACCESS** — implementation can start, but completion requires credentialed MIMIC-IV data.
- **PARTNER** — completion requires a hospital, clinical collaborator, or deployment environment.



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
- `docs/research/challenge-2019-eval.md`

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
- `docs/research/challenge-2019-eval.md`

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

- [x] The report clearly states that Challenge labels begin six hours before clinical onset.
- [x] No primary metric rewards an alert with unlimited early lead time.
- [x] Timing definitions are frozen before MIMIC holdout evaluation.



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

- [x] No screen or API labels SOFA threshold alone as confirmed sepsis.
- [x] Sepsis phenotype logic has versioned positive, negative, boundary, and missing-data cases.



### CURIE-009 — Implement stateful KDIGO timelines [P0]

**Objective:** Replace caller-provided AKI windows with reproducible temporal computation.

**Work**

- Maintain 48-hour and seven-day creatinine histories.
- Document and implement baseline-creatinine selection.
- Aggregate weight-normalized urine output over 6h, 12h, and 24h windows.
- Handle anuria, dialysis/RRT, ESRD, missing weight, duplicate labs, and corrected results.
- Emit criteria-specific evidence and onset time.

**Acceptance criteria**

- [x] KDIGO stages match reviewed fixtures at all temporal boundaries.
- [x] Restart, duplicate, and out-of-order tests preserve staging.
- [x] The algorithm does not infer a reassuring stage when required inputs are missing.



### CURIE-010 — Define a common clinical-signal output contract [P1]

**Objective:** Standardize outputs before adding more conditions.

The contract should include signal type, phenotype/risk distinction, score, confidence or
completeness, severity, onset estimate, required/missing inputs, evidence, exclusions, rule
version/hash, and resolution state.

**Acceptance criteria**

- [x] SOFA/sepsis and AKI emit the same top-level schema.
- [x] The API and dashboard render an unknown future signal without condition-specific code.

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

- [x] SOFA/sepsis and AKI are registered and dispatched through the same interface.
- [x] Listing an indicator proves that a compatible scorer is installed.
- [x] Unsupported score types fail at activation rather than during patient processing.



### CURIE-012 — Add patient episode aggregation and cross-condition arbitration [P1]

**Objective:** Produce one actionable patient episode instead of independent alert floods.

**Work**

- Group correlated signals within a configurable episode window.
- Maintain episode state: open, updated, escalated, acknowledged, resolved, reopened.
- Select a dominant problem while retaining supporting signals/differential context.
- Page on meaningful escalation or new actionability, not every component update.
- Preserve condition-specific evidence and suppression decisions in the audit trail.

**Acceptance criteria**

- [x] Concurrent sepsis, AKI, and hypotension signals generate one interruptive episode alert.
- [x] Passive updates remain visible without generating repeat pages.
- [x] Resolution and re-deterioration behavior is deterministic and tested.



### CURIE-013 — Add respiratory deterioration as indicator three [P2]

**Dependency:** CURIE-010 through CURIE-012.

Start with deterministic hypoxemic/ventilatory deterioration using oxygen support, SpO2/FiO2 or
PaO2/FiO2 when valid, respiratory rate, blood gas context, and ventilation escalation. Do not add
this as another bespoke job.

**Acceptance criteria**

- [x] The new indicator needs no dashboard-specific rendering path.
- [x] It participates in the shared episode arbiter and governance layer.

---



## Milestone 3 — MIMIC-IV retrospective study

Tasks CURIE-014 and CURIE-015 can begin against the demo schema while access is pending.

### CURIE-014 — Freeze the MIMIC-IV study protocol [P0]

**Objective:** Predefine the study before inspecting the temporal holdout.

Specify dataset and `mimic-code` versions, cohort, exclusions, labels, prediction cadence,
availability-time policy, development/calibration/test split, primary endpoint, non-inferiority
margin, ablations, subgroup analyses, bootstrap unit, and missing-data analyses.

**Acceptance criteria**

- [x] The protocol identifies one primary endpoint and operating-point selection rule.
- [x] The test split cannot be used by sweep/tuning commands.
- [x] Product claims are mapped to the evidence required to support them.

**Artifacts:** `[docs/research/mimic-iv-study-protocol.md](./research/mimic-iv-study-protocol.md)`,
`[eval/mimic_study/frozen/protocol.v1.json](../eval/mimic_study/frozen/protocol.v1.json)`,
`python -m eval.mimic_study.sweep`.

### CURIE-015 — Build a leakage-safe MIMIC timeline harness [P0]

**Work**

- Convert MIMIC events into the canonical envelope and replay them in availability-time order.
- Never use discharge diagnoses, future measurements, or later corrections before availability.
- Pin derived concept SQL and record dataset/code hashes.
- Cache only versioned derived artifacts without patient data entering Git.
- Produce per-stay signals, episodes, labels, and error/missingness summaries.

**Acceptance criteria**

- [x] A demo-schema run completes end to end before full access arrives.
- [x] Automated leakage tests fail when future information is introduced.
- [x] Repeated runs produce identical output hashes.

**Artifacts:** `[docs/research/mimic-timeline-harness.md](./research/mimic-timeline-harness.md)`,
`python -m eval.mimic_harness.runner` / `make mimic-harness`.

### CURIE-016 — Run the locked MIMIC ablation and robustness study [P1]

Compare threshold-only detection, full governance, and one-at-a-time removal of persistence,
crossings, baseline, refractory period, context suppression, page gate, episode arbitration, and
late-event buffering.

Report sensitivity, AUPRC/PPV where applicable, bounded lead time, calibration for probabilistic
models, alerts per 100 patient-days, false episodes, repeats, NNA/NNE, missingness, subgroup
performance, and patient-level confidence intervals.

**Acceptance criteria**

- [x] Thresholds are selected only on development/calibration data.
- [x] The locked temporal holdout is executed once for the primary result.
- [x] All tables can be regenerated from one versioned command or manifest.

**Artifacts:** `[docs/research/mimic-ablation-study.md](./research/mimic-ablation-study.md)`,
`make mimic-study` / `python -m eval.mimic_study.study run`.

---



## Milestone 4 — Durable shadow-mode product



### CURIE-017 — Replace the in-memory alert store [P1]

Add durable alert, episode, acknowledgement, rule-version, and audit tables. Consume Kafka with
manual commit after a successful idempotent transaction. Add migrations, unique keys, restart
tests, retention rules, and bounded query pagination.

**Acceptance criteria**

- [x] A process restart loses neither alerts nor acknowledgements.
- [x] Duplicate Kafka delivery cannot create a duplicate alert or episode transition.
- [x] Metrics are not silently truncated at 10,000 records.

**Artifacts:** `[docs/operations/durable-alert-store.md](./operations/durable-alert-store.md)`,
`CURIE_ALERT_DB=… make api`.

### CURIE-018 — Add production security and observability boundaries [P1]

Add OIDC/RBAC, restrictive CORS, encrypted transport, secret management, tenant/site boundaries,
PHI-safe structured logging, health/readiness endpoints, Kafka/Flink lag, watermark and lateness
metrics, DLQ monitoring, rule-activation audit, alert-volume alarms, and kill switches.

**Acceptance criteria**

- [x] No prototype service is internet-accessible with wildcard CORS and no authentication.
- [x] Operators can identify the active bundle, processing lag, missing-data rate, and alert rate.
- [x] A rule or alert lane can be disabled without redeploying code.

**Artifacts:** `[docs/operations/security-observability.md](./operations/security-observability.md)`,
`GET /ops/status`, `POST /ops/kill-switches`.

### CURIE-019 — Add standards-based integration boundary [P2]

Expose FHIR-compatible evidence references and a CDS Hooks-compatible presentation/feedback
boundary. Keep EHR-specific integration outside the scoring and governance core.

**Acceptance criteria**

- [x] Alert evidence ids project to FHIR R4 Reference-shaped objects (and a collection Bundle).
- [x] CDS Hooks discovery + `patient-view` cards expose governed alerts without rescoring.
- [x] CDS Hooks feedback maps to acknowledge and cannot change score/tier.

**Artifacts:** `[docs/operations/cds-hooks-integration.md](./operations/cds-hooks-integration.md)`,
`GET /cds-services`, `GET /alerts/{id}/fhir-evidence`.

---



## Milestone 5 — Paper and VC deliverables



### CURIE-020 — Produce the research manuscript package [P1]

- Methods and protocol with exact code/data versions.
- Cohort flow diagram, operating-point/Pareto plot, timing plot, calibration plot where relevant,
ablation table, subgroup table, and failure analysis.
- Clear separation of retrospective detection, alert-policy utility, and unproven clinical outcome
effects.
- Reproducibility manifest that does not expose protected MIMIC data.

**Acceptance criteria**

- [x] Methods pin code SHA + frozen protocol/operating-point/Challenge artifact hashes.
- [x] Package includes cohort flow, Pareto/timing/calibration specs, ablation + subgroup tables, and failure analysis.
- [x] Claim tiers separate retrospective detection, alert-policy utility, and unproven outcomes.
- [x] Reproducibility manifest regenerates without embedding protected MIMIC extracts (`make manuscript` / `phi-scan`).

**Artifacts:** `[docs/research/manuscript-package.md](./research/manuscript-package.md)`,
`make manuscript`, `eval/manuscript/frozen/reproducibility_manifest.v1.json`.

### CURIE-021 — Build the investor demonstration and claims matrix [P1]

The demo should replay a patient timeline, show multiple signals becoming one episode, compare
naive/passive/interruptive volume, expose evidence and rule hashes, and survive duplicate,
out-of-order, and restart scenarios.

Maintain a claims matrix with `demonstrated`, `under evaluation`, and `not claimed` categories.
Do not claim diagnosis, outcome improvement, clinical validation, or regulatory clearance without
the corresponding evidence.

**Acceptance criteria**

- [x] Demo replays a multi-signal timeline into one episode with naive/passive/interruptive volume.
- [x] Evidence IDs and rule hashes are exposed on every demo step.
- [x] Duplicate, out-of-order, and restart scenarios pass in the demo harness.
- [x] Claims matrix uses demonstrated / under_evaluation / not_claimed and forbids diagnosis,
  outcome, clinical-validation, and regulatory claims without evidence.

**Artifacts:** `[docs/research/claims-matrix.md](./research/claims-matrix.md)`, `make investor-demo`.

---



## Milestone 6 — Cross-project LLM workflows

Detailed designs, safety boundaries, and metrics are in
`[llm-workflows.md](llm-workflows.md)`. `curie-fhir` owns normalization, candidate extraction,
validation, and interface review; this project owns deterministic surveillance, episode state,
alert routing, and post-decision explanation.

### CURIE-022 — Define the trusted clinical-fact bridge [P1]

Create a versioned envelope shared with `curie-fhir` containing clinical and availability times,
trust status, source spans, validation results, extraction provenance, and a stable idempotency key.
Reject or quarantine candidate facts, unknown schemas, failed validation, and missing provenance.

**Acceptance criteria**

- [x] Both projects validate the same contract fixtures.
- [x] LLM-derived and deterministic facts are distinguishable in audit output.
- [x] Only trusted facts can mutate scoring state.

**Artifacts:** `[docs/operations/trusted-clinical-fact-bridge.md](./operations/trusted-clinical-fact-bridge.md)`,
`ingestion/bridge/`, `make trusted-fact-bridge`,
`curie-fhir` `src/curie_fhir/contracts/trusted_clinical_fact/`.

### CURIE-023 — Build grounded patient-episode narratives [P1]

Extend the current Guarded Reasoning Pipeline from individual alerts to immutable patient-episode
snapshots. Require sentence-level evidence IDs, missing-data disclosure, routing rationale, model
and prompt versions, abstention, quarantine, timeout, and prompt-injection tests.

**Acceptance criteria**

- [x] Narrative failure cannot delay or change alert delivery.
- [x] Every displayed clinical claim maps to allowed episode evidence.
- [x] Unsupported or malformed output is quarantined and audited.

**Artifacts:** [`docs/governance/episode-narratives.md`](./governance/episode-narratives.md),
`POST /episodes/{id}/explain`, `reasoning/episode_*.py`.



### CURIE-024 — Add LLM feedback classification for alert stewardship [P2]

Classify acknowledgement and dismissal feedback into a reviewed taxonomy. Aggregate findings by
site, service, indicator, rule version, and routing lane. Generate offline replay experiment
proposals only; never mutate active rules.

**Acceptance criteria**

- [x] Classification performance is measured against dual-reviewed feedback.
- [x] Every suggested rule change is evaluated through a frozen replay manifest.
- [x] Human approval is required before activation.

**Artifacts:** [`docs/governance/alert-stewardship.md`](./governance/alert-stewardship.md),
`make stewardship`, `eval/stewardship/`.



### CURIE-025 — Evaluate uncertainty-band contextual reasoning [P2]

Define a frozen eligibility policy for borderline/conflicting cases and evaluate source-grounded
context and mimic extraction retrospectively. Start as passive decision support and prohibit the
LLM from suppressing or escalating deterministic alerts.

**Acceptance criteria**

- [x] The study reports sensitivity, PPV, alert burden, unsupported claims, abstention, and
  subgroup performance.
- [x] No interruptive routing depends on the LLM during retrospective or shadow evaluation.

**Artifacts:** [`docs/governance/uncertainty-band.md`](./governance/uncertainty-band.md),
`make uncertainty-band`, `eval/uncertainty/`.

---



## Milestone 7 — Close deterministic reliability gaps

These tasks supersede the original “first five Cursor tasks,” which are complete. Finish this
milestone before adding another clinical indicator or promoting the reliability claim.

### CURIE-026 — Flush SOFA event-time state without a following event [P0 · READY]

**Objective:** Ensure a valid event cannot remain buffered forever when it is the final event for a
patient, encounter, partition, or replay.

**Work**

- Connect `EventTimeBuffer` to a real event-time timer/watermark completion mechanism; refactor to
  a keyed pre-processing operator if the broadcast-process API cannot provide the required timer.
- Define behavior for source idleness, bounded replay completion, equal timestamps, late events,
  checkpoint restoration, and end-of-input.
- Keep the allowed-lateness policy and late-data DLQ disposition versioned and observable.

**Acceptance criteria**

- [x] A single valid event is eventually scored without requiring a second event.
- [x] End-of-input and idle partitions flush all eligible events exactly once.
- [x] All within-lateness permutations produce byte-equivalent normalized alerts.
- [x] Restart before and after timer registration produces identical output and DLQ records.

**Likely files:** `SofaAlertFunction.java`, `EventTimeBuffer.java`, Flink operator tests,
`docs/governance/event-time-policy.md`.

### CURIE-027 — Apply the same deterministic ordering policy to AKI [P0 · READY]

**Objective:** Prevent arrival order from changing AKI baselines, stages, onset, evidence, or
governance decisions.

**Work**

- Put AKI feature mutation behind the shared event-time reordering/late-data boundary.
- Cover creatinine corrections, urine-output windows, duplicate observations, equal timestamps,
  ESRD/RRT context, encounter transitions, idleness, and restart.
- Expose AKI watermark, buffered-event, and late-event metrics through `/ops/status`.

**Acceptance criteria**

- [x] AKI output is invariant across all permutations within allowed lateness.
- [x] Late corrections have a deterministic, documented disposition.
- [x] Checkpoint/restart output matches uninterrupted processing byte-for-byte after normalization.
- [x] SOFA and AKI report the same event-time policy version.

**Likely files:** `AkiJob.java`, `AkiAlertFunction.java`, shared state package, AKI replay tests.

### CURIE-028 — Make episode identity and state replay-stable [P0 · READY]

**Objective:** Produce the same episode IDs, ordering, dominant signal, routing, and audit history
for equivalent event sets regardless of arrival order or process restart.

**Work**

- Replace first-arrival-dependent identity inputs with a canonical episode-open identity rule.
- Make episode timestamps monotonic; an older signal must not move `updated_at` backward.
- Define deterministic tie-breaking for concurrent signals and encounter boundaries.
- Strengthen chaos and durable-store tests to compare complete normalized episode payloads.

**Acceptance criteria**

- [x] In-order, reverse-order, duplicate, and restart replays return the same episode ID.
- [x] `opened_at <= updated_at`, audit entries are canonically ordered, and timestamps never regress.
- [x] A resolved/reopened episode follows the same transitions after restart.
- [x] The investor `RELIABILITY` claim remains `under_evaluation` until these tests pass.

**Likely files:** `eval/episodes/arbiter.py`, episode models, durable store, investor chaos tests.

### CURIE-029 — Complete respiratory parity and runtime dispatch [P0 · READY]

**Objective:** Hold respiratory deterioration to the same implementation and parity standard as
SOFA and AKI without creating another bespoke platform path.

**Work**

- Resolve Python/Java boundary differences, including `PaCO2 > 60` staging.
- Add respiratory cases to the shared cross-runtime golden fixture and parity count.
- Prove bundle activation dispatches `resp_hypoxemia` to the respiratory scorer and fails closed
  when no compatible runtime implementation exists.
- Add a Kafka/Flink pipeline test through shared governance and episode arbitration.

**Acceptance criteria**

- [x] Python and Java match score, stage, criteria, missingness, tier, evidence, and routing.
- [x] The parity gate contains respiratory positive, negative, boundary, and missing-data cases.
- [x] A respiratory bundle cannot be activated against the SOFA scorer accidentally.
- [x] Respiratory participates in one multi-signal episode without dashboard-specific code.

**Likely files:** respiratory scorers, plugin registry, parity fixtures/gate, Flink job wiring.

### CURIE-030 — Normalize benchmark semantics and implement miss attribution [P0 · READY]

**Objective:** Make every benchmark number unambiguous, reproducible, and useful for improving the
page lane.

**Work**

- Make primary `window_m12_p6` metrics the default everywhere; label legacy grace-window metrics
  as sensitivity analyses.
- Separate SOFA, AKI, respiratory, governed-emission, interruptive-emission, and episode-page
  denominators instead of combining unlike counts.
- Include scoring errors, missingness, unscoreable stays, and zero-signal indicators in reports.
- Attribute each governed false negative to the first decisive cause: unavailable/missing input,
  scorer threshold, persistence, baseline, context suppression, refractory, page gate, arbitration,
  or timing-window mismatch.

**Acceptance criteria**

- [x] Dashboard, manuscript, docs, and frozen summaries agree on 79.5% governed sensitivity,
  34.0% interruptive sensitivity, and 106.1 interruptive-emission NNA for the pinned primary
  Challenge holdout artifact.
- [x] Legacy 81.1% is never displayed as the primary timing result.
- [x] Every false negative has one primary reason plus optional contributing reasons.
- [x] A generated miss-analysis table reports counts, rates, representative de-identified traces,
  and rule/config hashes.

**Likely files:** `eval/benchmarks/`, `eval/challenge2019/`, `eval/mimic_study/`, manuscript output,
benchmark dashboard.

### CURIE-031 — Make the dashboard self-contained under production CSP [P1 · READY]

**Objective:** Ensure the architecture, benchmark, and evidence views render when production
content-security policy blocks inline or third-party scripts.

**Work**

- Vendor or bundle Mermaid locally, or replace it with a CSP-compatible static renderer.
- Remove production dependence on CDN scripts/fonts where practical.
- Add a browser smoke test that checks rendered diagrams and absence of permanent loading states.

**Acceptance criteria**

- [x] All diagrams render with the production CSP enabled and no console security errors.
- [x] The dashboard remains usable when external network access is unavailable.
- [x] A failed optional visualization displays readable fallback content.

---

## Milestone 8 — Improve alert accuracy without weakening safety

### CURIE-032 — Add component-delta paging [P0 · READY]

**Objective:** Page on newly worsened organ components and meaningful trajectory, not only an
absolute total-score increase.

**Work**

- Persist the prior component vector and emit deterministic per-component deltas with evidence.
- Add bundle parameters for newly worsened component count, minimum component delta, and selected
  high-actionability components.
- Keep total-score delta available as a separate gate; do not silently change frozen studies.
- Add a pre-specified Challenge regression and MIMIC ablation configuration.

**Acceptance criteria**

- [x] Alerts identify exactly which components newly worsened and which observations caused it.
- [x] Python/Java page decisions match on component-delta fixtures.
- [x] Existing frozen Challenge results remain reproducible under the old policy version.
- [x] The new policy reports sensitivity, page burden, NNA, lead time, and miss reasons.

### CURIE-033 — Add deterministic page-quality and uncertainty gates [P0 · READY]

**Objective:** Abstain from interruptive paging on stale, contradictory, invalid, or insufficient
data using deterministic policy only.

**Work**

- Define versioned gates for freshness, missing critical inputs, unit/status validity,
  contradictory observations, source trust, and optional out-of-distribution ranges.
- Route ineligible cases to passive watch plus an explicit reason; never silently discard them.
- Keep the LLM uncertainty workflow downstream and observational—it cannot suppress or escalate.
- Evaluate each gate independently in the ablation framework.

**Acceptance criteria**

- [x] Identical inputs always produce the same eligibility and routing result.
- [x] Every page abstention is visible, auditable, and linked to evidence/data-quality reasons.
- [x] No routing decision depends on an LLM response, timeout, or model availability.
- [x] The study reports both false-page reduction and true-positive pages lost by each gate.

### CURIE-034 — Build a real shadow-mode execution harness [P0 · READY]

**Objective:** Run the complete system silently and measure what would have alerted without
delivering interruptive notifications.

**Work**

- Add an explicit deployment mode that executes scoring/governance normally but writes pages to a
  `would_have_paged` audit stream/store only.
- Record active bundles, policy hashes, processing/availability times, suppression reasons,
  pipeline lag, missingness, DLQ counts, and kill-switch state.
- Define import contracts for later clinician actions and local outcome labels without requiring
  them for synthetic testing.
- Generate a site/day/indicator shadow report with alert burden and operational reliability.

**Acceptance criteria**

- [x] Shadow mode cannot call an interruptive delivery adapter.
- [x] The same replay in shadow and active simulation produces identical decisions before delivery.
- [x] Restart and duplicate delivery do not duplicate `would_have_paged` records.
- [x] `SHADOW-PROD` remains `under_evaluation` until partner-site evidence exists.

### CURIE-035 — Add site calibration and production drift monitoring [P1 · READY]

**Objective:** Detect when a site's inputs, missingness, or alert behavior differ materially from
the development/reference population.

**Work**

- Separate threshold/operating-point selection from probability calibration terminology.
- Define a versioned site profile and minimum evidence requirements before local threshold changes.
- Monitor input ranges/distributions, units, missingness, arrival delay, completeness, score/tier
  rates, page rates, and suppression reasons by site and indicator.
- Add warning/critical thresholds, baseline versioning, rollback, and drift-report generation.

**Acceptance criteria**

- [x] Synthetic distribution, missingness, unit, and alert-rate shifts trigger deterministic alarms.
- [x] A site profile cannot be selected or tuned on its locked test period.
- [x] Site overrides identify parent bundle, approver, evidence window, version, and rollback target.
- [x] Drift alarms do not automatically mutate active clinical rules.

### CURIE-036 — Select and implement indicator four [P1 · READY]

**Objective:** Demonstrate repeatable product expansion while avoiding unsupported diagnosis
claims.

**Work**

- Score candidates using actionability, data availability, label quality, overlap with current
  ingestion, clinical risk, and validation cost.
- Start with one bounded surveillance signal; hemodynamic shock/hyperlactatemia is the default
  candidate unless the documented rubric selects another.
- Implement the rule bundle, Python and Java scorer/dispatcher, fixtures, parity, governance,
  episode behavior, missing-data policy, and resolution logic.
- Describe outputs as surveillance indicators/phenotypes, not confirmed diagnoses.

**Acceptance criteria**

- [x] The selection rubric and rejected alternatives are documented before implementation.
- [x] The new indicator passes the plugin, parity, replay, and activation gates.
- [x] It reuses shared governance, shadow, API, and dashboard paths without bespoke condition code.
- [x] Clinical validity remains an explicit non-claim until evaluated on an appropriate dataset.

---

## Milestone 9 — Commercial prototype boundaries

### CURIE-037 — Add Postgres persistence and enforce tenant isolation [P1 · READY]

**Objective:** Retain SQLite for local demos while providing a production-shaped durable store with
enforced hospital/site isolation.

**Work**

- Introduce a storage interface and Postgres implementation with migrations and idempotent writes.
- Put tenant/site identity on every alert, episode, acknowledgement, audit, feedback, activation,
  and shadow record.
- Enforce isolation in database queries and service authorization, not only response filtering.
- Add migration, concurrency, retry, pagination, backup/restore, and cross-tenant denial tests.

**Acceptance criteria**

- [x] SQLite and Postgres pass the same store contract suite.
- [x] Cross-tenant reads, writes, acknowledgements, and episode joins fail closed.
- [x] Kafka offset commit occurs only after the idempotent database transaction succeeds.
- [x] Tenant-specific retention and deletion jobs have auditable dry-run modes.

### CURIE-038 — Replace prototype OIDC with verified production identity [P1 · READY]

**Objective:** Remove insecure JWT decoding from any production path and document a realistic
HIPAA operational boundary without claiming compliance certification.

**Work**

- Verify JWT signatures through cached JWKS with issuer, audience, expiry, not-before, algorithm,
  key-rotation, and failure-mode tests.
- Map external groups/scopes to explicit clinician, reviewer, and operator permissions.
- Add access/audit events for PHI-adjacent reads and mutations; prohibit raw tokens and identifiers
  in logs.
- Document encryption, secret rotation, backup, retention, incident response, BAA/shared
  responsibility, and deployment-control gaps.

**Acceptance criteria**

- [x] Production rejects unsigned, expired, wrong-audience, wrong-issuer, and unknown-key tokens.
- [x] Key rotation works without accepting a token whose signature cannot be verified.
- [x] Authorization tests cover tenant plus role, including privilege-escalation attempts.
- [x] Documentation says “production-shaped controls,” not “HIPAA compliant,” until independently
  assessed in a real environment.

### CURIE-039 — Validate the `curie-fhir` / HL7v2 integration contract [P1 · READY]

**Objective:** Make the sibling project the explicit EHR normalization boundary while preserving
deterministic trust and provenance requirements in this repository.

**Work**

- Add shared fixtures for HL7v2/FHIR-to-trusted-fact normalization, corrections, cancellations,
  units, source timestamps, availability times, and provenance failures.
- Version the compatibility matrix between both repositories and fail on unknown schemas.
- Provide a local connector simulator that publishes trusted facts and verifies resulting alerts,
  DLQ events, and evidence references.
- Keep Mirth/vendor credentials and transforms outside the scoring/governance core.

**Acceptance criteria**

- [x] Both repositories validate byte-equivalent trusted-fact contract fixtures.
- [x] Candidate, invalid, corrected, and cancelled facts have deterministic dispositions.
- [x] No untrusted LLM-derived fact can mutate scoring state.
- [x] The integration demo runs without real PHI or a hospital connection.

### CURIE-040 — Maintain a sourced prior-art and product landscape [P1 · READY]

**Objective:** Turn the Epic/TREWS/COMPOSER/Prenosis/eCART discussion into a defensible, dated
research and commercial artifact.

**Work**

- Create a source table covering intended use, inputs, deployment setting, validation design,
  alert workflow, adoption/burden metrics, regulatory status, and limitations.
- Add academic work on alert fatigue, tiered routing, refractory/dedup policy, abstention,
  distribution shift, multi-condition deterioration, and clinical CDS evaluation.
- Separate sourced facts, project inference, and proposed differentiation.
- Search explicitly for prior governance-policy ablations before claiming novelty.

**Acceptance criteria**

- [x] Every external claim has a primary source, access date, and short evidence note.
- [x] Regulatory/product status is timestamped and marked for periodic re-verification.
- [x] The manuscript novelty statement is no stronger than the completed search supports.
- [x] Investor language distinguishes “different architecture” from proven clinical superiority.

---

## Milestone 10 — Evidence requiring external access

### CURIE-041 — Execute the locked MIMIC-IV Stage B study [P0 · ACCESS]

Do not begin test-set evaluation until CURIE-026 through CURIE-035 pass and the extract/version
manifest is frozen.

**Acceptance criteria**

- [ ] Cohort, availability-time timeline, Sepsis-3 labels, complete SOFA inputs, KDIGO labels,
  exclusions, and missingness match the frozen protocol and pinned `mimic-code` concepts.
- [ ] Development sweep and calibration selection produce a new immutable operating-point artifact.
- [ ] The temporal test split is evaluated once, with stay-level confidence intervals, subgroups,
  miss analysis, and all pre-specified ablations.
- [ ] No protected row-level data or identifiers enter git, logs, manuscript artifacts, or demos.

### CURIE-042 — Conduct silent prospective validation [P0 · PARTNER]

**Acceptance criteria**

- [ ] IRB/DUA/BAA and clinical safety ownership are documented as applicable.
- [ ] Shadow decisions are compared with local labels, clinician actions, workflow timing, and data
  availability while no interruptive pages are delivered.
- [ ] Uptime, lag, DLQ, missingness, drift, alert burden, subgroup, and miss reports are reviewed.
- [ ] Activation criteria, rollback thresholds, human-factors review, and harm monitoring are agreed
  before any interruptive pilot.

### CURIE-043 — Refresh the manuscript, claims matrix, and investor package [P1 · ACCESS]

**Objective:** Promote claims only after the corresponding MIMIC or shadow evidence exists.

**Acceptance criteria**

- [ ] The manuscript uses full study outputs rather than demo-schema placeholders.
- [ ] The claims matrix changes status only when a pinned evidence artifact satisfies its gate.
- [ ] The investor demo separates engineering proof, retrospective evidence, prospective evidence,
  outcome claims, and regulatory non-claims.
- [ ] All benchmark cards state dataset, cohort, timing window, denominator, lane, confidence
  interval, code SHA, and rule/config hash.

---

## Current recommended Cursor sequence

Use one branch/PR per task. The recommended order is:

1. **CURIE-026** — SOFA event-time completion.
2. **CURIE-027** — AKI event-time determinism.
3. **CURIE-028** — replay-stable episode identity.
4. **CURIE-029** — respiratory parity and runtime dispatch.
5. **CURIE-030** — benchmark semantics and false-negative attribution.
6. **CURIE-031** — CSP-safe dashboard.
7. **CURIE-032** — component-delta paging.
8. **CURIE-033** — deterministic page-quality gates.
9. **CURIE-034** — shadow-mode harness.
10. **CURIE-035** — site drift and calibration infrastructure.

CURIE-036 through CURIE-040 can follow or run in parallel after the P0 reliability tasks. Keep
CURIE-041 through CURIE-043 blocked until their stated access/evidence dependency is satisfied.

After every code task, run:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
git diff --check
make flink-test
```

Rerun frozen Challenge configurations only as regression reports—not as opportunities to retune on
`training_setB`.
