"""CURIE-035 drift / site profile tests."""

from __future__ import annotations

import pytest

from eval.ops.drift import (
    DriftBaseline,
    SiteProfile,
    assert_not_tuning_on_locked_test,
    drift_report,
    evaluate_drift,
)


def test_drift_alarms_do_not_mutate_rules() -> None:
    baseline = DriftBaseline(
        version="b1",
        missingness_rate=0.1,
        page_rate=0.05,
        mean_score=2.0,
        unit_error_rate=0.0,
    )
    alarms = evaluate_drift(
        baseline=baseline,
        observed={
            "missingness_rate": 0.3,
            "page_rate": 0.2,
            "mean_score": 2.1,
            "unit_error_rate": 0.05,
        },
    )
    assert any(a.level == "critical" for a in alarms)
    assert all(a.mutates_rules is False for a in alarms)
    report = drift_report(site_id="site-a", baseline=baseline, alarms=alarms)
    assert report["baseline_version"] == "b1"


def test_locked_test_period_blocks_tuning() -> None:
    profile = SiteProfile(
        site_id="site-a",
        parent_bundle_id="sepsis-sofa",
        version="1.0.0",
        approver="cds-committee",
        evidence_window_start="2024-01-01",
        evidence_window_end="2024-06-01",
        rollback_target_version="0.9.0",
        locked_test_start="2024-07-01",
        locked_test_end="2024-12-31",
    )
    with pytest.raises(ValueError, match="locked test"):
        assert_not_tuning_on_locked_test(profile, as_of="2024-08-15")
    assert_not_tuning_on_locked_test(profile, as_of="2024-05-01")
    d = profile.to_dict()
    assert d["approver"] == "cds-committee"
    assert d["rollback_target_version"] == "0.9.0"
