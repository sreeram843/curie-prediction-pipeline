# Production-shaped identity controls (CURIE-038)

This repository provides **production-shaped controls**, not a HIPAA compliance
certification. Independent assessment in a real deployment environment is still
required before any compliance claim.

## JWT / OIDC

| Env | Behavior |
| --- | --- |
| `CURIE_OIDC_ISSUER` + `CURIE_OIDC_AUDIENCE` + `CURIE_OIDC_JWKS_URI` | Verify signature (HS256/RS256), iss, aud, exp, nbf, kid |
| `CURIE_OIDC_INSECURE_DEV=true` without JWKS | Payload iss/aud only — **dev only** |
| Missing JWKS in production | Bearer JWT path fails closed (API keys may still work) |

Key rotation: unknown `kid` triggers one JWKS refresh, then reject.

## Roles

JWT `roles` / `groups` map to `clinician` / `reviewer` / `ops` / `admin`.
Tenant checks combine with `CURIE_TENANT_ID` on durable-store paths (CURIE-037).

## Logging

Do not log raw tokens or direct patient identifiers in auth failures — only
reason codes (`expired`, `wrong audience`, `unknown kid`, …).
