# MIMIC leakage-safe timeline harness (CURIE-015)

**Status:** Demo-schema E2E available — PhysioNet extract wiring pending DUA  
**Code:** `eval/mimic_harness/`, `ingestion/adapters/mimic/timeline.py`, `envelope.py`  
**Fixtures:** `eval/fixtures/mimic_harness/demo_schema_stays.v1.json` (synthetic; no patient PHI)  
**Protocol:** [`mimic-iv-study-protocol.md`](./mimic-iv-study-protocol.md)

> Prototype plumbing. Not clinical validation. Do not commit PhysioNet extracts.

## What it does

1. Convert MIMIC-shaped events into **canonical envelopes** with `event_time` (charttime) and `availability_time` (storetime when present).
2. Replay in **availability-time** order.
3. Score SOFA/AKI, fold episodes, attach fixture labels, summarize errors/missingness.
4. Emit a **content hash** that is identical across repeated runs.
5. Fail closed if evidence is used before availability or if discharge diagnoses enter scoring features.

## Run

```bash
make mimic-harness
# or
python -m eval.mimic_harness.runner
```

## Pins recorded in the report

| Field | Meaning |
|---|---|
| `dataset_pin` | Fixture or future PhysioNet extract hash |
| `code_pins.derived_concept_sql` | mimic-code SHA placeholder until Stage B |
| `code_pins.protocol_id` | Frozen study protocol id |
| `content_hash` | Canonical hash of the public report body |

## Leakage rules

- Labs: `availability_time = max(charttime, storetime)` when storetime exists.
- Discharge diagnoses: tracked but **never** used as scoring evidence.
- Snapshot auditor: every `evidence_id` in a score must have `availability_time <= clock`.

## Envelope note

`CanonicalEventEnvelope.availability_time` is optional for Synthea backward compatibility. When null, `effective_availability_time()` falls back to `event_time`. MIMIC envelopes always set it.
