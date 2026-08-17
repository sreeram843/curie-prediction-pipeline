# API surface

FastAPI service (`action/api/`). Run with `make api` (host dev, `:8000`) or `make up-full` (containerized).
The dashboard is a thin client over these endpoints; there is no separate API doc generator wired yet.

Authentication is fail-closed in production: see [`operations/security-observability.md`](operations/security-observability.md)
and [`operations/oidc-production-identity.md`](operations/oidc-production-identity.md). In development,
auth is off and CORS is localhost-only.

## Endpoints

### Health & ops

| Path | Auth | Purpose |
|---|---|---|
| `GET /health` | public | Liveness |
| `GET /ready` | public | Readiness + feature flags |
| `GET /ops/status` | required in prod | Active bundles, alert rate, missing-data rate, lag, DLQ depth, kill switches, alarms |
| `GET /ops/lag` | ops role in prod | Push lag / DLQ gauges |
| `GET /ops/kill-switches` | ops role in prod | Read runtime gates |
| `POST /ops/kill-switches` | ops role in prod | Patch runtime gates (persisted to `CURIE_KILL_SWITCH_PATH`) |

### Alerts

| Path | Purpose |
|---|---|
| `GET /alerts` | List alerts (bounded `limit≤1000` + `offset`) |
| `GET /alerts/{alert_id}` | Single alert |
| `GET /alerts/{alert_id}/fhir-evidence` | FHIR R4 `Reference`-shaped evidence + collection `Bundle` |
| `POST /alerts/{alert_id}/acknowledge` | Acknowledge (resolution state) |

Every alert embeds a `signal` object following the shared contract
([`contracts/signal-contract.md`](contracts/signal-contract.md)); `AlertRecord.indicator` is an open string.

### Episodes

| Path | Purpose |
|---|---|
| `GET /episodes` | List patient episodes |
| `GET /episodes/{episode_id}` | Single episode |
| `POST /episodes/{episode_id}/explain` | Additive GRP narrative (never on the alert path) |

### Indicators & plugins

| Path | Purpose |
|---|---|
| `GET /indicators` | Bundles with `scorer_installed=True` (+ `plugin_id`, `runtime_impl`) |
| `GET /plugins` | Full plugin catalog |

### CDS Hooks / standards boundary

| Path | Purpose |
|---|---|
| `GET /cds-services` | Discovery (`patient-view` service `curie-patient-view`) |
| `POST /cds-services/curie-patient-view` | Cards for `context.patientId` |
| `POST /cds-services/curie-patient-view/feedback` | Map accept/override → acknowledge |

These endpoints never change score, tier, routing, or episode state.

### Stewardship

| Path | Purpose |
|---|---|
| `GET /stewardship/taxonomy` | Feedback category list |
| `POST /stewardship/classify` | Classify free-text feedback |
| `GET /stewardship/report` | Dual-review metrics + proposals |
| `POST /stewardship/proposals/{id}/approve` | Human approval (no activation) |

### Demo / claims

| Path | Purpose |
|---|---|
| `GET /claims-matrix` | Demonstrated / under-evaluation / not-claimed tiers |

## Auth model

- **API keys** (`CURIE_API_KEYS`, `ops:…` → ops role) or **OIDC** (`CURIE_OIDC_ISSUER` +
  `CURIE_OIDC_AUDIENCE` + JWKS).
- JWT `roles` / `groups` map to `clinician` / `reviewer` / `ops` / `admin`.
- Production refuses wildcard CORS and refuses to bind `0.0.0.0` without `CURIE_TLS_TERMINATED=true`.
- Logs redact `Patient/…` / `Encounter/…` identifiers and raw tokens.

## Environment

| Variable | Meaning |
|---|---|
| `CURIE_ENV` | `development` (default) \| `production` |
| `CURIE_API_KEYS` | Comma-separated keys (`ops:…` → ops role) |
| `CURIE_CORS_ORIGINS` | Allowlist (no `*` in prod) |
| `CURIE_REQUIRE_AUTH` | Override auth requirement |
| `CURIE_OIDC_ISSUER` / `CURIE_OIDC_AUDIENCE` / `CURIE_OIDC_JWKS_URI` | OIDC verification |
| `CURIE_OIDC_INSECURE_DEV` | Payload iss/aud only — **dev only** |
| `CURIE_TLS_TERMINATED` | Reverse-proxy TLS posture |
| `CURIE_ALERT_DB` | Durable SQLite store path (`data/curie_alerts.sqlite`) |
| `CURIE_KAFKA_ALERTS_CONSUMER` | Live Kafka → API ingest (needs `.[kafka]`) |
| `CURIE_TENANT_ID` / `CURIE_SITE_ID` | Tenant/site tags |
| `CURIE_KILL_SWITCH_PATH` | Kill-switch JSON file |

Durable store details: [`operations/durable-alert-store.md`](operations/durable-alert-store.md).
