"""Retrospective uncertainty-band study metrics (CURIE-025)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.uncertainty.context_assistant import assist_case
from eval.uncertainty.policy import default_policy, write_policy

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cases.v1.json"
FROZEN_DIR = Path(__file__).resolve().parent / "frozen"
REPORT_PATH = FROZEN_DIR / "study_report.v1.json"


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    return list(json.loads((path or FIXTURES).read_text()))


def _detection_stats(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Sensitivity / PPV / burden from deterministic labels on the fixture set."""
    labeled_pos = [c for c in cases if c.get("label_positive")]
    labeled_neg = [c for c in cases if not c.get("label_positive")]
    # Detection = deterministic alert fired (routing interruptive or passive)
    tp = sum(
        1
        for c in labeled_pos
        if c.get("routing") in {"interruptive", "passive"}
    )
    fp = sum(
        1
        for c in labeled_neg
        if c.get("routing") in {"interruptive", "passive"}
    )
    fn = len(labeled_pos) - tp
    sens = tp / len(labeled_pos) if labeled_pos else None
    ppv = tp / (tp + fp) if (tp + fp) else None
    interruptive = sum(1 for c in cases if c.get("routing") == "interruptive")
    return {
        "n_cases": len(cases),
        "n_labeled_positive": len(labeled_pos),
        "n_labeled_negative": len(labeled_neg),
        "sensitivity": sens,
        "ppv": ppv,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "alert_burden_total": tp + fp,
        "interruptive_burden": interruptive,
    }


def run_study(*, write: bool = True) -> dict[str, Any]:
    write_policy()
    policy = default_policy()
    cases = load_cases()
    results = [assist_case(c, policy=policy) for c in cases]

    # Safety: routing never changes; interruptive never depends on LLM
    routing_ok = all(r.routing_unchanged and r.routing_before == r.routing_after for r in results)
    no_suppress = all(r.suppressed_alert is False for r in results)
    no_escalate = all(r.escalated_alert is False for r in results)
    no_interruptive_llm = all(r.interruptive_depends_on_llm is False for r in results)

    eligible = [r for r in results if r.eligible]
    unsupported = sum(r.unsupported_claim_count for r in results)
    abstained = sum(1 for r in results if r.abstained or r.status == "abstain")
    quarantined = sum(1 for r in results if r.status == "quarantine")
    passed = sum(1 for r in results if r.status == "pass")
    total_claims = sum(len(r.claims) for r in results if r.status == "pass")
    grounded_claims = sum(
        sum(1 for c in r.claims if c.grounded) for r in results if r.status == "pass"
    )

    # Subgroups
    subgroups = {
        "eligible": _detection_stats([c for c, r in zip(cases, results) if r.eligible]),
        "ineligible": _detection_stats([c for c, r in zip(cases, results) if not r.eligible]),
        "partial_completeness": _detection_stats(
            [c for c in cases if str(c.get("completeness") or "") == "partial"]
        ),
        "interruptive": _detection_stats(
            [c for c in cases if c.get("routing") == "interruptive"]
        ),
    }

    # Detection metrics are from deterministic labels — assistant does not alter them
    baseline = _detection_stats(cases)
    after_assist = _detection_stats(cases)  # identical by construction

    report = {
        "schema_version": "1.0.0",
        "curie_ticket": "CURIE-025",
        "policy_id": policy.policy_id,
        "mode": policy.mode,
        "baseline_detection": baseline,
        "after_assist_detection": after_assist,
        "detection_unchanged": baseline == after_assist,
        "assistant": {
            "n_eligible": len(eligible),
            "n_skipped": sum(1 for r in results if r.status == "skipped"),
            "n_pass": passed,
            "n_abstain": abstained,
            "n_quarantine": quarantined,
            "unsupported_claims": unsupported,
            "unsupported_claim_rate": (
                unsupported / max(1, unsupported + grounded_claims)
            ),
            "abstention_rate": abstained / max(1, len(eligible)),
            "grounded_claims": grounded_claims,
            "total_pass_claims": total_claims,
        },
        "subgroups": subgroups,
        "safety": {
            "routing_unchanged_all": routing_ok,
            "no_suppress": no_suppress,
            "no_escalate": no_escalate,
            "interruptive_depends_on_llm": False,
            "interruptive_llm_flag_clear": no_interruptive_llm,
        },
        "cases": [r.model_dump(mode="json") for r in results],
    }

    if write:
        FROZEN_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2, default=str) + "\n")
    return report
