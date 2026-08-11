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

## Phase 1 — Deterministic vertical slice (in progress)

1. [x] Canonical event envelope + SOFA input contract (versioned schemas) + T0 fixtures
2. [x] Synthea → Kafka replay producer (dry-run + produce; delay injection hooks TBD)
3. [ ] Flink SOFA score + alert job; thresholds via broadcast JSON rule bundle
4. [ ] Governance operators (trajectory, baseline, suppression, dedup, tiering)
5. [ ] Alerts → `alerts` topic + minimal read/acknowledge API
6. [ ] Replay/backtest harness + alert-reduction-ratio metric (naive vs governance)
7. [ ] Minimal dashboard: list alerts, evidence, acknowledge

**Exit criteria:** Same replay twice → identical alerts; governance reduces alert volume vs threshold-only; dashboard shows evidence-backed alerts.

---

## Phase 2 — LLM layer (after Phase 1 metrics look good)

8. Text→FHIR extraction adapter (feature-flagged) against labeled notes (T4)
9. Guarded Reasoning Pipeline: context → model → claim validator → policy gate → quarantine
10. Wire GRP as strictly additive (§6.4); feature-flagged

**Exit criteria:** Deterministic alert still ships if LLM fails; ungrounded claims hard-fail.

---

## Phase 3 — Prove modularity

11. Second indicator (e.g. AKI) via rule bundle only — no changes to ingest, Kafka, or governance core

**Exit criteria:** New indicator reuses governance; alert-reduction metric reported for it.
