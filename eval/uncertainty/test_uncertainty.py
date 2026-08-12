"""CURIE-025 uncertainty-band tests."""

from __future__ import annotations

from eval.uncertainty.context_assistant import assist_case
from eval.uncertainty.policy import evaluate_eligibility, write_policy
from eval.uncertainty.study import load_cases, run_study


def test_eligibility_policy_selects_borderline_not_all() -> None:
    write_policy()
    cases = load_cases()
    flags = [evaluate_eligibility(c)["eligible"] for c in cases]
    assert any(flags)
    assert not all(flags)


def test_assistant_never_changes_routing_or_interruptive() -> None:
    cases = load_cases()
    for case in cases:
        before = case.get("routing")
        result = assist_case(case)
        assert result.routing_before == before
        assert result.routing_after == before
        assert result.routing_unchanged is True
        assert result.suppressed_alert is False
        assert result.escalated_alert is False
        assert result.interruptive_depends_on_llm is False


def test_ungrounded_quarantines() -> None:
    case = next(c for c in load_cases() if c.get("evidence_ids"))
    result = assist_case(case, inject_ungrounded=True)
    assert result.status == "quarantine"
    assert result.unsupported_claim_count >= 1
    assert result.routing_unchanged is True


def test_study_reports_required_metrics() -> None:
    report = run_study(write=True)
    det = report["baseline_detection"]
    assert det["sensitivity"] is not None
    assert det["ppv"] is not None
    assert "alert_burden_total" in det
    assert "unsupported_claim_rate" in report["assistant"]
    assert "abstention_rate" in report["assistant"]
    assert "subgroups" in report
    assert report["detection_unchanged"] is True
    assert report["safety"]["interruptive_depends_on_llm"] is False
    assert report["safety"]["routing_unchanged_all"] is True
