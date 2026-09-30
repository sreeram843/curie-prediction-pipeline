"""Tests for the frozen JBHI publication aggregates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.mimic_harness.replay import stable_report_hash
from eval.mimic_study.protocol import load_protocol
from eval.mimic_study.publication_aggregates import (
    MIN_CELL,
    OUTPUT_PATH,
    _lead_hours,
    build_cohort_flow,
    build_subgroups,
)


def _stay(stay_id: str, subject: str, hadm: str, intime: str, outtime: str) -> dict:
    extra = {"hadm_id": hadm, "intime": intime, "outtime": outtime}
    return {"stay_id": stay_id, "subject_id": subject, "hadm_id": hadm, "extra_json": extra}


def test_cohort_flow_keeps_later_eligible_stay_when_first_is_short() -> None:
    patients = {
        "p1": {"anchor_age": 60, "anchor_year_group": "2017 - 2019"},
        "p2": {"anchor_age": 10, "anchor_year_group": "2017 - 2019"},
        "p3": {"anchor_age": 70, "anchor_year_group": "2020 - 2022"},
    }
    stays = [
        # admission h1: first stay 2h (too short), later stay 10h -> kept under v2 only
        _stay("s1", "p1", "h1", "2100-01-01 00:00:00", "2100-01-01 02:00:00"),
        _stay("s2", "p1", "h1", "2100-01-02 00:00:00", "2100-01-02 10:00:00"),
        _stay("s3", "p2", "h2", "2100-01-01 00:00:00", "2100-01-02 00:00:00"),  # pediatric
        _stay("s4", "p3", "h3", "2100-01-01 00:00:00", "2100-01-02 00:00:00"),  # outside
        _stay("s5", "p1", "h4", "2100-02-01 00:00:00", ""),  # invalid time
    ]
    flow = build_cohort_flow(stays, patients, protocol=load_protocol(version="v2"))
    assert flow["icustays_source"] == 5
    assert flow["excluded_age_under_18_or_unknown"] == 1
    assert flow["excluded_invalid_intime_outtime"] == 1
    assert flow["excluded_los_under_4h"] == 1
    assert flow["protocol_cohort_stays"] == 2
    assert flow["split_counts"]["test"] == 1
    assert flow["split_counts"]["outside_protocol_anchor_groups"] == 1
    recon = flow["reconciliation_with_v1_audit"]
    assert recon["stays_selected_only_under_v2_rule"] == 1
    assert recon["stays_selected_only_under_v1_rule"] == 0


def test_lead_hours_uses_earliest_in_window_alert_and_ignores_out_of_window() -> None:
    row = {
        "labels": {"sepsis3_onset": "2100-01-01T12:00:00"},
        "governed_alert_times": [
            "2099-12-31T20:00:00",  # 16h before: outside window
            "2100-01-01T11:00:00",  # 1h lead
            "2100-01-01T09:00:00",  # 3h lead (earliest in window)
            "2100-01-01T20:00:00",  # 8h after: outside window
        ],
    }
    assert _lead_hours(row, "governed_alert_times") == 3.0
    assert _lead_hours({"labels": {"sepsis3_onset": None}}, "governed_alert_times") is None


def test_subgroups_suppress_small_cells() -> None:
    unit = {"s3": True, "icd": False, "lead_gov": 3.0, "lead_page": None, "any_gov": True,
            "any_page": False, "pages": 1, "days": 1.0, "sex": "F", "age_band": "18-44"}
    units = [dict(unit) for _ in range(MIN_CELL + 5)] + [dict(unit, sex="M")]
    out = build_subgroups(units)
    assert out["sex"]["female"]["governed_sensitivity"] == 1.0
    assert out["sex"]["male"]["stays"] is None
    assert out["sex"]["male"]["governed_sensitivity"] is None


@pytest.mark.skipif(not OUTPUT_PATH.exists(), reason="publication aggregates not frozen")
def test_frozen_publication_aggregates_hash_and_consistency() -> None:
    body = json.loads(OUTPUT_PATH.read_text())
    recorded = body.pop("content_hash")
    assert stable_report_hash(body) == recorded
    flow = body["cohort_flow"]
    splits = flow["split_counts"]
    assert flow["study_stays_all_splits"] == (
        splits["development"] + splits["calibration"] + splits["test"]
    )
    assert flow["protocol_cohort_stays"] == (
        flow["study_stays_all_splits"] + splits["outside_protocol_anchor_groups"]
    )
    manifest = json.loads(
        (Path(OUTPUT_PATH).parent / "study_manifest.v3.json").read_text()
    )
    assert body["test_ablations"] == manifest["test_ablations"]
    assert splits["test"] == manifest["test_primary"]["stays"]
    timing = body["test_timing_and_labels"]
    assert timing["labeled_positive"] == manifest["test_primary"]["labeled_positive"]
