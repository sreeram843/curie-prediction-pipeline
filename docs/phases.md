# Build phases

Locked decisions for v1 (from PRD §13):

| Decision | Choice |
|---|---|
| Care setting | Fully simulated, ICU-flavored Synthea cohort |
| Missing SOFA components | Partial score + `missing_components[]` — never silent impute |
| Alert contract | Internal event first; FHIR `RiskAssessment` as external; `Communication` deferred |
| Dashboard | View-only + acknowledge |
| Flink language | Java (mature Kafka/CEP); Python for ingest, API, eval |
| API | FastAPI |

---

## Phase 0 — Scaffolding ✅

- [x] Repo layout matching PRD §15
- [x] Docker Compose: Kafka (KRaft) + Flink JobManager/TaskManager
- [x] Synthea generation script
- [x] CI skeleton (lint/test placeholders)
- [x] Root README + this plan
- [x] Draft canonical envelope schema + Pydantic model
- [x] Draft sepsis-sofa rule bundle (`streaming/rule-registry/bundles/`)

**Exit criteria:** `docker compose up` brings up Kafka + Flink; Synthea can emit FHIR bundles to disk; CI runs green on empty/stub checks.

**Verified locally:** Kafka healthy on `:9092` with topics `observations|conditions|medications|alerts|rules|dlq`; Flink UI on `:8081` (1 TM, 2 slots); `pytest` + `ruff` green.

---

## Phase 1 — Deterministic vertical slice ✅

1. [x] Canonical event envelope + SOFA input contract (versioned schemas) + T0 fixtures
2. [x] Synthea → Kafka replay producer (dry-run + produce; delay injection hooks TBD)
3. [x] Flink SOFA score + alert job; thresholds via broadcast JSON rule bundle
4. [x] Governance operators (trajectory, baseline, suppression, dedup, tiering)
5. [x] Alerts → `alerts` topic + minimal read/acknowledge API
6. [x] Replay/backtest harness + alert-reduction-ratio metric (naive vs governance)
7. [x] Minimal dashboard: list alerts, evidence, acknowledge

**Exit criteria:** Same replay twice → identical alerts; governance reduces alert volume vs threshold-only; dashboard shows evidence-backed alerts.

**Phase 1 headline metric (T2 built-in library, v0.2 edge cases):** naive=14, governed=3, **alert_reduction_ratio ≈ 0.21**.

**Reliability hardening (follow-on):** shared golden SOFA fixtures (Python+Java), event-time/encounter-scoped feature state + idempotency keys, bundle-driven governance + **component thresholds** in Flink/Python, FHIR unit/status validation with **DLQ** side output, Flink **AkiScorer** + **AkiJob** (Kafka → score → shared governance → alerts/dlq), richer T3 tests (late events, rule-version drift, resolution gap, checkpoint-style restart/replay). **FiO₂ policy:** SpO2/PaO2 alone do not invent a ratio — no ambient-air `÷0.21` proxy; ratio only when FiO₂ is present or an explicit ratio field is supplied. **Governance parity:** Flink forwards below-threshold (`tier=none`) recovery signals and `context_flags`; baseline `lookback_hours` expires the stored baseline. **Idempotency:** TTL + eldest-eviction cache (not full clear).

---

## Phase 2 — LLM layer ✅

8. [x] Text→FHIR extraction adapter (feature-flagged) + T4 fixtures
9. [x] Guarded Reasoning Pipeline: context → model → claim validator → policy gate → quarantine
10. [x] Wire GRP as strictly additive (§6.4); feature-flagged (`CURIE_ENABLE_GRP`, dashboard force for demo)

**Exit criteria:** Deterministic alert still ships if LLM fails; ungrounded claims hard-fail.

---

## Phase 3 — Prove modularity ✅

11. [x] Second indicator (AKI / KDIGO-inspired) via rule bundle + scorer plugin
    - Bundle: `streaming/rule-registry/bundles/aki-kdigo.v0.2.0.json`
    - Scorer: `eval/aki/` + Flink `com.curie.sofa.aki.AkiScorer` / `AkiJob`
    - Shared governance reused via `eval.replay_harness.governance.evaluate` and Flink `GovernanceFilterFunction`
    - Replay: `make replay-aki`
    - Flink entrypoint: `flink run -c com.curie.sofa.aki.AkiJob …` (shade jar default main remains `SofaJob`)

**Exit criteria:** New indicator reuses governance; alert-reduction metric reported for it.

**Phase 3 headline metric (AKI T2 library, v0.2 edge cases):** naive=13, governed=4, **alert_reduction_ratio ≈ 0.31**.
