# Trusted-fact / HL7v2 compatibility matrix (CURIE-039)

**curie-prediction-pipeline** ↔ **curie-fhir** contract.

| Schema | Version | Disposition | Mutates scoring? | Fixture (this repo) |
| --- | --- | --- | --- | --- |
| `TrustedClinicalFactEnvelope` | `1.0.0` | admit when `trust_tier=trusted` | Yes | `ingestion/bridge/fixtures/valid_trusted_*.json` |
| Candidate fact | `1.0.0` | quarantine | No | `candidate_quarantine.json` |
| Invalid / failed validation | `1.0.0` | reject | No | `failed_validation.json` |
| Missing provenance | `1.0.0` | reject | No | `missing_provenance.json` |
| Future availability time | `1.0.0` | reject until available | No | `future_availability.json` |
| Unknown schema version | — | fail closed | No | `unknown_schema.json` |
| Corrected observation | `1.0.0` | replace prior fact id | Yes (trusted only) | `corrected_trusted_observation.json` |
| Cancelled observation | `1.0.0` | tombstone; no feature write | No | `cancelled_observation.json` |
| HL7v2 ORU→trusted map (synthetic) | `1.0.0` | after Connect normalize | Only post-admit | `hl7v2_oru_to_trusted.json` |

Unknown schema versions **must fail** on both repositories. LLM-derived candidates never cross the trust boundary without deterministic validation + human/policy promotion.
