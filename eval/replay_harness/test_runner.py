from eval.replay_harness.runner import run_all


def test_alert_reduction_on_t2_library() -> None:
    report = run_all()
    totals = report["totals"]
    assert totals["naive_alert_count"] > totals["governed_alert_count"]
    assert 0 <= totals["alert_reduction_ratio"] < 1

    by_id = {r["scenario_id"]: r for r in report["scenarios"]}
    # Frozen Challenge OP (persist=0, crossings=1) may emit a single spike as watch;
    # page gate must keep flicker non-interruptive.
    assert by_id["t2-noisy-flicker"]["naive_alert_count"] >= 1
    flicker_routes = [
        a.get("routing") for a in by_id["t2-noisy-flicker"]["governed_alerts"]
    ]
    assert all(r != "interruptive" for r in flicker_routes)
    # Sustained deterioration should still surface at least one governed alert
    assert by_id["t2-abrupt-deterioration"]["governed_alert_count"] >= 1
    # Comfort care must never interrupt even when naive fires
    assert by_id["t2-comfort-care-suppressed"]["naive_alert_count"] >= 1
    assert by_id["t2-comfort-care-suppressed"]["governed_alert_count"] == 0
    # Vent / urine edge paths still get through governance when sustained
    assert by_id["t2-vent-resp-sustained"]["governed_alert_count"] >= 1
    assert by_id["t2-urine-renal-edge"]["governed_alert_count"] >= 1
