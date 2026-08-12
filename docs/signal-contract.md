# Clinical signal output contract v1.0 (CURIE-010)

Prototype only — not clinically validated.

Every indicator projects onto one top-level schema before Kafka / API / dashboard
use. Condition-specific fields belong in `extensions` and must not be required
to render an unknown `signal_type`.

**Implementation:** `eval/signals/contract.py`

## Top-level fields

| Field | Meaning |
|---|---|
| `schema_version` | Contract version (`1.0.0`) |
| `signal_id` | Stable id (alert id) |
| `signal_type` | Open string (`sofa-deterioration`, `aki`, `sepsis-3`, future…) |
| `signal_kind` | `risk` (score/stage) or `phenotype` (met/not-met) |
| `patient_id` / `encounter_id` | Subject |
| `event_time` | Score / evaluation time |
| `score` | Numeric score or phenotype 0/1 |
| `stage` | Optional ordinal stage (AKI) |
| `completeness` | `complete` \| `partial` \| `insufficient_data` |
| `severity` | Acuity tier (`none` / `watch` / `urgent` / `critical`) |
| `onset_time` | Best onset estimate when known |
| `required_inputs` / `missing_inputs` | Explicit missing-data policy |
| `evidence_ids` | Provenance |
| `exclusions` / `criteria_met` | Gate / phenotype criteria |
| `rule_bundle_id` / `rule_version` / `rule_bundle_hash` | Rule provenance |
| `resolution_state` | `open` \| `acknowledged` \| `resolved` \| `suppressed` |
| `components` | Uniform component breakdown |
| `extensions` | Indicator-specific extras only |

## Adapters

| Source | Adapter |
|---|---|
| SOFA score | `signal_from_sofa` → `sofa-deterioration` / `risk` |
| AKI score / timeline | `signal_from_aki` → `aki` / `risk` |
| Sepsis-3 phenotype | `signal_from_sepsis3` → `sepsis-3` / `phenotype` |
| Alert / Kafka dict | `signal_from_alert_record` (unknown types OK) |

## API / dashboard

- `AlertRecord.indicator` is an open string (not a closed enum).
- Each alert includes a nested `signal` object with this contract.
- The dashboard renders via `signalView()` using only contract fields — no
  per-condition branches beyond optional glyphs.

## Related

- [sofa-contract.md](./sofa-contract.md)
- [aki-contract.md](./aki-contract.md)
