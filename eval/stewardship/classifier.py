"""Feedback classification for alert stewardship (CURIE-024).

Deterministic keyword classifier by default. Never mutates rule bundles.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from eval.stewardship.taxonomy import (
    CATEGORY_HINTS,
    FeedbackCategory,
)


class FeedbackRecord(BaseModel):
    feedback_id: str
    text: str
    alert_id: str | None = None
    patient_id: str | None = None
    site_id: str = "local"
    service: str | None = None
    indicator: str | None = None
    rule_bundle_id: str | None = None
    rule_version: str | None = None
    routing: Literal["interruptive", "passive", "none"] | None = None
    clinician_role: str | None = None
    # Dual review labels (gold) — optional for live classify
    reviewer_a: FeedbackCategory | None = None
    reviewer_b: FeedbackCategory | None = None


class ClassificationResult(BaseModel):
    feedback_id: str
    category: FeedbackCategory
    confidence: float = Field(ge=0.0, le=1.0)
    method: Literal["deterministic", "llm", "human"] = "deterministic"
    model_name: str | None = "curie-steward-stub-v1"
    prompt_version: str | None = "feedback-classify.v1"
    matched_hints: list[str] = Field(default_factory=list)
    classified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Never activates rules
    mutates_active_rules: Literal[False] = False


def classify_feedback_text(text: str) -> ClassificationResult:
    """Deterministic multi-hint scorer; abstains when no hint matches."""
    lowered = (text or "").strip().lower()
    if not lowered:
        return ClassificationResult(
            feedback_id="adhoc",
            category=FeedbackCategory.ABSTAIN,
            confidence=0.0,
            matched_hints=[],
        )

    scores: dict[FeedbackCategory, list[str]] = {}
    for category, hints in CATEGORY_HINTS.items():
        hits = [h for h in hints if h in lowered]
        if hits:
            scores[category] = hits

    if not scores:
        return ClassificationResult(
            feedback_id="adhoc",
            category=FeedbackCategory.ABSTAIN,
            confidence=0.0,
            matched_hints=[],
        )

    # Prefer category with most hint hits; tie-break by enum order
    best = max(
        scores.items(),
        key=lambda kv: (len(kv[1]), -list(FeedbackCategory).index(kv[0])),
    )
    category, hits = best
    # Confidence grows with hint count, capped
    confidence = min(0.95, 0.55 + 0.15 * (len(hits) - 1))
    return ClassificationResult(
        feedback_id="adhoc",
        category=category,
        confidence=confidence,
        matched_hints=hits,
    )


def classify_record(record: FeedbackRecord) -> ClassificationResult:
    result = classify_feedback_text(record.text)
    return result.model_copy(update={"feedback_id": record.feedback_id})


def consensus_label(record: FeedbackRecord) -> FeedbackCategory | None:
    """Dual-review consensus when both reviewers agree."""
    if record.reviewer_a is None or record.reviewer_b is None:
        return None
    if record.reviewer_a == record.reviewer_b:
        return record.reviewer_a
    return None


def agreement_metrics(
    records: list[FeedbackRecord],
    predictions: list[ClassificationResult] | None = None,
) -> dict[str, Any]:
    """Measure dual-review agreement and optional classifier vs consensus."""
    paired = [r for r in records if r.reviewer_a and r.reviewer_b]
    if not paired:
        return {
            "n_dual_reviewed": 0,
            "reviewer_agreement": None,
            "classifier_vs_consensus_accuracy": None,
        }

    agree = sum(1 for r in paired if r.reviewer_a == r.reviewer_b)
    reviewer_agreement = agree / len(paired)

    pred_by_id = {p.feedback_id: p for p in predictions or []}
    consensus_cases = []
    for r in paired:
        cons = consensus_label(r)
        if cons is None:
            continue
        pred = pred_by_id.get(r.feedback_id)
        if pred is None:
            pred = classify_record(r)
        consensus_cases.append(pred.category == cons)

    clf_acc = (
        sum(consensus_cases) / len(consensus_cases) if consensus_cases else None
    )
    return {
        "n_dual_reviewed": len(paired),
        "n_reviewer_agree": agree,
        "reviewer_agreement": round(reviewer_agreement, 4),
        "n_consensus": len(consensus_cases),
        "classifier_vs_consensus_accuracy": (
            round(clf_acc, 4) if clf_acc is not None else None
        ),
        "mutates_active_rules": False,
    }


def aggregate_classifications(
    records: list[FeedbackRecord],
    predictions: list[ClassificationResult],
) -> dict[str, Any]:
    """Aggregate by site, service, indicator, rule version, routing lane."""
    pred_by_id = {p.feedback_id: p for p in predictions}
    buckets: dict[str, dict[str, int]] = {
        "by_category": {},
        "by_site": {},
        "by_service": {},
        "by_indicator": {},
        "by_rule": {},
        "by_routing": {},
    }
    for record in records:
        pred = pred_by_id.get(record.feedback_id) or classify_record(record)
        cat = pred.category.value
        buckets["by_category"][cat] = buckets["by_category"].get(cat, 0) + 1
        site = record.site_id or "unknown"
        buckets["by_site"][site] = buckets["by_site"].get(site, 0) + 1
        service = record.service or "unknown"
        buckets["by_service"][service] = buckets["by_service"].get(service, 0) + 1
        ind = record.indicator or "unknown"
        buckets["by_indicator"][ind] = buckets["by_indicator"].get(ind, 0) + 1
        rule = f"{record.rule_bundle_id or '?'}@{record.rule_version or '?'}"
        buckets["by_rule"][rule] = buckets["by_rule"].get(rule, 0) + 1
        route = record.routing or "unknown"
        buckets["by_routing"][route] = buckets["by_routing"].get(route, 0) + 1

    return {
        "n_feedback": len(records),
        "aggregates": buckets,
        "mutates_active_rules": False,
    }
