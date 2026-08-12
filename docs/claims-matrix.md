# Claims matrix (CURIE-021)

**Machine-readable:** [`eval/investor_demo/frozen/claims_matrix.v1.json`](../eval/investor_demo/frozen/claims_matrix.v1.json)  
**Related:** [`investor-demo.md`](./investor-demo.md), [`manuscript-package.md`](./manuscript-package.md)

This is an **investor/demo communication matrix**, not a regulatory claims matrix.

## Demonstrated

| ID | Claim |
|---|---|
| DET-STREAM | Deterministic multi-indicator scoring with versioned rule bundles and evidence IDs |
| GOV-VOLUME | Shared governance reduces interruptive volume vs naive thresholding (offline evals + demo) |
| EPISODE-ARB | Multiple correlated signals → one episode with arbitration |
| RELIABILITY | Duplicate / out-of-order / restart survival |
| CDS-BOUNDARY | CDS Hooks / FHIR evidence presentation without rescoring |
| OPS-SEC | Auth/CORS, ops status, kill switches |

## Under evaluation

| ID | Claim |
|---|---|
| MIMIC-STAGE-B | Full MIMIC-IV Stage B locked holdout (protocol frozen; extract pending DUA) |
| SHADOW-PROD | Silent prospective hospital shadow metrics |
| LLM-STEWARD | LLM feedback classification for alert stewardship |

## Not claimed

| ID | Claim |
|---|---|
| DX-SEPSIS | Diagnoses sepsis / AKI / respiratory failure |
| OUTCOME-MORT | Improves mortality, organ failure, or time-to-antibiotics |
| CLIN-VALID | Clinically validated for patient care |
| REG-CLEAR | FDA cleared / SaMD authorized |
| SUPERIOR-NEWS | Superior to NEWS/qSOFA/vendor CDS across sites |

Do not promote a `not_claimed` item without new evidence and an explicit matrix update.
