from __future__ import annotations

from eval.mimic_study.metrics import (
    decision_curve,
    fixed_lead_time_discrimination,
    ranking_metrics,
)


def test_ranking_metrics_reports_auc_auprc_and_brier() -> None:
    result = ranking_metrics(
        [0, 1, 0, 1],
        [0.1, 0.9, 0.8, 0.7],
    )
    assert result["n"] == 4
    assert result["auroc"] == 0.75
    assert result["auprc"] == (1.0 + 2 / 3) / 2
    assert result["brier"] == (0.01 + 0.01 + 0.64 + 0.09) / 4


def test_decision_curve_returns_net_benefit() -> None:
    result = decision_curve([0, 1, 0, 1], [0.1, 0.9, 0.8, 0.7], thresholds=[0.5])
    assert result == [{"threshold": 0.5, "net_benefit": 0.25, "tp": 2, "fp": 1, "n": 4}]


def test_fixed_lead_time_discrimination_uses_scores_available_at_cutoff() -> None:
    rows = [
        {
            "labels": {"sepsis3_onset": "2020-01-01T12:00:00"},
            "outtime": "2020-01-01 18:00:00",
            "risk_scores": [
                {"time": "2020-01-01T09:00:00", "score": 0.8},
                {"time": "2020-01-01T11:00:00", "score": 0.9},
            ],
        },
        {
            "labels": {"sepsis3_onset": None},
            "outtime": "2020-01-01 18:00:00",
            "risk_scores": [{"time": "2020-01-01T10:00:00", "score": 0.2}],
        },
    ]
    result = fixed_lead_time_discrimination(rows, lead_hours=[2])
    assert result[0]["n_scored"] == 2
    assert result[0]["auroc"] == 1.0
