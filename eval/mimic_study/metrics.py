"""Detection and burden metrics for the MIMIC demo-schema study (CURIE-016)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from eval.mimic_study.protocol import load_protocol


def _parse_dt(raw: str | datetime | None) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


def in_detection_window(
    alert_time: datetime,
    onset: datetime,
    *,
    before_hours: float = 12.0,
    after_hours: float = 6.0,
) -> bool:
    delta_h = (alert_time - onset).total_seconds() / 3600.0
    return -before_hours <= delta_h <= after_hours


def stay_detection(
    *,
    labels: dict[str, Any],
    alert_times: list[datetime],
    before_hours: float = 12.0,
    after_hours: float = 6.0,
) -> dict[str, Any]:
    onset = _parse_dt(labels.get("sepsis3_onset"))
    labeled = onset is not None
    if not labeled:
        return {
            "labeled_positive": False,
            "detected": False,
            "lead_hours": None,
        }
    hits = [t for t in alert_times if in_detection_window(t, onset, before_hours=before_hours, after_hours=after_hours)]  # noqa: E501
    if not hits:
        return {"labeled_positive": True, "detected": False, "lead_hours": None}
    first = min(hits)
    lead = (onset - first).total_seconds() / 3600.0
    return {"labeled_positive": True, "detected": True, "lead_hours": lead}


def summarize_cohort(
    stay_rows: list[dict[str, Any]],
    *,
    before_hours: float | None = None,
    after_hours: float | None = None,
) -> dict[str, Any]:
    proto = load_protocol()
    timing = proto.get("detection_timing") or {}
    before = float(before_hours if before_hours is not None else timing.get("before_hours", 12))
    after = float(after_hours if after_hours is not None else timing.get("after_hours", 6))

    labeled = 0
    detected_naive = 0
    detected_gov = 0
    detected_page = 0
    lead_gov: list[float] = []
    naive_alerts = 0
    gov_alerts = 0
    page_alerts = 0
    episodes = 0
    false_episodes = 0
    patient_days = 0.0
    missing_partial = 0

    for row in stay_rows:
        labels = row.get("labels") or {}
        pdays = float(row.get("patient_days") or 1.0)
        patient_days += pdays
        naive_alerts += int(row.get("naive_alert_count") or 0)
        gov_alerts += int(row.get("governed_alert_count") or 0)
        page_alerts += int(row.get("interruptive_alert_count") or 0)
        episodes += int(row.get("episode_count") or 0)
        if row.get("completeness_partial"):
            missing_partial += 1

        det_n = stay_detection(
            labels=labels,
            alert_times=[_parse_dt(t) for t in row.get("naive_alert_times") or [] if _parse_dt(t)],
            before_hours=before,
            after_hours=after,
        )
        det_g = stay_detection(
            labels=labels,
            alert_times=[_parse_dt(t) for t in row.get("governed_alert_times") or [] if _parse_dt(t)],  # noqa: E501
            before_hours=before,
            after_hours=after,
        )
        det_p = stay_detection(
            labels=labels,
            alert_times=[
                _parse_dt(t) for t in row.get("interruptive_alert_times") or [] if _parse_dt(t)
            ],
            before_hours=before,
            after_hours=after,
        )
        if det_n["labeled_positive"]:
            labeled += 1
            if det_n["detected"]:
                detected_naive += 1
            if det_g["detected"]:
                detected_gov += 1
            if det_p["detected"]:
                detected_page += 1
            if det_g["lead_hours"] is not None:
                lead_gov.append(float(det_g["lead_hours"]))
            if not det_n["labeled_positive"]:
                pass
        else:
            if int(row.get("episode_count") or 0) > 0:
                false_episodes += 1

    def _sens(num: int) -> float | None:
        return None if labeled == 0 else num / labeled

    naive_sens = _sens(detected_naive)
    gov_sens = _sens(detected_gov)
    page_sens = _sens(detected_page)
    reduction = None if naive_alerts == 0 else page_alerts / naive_alerts
    # Prefer interruptive vs naive interruptive if available
    naive_pages = sum(int(r.get("naive_interruptive_count") or 0) for r in stay_rows)
    if naive_pages > 0:
        reduction = page_alerts / naive_pages

    pe1 = False
    if gov_sens is not None and naive_sens is not None:
        pe1 = gov_sens >= naive_sens - 0.10 or gov_sens >= 0.70
    elif gov_sens is not None:
        pe1 = gov_sens >= 0.70

    pe2 = reduction is not None and reduction <= 0.25

    return {
        "stays": len(stay_rows),
        "labeled_positive": labeled,
        "naive_sensitivity": naive_sens,
        "governed_sensitivity": gov_sens,
        "interruptive_sensitivity": page_sens,
        "naive_alerts": naive_alerts,
        "governed_alerts": gov_alerts,
        "interruptive_alerts": page_alerts,
        "naive_interruptive_alerts": naive_pages,
        "interruptive_reduction_ratio": reduction,
        "alerts_per_100_patient_days": (
            None if patient_days <= 0 else 100.0 * gov_alerts / patient_days
        ),
        "interruptive_per_100_patient_days": (
            None if patient_days <= 0 else 100.0 * page_alerts / patient_days
        ),
        "episodes": episodes,
        "false_episodes_label_negative": false_episodes,
        "episode_per_100_patient_days": (
            None if patient_days <= 0 else 100.0 * episodes / patient_days
        ),
        "interruptive_nna": (
            None if detected_page == 0 else page_alerts / detected_page
        ),
        "mean_in_window_lead_hours": (
            None if not lead_gov else sum(lead_gov) / len(lead_gov)
        ),
        "partial_completeness_stays": missing_partial,
        "patient_days": patient_days,
        "meets_pe1": pe1,
        "meets_pe2": pe2,
        "detection_window": {"before_hours": before, "after_hours": after},
    }
