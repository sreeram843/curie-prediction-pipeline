# Runbook: production API posture

## Symptom

API won't start in production, auth is rejected, or you're about to expose it beyond localhost.

## Rules that must hold (fail-closed)

- CORS never uses `*` in production (`CURIE_CORS_ORIGINS` allowlist).
- Binding `0.0.0.0` without `CURIE_TLS_TERMINATED=true` is refused at startup.
- Auth: `CURIE_API_KEYS` and/or OIDC (`CURIE_OIDC_ISSUER` + `CURIE_OIDC_AUDIENCE` + `CURIE_OIDC_JWKS_URI`).
- Missing JWKS in production → bearer JWT path fails closed (API keys may still work).
- `CURIE_OIDC_INSECURE_DEV=true` is **dev only**.

## Diagnose

```bash
GET /ops/status           # ops-role snapshot
GET /health               # public liveness
```

Check auth-failure reason codes in logs (`expired`, `wrong audience`, `unknown kid`) — logs never contain
raw tokens or patient identifiers.

## Fix / configure

Production-shaped launch:

```bash
CURIE_ENV=production \
CURIE_API_KEYS=ops:replace-me \
CURIE_CORS_ORIGINS=https://curie.example \
CURIE_TLS_TERMINATED=true \
CURIE_ALERT_DB=data/curie_alerts.sqlite \
uvicorn action.api.app.main:app --host 127.0.0.1 --port 8000
```

Emergency: `POST /ops/kill-switches` disables ingest, interruptive/passive lanes, explain/extract, or
per-indicator gates without redeploy. Full posture: [`../operations/security-observability.md`](../operations/security-observability.md),
identity: [`../operations/oidc-production-identity.md`](../operations/oidc-production-identity.md).
