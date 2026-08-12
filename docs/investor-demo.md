# Investor demonstration and claims matrix (CURIE-021)

**Status:** Runnable synthetic demo for diligence conversations  
**Commands:** `make investor-demo` / `python -m eval.investor_demo.runner run`  
**Frozen:** [`eval/investor_demo/frozen/demo_report.v1.json`](../eval/investor_demo/frozen/demo_report.v1.json),
[`claims_matrix.v1.json`](../eval/investor_demo/frozen/claims_matrix.v1.json)  
**UI:** Dashboard sections + `GET /investor-demo`, `GET /claims-matrix`

> Synthetic data only. Not clinical validation, not FDA evidence, not for patient care.

## What the demo shows

1. **Timeline replay** — SOFA → AKI → hypotension → SOFA escalation → watch update for one patient.  
2. **Episode merge** — five signals collapse into **one** episode with a dominant problem.  
3. **Volume comparison** — naive pages vs episode interruptive pages vs passive lane.  
4. **Evidence + rule hashes** — every step exposes `evidence_ids` and `rule_bundle_hash`.  
5. **Chaos survival** — duplicate upsert, out-of-order ingest, SQLite restart + Kafka dedupe.

Example output shape:

| Metric | Typical demo value |
|---|---|
| Signals merged | 5 → 1 episode |
| Naive alert/pages | 5 |
| Episode interruptive pages | 1 |
| Passive governed | 1 |
| Chaos | all passed |

## Claims matrix

See [`claims-matrix.md`](./claims-matrix.md). Categories:

- `demonstrated` — backed by code + frozen eval/demo artifacts  
- `under_evaluation` — protocol/harness ready, clinical/site evidence pending  
- `not_claimed` — diagnosis, outcomes, clinical validation, regulatory clearance

## Reproduce

```bash
make investor-demo
curl -s localhost:8000/investor-demo | jq '.timeline.volume, .chaos_all_passed'
curl -s localhost:8000/claims-matrix | jq '.by_status'
```
