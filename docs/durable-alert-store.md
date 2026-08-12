# Durable alert store (CURIE-017)

**Status:** SQLite-backed store + Kafka manual-commit ingest  
**Code:** `action/api/app/durable_store.py`, `db.py`, `alerts_consumer.py`

## Backends

| Mode | How |
|---|---|
| Memory (default for tests) | unset `CURIE_ALERT_DB` |
| Durable SQLite | `CURIE_ALERT_DB=data/curie_alerts.sqlite` or `make api` |

Tables: `alerts`, `episodes`, `rule_versions`, `audit_log`, `kafka_dedupe`, `schema_migrations`.

## Acceptance

1. **Restart safety** — reopen the same DB path; alerts and acknowledgements remain.
2. **Kafka idempotency** — `ingest_kafka(idempotency_key=…)` dedupes; consumer uses `enable.auto.commit=false` and commits only after a successful transaction.
3. **Metrics** — `metrics()` scans the full table (no silent 10k truncation). List endpoints stay bounded (`limit≤1000` + `offset`).

## Retention

Optional: `CURIE_ALERT_RETENTION_DAYS=N` then `store.apply_retention()`.

## Run

```bash
make api   # sets CURIE_ALERT_DB=data/curie_alerts.sqlite
pytest action/api/app/test_durable_store.py -q
```
