"""GRP unit tests — grounding failures hard-fail; abstention is success."""

from __future__ import annotations

import pytest

from ingestion.extraction import settings as settings_mod
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


@pytest.fixture(autouse=True)
def _deterministic_grp_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate unit tests from local .env (e.g. LM Studio openai_compat)."""
    monkeypatch.setattr(settings_mod.settings, "enable_grp", False)
    monkeypatch.setattr(settings_mod.settings, "grp_backend", "deterministic")
    monkeypatch.setattr(settings_mod.settings, "grp_model_name", "curie-grp-stub-v1")
    monkeypatch.setattr(settings_mod.settings, "grp_fail_closed", True)


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


def test_openai_compat_parses_fenced_json(monkeypatch) -> None:
    from ingestion.extraction import settings as settings_mod
    from reasoning import openai_compat as oc

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '```json\n{"summary":"Partial SOFA alert.",'
                                '"claims":[{"text":"Coagulation elevated.",'
                                '"evidence_ids":["Observation/plt-1"]}],'
                                '"abstain":false,"abstain_reason":null}\n```'
                            )
                        }
                    }
                ]
            }

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr(settings_mod.settings, "grp_backend", "openai_compat")
    monkeypatch.setattr(settings_mod.settings, "grp_model_name", "medgemma-4b-it-mlx")
    monkeypatch.setattr(oc.httpx, "Client", _Client)

    decision = explain_alert(ALERT, force=True)
    assert decision.status == "pass"
    assert decision.narrative is not None
    assert "Partial SOFA alert" in decision.narrative
    assert decision.model_name == "medgemma-4b-it-mlx"


def test_rewrite_grp_base_url_loopback_only_in_docker() -> None:
    from ingestion.extraction.settings import rewrite_grp_base_url

    loop = "http://127.0.0.1:1234/v1"
    assert rewrite_grp_base_url(loop, in_docker=False) == loop
    assert rewrite_grp_base_url(loop, in_docker=True) == "http://host.docker.internal:1234/v1"
    cloud = "https://api.openai.com/v1"
    assert rewrite_grp_base_url(cloud, in_docker=True) == cloud
