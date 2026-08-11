"""GRP unit tests — grounding failures hard-fail; abstention is success."""

from __future__ import annotations

from reasoning.pipeline import explain_alert

ALERT = {
    "alert_id": "alert-grp-001",
    "patient_id": "Patient/grp-001",
    "score": 7,
    "tier": "critical",
    "completeness": "partial",
    "evidence_ids": ["Observation/plt-1", "Observation/bili-1", "Observation/cr-1"],
    "missing_components": ["respiration", "cns"],
    "component_breakdown": [
        {
            "name": "coagulation",
            "points": 3,
            "missing": False,
            "evidence_ids": ["Observation/plt-1"],
        },
        {
            "name": "liver",
            "points": 2,
            "missing": False,
            "evidence_ids": ["Observation/bili-1"],
        },
        {
            "name": "renal",
            "points": 2,
            "missing": False,
            "evidence_ids": ["Observation/cr-1"],
        },
        {"name": "respiration", "points": None, "missing": True, "evidence_ids": []},
    ],
    "rule_bundle_id": "sepsis-sofa",
    "rule_version": "0.1.0",
}


def test_grp_disabled_by_default() -> None:
    decision = explain_alert(ALERT)
    assert decision.status == "disabled"
    assert decision.score_unchanged is True


def test_grp_pass_with_grounded_claims() -> None:
    decision = explain_alert(ALERT, force=True)
    assert decision.status == "pass"
    assert decision.narrative is not None
    assert "Patient/grp-001" in decision.narrative
    assert all(c.grounded for c in decision.claims)
    assert decision.score_unchanged is True


def test_ungrounded_claim_quarantines() -> None:
    decision = explain_alert(ALERT, force=True, inject_ungrounded=True)
    assert decision.status == "quarantine"
    assert decision.narrative is None
    assert decision.quarantine_reason is not None
    assert "ungrounded" in decision.quarantine_reason or "grounding_failure" in (
        decision.quarantine_reason or ""
    )


def test_abstain_without_evidence() -> None:
    bare = {
        **ALERT,
        "alert_id": "alert-grp-empty",
        "evidence_ids": [],
        "component_breakdown": [
            {"name": "coagulation", "points": 3, "missing": False, "evidence_ids": []}
        ],
    }
    decision = explain_alert(bare, force=True)
    assert decision.status == "abstain"
    assert decision.narrative is None
