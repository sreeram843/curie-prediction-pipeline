"""Tests for the memory-safe Stage B runner helpers."""

from __future__ import annotations

from eval.mimic_study.protocol import load_protocol
from eval.mimic_study.stage_b_run import bootstrap_primary_metrics, miss_analysis


def test_miss_analysis_counts_undetected_positives() -> None:
    protocol = load_protocol(version="v2")
    rows = [
        {
            "stay_id": "1",
            "labels": {"sepsis3_onset": "2020-01-01T12:00:00"},
            "governed_alert_times": [],
            "naive_alert_times": ["2020-01-01T10:00:00"],
            "naive_alert_count": 1,
            "governed_alert_count": 0,
            "completeness_partial": False,
        },
        {
            "stay_id": "2",
            "labels": {"sepsis3_onset": "2020-01-01T12:00:00"},
            "governed_alert_times": ["2020-01-01T11:00:00"],
            "naive_alert_times": ["2020-01-01T11:00:00"],
            "naive_alert_count": 1,
            "governed_alert_count": 1,
            "completeness_partial": False,
        },
        {
            "stay_id": "3",
            "labels": {"sepsis3_onset": None},
            "governed_alert_times": [],
            "naive_alert_times": [],
            "naive_alert_count": 0,
            "governed_alert_count": 0,
            "completeness_partial": True,
        },
    ]
    out = miss_analysis(rows, protocol=protocol)
    assert out["labeled_positive"] == 2
    assert out["detected_governed"] == 1
    assert out["miss_count"] == 1
    assert out["misses"][0]["stay_id"] == "1"
    assert out["misses"][0]["naive_detected"] is True


def test_bootstrap_primary_metrics_seed_stable() -> None:
    protocol = load_protocol(version="v2")
    rows = [
        {
            "stay_id": str(i),
            "labels": {"sepsis3_onset": "2020-01-01T12:00:00" if i % 2 == 0 else None},
            "patient_days": 1.0,
            "naive_alert_count": 10,
            "naive_interruptive_count": 8,
            "naive_alert_times": ["2020-01-01T10:00:00"] if i % 2 == 0 else [],
            "governed_alert_count": 2,
            "governed_alert_times": ["2020-01-01T10:00:00"] if i % 2 == 0 else [],
            "interruptive_alert_count": 1,
            "interruptive_alert_times": ["2020-01-01T10:00:00"] if i % 2 == 0 else [],
            "episode_count": 1,
            "completeness_partial": False,
        }
        for i in range(20)
    ]
    a = bootstrap_primary_metrics(rows, protocol=protocol)
    b = bootstrap_primary_metrics(rows, protocol=protocol)
    assert a["governed_sensitivity"]["point"] == b["governed_sensitivity"]["point"]
    assert a["governed_sensitivity"]["lo_2p5"] == b["governed_sensitivity"]["lo_2p5"]
    assert a["n_replicates"] == 1000
