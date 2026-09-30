"""Tests for secondary fairness scorecards."""

from __future__ import annotations

from eval.mimic_study.fairness import (
    build_fairness_report,
    icd_positive_scorecard,
    lead_gated_scorecard,
)


def _row(
    *,
    onset: str | None,
    gov_times: list[str],
    icd: bool,
    stay_id: str = "1",
) -> dict:
    return {
        "stay_id": stay_id,
        "hadm_id": stay_id,
        "labels": {"sepsis3_onset": onset, "sepsis3_label_observed": True},
        "patient_days": 1.0,
        "naive_alert_count": len(gov_times),
        "governed_alert_count": len(gov_times),
        "interruptive_alert_count": 0,
        "naive_interruptive_count": 0,
        "naive_alert_times": list(gov_times),
        "governed_alert_times": list(gov_times),
        "interruptive_alert_times": [],
        "episode_count": 0,
        "icd_sepsis_positive": icd,
    }


def test_lead_gated_scorecard_drops_near_onset_hits() -> None:
    rows = [
        _row(onset="2020-01-01T12:00:00", gov_times=["2020-01-01T11:00:00"], icd=False),
        _row(
            onset="2020-01-02T12:00:00",
            gov_times=["2020-01-02T08:00:00"],
            icd=False,
            stay_id="2",
        ),
    ]
    card = lead_gated_scorecard(rows, min_lead_hours=2.0)
    assert card["primary_window_governed_sensitivity"] == 1.0
    assert card["summary"]["governed_sensitivity"] == 0.5
    assert card["summary"]["detection_window"]["min_lead_hours"] == 2.0


def test_icd_positive_scorecard_any_alert_and_overlap_window() -> None:
    rows = [
        # ICD+ with sepsis3; alert 4h before onset
        _row(
            onset="2020-01-01T12:00:00",
            gov_times=["2020-01-01T08:00:00"],
            icd=True,
            stay_id="1",
        ),
        # ICD+ only (no sepsis3 onset); any alert during stay
        _row(onset=None, gov_times=["2020-01-03T01:00:00"], icd=True, stay_id="2"),
        # ICD+ miss
        _row(onset=None, gov_times=[], icd=True, stay_id="3"),
        # sepsis3+ but not ICD
        _row(
            onset="2020-01-04T12:00:00",
            gov_times=["2020-01-04T08:00:00"],
            icd=False,
            stay_id="4",
        ),
    ]
    card = icd_positive_scorecard(rows)
    assert card["cohort"]["icd_positive"] == 3
    assert card["cohort"]["icd_and_sepsis3"] == 1
    assert card["cohort"]["icd_only"] == 2
    assert card["any_alert_during_stay"]["governed"]["sensitivity"] == 2 / 3
    assert card["sepsis3_window_among_overlap"]["governed"]["sensitivity"] == 1.0


def test_build_fairness_report_bundles_sections() -> None:
    rows = [
        _row(
            onset="2020-01-01T12:00:00",
            gov_times=["2020-01-01T08:00:00"],
            icd=True,
        )
    ]
    report = build_fairness_report(rows, min_lead_hours=2.0)
    assert report["report_id"] == "mimic_fairness_scorecards.v1"
    assert "primary_reference" in report
    assert report["lead_gated"]["summary"]["governed_sensitivity"] == 1.0
    assert report["icd_sepsis"]["cohort"]["icd_positive"] == 1
