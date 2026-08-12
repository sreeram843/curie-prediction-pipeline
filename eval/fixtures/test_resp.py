"""CURIE-013: respiratory deterioration fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from eval.episodes.arbiter import EpisodeArbiter
from eval.respiratory.scoring import RespInput, compute_resp_score, tier_for_resp_score
from eval.signals.contract import SIGNAL_CONTRACT_VERSION, signal_from_respiratory

CASES = Path(__file__).resolve().parent / "golden" / "resp_cases.v0.1.json"


def test_resp_fixture_cases() -> None:
    data = json.loads(CASES.read_text())
    as_of = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
    for case in data["cases"]:
        result = compute_resp_score(
            patient_id="Patient/resp-fx",
            event_time=as_of,
            inputs=RespInput(**case["inputs"]),
            rule_bundle_id=data["bundle_id"],
            rule_version=data["rule_version"],
        )
        expect = case["expect"]
        assert result.stage == expect["stage"], case["id"]
        assert result.total_score == expect["total_score"], case["id"]
        assert result.completeness.value == expect["completeness"], case["id"]
        if "tier" in expect:
            tier = tier_for_resp_score(result.total_score)
            assert tier.value == expect["tier"], case["id"]
        for key in (
            "oxygenation_stage",
            "rate_stage",
            "support_stage",
            "blood_gas_stage",
            "ratio_source",
        ):
            if key in expect:
                assert getattr(result, key) == expect[key], f"{case['id']}:{key}"


def test_resp_signal_uses_shared_contract_keys() -> None:
    as_of = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
    result = compute_resp_score(
        patient_id="Patient/resp-sig",
        event_time=as_of,
        inputs=RespInput(
            spo2_fio2=180,
            respiratory_rate=34,
            oxygen_device="high_flow",
        ),
    )
    signal = signal_from_respiratory(
        alert_id="alert-resp-1",
        score_result=result,
        severity=tier_for_resp_score(result.total_score).value,
    )
    dumped = signal.model_dump()
    assert dumped["schema_version"] == SIGNAL_CONTRACT_VERSION
    assert dumped["signal_type"] == "respiratory-deterioration"
    assert dumped["signal_kind"] == "risk"
    # Top-level keys match SOFA/AKI — no indicator-specific required fields
    for key in (
        "signal_id",
        "patient_id",
        "score",
        "severity",
        "completeness",
        "components",
        "missing_inputs",
        "evidence_ids",
        "rule_bundle_id",
        "rule_version",
    ):
        assert key in dumped
    assert "ratio_source" in dumped["extensions"]


def test_resp_participates_in_episode_arbiter() -> None:
    arb = EpisodeArbiter()
    t0 = datetime(2024, 6, 15, 10, 0, tzinfo=UTC)
    sofa = arb.ingest(
        {
            "alert_id": "a-sofa",
            "patient_id": "Patient/p-resp-ep",
            "encounter_id": "Encounter/e1",
            "indicator": "sofa-deterioration",
            "tier": "urgent",
            "routing": "interruptive",
            "score": 5,
            "event_time": t0,
        }
    )
    assert sofa.should_page
    resp = arb.ingest(
        {
            "alert_id": "a-resp",
            "patient_id": "Patient/p-resp-ep",
            "encounter_id": "Encounter/e1",
            "indicator": "respiratory-deterioration",
            "tier": "critical",
            "routing": "interruptive",
            "score": 6,
            "event_time": t0.replace(minute=10),
        }
    )
    # Escalation to critical may page or stay passive depending on refractory;
    # either way one episode with respiratory in the differential.
    episodes = arb.list_for_patient("Patient/p-resp-ep")
    assert len(episodes) == 1
    ep = episodes[0]
    types = {ep.dominant_signal_type, *ep.supporting_signal_types}
    assert "respiratory-deterioration" in types
    assert "sofa-deterioration" in types
    assert resp.action.value in {"page", "passive"}
