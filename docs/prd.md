# PRD: Curie — Streaming Clinical Deterioration Platform

**Status:** Draft for implementation  
**Owner:** Sriram  
**Repo:** github.com/sreeram843/curie-prediction-pipeline  
**Target:** Prototype for a technical publication + evaluation as a startup direction

See [phases.md](./phases.md) for the active build plan. The full PRD content lives in the conversation/history that seeded this repo; keep this file as the product north star and update when scope changes.

## Vision

A streaming platform that ingests FHIR clinical data, computes deterioration risk in real time, and surfaces alerts a clinician will actually trust. Sepsis (via a SOFA-based score) is the first indicator. Adding indicator #2 is authoring a rule bundle, not rebuilding infrastructure.

**Core bet:** the hard, defensible part is the shared alert governance layer (trajectory, baseline, suppression, dedup, tiering, dismiss-rate feedback) — not any single score.

**Explicit non-goal for v1:** not a cleared or clinically-validated medical device. No real patients / PHI.

Clinical validation tests required before any validity claim: [`clinical-validation.md`](./clinical-validation.md).

## Stack (locked)

- Kafka + Flink
- First indicator: SOFA sepsis
- Synthea for T0–T2 testing
- JSON rule bundles (CQL = v2+)
- LLM only for extraction + post-alert narrative (v2); never on alert critical path

## Regulatory posture

Synthetic data only. Do not claim clinical validation, FDA clearance, or readiness for deployment.
