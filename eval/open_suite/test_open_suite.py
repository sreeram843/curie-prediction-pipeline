"""Open-suite coverage + probe tests (no large dumps required)."""

from __future__ import annotations

from eval.open_suite.coverage import summarize_challenge_report, summarize_harness_results
from eval.open_suite.runner import probe
from ingestion.adapters.demo_schema import downsample_hourly


def test_downsample_hourly_keeps_last_in_hour() -> None:
    events = [
        {"concept": "map", "itemid": "a", "charttime": "2019-01-01 10:05:00", "valuenum": 1},
        {"concept": "map", "itemid": "b", "charttime": "2019-01-01 10:55:00", "valuenum": 2},
        {"concept": "map", "itemid": "c", "charttime": "2019-01-01 11:01:00", "valuenum": 3},
        {"concept": "spo2", "itemid": "d", "charttime": "2019-01-01 10:10:00", "valuenum": 90},
    ]
    out = downsample_hourly(events)
    by_item = {e["itemid"]: e["valuenum"] for e in out}
    assert by_item["b"] == 2
    assert "a" not in by_item
    assert by_item["c"] == 3
    assert by_item["d"] == 90


def test_summarize_harness_results() -> None:
    metrics = summarize_harness_results(
        [
            {
                "signals": [{"signal_type": "sofa-deterioration"}],
                "episodes": [{}],
                "errors": [],
                "envelopes": 4,
                "final_snapshot": {
                    "completeness": "partial",
                    "score": 6,
                    "tier": "watch",
                    "missing_components": ["cns"],
                },
            },
            {
                "signals": [],
                "episodes": [],
                "errors": ["x"],
                "envelopes": 1,
                "final_snapshot": None,
            },
        ]
    )
    assert metrics["metric_family"] == "plumbing"
    assert metrics["stays_scored"] == 2
    assert metrics["stays_with_signal"] == 1
    assert metrics["sofa_alertable_final"] == 1
    assert metrics["errors"] == 1
    assert metrics["missing_components"]["cns"] == 1


def test_summarize_challenge_report() -> None:
    summary = summarize_challenge_report(
        {
            "stays_scored": 200,
            "gov_profile": "accuracy",
            "cohort": {"sepsis_stays": 20},
            "alerts": {"interruptive_reduction_ratio": 0.2, "naive_total": 100},
            "detection": {
                "governed_sensitivity": 0.8,
                "mean_lead_hours_governed_in_window": 4.0,
            },
            "challenge_utility": {"governed": {"normalized_utility": 0.1}},
        }
    )
    assert summary["metric_family"] == "detection"
    assert summary["detection"]["governed_sensitivity"] == 0.8
    assert summary["detection"]["mean_lead_hours_governed_in_window"] == 4.0


def test_probe_lists_expected_ids() -> None:
    ids = {row["id"] for row in probe()}
    assert ids == {
        "challenge-2019",
        "mimic-iv-demo",
        "mimic-iv-fhir-demo",
        "eicu-crd-demo",
        "syn-icu",
        "synthea",
    }
