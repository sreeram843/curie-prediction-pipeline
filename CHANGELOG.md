# Changelog

Notable changes to Curie Prediction Pipeline. This is a prototype; versions here are the `pyproject.toml`
package version and the rule-bundle semver versions (see `streaming/rule-registry/`). Dates are ISO 8601.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

- Docs cleanup: single-source-of-truth landing + agent manual, `docs/adr/`, `docs/runbooks/`, `docs/api.md`.

## [0.1.0] - 2026-08-12

Initial prototype. Synthetic data only; not clinically validated.

### Added

- **Phase 0 — Scaffolding.** Repo layout, Docker Compose (Kafka + Flink + Kafka UI), Synthea generation, CI.
- **Phase 1 — Deterministic vertical slice.** Canonical event envelope, Synthea replay producer, Flink
  SOFA score/alert job, shared alert-governance operators, read/acknowledge API + dashboard, replay/backtest
  harness with alert-reduction metric.
- **Phase 2 — LLM layer.** Text→FHIR extraction adapter and Guarded Reasoning Pipeline (GRP), both
  feature-flagged and strictly additive to the deterministic alert.
- **Phase 3 — Modularity.** AKI (KDIGO-inspired) as a second indicator authored purely as a rule bundle +
  scorer plugin, reusing shared governance.
- Reliability and determinism: cross-runtime Python/Java parity gate (CURIE-007), deterministic event-time
  ordering with allowed lateness, replay-stable episode identity, component-delta and quality gates.
- Product boundaries: durable alert store, security/observability posture (OIDC/RBAC, kill switches), CDS
  Hooks / FHIR evidence boundary, trusted clinical-fact bridge with `curie-fhir`.
- Deliverables: research manuscript package, investor demo + claims matrix, alert stewardship, uncertainty
  band, prior-art landscape.
- Indicators: SOFA deterioration, Sepsis-3 phenotype (separate), AKI, respiratory deterioration,
  hemodynamic shock (indicator four, selected).

### Security

- Fail-closed production posture for the alert API: no wildcard CORS, OIDC/API-key auth, PHI-safe logging.
