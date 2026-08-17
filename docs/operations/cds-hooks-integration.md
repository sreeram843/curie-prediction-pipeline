# Standards-based integration boundary (CURIE-019)

**Status:** Presentation / feedback adapter only — not an EHR connector  
**Code:** `action/api/app/fhir_evidence.py`, `cds_hooks.py`, routes on `main.py`

## Goal

Expose FHIR-compatible evidence references and a CDS Hooks–compatible card /
feedback surface so EHR adapters can sit **outside** scoring and governance.

Hard rule: these endpoints never change score, tier, routing, or episode state
except via the existing acknowledge path on feedback.

## FHIR evidence

`GET /alerts/{alert_id}/fhir-evidence`

Returns:

- `references` — FHIR R4 `Reference`-shaped objects for each evidence id
  - Canonical `Observation/cr-1` → `{ "reference", "type", "display" }`
  - Non-canonical `lab/plt-1` → `{ "type", "identifier": { system, value }, "display" }`
- `bundle` — a FHIR `Bundle` (`type=collection`) of evidence pointers with rule
  metadata tags (not full Observation resources)

## CDS Hooks

| Path | Role |
|---|---|
| `GET /cds-services` | Discovery (`patient-view` service `curie-patient-view`) |
| `POST /cds-services/curie-patient-view` | Cards for `context.patientId` |
| `POST /cds-services/curie-patient-view/feedback` | Map accept/override → `STORE.acknowledge` |

Cards carry Curie extensions (`curieAlertId`, rule hash, evidence references).
Suggestion UUID `ack-{alert_id}` is the stable feedback key.

Example:

```bash
curl -s localhost:8000/cds-services | jq .
curl -s -X POST localhost:8000/cds-services/curie-patient-view \
  -H 'content-type: application/json' \
  -d '{"hook":"patient-view","hookInstance":"demo","context":{"patientId":"Patient/demo-1"}}'
```

## Non-goals

- SMART-on-FHIR launch, JWKS verification against an EHR, or vendor-specific CDS
  sandbox plumbing
- Replacing the dashboard acknowledge UI
- Emitting DiagnosticReport / Condition resources as clinical truth

EHR-specific adapters should consume this boundary and keep credentials, launch
context, and UI chrome in a separate deployable.
