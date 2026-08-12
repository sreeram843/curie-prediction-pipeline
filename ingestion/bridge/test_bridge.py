"""Contract tests for the trusted clinical-fact bridge (CURIE-022)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ingestion.bridge.adapter import admit_and_canonicalize
from ingestion.bridge.gate import admit_trusted_fact
from ingestion.bridge.models import TrustedClinicalFactEnvelope

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MANIFEST = FIXTURES / "manifest.v1.json"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_manifest_cases() -> None:
    manifest = json.loads(MANIFEST.read_text())
    for case in manifest["cases"]:
        payload = _load(case["file"])
        clock = None
        if case.get("clock"):
            clock = datetime.fromisoformat(case["clock"].replace("Z", "+00:00"))
        decision = admit_trusted_fact(payload, clock=clock)
        assert decision.outcome == case["expect_outcome"], case["id"]
        assert decision.may_mutate_scoring is case["may_mutate_scoring"], case["id"]
        if case.get("extraction_method") and decision.fact is not None:
            assert decision.fact.extraction.method == case["extraction_method"]


def test_llm_and_deterministic_distinguishable_in_audit() -> None:
    det = TrustedClinicalFactEnvelope.model_validate(
        _load("valid_trusted_deterministic.v1.json")
    )
    llm = TrustedClinicalFactEnvelope.model_validate(_load("valid_trusted_llm.v1.json"))
    assert det.audit_record()["is_deterministic"] is True
    assert det.audit_record()["is_llm_derived"] is False
    assert llm.audit_record()["is_llm_derived"] is True
    assert llm.audit_record()["is_deterministic"] is False
    assert llm.audit_record()["extraction_model"]
    assert llm.audit_record()["prompt_version"]


def test_only_trusted_facts_canonicalize() -> None:
    decision, env = admit_and_canonicalize(_load("valid_trusted_deterministic.v1.json"))
    assert decision.may_mutate_scoring is True
    assert env is not None
    assert env.idempotency_key.endswith("sha256:abc")
    assert env.event_time.isoformat().startswith("2026-08-12T10:00:00")
    assert "deterministic" in env.provenance.adapter

    decision2, env2 = admit_and_canonicalize(_load("candidate_quarantine.v1.json"))
    assert decision2.may_mutate_scoring is False
    assert env2 is None


def test_unknown_schema_never_scores() -> None:
    decision, env = admit_and_canonicalize(_load("unknown_schema.v1.json"))
    assert decision.outcome == "reject"
    assert decision.reason == "unknown_schema"
    assert env is None


def test_scoring_mutation_guard() -> None:
    """Explicit guard: non-admit decisions cannot produce scoring envelopes."""
    for name in (
        "candidate_quarantine.v1.json",
        "failed_validation.v1.json",
        "missing_provenance.v1.json",
        "unknown_schema.v1.json",
    ):
        decision, env = admit_and_canonicalize(_load(name))
        assert decision.may_mutate_scoring is False
        assert env is None
