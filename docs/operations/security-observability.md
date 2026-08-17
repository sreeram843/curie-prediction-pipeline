# Security and observability boundaries (CURIE-018)

**Status:** Production fail-closed posture for the alert API  
**Code:** `action/api/app/security.py`, `ops.py`, `logging_config.py`, `main.py`

## Acceptance posture

1. **No internet-safe wildcard** — CORS never uses `*` in production; development defaults to localhost origins only. Production requires `CURIE_API_KEYS` and/or `CURIE_OIDC_ISSUER` when auth is required; binding `0.0.0.0` without `CURIE_TLS_TERMINATED=true` is refused at startup.
2. **Operator visibility** — `GET /ops/status` reports active rule bundles, alert rate, missing-data rate, Kafka/Flink lag gauges, DLQ depth, kill switches, and alarms.
3. **Kill switches without redeploy** — `POST /ops/kill-switches` (persisted to `CURIE_KILL_SWITCH_PATH`) can disable ingest, interruptive/passive lanes, explain/extract, or per-indicator / per-bundle gates.

## Endpoints

| Path | Auth | Purpose |
|---|---|---|
| `/health` | public | Liveness |
| `/ready` | public | Readiness + feature flags |
| `/ops/status` | required in prod | Operator snapshot |
| `/ops/kill-switches` | ops role in prod | Get/patch runtime gates |
| `/ops/lag` | ops role in prod | Push lag / DLQ gauges |

## Environment

| Variable | Meaning |
|---|---|
| `CURIE_ENV` | `development` (default) \| `production` |
| `CURIE_CORS_ORIGINS` | Comma-separated allowlist (no `*` in prod) |
| `CURIE_API_KEYS` | Comma-separated keys (`ops:…` → ops role) |
| `CURIE_REQUIRE_AUTH` | Override auth requirement |
| `CURIE_OIDC_ISSUER` / `CURIE_OIDC_AUDIENCE` | Optional OIDC (dev JWT decode behind `CURIE_OIDC_INSECURE_DEV`) |
| `CURIE_TLS_TERMINATED` | Reverse-proxy TLS posture |
| `CURIE_TENANT_ID` / `CURIE_SITE_ID` | Tenant/site tags |
| `CURIE_KILL_SWITCH_PATH` | Kill-switch JSON file (default `data/curie_kill_switches.json`) |
| `CURIE_BIND_HOST` | Documented bind host for production gate |

## Local vs production

```bash
# Local prototype (localhost CORS, auth off)
make api

# Production-shaped
CURIE_ENV=production \
CURIE_API_KEYS=ops:replace-me \
CURIE_CORS_ORIGINS=https://curie.example \
CURIE_TLS_TERMINATED=true \
CURIE_ALERT_DB=data/curie_alerts.sqlite \
uvicorn action.api.app.main:app --host 127.0.0.1 --port 8000
```

PHI-safe JSON logging redacts `Patient/…` and `Encounter/…` identifiers from log lines.
