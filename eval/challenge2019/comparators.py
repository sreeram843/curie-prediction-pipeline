"""Threshold-only SIRS / NEWS2 / qSOFA replay on Challenge stays."""

from __future__ import annotations

from typing import Any

from eval.challenge2019.bedside import BEDSIDE_COLS, hour_alerts, update_vitals
from eval.challenge2019.bootstrap import summarize_stay_metrics
from ingestion.adapters.challenge2019.loader import ChallengeHour, sepsis_onset_iculos

COMPARATOR_IDS = ("sirs", "news2", "qsofa")


def _stay_row_from_alert_hours(
    hours: list[ChallengeHour],
    alert_hours: list[int],
) -> dict[str, Any]:
    onset = sepsis_onset_iculos(hours)
    first = alert_hours[0] if alert_hours else None
    return {
        "stay_id": hours[0].stay_id if hours else "unknown",
        "hours": len(hours),
        "sepsis": onset is not None,
        "onset_iculos": onset,
        "sepsis_labels": [int(h.sepsis_label) for h in hours],
        "iculos_hours": [int(h.iculos) for h in hours],
        "naive_alert_count": len(alert_hours),
        "governed_alert_count": len(alert_hours),
        "watch_alert_count": 0,
        "interruptive_alert_count": len(alert_hours),
        "naive_alert_hours": list(alert_hours),
        "governed_alert_hours": list(alert_hours),
        "watch_alert_hours": [],
        "interruptive_alert_hours": list(alert_hours),
        "first_naive_iculos": first,
        "first_governed_iculos": first,
        "first_watch_iculos": None,
        "first_interruptive_iculos": first,
    }


def replay_bedside_stay(hours: list[ChallengeHour], comparator: str) -> dict[str, Any]:
    if comparator not in COMPARATOR_IDS:
        raise ValueError(f"Unknown comparator {comparator!r}")
    alert_key = {
        "sirs": "sirs_alert",
        "news2": "news2_alert",
        "qsofa": "qsofa_alert",
    }[comparator]
    state: dict[str, float | None] = {c: None for c in BEDSIDE_COLS}
    alert_hours: list[int] = []
    for h in hours:
        state = update_vitals(state, h.raw)
        flags = hour_alerts(state)
        if flags[alert_key]:
            alert_hours.append(h.iculos)
    return _stay_row_from_alert_hours(hours, alert_hours)


def run_comparators(
    stay_hours: list[list[ChallengeHour]],
    *,
    comparators: tuple[str, ...] = COMPARATOR_IDS,
) -> dict[str, Any]:
    """Score each comparator as a single-lane threshold policy (no governance)."""
    cards: list[dict[str, Any]] = []
    for comparator in comparators:
        rows = [replay_bedside_stay(hours, comparator) for hours in stay_hours]
        metrics = summarize_stay_metrics(rows)
        det = metrics["detection"]
        alerts = metrics["alerts"]
        cards.append(
            {
                "id": comparator,
                "title": {
                    "sirs": "SIRS ≥ 2 (Temp, HR, RR, WBC)",
                    "news2": "NEWS2 ≥ 5 (consciousness omitted)",
                    "qsofa": "Partial qSOFA ≥ 2 (RR and SBP; GCS omitted)",
                }[comparator],
                "lane": "threshold_only",
                "metrics": {
                    "sensitivity": det.get("naive_sensitivity"),
                    "emissions": alerts.get("naive_total"),
                    "nna": det.get("naive_nna"),
                    "mean_lead_hours_in_window": det.get(
                        "mean_lead_hours_governed_in_window"
                    ),
                    "fp_non_sepsis_stays": det.get("naive_fp_non_sepsis"),
                },
                "cohort": metrics["cohort"],
            }
        )
    return {
        "schema_version": "1.0.0",
        "detection_mode_id": metrics["detection_mode"] if cards else None,
        "notes": [
            "Comparators are hourly threshold-only emissions, not governed Curie output.",
            "NEWS2 consciousness/AVPU is scored 0 (Challenge has no GCS).",
            "qSOFA is partial: mentation limb omitted, so ≥2 requires both RR and SBP.",
            "Not a claim of superiority to NEWS/qSOFA in clinical practice.",
        ],
        "comparators": cards,
    }
