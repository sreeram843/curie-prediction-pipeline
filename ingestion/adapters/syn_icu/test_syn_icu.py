"""SYN-ICU adapter tests — no xlsx or real data required.

Exercises the concept mapping and the converter→harness path using synthetic
in-memory rows, plus an end-to-end replay through the demo-schema harness.
"""

from __future__ import annotations

from pathlib import Path

from eval.mimic_harness.replay import replay_stay
from ingestion.adapters.syn_icu import concepts as c
from ingestion.adapters.syn_icu import convert as conv
from ingestion.adapters.syn_icu.convert import (
    _emit_stay,
    _gcs_and_respiration,
    _to_float,
    _ts_str,
)


def test_match_concept_labels() -> None:
    assert c.match_concept("Creatinine") == c.CREATININE
    assert c.match_concept("Platelet Count") == c.PLATELETS
    assert c.match_concept("Total Bilirubin") == c.BILIRUBIN_TOTAL
    assert c.match_concept("Arterial Blood Pressure mean") == c.MAP
    assert c.match_concept("SpO2") == c.SPO2
    assert c.match_concept("FiO2") == c.FIO2
    assert c.match_concept("GCS - Eye Opening") == c.GCS_EYE
    assert c.match_concept("GCS - Verbal Response") == c.GCS_VERBAL
    assert c.match_concept("GCS - Motor Response") == c.GCS_MOTOR
    assert c.match_concept("Not a real label") is None


def test_match_concept_khdp_syn_icu_labels() -> None:
    """Real SYN-ICU v2.0.0 d_items / d_labitems strings (Korean + English)."""
    assert c.match_concept("Creatinine(검사24시간가능)") == c.CREATININE
    assert c.match_concept("PLT(검사24시간가능)") == c.PLATELETS
    assert c.match_concept("Bilirubin, total(검사24시간가능)") == c.BILIRUBIN_TOTAL
    assert c.match_concept("SpO2 > 산소포화도") == c.SPO2
    assert c.match_concept("FIO2 > FiO2") == c.FIO2
    assert c.match_concept("mean ABP > 평균혈압(연동)") == c.MAP
    assert c.match_concept("mean BP(연동) > 평균혈압(연동)") == c.MAP
    assert c.match_concept("MAP > mean airway pressure") is None
    assert (
        c.match_concept("E(eye)/V(verbal)/M(motor) > Glasgow coma scale(eye)")
        == c.GCS_EYE
    )
    assert (
        c.match_concept("E(eye)/V(verbal)/M(motor) > Glasgow coma scale(verbal)")
        == c.GCS_VERBAL
    )
    assert (
        c.match_concept("E(eye)/V(verbal)/M(motor) > Glasgow coma scale(motor)")
        == c.GCS_MOTOR
    )


def test_match_concept_case_and_ordering() -> None:
    # "bilirubin" matches total bilirubin before any creatinine fallback
    assert c.match_concept("BILIRUBIN") == c.BILIRUBIN_TOTAL
    assert c.match_concept("  creatinine  ") == c.CREATININE


def test_build_concept_index() -> None:
    itemid_to_concept, concept_to_itemids = c.build_concept_index(
        d_labitems=[
            {"itemid": "L100", "label": "Creatinine"},
            {"itemid": "L101", "label": "Platelet Count"},
        ],
        d_items=[
            {"itemid": 200, "label": "Arterial Blood Pressure mean"},
            {"itemid": 201, "label": "SpO2"},
        ],
    )
    assert itemid_to_concept["L100"] == c.CREATININE
    assert itemid_to_concept["L101"] == c.PLATELETS
    assert itemid_to_concept["200"] == c.MAP
    assert itemid_to_concept["201"] == c.SPO2
    assert c.MAP in concept_to_itemids
    assert "200" in concept_to_itemids[c.MAP]


def test_to_float_and_ts_str() -> None:
    assert _to_float("1.5") == 1.5
    assert _to_float(None) is None
    assert _to_float("abc") is None
    assert _ts_str("2019-01-01 10:00:00") == "2019-01-01 10:00:00"


def test_gcs_summing_and_spo2_fio2_ratio() -> None:
    def row(concept, itemid, value, ts):
        return {"concept": concept, "itemid": itemid, "valuenum": value,
                "unit": "", "charttime": ts, "storetime": None}

    rows = [
        row(c.GCS_EYE, "1", 4.0, "t1"),
        row(c.GCS_VERBAL, "2", 5.0, "t1"),
        row(c.GCS_MOTOR, "3", 6.0, "t1"),
        row(c.SPO2, "4", 96.0, "t2"),
        row(c.FIO2, "5", 40.0, "t2"),
    ]
    out = _gcs_and_respiration(rows)
    gcs = next(e for e in out if e["concept"] == c.GCS_TOTAL and e["itemid"] == "gcs-sum")
    assert gcs["valuenum"] == 15.0
    ratio = next(e for e in out if e["itemid"] == "spo2-fio2")
    assert ratio["unit"] == "ratio"
    assert ratio["valuenum"] == round(96.0 / 0.40, 4)


def test_emit_stay_shape_and_harness_replay() -> None:
    stay = _emit_stay(
        stay_meta={
            "stay_id": "s1",
            "subject_id": "p1",
            "hadm_id": "h1",
            "intime": "2019-01-01 08:00:00",
            "outtime": "2019-01-02 08:00:00",
            "dischtime": "2019-01-02 08:00:00",
        },
        lab_events=[
            {
                "concept": c.CREATININE,
                "itemid": "L100",
                "valuenum": 2.5,
                "unit": "mg/dL",
                "charttime": "2019-01-01 12:00:00",
                "storetime": "2019-01-01 14:00:00",
            },
            {
                "concept": c.PLATELETS,
                "itemid": "L101",
                "valuenum": 45.0,
                "unit": "10*9/L",
                "charttime": "2019-01-01 12:00:00",
                "storetime": "2019-01-01 14:00:00",
            },
        ],
        chart_events=[
            {
                "concept": c.MAP,
                "itemid": "200",
                "valuenum": 55.0,
                "unit": "mmHg",
                "charttime": "2019-01-01 12:30:00",
                "storetime": None,
            },
        ],
        diagnoses=[{"icd_code": "A41.9", "long_title": "Sepsis"}],
    )

    assert stay["stay_id"] == "s1"
    assert stay["labels"]["sepsis3_onset"] is None
    lab_codes = {lab["code"] for lab in stay["labs"]}
    assert c.CREATININE_LOINC in lab_codes
    assert c.PLATELETS_LOINC in lab_codes
    assert any(lab["itemid"] == "L100" for lab in stay["labs"])
    assert all(cx["code"] == c.MAP_LOINC for cx in stay["charts"])
    assert stay["conditions"][0]["is_discharge_diagnosis"] is True

    # End-to-end: the emitted stay must replay through the harness and produce signals.
    result = replay_stay(stay)
    assert not result.errors
    assert result.envelopes >= 3
    assert result.signals, "deteriorating synthetic stay should emit at least one signal"


def test_index_events_routes_lab_by_subject(monkeypatch) -> None:
    rows = [
        {
            "itemid": "L100",
            "valuenum": 1.0,
            "charttime": "2019-01-01 10:00:00",
            "subject_id": "p1",
        },
        {
            "itemid": "L999",  # unmapped itemid → skipped
            "valuenum": 2.0,
            "charttime": "2019-01-01 10:00:00",
            "subject_id": "p1",
        },
    ]
    monkeypatch.setattr(conv.reader, "iter_table", lambda root, table: iter(rows))
    stay_events, counts = conv._index_events(
        Path("."),
        "syn_labevents",
        itemid_to_concept={"L100": c.CREATININE},
        stay_id_to_key={"s1": {"subject_id": "p1", "stay_id": "s1"}},
        wanted={c.CREATININE},
    )
    assert "s1" in stay_events
    assert counts[c.CREATININE] == 1
    assert len(stay_events["s1"]) == 1
