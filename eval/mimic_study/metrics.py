"""Detection and burden metrics for the MIMIC demo-schema study (CURIE-016)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from eval.mimic_study.protocol import load_protocol


def _parse_dt(raw: str | datetime | None) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def ranking_metrics(labels: list[int | bool], scores: list[float]) -> dict[str, Any]:
    """Compute dependency-free AUROC, average precision, and Brier score."""
    if len(labels) != len(scores) or not labels:
        raise ValueError("labels and scores must be non-empty and have equal length")
    binary = [1 if bool(label) else 0 for label in labels]
    positives = sum(binary)
    negatives = len(binary) - positives
    ordered = sorted(zip(scores, binary), key=lambda pair: pair[0], reverse=True)
    # Tied scores are one threshold, not an arbitrary sub-ordering: grouping them
    # keeps AUPRC invariant to how equal-score rows happen to be sorted (a score
    # of [0.5, 0.5] with labels [1, 0] must equal [0, 1] — same threshold, same
    # decision). Precision for a group is evaluated once the whole group is in.
    precision_sum = 0.0
    rank = 0
    seen_positive = 0
    i = 0
    while i < len(ordered):
        j = i
        group_positives = 0
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            group_positives += ordered[j][1]
            j += 1
        rank += j - i
        seen_positive += group_positives
        if group_positives:
            precision_sum += group_positives * seen_positive / rank
        i = j
    auprc = precision_sum / positives if positives else None
    auroc = None
    if positives and negatives:
        favorable = 0.0
        for positive in (score for score, label in zip(scores, binary) if label):
            for negative in (score for score, label in zip(scores, binary) if not label):
                favorable += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
        auroc = favorable / (positives * negatives)
    return {
        "n": len(binary),
        "positives": positives,
        "negatives": negatives,
        "auroc": auroc,
        "auprc": auprc,
        "brier": round(
            sum((score - label) ** 2 for score, label in zip(scores, binary)) / len(binary),
            12,
        ),
    }


def decision_curve(
    labels: list[int | bool],
    probabilities: list[float],
    *,
    thresholds: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Return decision-curve net benefit at prespecified probability thresholds."""
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("labels and probabilities must be non-empty and have equal length")
    points = thresholds if thresholds is not None else [i / 10 for i in range(1, 10)]
    binary = [1 if bool(label) else 0 for label in labels]
    result = []
    for threshold in points:
        if not 0.0 < threshold < 1.0:
            raise ValueError("decision-curve thresholds must be between 0 and 1")
        predicted = [probability >= threshold for probability in probabilities]
        tp = sum(p and label for p, label in zip(predicted, binary))
        fp = sum(p and not label for p, label in zip(predicted, binary))
        net_benefit = tp / len(binary) - fp / len(binary) * threshold / (1 - threshold)
        result.append(
            {
                "threshold": threshold,
                "net_benefit": net_benefit,
                "tp": tp,
                "fp": fp,
                "n": len(binary),
            }
        )
    return result


def fixed_lead_time_discrimination(
    stay_rows: list[dict[str, Any]],
    *,
    lead_hours: list[float] | tuple[float, ...] = (1, 2, 4, 6, 12),
    score_field: str = "risk_scores",
) -> list[dict[str, Any]]:
    """Evaluate scores at fixed hours before onset using availability timestamps.

    Each row's ``risk_scores`` entries must contain ``time`` and ``score``. For a
    positive stay, the latest score available by ``onset - lead`` is used; for a
    negative stay, the latest score before ``outtime`` is used. Missing cutoff
    scores are excluded and reported through ``n_scored``.
    """
    prepared: list[tuple[int, datetime | None, datetime | None, list[tuple[datetime, float]]]] = []
    for row in stay_rows:
        labels = row.get("labels") or {}
        if labels.get("sepsis3_label_observed") is False:
            continue
        onset = _parse_dt(labels.get("sepsis3_onset"))
        scores: list[tuple[datetime, float]] = []
        for item in row.get(score_field) or []:
            when = _parse_dt(item.get("availability_time") or item.get("time"))
            if when is None or item.get("score") is None:
                continue
            scores.append((when, float(item["score"])))
        scores.sort(key=lambda pair: pair[0])
        outtime = _parse_dt(row.get("outtime"))
        prepared.append((1 if onset is not None else 0, onset, outtime, scores))

    output: list[dict[str, Any]] = []
    for hours in lead_hours:
        y_true: list[int] = []
        y_score: list[float] = []
        for label, onset, outtime, scores in prepared:
            cutoff = onset - timedelta(hours=float(hours)) if onset else outtime
            if cutoff is None:
                continue
            available = [score for when, score in scores if when <= cutoff]
            if not available:
                continue
            y_true.append(label)
            y_score.append(available[-1])
        metrics = ranking_metrics(y_true, y_score) if y_true else {
            "n": 0,
            "positives": 0,
            "negatives": 0,
            "auroc": None,
            "auprc": None,
            "brier": None,
        }
        output.append({"lead_hours": float(hours), "n_scored": len(y_true), **metrics})
    return output


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
    protocol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proto = protocol or load_protocol()
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
    valid_interruptive_alerts = 0
    unknown_label_stays = 0
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
        if labels.get("sepsis3_label_observed") is False and labels.get("sepsis3_onset") is None:
            unknown_label_stays += 1
            continue

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
        if labels.get("sepsis3_onset") is not None:
            valid_interruptive_alerts += sum(
                in_detection_window(
                    alert_time,
                    _parse_dt(labels["sepsis3_onset"]),
                    before_hours=before,
                    after_hours=after,
                )
                for alert_time in [
                    _parse_dt(t)
                    for t in row.get("interruptive_alert_times") or []
                    if _parse_dt(t)
                ]
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
        "unknown_label_stays": unknown_label_stays,
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
        "false_episode_rate_per_100_patient_days": (
            None if patient_days <= 0 else 100.0 * false_episodes / patient_days
        ),
        "episode_per_100_patient_days": (
            None if patient_days <= 0 else 100.0 * episodes / patient_days
        ),
        "interruptive_nna": (
            None if detected_page == 0 else page_alerts / detected_page
        ),
        "interruptive_precision": (
            None if page_alerts == 0 else valid_interruptive_alerts / page_alerts
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
