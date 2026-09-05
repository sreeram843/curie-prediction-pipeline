"""CURIE-049: matched MIMIC/eICU protocol cohort filters."""

from __future__ import annotations

import pytest

from eval.mimic_study.completeness_check import (
    filter_eicu_protocol_cohort,
    filter_mimic_protocol_cohort,
    parse_eicu_age_years,
    seeded_sample,
)
from ingestion.adapters.eicu.paths import eicu_dir, require_eicu_dir


def test_parse_eicu_age_handles_over_89() -> None:
    assert parse_eicu_age_years("70") == 70
    assert parse_eicu_age_years("> 89") == 89
    assert parse_eicu_age_years("") is None


def test_seeded_sample_is_deterministic_and_not_prefix() -> None:
    rows = [{"id": str(i)} for i in range(20)]
    a = seeded_sample(rows, 5, seed=42)
    b = seeded_sample(rows, 5, seed=42)
    c = seeded_sample(rows, 5, seed=7)
    assert a == b
    assert a != c
    assert [r["id"] for r in a] != ["0", "1", "2", "3", "4"]


def test_eicu_protocol_cohort_filters_peds_short_and_keeps_first_visit() -> None:
    patients = [
        {
            "patientunitstayid": "1",
            "patienthealthsystemstayid": "H1",
            "age": "17",
            "unitvisitnumber": "1",
            "unitdischargeoffset": "600",
        },
        {
            "patientunitstayid": "2",
            "patienthealthsystemstayid": "H2",
            "age": "40",
            "unitvisitnumber": "1",
            "unitdischargeoffset": "100",  # < 4h
        },
        {
            "patientunitstayid": "3",
            "patienthealthsystemstayid": "H3",
            "age": "55",
            "unitvisitnumber": "2",
            "unitdischargeoffset": "600",
        },
        {
            "patientunitstayid": "4",
            "patienthealthsystemstayid": "H3",
            "age": "55",
            "unitvisitnumber": "1",
            "unitdischargeoffset": "600",
        },
        {
            "patientunitstayid": "5",
            "patienthealthsystemstayid": "H4",
            "age": "> 89",
            "unitvisitnumber": "1",
            "unitdischargeoffset": "600",
        },
    ]
    out = filter_eicu_protocol_cohort(patients)
    ids = {p["patientunitstayid"] for p in out}
    assert ids == {"4", "5"}


def test_mimic_protocol_cohort_first_stay_per_hadm() -> None:
    patients = [
        {"subject_id": "1", "anchor_age": "40"},
        {"subject_id": "2", "anchor_age": "16"},
    ]
    stays = [
        {
            "subject_id": "1",
            "hadm_id": "10",
            "stay_id": "100",
            "intime": "2150-01-01 00:00:00",
            "outtime": "2150-01-01 12:00:00",
        },
        {
            "subject_id": "1",
            "hadm_id": "10",
            "stay_id": "101",
            "intime": "2150-01-02 00:00:00",
            "outtime": "2150-01-03 00:00:00",
        },
        {
            "subject_id": "1",
            "hadm_id": "11",
            "stay_id": "102",
            "intime": "2150-02-01 00:00:00",
            "outtime": "2150-02-01 01:00:00",  # short
        },
        {
            "subject_id": "2",
            "hadm_id": "20",
            "stay_id": "200",
            "intime": "2150-01-01 00:00:00",
            "outtime": "2150-01-02 00:00:00",
        },
    ]
    out = filter_mimic_protocol_cohort(icustays=stays, patients=patients)
    ids = {s["stay_id"] for s in out}
    assert ids == {"100"}


def test_sofa_component_missing_rates() -> None:
    from eval.mimic_study.completeness_check import sofa_component_missing_rates

    results = [
        {
            "final_snapshot": {
                "completeness": "partial",
                "missing_components": ["respiration", "liver"],
            }
        },
        {"final_snapshot": {"completeness": "complete", "missing_components": []}},
        {"snapshots": [{"missing_components": ["renal"]}]},
    ]
    out = sofa_component_missing_rates(results)
    assert out["stays_scored"] == 3
    assert out["components"]["respiration"]["missing_stays"] == 1
    assert abs(out["components"]["respiration"]["missing_rate"] - 1 / 3) < 1e-9
    assert out["components"]["renal"]["missing_stays"] == 1
    assert out["components"]["cns"]["missing_stays"] == 0


def test_full_eicu_path_requires_explicit_environment(monkeypatch) -> None:
    monkeypatch.delenv("CURIE_EICU_DIR", raising=False)
    monkeypatch.delenv("EICU_DIR", raising=False)
    with pytest.raises(FileNotFoundError, match="CURIE_EICU_DIR"):
        eicu_dir()


def test_full_eicu_path_validates_required_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CURIE_EICU_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="patient.csv.gz"):
        require_eicu_dir()
    (tmp_path / "patient.csv.gz").touch()
    (tmp_path / "lab.csv.gz").touch()
    assert require_eicu_dir() == tmp_path.resolve()
