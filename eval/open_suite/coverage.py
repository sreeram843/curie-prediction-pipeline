"""Coverage metrics for unlabeled demo-schema harness runs.

These numbers prove adapters + scorers fire on a dataset. They are not
detection performance (no onset labels) and must not be quoted as clinical
validity.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def summarize_harness_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    signals = 0
    episodes = 0
    errors = 0
    stays_with_signal = 0
    envelopes = 0
    sofa_alertable = 0
    completeness: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    max_score: float | None = None

    for row in results:
        n_signals = len(row.get("signals") or [])
        signals += n_signals
        episodes += len(row.get("episodes") or [])
        errors += len(row.get("errors") or [])
        envelopes += int(row.get("envelopes") or 0)
        if n_signals:
            stays_with_signal += 1
        snap = row.get("final_snapshot") or {}
        if snap:
            completeness[str(snap.get("completeness") or "unknown")] += 1
            score = snap.get("score")
            if isinstance(score, (int, float)):
                max_score = score if max_score is None else max(max_score, float(score))
            if snap.get("tier") not in {None, "none"}:
                sofa_alertable += 1
            for component in snap.get("missing_components") or []:
                missing[str(component)] += 1

    return {
        "metric_family": "plumbing",
        "stays_scored": len(results),
        "stays_with_signal": stays_with_signal,
        "signals": signals,
        "episodes": episodes,
        "errors": errors,
        "envelopes": envelopes,
        "sofa_alertable_final": sofa_alertable,
        "completeness": dict(completeness),
        "missing_components": dict(missing),
        "max_final_sofa": max_score,
    }


def summarize_challenge_report(report: dict[str, Any]) -> dict[str, Any]:
    detection = report.get("detection") or {}
    alerts = report.get("alerts") or {}
    cohort = report.get("cohort") or {}
    return {
        "metric_family": "detection",
        "stays_scored": report.get("stays_scored"),
        "gov_profile": report.get("gov_profile"),
        "cohort": cohort,
        "alerts": {
            "naive_total": alerts.get("naive_total"),
            "governed_total": alerts.get("governed_total"),
            "interruptive_total": alerts.get("interruptive_total"),
            "interruptive_reduction_ratio": alerts.get("interruptive_reduction_ratio"),
        },
        "detection": {
            "governed_sensitivity": detection.get("governed_sensitivity"),
            "interruptive_sensitivity": detection.get("interruptive_sensitivity"),
            "interruptive_nna": detection.get("interruptive_nna"),
            "mean_lead_hours_governed_in_window": detection.get(
                "mean_lead_hours_governed_in_window"
            ),
        },
        "challenge_utility": report.get("challenge_utility"),
    }
