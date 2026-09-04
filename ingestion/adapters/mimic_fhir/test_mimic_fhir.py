"""MIMIC-IV FHIR demo converter tests — no PhysioNet dump required."""

from __future__ import annotations

from eval.mimic_harness.replay import replay_stay
from ingestion.adapters.mimic_fhir.convert import convert_fhir_resources
from ingestion.adapters.syn_icu import concepts as c


def test_fhir_resources_emit_demo_schema_and_replay() -> None:
    converted = convert_fhir_resources(
        encounters=[
            {
                "id": "icu-1",
                "subject": {"reference": "Patient/p1"},
                "period": {
                    "start": "2180-01-01T08:00:00",
                    "end": "2180-01-02T08:00:00",
                },
                "identifier": [
                    {
                        "system": "http://mimic.mit.edu/fhir/mimic/identifier/encounter-icu",
                        "value": "31269608",
                    }
                ],
            }
        ],
        labs=[
            {
                "subject": {"reference": "Patient/p1"},
                "code": {"coding": [{"code": "50912", "display": "Creatinine"}]},
                "valueQuantity": {"value": 3.1, "unit": "mg/dL"},
                "effectiveDateTime": "2180-01-01T12:00:00",
                "issued": "2180-01-01T13:00:00",
            },
            {
                "subject": {"reference": "Patient/p1"},
                "code": {"coding": [{"code": "51265", "display": "Platelet Count"}]},
                "valueQuantity": {"value": 35, "unit": "K/uL"},
                "effectiveDateTime": "2180-01-01T12:00:00",
                "issued": "2180-01-01T13:00:00",
            },
        ],
        charts=[
            {
                "encounter": {"reference": "Encounter/icu-1"},
                "code": {"coding": [{"code": "220052", "display": "Arterial Blood Pressure mean"}]},
                "valueQuantity": {"value": 50, "unit": "mmHg"},
                "effectiveDateTime": "2180-01-01T12:30:00",
                "issued": "2180-01-01T12:30:00",
            }
        ],
    )
    stay = converted["stays"][0]
    assert stay["hadm_id"] == "31269608"
    assert {lab["code"] for lab in stay["labs"]} >= {c.CREATININE_LOINC, c.PLATELETS_LOINC}
    result = replay_stay(stay)
    assert not result.errors
    assert result.signals
