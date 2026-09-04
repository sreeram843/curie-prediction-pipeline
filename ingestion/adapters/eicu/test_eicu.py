"""eICU demo converter tests — no PhysioNet dump required."""

from __future__ import annotations

from eval.mimic_harness.replay import replay_stay
from ingestion.adapters.eicu.convert import convert_eicu_rows
from ingestion.adapters.syn_icu import concepts as c


def test_eicu_rows_emit_demo_schema_and_replay() -> None:
    converted = convert_eicu_rows(
        patients=[
            {
                "patientunitstayid": "1",
                "uniquepid": "u1",
                "patienthealthsystemstayid": "h1",
                "unitdischargeoffset": "180",
            }
        ],
        labs=[
            {
                "patientunitstayid": "1",
                "labname": "creatinine",
                "labresult": "2.8",
                "labresultoffset": "60",
                "labmeasurenamesystem": "mg/dL",
            },
            {
                "patientunitstayid": "1",
                "labname": "platelets x 1000",
                "labresult": "40",
                "labresultoffset": "60",
                "labmeasurenamesystem": "",
            },
            {
                "patientunitstayid": "1",
                "labname": "FiO2",
                "labresult": "0.4",
                "labresultoffset": "70",
                "labmeasurenamesystem": "",
            },
        ],
        vital_periodic=[
            {
                "patientunitstayid": "1",
                "observationoffset": "65",
                "sao2": "88",
                "systemicmean": "52",
            }
        ],
        vital_aperiodic=[],
        nurse_charting=[
            {
                "patientunitstayid": "1",
                "nursingchartoffset": "80",
                "nursingchartcelltypevallabel": "Glasgow coma score",
                "nursingchartcelltypevalname": "GCS Total",
                "nursingchartvalue": "8",
            }
        ],
    )
    assert converted["stays"]
    stay = converted["stays"][0]
    assert stay["stay_id"] == "1"
    assert stay["labels"]["sepsis3_onset"] is None
    lab_concepts = {lab["code"] for lab in stay["labs"]}
    assert c.CREATININE_LOINC in lab_concepts
    assert c.PLATELETS_LOINC in lab_concepts
    result = replay_stay(stay)
    assert not result.errors
    assert result.signals
