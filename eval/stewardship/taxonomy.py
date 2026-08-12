"""Reviewed feedback taxonomy for alert stewardship (CURIE-024 / LLM-WF-09)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class FeedbackCategory(StrEnum):
    ALREADY_RECOGNIZED = "already_recognized"
    ALREADY_TREATED = "already_treated"
    CHRONIC_BASELINE = "chronic_baseline"
    INCORRECT_INPUT = "incorrect_input"
    APPROPRIATE_NON_ACTIONABLE = "appropriate_non_actionable"
    WRONG_RECIPIENT = "wrong_recipient"
    REPEATED_EPISODE = "repeated_episode"
    TRUE_ESCALATION = "true_escalation"
    OTHER = "other"
    ABSTAIN = "abstain"


CATEGORY_LABELS: dict[FeedbackCategory, str] = {
    FeedbackCategory.ALREADY_RECOGNIZED: "Already recognized by care team",
    FeedbackCategory.ALREADY_TREATED: "Already treated / on pathway",
    FeedbackCategory.CHRONIC_BASELINE: "Chronic baseline / expected values",
    FeedbackCategory.INCORRECT_INPUT: "Incorrect input data",
    FeedbackCategory.APPROPRIATE_NON_ACTIONABLE: "Appropriate but non-actionable",
    FeedbackCategory.WRONG_RECIPIENT: "Wrong recipient / service",
    FeedbackCategory.REPEATED_EPISODE: "Repeated episode / duplicate page",
    FeedbackCategory.TRUE_ESCALATION: "True escalation / useful interrupt",
    FeedbackCategory.OTHER: "Other / free text",
    FeedbackCategory.ABSTAIN: "Classifier abstained",
}


# Keyword hints for the deterministic classifier (prototype — not clinical NLP).
CATEGORY_HINTS: dict[FeedbackCategory, tuple[str, ...]] = {
    FeedbackCategory.ALREADY_RECOGNIZED: (
        "already aware",
        "already recognized",
        "known to team",
        "team already",
    ),
    FeedbackCategory.ALREADY_TREATED: (
        "already treated",
        "on protocol",
        "on sepsis pathway",
        "antibiotics started",
        "already on pressors",
    ),
    FeedbackCategory.CHRONIC_BASELINE: (
        "chronic",
        "baseline",
        "end stage",
        "esrd",
        "expected for",
    ),
    FeedbackCategory.INCORRECT_INPUT: (
        "wrong lab",
        "incorrect",
        "bad data",
        "artifact",
        "misdocumented",
        "unit error",
    ),
    FeedbackCategory.APPROPRIATE_NON_ACTIONABLE: (
        "non-actionable",
        "not actionable",
        "appropriate but",
        "no change needed",
        "watch only",
    ),
    FeedbackCategory.WRONG_RECIPIENT: (
        "wrong team",
        "wrong recipient",
        "wrong service",
        "page medicine not",
        "not my patient",
    ),
    FeedbackCategory.REPEATED_EPISODE: (
        "duplicate",
        "repeated",
        "same episode",
        "already paged",
        "again",
    ),
    FeedbackCategory.TRUE_ESCALATION: (
        "helpful",
        "true positive",
        "good catch",
        "useful page",
        "escalation warranted",
    ),
}


def taxonomy_public() -> list[dict[str, Any]]:
    return [
        {"id": c.value, "label": CATEGORY_LABELS[c]}
        for c in FeedbackCategory
        if c != FeedbackCategory.ABSTAIN
    ]
