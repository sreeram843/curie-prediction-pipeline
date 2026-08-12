# Trusted clinical-fact bridge (CURIE-022)

**Status:** Shared contract between `curie-fhir` (producer) and this pipeline (consumer)  
**Code:** `ingestion/bridge/`  
**Fixtures:** `ingestion/bridge/fixtures/` + `schema/trusted_clinical_fact.v1.schema.json`  
**Mirror:** `curie-fhir/contracts/trusted_clinical_fact/` (same fixtures)

## Envelope (v1)

Minimum fields match [`llm-workflows.md`](./llm-workflows.md):

| Field | Role |
|---|---|
| `clinical_event_time` | Bedside / chart time (ordering content) |
| `availability_time` | When the fact became knowable (leakage-safe clock) |
| `trust_status` | `candidate` \| `trusted` \| `quarantined` \| `rejected` |
| `extraction.method` | `deterministic` \| `llm` \| `human_review` \| `hybrid` |
| `validation.*` | schema / terminology / provenance / semantic_review |
| `idempotency_key` | Stable dedupe key |
| `source` | System + resource id + optional spans |

LLM metadata must **never** alter event-time ordering.

## Admission gate

`admit_trusted_fact` / `admit_and_canonicalize`:

| Input | Outcome | Mutate scoring? |
|---|---|---|
| Trusted + validation passed | `admit` | yes → `CanonicalEventEnvelope` |
| `candidate` | `quarantine` | no |
| Failed validation / missing provenance | `reject` | no |
| Unknown `schema_version` | `reject` | no |
| Future `availability_time` vs clock | `reject` | no |

Audit rows set `is_llm_derived` / `is_deterministic` so LLM and deterministic facts are distinguishable.

## Commands

```bash
make trusted-fact-bridge
python -m ingestion.bridge.validate_fixtures
pytest ingestion/bridge -q
```

## Cross-project fixture sync

Canonical fixtures live in this repo. `curie-fhir` vendors an identical copy under
`contracts/trusted_clinical_fact/` and runs the same manifest expectations. When changing
fixtures, update **both** trees in the same change set.
