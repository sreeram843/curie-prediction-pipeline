# Curie Prediction Pipeline

Streaming platform that ingests FHIR clinical data, computes deterioration risk in real time, and surfaces
alerts a clinician will actually trust.

> **Prototype only.** Synthetic data, no real PHI, not clinically validated, not FDA-cleared, not for
> patient care. See [Regulatory posture](#regulatory-posture).

## The core bet

The defensible part is not any single score — it is the shared **alert governance layer** that decides
whether a computed risk is worth interrupting a clinician for: trajectory/persistence, baseline-relative
scoring, context suppression, dedup + refractory windows, and acuity tiering. Every indicator inherits
that layer. The LLM ("GRP") only adds narrative on top of an alert that already fired; it is **never** on
the alert-firing path.

## Quick start

```bash
pip install -e ".[dev]"    # + [api] for the dashboard, [kafka] for live Kafka consumers
make up                    # Kafka + Flink + Kafka UI (Kafka UI :8080, Flink UI :8081)
make test                  # pytest
make lint                  # ruff
```

Full commands (replay, parity, rules, Flink tests, optional MIMIC/Challenge evals):
[`AGENTS.md`](AGENTS.md).

## Where everything lives

| Want to know… | Read |
|---|---|
| How the system is shaped and why | [`docs/architecture.md`](docs/architecture.md) |
| What the API exposes | [`docs/api.md`](docs/api.md) |
| Why a decision was made this way | [`docs/adr/`](docs/adr/) (Architecture Decision Records) |
| What to do when something breaks | [`docs/runbooks/`](docs/runbooks/) |
| How each indicator is scored | [`docs/contracts/`](docs/contracts/) |
| Governance, episodes, event-time policies | [`docs/governance/`](docs/governance/) |
| Security, store, integrations, identity | [`docs/operations/`](docs/operations/) |
| Clinical validation + study protocols | [`docs/research/`](docs/research/) |
| The active engineering backlog | [`docs/implementation-backlog.md`](docs/implementation-backlog.md) |
| Cross-project LLM workflow roadmap | [`docs/llm-workflows.md`](docs/llm-workflows.md) |
| How to contribute | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| What changed | [`CHANGELOG.md`](CHANGELOG.md) |

## Stack

Kafka (event backbone) → Flink (event-time stream processing) → versioned JSON rule bundles → shared alert
governance → FastAPI/dashboard. Test data: Synthea (integration only), PhysioNet Challenge 2019 + MIMIC-IV
demo (optional evals). LLM (v2): extraction + post-alert narrative only.

## Regulatory posture

This prototype does not touch real patients or real PHI. Do not describe it as clinically validated,
FDA-cleared, or ready for deployment. Clinical validity is explicitly out of scope until the stages in
[`docs/research/clinical-validation.md`](docs/research/clinical-validation.md) are completed under
appropriate IRB/DUA oversight.

## Status

Phases 0–3 complete: SOFA deterioration, Sepsis-3 (separate), AKI, respiratory, and hemodynamic-shock
indicators on a shared governance layer. See the backlog for what's next.
