"""Tests for the MIMIC cohort-flow audit (Phase A scaffolding)."""

from __future__ import annotations

import csv
import gzip
from pathlib import Path

from eval.mimic_study.cohort_flow import (
    _parse_ts,
    _split_for_intime,
    apply_cohort,
)
from eval.mimic_study.protocol import load_protocol


def _write(root: Path, rel: str, fields: list[str], rows: list[list[str]]) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(fields)
        w.writerows(rows)


def _make_root(tmp: Path) -> Path:
    root = tmp / "mimic"
    _write(
        root,
        "hosp/patients.csv.gz",
        ["subject_id", "gender", "anchor_age", "anchor_year", "anchor_year_group"],
        [
            ["1", "F", "70", "2015", "2014 - 2016"],
            ["2", "M", "16", "2015", "2014 - 2016"],
            ["3", "F", "65", "2017", "2017 - 2019"],
            ["4", "M", "60", "2015", "2014 - 2016"],
        ],
    )
    _write(
        root,
        "hosp/admissions.csv.gz",
        ["subject_id", "hadm_id", "admittime"],
        [["1", "h1", "2015-01-01 00:00:00"], ["2", "h2", "2015-01-01 00:00:00"]],
    )
    _write(
        root,
        "icu/icustays.csv.gz",
        [
            "subject_id",
            "hadm_id",
            "stay_id",
            "intime",
            "outtime",
            "first_careunit",
        ],
        [
            ["1", "h1", "s1", "2015-01-01 01:00:00", "2015-01-01 12:00:00", "MICU"],
            ["1", "h1", "s2", "2015-01-02 01:00:00", "2015-01-02 12:00:00", "MICU"],
            ["2", "h2", "s3", "2015-01-01 01:00:00", "2015-01-01 12:00:00", "PICU"],
            ["1", "h1", "s4", "2015-01-01 01:00:00", "2015-01-01 02:00:00", "MICU"],
            ["1", "", "s5", "2015-01-01 01:00:00", "2015-01-01 12:00:00", "MICU"],
            ["1", "h6", "s6", "bad", "2015-01-01 12:00:00", "MICU"],
            ["3", "h3", "s7", "2017-06-01 01:00:00", "2017-06-01 12:00:00", "OR"],
            ["4", "h8", "s8", "2015-02-01 01:00:00", "2015-02-01 02:00:00", "MICU"],
        ],
    )
    _write(
        root,
        "hosp/diagnoses_icd.csv.gz",
        ["subject_id", "hadm_id", "icd_code", "icd_version"],
        [["1", "h1", "585.6", "9"], ["4", "h4", "Z515", "10"]],
    )
    return root


def test_cohort_flow_denominators(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    out = apply_cohort(root)
    flow = out["cohort_flow"]
    assert flow["patients_source"] == 4
    assert flow["icustays_source"] == 8
    assert flow["excluded_missing_hadm_id"] == 1
    assert flow["excluded_pediatric_or_unknown_age"] == 1
    assert flow["excluded_later_icu_stays_same_admission"] == 2
    assert flow["excluded_invalid_intime_outtime"] == 1
    assert flow["excluded_los_under_4h"] == 1
    assert flow["final_cohort_stays"] == 2

    stays = out["stays"]
    by_id = {s["stay_id"]: s for s in stays}
    assert set(by_id) == {"s1", "s7"}
    assert by_id["s1"]["esrd_on_dialysis"] is True
    assert by_id["s7"]["or_transfer_gap_flagged"] is True
    assert by_id["s7"]["comfort_care"] is False
    splits = out["splits"]
    assert splits["status"] == "suspended_pending_protocol_amendment"
    assert splits["anchor_year_group_counts"] == {"2014 - 2016": 1, "2017 - 2019": 1}


def test_cohort_without_diagnoses_file(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    (root / "hosp" / "diagnoses_icd.csv.gz").unlink()
    out = apply_cohort(root)
    assert out["cohort_flow"]["final_cohort_stays"] == 2
    assert out["declared_handling"]["esrd_on_dialysis"]["flagged_stays"] == 0


def test_split_assignment_boundaries() -> None:
    assert _split_for_intime(_parse_ts("2016-12-31 23:59:59")) == "development"
    assert _split_for_intime(_parse_ts("2017-01-01 00:00:00")) == "calibration"
    assert _split_for_intime(_parse_ts("2019-12-31 23:59:59")) == "test"
    assert _split_for_intime(_parse_ts("2020-01-01 00:00:00")) == "outside_split_ranges"


def test_parse_ts_variants() -> None:
    assert _parse_ts("2015-01-01 01:02:03") is not None
    assert _parse_ts("2015-01-01") is not None
    assert _parse_ts("") is None
    assert _parse_ts("garbage") is None


def test_cohort_v2_assigns_anchor_year_group_splits(tmp_path: Path) -> None:
    out = apply_cohort(_make_root(tmp_path), protocol=load_protocol(version="v2"))

    by_id = {row["stay_id"]: row for row in out["stays"]}
    assert by_id["s1"]["split_id"] == "calibration"
    assert by_id["s7"]["split_id"] == "test"
    assert out["protocol_id"] == "mimic-iv-governance-study.v2"
    assert out["splits"]["status"] == "frozen"
