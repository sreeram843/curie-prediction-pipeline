"""Fairer grading scorecards for MIMIC Stage B (secondary analyses).

Two independent checks beside the primary Sepsis-3 ``window_m12_p6`` PE:

1. Lead-time gate — count a catch only if the first in-window alert is at least
   ``min_lead_hours`` before onset (default 2h).
2. ICD sepsis scorecard — sensitivity among stays whose hospital admission has a
   pinned discharge sepsis ICD code (independent of SOFA-derived labels).

Neither scorecard replaces PE-1 / PE-2.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from eval.mimic_study.metrics import stay_detection, summarize_cohort
from eval.mimic_study.protocol import load_protocol


def _parse_dt(raw: str | datetime | None) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _alert_times(row: dict[str, Any], field: str) -> list[datetime]:
    out: list[datetime] = []
    for raw in row.get(field) or []:
        parsed = _parse_dt(raw)
        if parsed is not None:
            out.append(parsed)
    return out


def lead_gated_scorecard(
    stay_rows: list[dict[str, Any]],
    *,
    min_lead_hours: float = 2.0,
    protocol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Primary Sepsis-3 denominator with a stricter pre-onset lead requirement."""
    proto = protocol or load_protocol()
    summary = summarize_cohort(
        stay_rows,
        protocol=proto,
        min_lead_hours=min_lead_hours,
    )
    primary = summarize_cohort(stay_rows, protocol=proto, min_lead_hours=0.0)
    lead_tag = (
        str(int(min_lead_hours))
        if float(min_lead_hours).is_integer()
        else str(min_lead_hours)
    )
    return {
        "scorecard_id": f"window_m12_p6_lead{lead_tag}",
        "role": "secondary_sensitivity",
        "denominator": "sepsis3_onset labeled-positive stays",
        "rule": (
            f"Alert counts only if event_time ∈ [onset−12h, onset−{min_lead_hours}h] "
            f"(min_lead_hours={min_lead_hours})"
        ),
        "min_lead_hours": float(min_lead_hours),
        "primary_window_governed_sensitivity": primary.get("governed_sensitivity"),
        "summary": summary,
    }


def icd_positive_scorecard(
    stay_rows: list[dict[str, Any]],
    *,
    protocol: dict[str, Any] | None = None,
    min_lead_hours: float = 0.0,
) -> dict[str, Any]:
    """Scorecard on ICD+ stays (independent diagnosis-code answer key).

    Metrics:
    - ``any_alert_during_stay``: ≥1 governed/naive alert anytime in the stay
      (ICD has no bedside onset; this is the primary ICD estimand).
    - ``sepsis3_window_among_overlap``: among ICD+ stays that also have
      ``sepsis3_onset``, use the usual detection window (optionally lead-gated).
    """
    proto = protocol or load_protocol()
    timing = proto.get("detection_timing") or {}
    before = float(timing.get("before_hours", 12))
    after = float(timing.get("after_hours", 6))
    min_lead = float(min_lead_hours)

    icd_rows = [r for r in stay_rows if r.get("icd_sepsis_positive")]
    sepsis3_pos = 0
    icd_only = 0
    overlap = 0
    for row in stay_rows:
        labels = row.get("labels") or {}
        has_s3 = labels.get("sepsis3_onset") is not None
        has_icd = bool(row.get("icd_sepsis_positive"))
        if has_s3:
            sepsis3_pos += 1
        if has_icd and has_s3:
            overlap += 1
        elif has_icd and not has_s3:
            icd_only += 1

    def _any_alert_rate(field: str) -> dict[str, Any]:
        if not icd_rows:
            return {"n": 0, "detected": 0, "sensitivity": None}
        detected = sum(1 for r in icd_rows if _alert_times(r, field))
        return {
            "n": len(icd_rows),
            "detected": detected,
            "sensitivity": detected / len(icd_rows),
        }

    overlap_rows = [
        r
        for r in icd_rows
        if (r.get("labels") or {}).get("sepsis3_onset") is not None
    ]

    def _window_rate(field: str) -> dict[str, Any]:
        if not overlap_rows:
            return {"n": 0, "detected": 0, "sensitivity": None, "mean_lead_hours": None}
        detected = 0
        leads: list[float] = []
        for row in overlap_rows:
            det = stay_detection(
                labels=row.get("labels") or {},
                alert_times=_alert_times(row, field),
                before_hours=before,
                after_hours=after,
                min_lead_hours=min_lead,
            )
            if det["detected"]:
                detected += 1
                if det["lead_hours"] is not None:
                    leads.append(float(det["lead_hours"]))
        return {
            "n": len(overlap_rows),
            "detected": detected,
            "sensitivity": detected / len(overlap_rows),
            "mean_lead_hours": (sum(leads) / len(leads)) if leads else None,
        }

    return {
        "scorecard_id": "icd_sepsis_positive",
        "role": "secondary_independent_label",
        "denominator": "stays with ≥1 pinned discharge sepsis ICD on hadm_id",
        "not_primary_onset": True,
        "cohort": {
            "stays": len(stay_rows),
            "icd_positive": len(icd_rows),
            "sepsis3_positive": sepsis3_pos,
            "icd_and_sepsis3": overlap,
            "icd_only": icd_only,
        },
        "any_alert_during_stay": {
            "naive": _any_alert_rate("naive_alert_times"),
            "governed": _any_alert_rate("governed_alert_times"),
            "interruptive": _any_alert_rate("interruptive_alert_times"),
        },
        "sepsis3_window_among_overlap": {
            "min_lead_hours": min_lead,
            "before_hours": before,
            "after_hours": after,
            "naive": _window_rate("naive_alert_times"),
            "governed": _window_rate("governed_alert_times"),
            "interruptive": _window_rate("interruptive_alert_times"),
        },
    }


def build_fairness_report(
    stay_rows: list[dict[str, Any]],
    *,
    protocol: dict[str, Any] | None = None,
    min_lead_hours: float = 2.0,
    icd_pin_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bundle primary reference + lead-gated + ICD scorecards."""
    proto = protocol or load_protocol()
    primary = summarize_cohort(stay_rows, protocol=proto, min_lead_hours=0.0)
    lead = lead_gated_scorecard(
        stay_rows, min_lead_hours=min_lead_hours, protocol=proto
    )
    icd = icd_positive_scorecard(stay_rows, protocol=proto, min_lead_hours=0.0)
    icd_lead = icd_positive_scorecard(
        stay_rows, protocol=proto, min_lead_hours=min_lead_hours
    )
    return {
        "schema_version": "1.0.0",
        "report_id": "mimic_fairness_scorecards.v1",
        "protocol_id": proto.get("protocol_id"),
        "disclaimer": (
            "Secondary fairness analyses only. Primary PE-1/PE-2 remain "
            "window_m12_p6 on sepsis3_onset. ICD codes are not features and not "
            "primary onset."
        ),
        "primary_reference": {
            "scorecard_id": "window_m12_p6",
            "summary": primary,
        },
        "lead_gated": lead,
        "icd_sepsis": icd,
        "icd_sepsis_lead_gated_overlap": {
            "note": (
                "ICD+ ∩ sepsis3_onset only; applies lead gate to the Sepsis-3 "
                "window (ICD itself has no onset time)."
            ),
            "scorecard": icd_lead,
        },
        "icd_pin": {
            "pin_id": (icd_pin_meta or {}).get("pin_id"),
            "path": (icd_pin_meta or {}).get("_path"),
            "not_primary_onset": True,
        },
    }
