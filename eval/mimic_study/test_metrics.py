from __future__ import annotations

from eval.mimic_study.metrics import (
    decision_curve,
    fixed_lead_time_discrimination,
    ranking_metrics,
    summarize_cohort,
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


def test_ranking_metrics_auprc_is_invariant_to_tied_score_order() -> None:
    forward = ranking_metrics([1, 0], [0.5, 0.5])
    reversed_labels = ranking_metrics([0, 1], [0.5, 0.5])
    assert forward["auprc"] == reversed_labels["auprc"] == 0.5


def test_ranking_metrics_groups_ties_across_larger_cohort() -> None:
    # One clear positive at 0.9, then a tied group of 4 at 0.5 (2 positives, 2 negatives).
    result = ranking_metrics(
        [1, 1, 0, 0, 1],
        [0.9, 0.5, 0.5, 0.5, 0.5],
    )
    # Precision for the tied group uses cumulative TP/total after the whole group
    # is included (3 TP / 5 total = 0.6), applied to each of its 2 positives —
    # not the within-group fraction alone. Rank-1 positive contributes 1/1.
    expected = (1.0 + 0.6 + 0.6) / 3
    assert result["auprc"] == expected


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


def test_explicit_unknown_label_is_not_counted_as_negative() -> None:
    result = summarize_cohort(
        [
            {
                "labels": {"sepsis3_onset": None, "sepsis3_label_observed": False},
                "patient_days": 1,
                "episode_count": 2,
                "interruptive_alert_count": 2,
                "interruptive_alert_times": [],
            }
        ]
    )
    assert result["unknown_label_stays"] == 1
    assert result["labeled_positive"] == 0
    assert result["false_episodes_label_negative"] == 0
