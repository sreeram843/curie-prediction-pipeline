from eval.indicators.registry import list_indicators, load_rule_bundle
from eval.replay_harness.aki_runner import run_all_aki
from eval.replay_harness.governance import GovernanceConfig, PatientGovState, evaluate


def test_aki_bundle_registered_alongside_sepsis() -> None:
    indicators = {i["indicator"] for i in list_indicators()}
    assert "sepsis" in indicators
    assert "aki" in indicators
    bundle = load_rule_bundle("aki-kdigo")
    assert bundle["score"]["type"] == "aki_kdigo"
    assert "governance" in bundle


def test_aki_reuses_shared_governance_without_core_changes() -> None:
    """Same evaluate() function used by sepsis — no governance fork."""
    config = GovernanceConfig(
        trajectory_persistence_minutes=30,
        min_crossings=2,
        baseline_enabled=False,
        refractory_minutes=180,
    )
    state = PatientGovState()
    alert = {
        "score": 4,
        "tier": "urgent",
        "event_time": "2024-02-01T09:00:00+00:00",
        "patient_id": "Patient/aki-gov",
        "indicator": "aki",
    }
    d1 = evaluate(alert, state, config)
    assert d1.emit is False
    assert d1.reason == "trajectory_not_met"


def test_aki_alert_reduction_on_t2_library() -> None:
    report = run_all_aki()
    totals = report["totals"]
    assert totals["naive_alert_count"] > totals["governed_alert_count"]
    assert 0 <= totals["alert_reduction_ratio"] < 1
    by_id = {r["scenario_id"]: r for r in report["scenarios"]}
    assert by_id["t2-aki-flicker"]["governed_alert_count"] == 0
    assert by_id["t2-aki-rising"]["governed_alert_count"] >= 1
