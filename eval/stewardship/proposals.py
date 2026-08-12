"""Offline experiment proposals — never mutate active rules (CURIE-024)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from eval.stewardship.classifier import ClassificationResult, FeedbackRecord
from eval.stewardship.taxonomy import FeedbackCategory

FROZEN_DIR = Path(__file__).resolve().parent / "frozen"
REPLAY_MANIFEST_PATH = FROZEN_DIR / "replay_manifest.v1.json"
PROPOSALS_PATH = FROZEN_DIR / "proposals.v1.json"

# Map feedback categories → suggested offline experiments (not activations).
CATEGORY_EXPERIMENTS: dict[FeedbackCategory, dict[str, Any]] = {
    FeedbackCategory.REPEATED_EPISODE: {
        "title": "Increase episode page refractory",
        "knob": "page_refractory_minutes",
        "proposed_delta": "+30",
        "rationale": "Reduce repeat interruptive pages within the same episode.",
    },
    FeedbackCategory.CHRONIC_BASELINE: {
        "title": "Enable baseline delta gate",
        "knob": "baseline_enabled",
        "proposed_delta": "true",
        "rationale": "Suppress alerts that reflect chronic baselines when evidence supports it.",
    },
    FeedbackCategory.ALREADY_TREATED: {
        "title": "Strengthen context suppression for active protocols",
        "knob": "suppression_flags",
        "proposed_delta": "already_on_sepsis_protocol",
        "rationale": "Passive-route when patient already on documented pathway.",
    },
    FeedbackCategory.INCORRECT_INPUT: {
        "title": "Tighten unit/status validation before scoring",
        "knob": "validation_gate",
        "proposed_delta": "reject_invalid_units",
        "rationale": "Keep bad inputs out of scoring via DLQ rather than paging.",
    },
    FeedbackCategory.WRONG_RECIPIENT: {
        "title": "Review routing recipient map (ops only)",
        "knob": "routing_directory",
        "proposed_delta": "site_service_review",
        "rationale": "Directory/ops change — not a score threshold.",
    },
}


class ExperimentProposal(BaseModel):
    proposal_id: str
    category: FeedbackCategory
    title: str
    knob: str
    proposed_delta: str
    rationale: str
    supporting_feedback_ids: list[str] = Field(default_factory=list)
    replay_manifest_id: str
    replay_manifest_path: str
    status: Literal["proposed", "approved", "rejected", "evaluated"] = "proposed"
    human_approved: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    evaluation_status: Literal["pending", "queued", "complete"] = "pending"
    # Explicit safety flags
    mutates_active_rules: Literal[False] = False
    activation_blocked_until_human_approval: Literal[True] = True


def load_replay_manifest(path: Path | None = None) -> dict[str, Any]:
    p = path or REPLAY_MANIFEST_PATH
    return json.loads(p.read_text())


def build_proposals(
    records: list[FeedbackRecord],
    predictions: list[ClassificationResult],
    *,
    replay_manifest: dict[str, Any] | None = None,
) -> list[ExperimentProposal]:
    """Group classifications into offline replay experiment proposals."""
    manifest = replay_manifest or load_replay_manifest()
    manifest_id = str(manifest.get("manifest_id") or "stewardship-replay.v1")
    manifest_path = str(
        manifest.get("path")
        or "eval/stewardship/frozen/replay_manifest.v1.json"
    )

    by_cat: dict[FeedbackCategory, list[str]] = {}
    pred_by_id = {p.feedback_id: p for p in predictions}
    for record in records:
        pred = pred_by_id.get(record.feedback_id) or ClassificationResult(
            feedback_id=record.feedback_id,
            category=FeedbackCategory.ABSTAIN,
            confidence=0.0,
        )
        if pred.category in {
            FeedbackCategory.ABSTAIN,
            FeedbackCategory.OTHER,
            FeedbackCategory.TRUE_ESCALATION,
            FeedbackCategory.APPROPRIATE_NON_ACTIONABLE,
            FeedbackCategory.ALREADY_RECOGNIZED,
        }:
            continue
        if pred.category not in CATEGORY_EXPERIMENTS:
            continue
        by_cat.setdefault(pred.category, []).append(record.feedback_id)

    proposals: list[ExperimentProposal] = []
    for category, ids in sorted(by_cat.items(), key=lambda kv: kv[0].value):
        spec = CATEGORY_EXPERIMENTS[category]
        proposals.append(
            ExperimentProposal(
                proposal_id=f"prop-{category.value}",
                category=category,
                title=str(spec["title"]),
                knob=str(spec["knob"]),
                proposed_delta=str(spec["proposed_delta"]),
                rationale=str(spec["rationale"]),
                supporting_feedback_ids=ids,
                replay_manifest_id=manifest_id,
                replay_manifest_path=manifest_path,
            )
        )
    return proposals


def evaluate_proposal_against_manifest(
    proposal: ExperimentProposal,
    *,
    replay_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind a proposal to a frozen replay manifest — does not run live retunes."""
    manifest = replay_manifest or load_replay_manifest()
    if proposal.replay_manifest_id != manifest.get("manifest_id"):
        return {
            "proposal_id": proposal.proposal_id,
            "ok": False,
            "reason": "replay_manifest_mismatch",
            "mutates_active_rules": False,
        }
    required = set(manifest.get("required_artifacts") or [])
    missing = [a for a in required if not Path(a).is_file()]
    return {
        "proposal_id": proposal.proposal_id,
        "ok": not missing,
        "missing_artifacts": missing,
        "evaluation_command": manifest.get("evaluation_command"),
        "forbidden": manifest.get("forbidden") or [],
        "mutates_active_rules": False,
        "note": "Offline evaluation only — human approval still required before any activation.",
    }


def approve_proposal(
    proposal: ExperimentProposal,
    *,
    approved_by: str,
) -> ExperimentProposal:
    """Record human approval. Still does not mutate active rules."""
    if not approved_by.strip():
        raise ValueError("approved_by required")
    return proposal.model_copy(
        update={
            "status": "approved",
            "human_approved": True,
            "approved_by": approved_by.strip(),
            "approved_at": datetime.now(UTC),
            "evaluation_status": "queued",
            "mutates_active_rules": False,
        }
    )


def assert_no_active_rule_mutation(proposal: ExperimentProposal) -> None:
    if proposal.mutates_active_rules:
        raise RuntimeError("stewardship proposals must never mutate active rules")
    if proposal.status == "approved" and not proposal.human_approved:
        raise RuntimeError("approved status requires human_approved=True")
