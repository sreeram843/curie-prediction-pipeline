"""CURIE-024 stewardship feedback classification tests."""

from __future__ import annotations

import json
from pathlib import Path

from eval.stewardship.classifier import (
    FeedbackRecord,
    agreement_metrics,
    classify_feedback_text,
    classify_record,
)
from eval.stewardship.proposals import (
    approve_proposal,
    assert_no_active_rule_mutation,
    build_proposals,
    evaluate_proposal_against_manifest,
    load_replay_manifest,
)
from eval.stewardship.taxonomy import FeedbackCategory

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dual_reviewed.v1.json"


def _records() -> list[FeedbackRecord]:
    return [FeedbackRecord.model_validate(r) for r in json.loads(FIXTURES.read_text())]


def test_taxonomy_classify_known_phrases() -> None:
    r = classify_feedback_text("Duplicate page for the same episode — already paged.")
    assert r.category == FeedbackCategory.REPEATED_EPISODE
    assert r.mutates_active_rules is False


def test_dual_review_agreement_metrics() -> None:
    records = _records()
    preds = [classify_record(r) for r in records]
    metrics = agreement_metrics(records, preds)
    assert metrics["n_dual_reviewed"] == 10
    assert metrics["reviewer_agreement"] is not None
    assert metrics["reviewer_agreement"] >= 0.8
    assert metrics["classifier_vs_consensus_accuracy"] is not None
    assert metrics["classifier_vs_consensus_accuracy"] >= 0.7
    assert metrics["mutates_active_rules"] is False


def test_proposals_require_frozen_replay_manifest() -> None:
    records = _records()
    preds = [classify_record(r) for r in records]
    proposals = build_proposals(records, preds)
    assert proposals
    manifest = load_replay_manifest()
    for prop in proposals:
        assert prop.replay_manifest_id == manifest["manifest_id"]
        bind = evaluate_proposal_against_manifest(prop, replay_manifest=manifest)
        assert bind["ok"] is True
        assert bind["mutates_active_rules"] is False
        assert_no_active_rule_mutation(prop)


def test_human_approval_required_and_no_rule_mutation() -> None:
    records = _records()
    preds = [classify_record(r) for r in records]
    prop = build_proposals(records, preds)[0]
    assert prop.human_approved is False
    assert prop.activation_blocked_until_human_approval is True
    approved = approve_proposal(prop, approved_by="stewardship-chair")
    assert approved.human_approved is True
    assert approved.status == "approved"
    assert approved.mutates_active_rules is False
    assert_no_active_rule_mutation(approved)
