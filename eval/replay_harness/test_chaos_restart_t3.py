"""Checkpoint-style chaos: serialize/restore state + duplicate replay after 'restart'."""

from __future__ import annotations

import pickle
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from eval.replay_harness.governance import GovernanceConfig, PatientGovState, evaluate
from eval.sofa.scoring import SofaComponentInput, SofaComponentName, compute_sofa_score
from eval.sofa.stream_scorer import PatientState, observation_to_input


def test_patient_state_pickle_roundtrip_preserves_spo2_fio2_merge() -> None:
    state = PatientState()
    t0 = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    state.apply(
        SofaComponentInput(
            name=SofaComponentName.RESPIRATION, spo2_percent=96.0, evidence_ids=["spo2"]
        ),
        t0,
    )
    state.apply(
        SofaComponentInput(
            name=SofaComponentName.RESPIRATION, fio2_fraction=0.5, evidence_ids=["fio2"]
        ),
        t0 + timedelta(minutes=1),
    )
    restored: PatientState = pickle.loads(pickle.dumps(state))
    resp = restored.latest[SofaComponentName.RESPIRATION]
    assert resp.spo2_percent == 96.0
    assert resp.fio2_fraction == 0.5
    from eval.sofa.scoring import effective_resp_ratio

    assert effective_resp_ratio(resp) == 192.0


def test_idempotency_survives_restart_and_duplicate_replay() -> None:
    state = PatientState()
    assert state.seen("obs-cr-1") is False
    restored: PatientState = pickle.loads(pickle.dumps(state))
    assert restored.seen("obs-cr-1") is True
    assert restored.seen("obs-cr-2") is False


def test_governance_state_deepcopy_restart_continues_trajectory() -> None:
    config = GovernanceConfig(baseline_enabled=False, min_crossings=2)
    state = PatientGovState()
    t0 = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    evaluate(
        {
            "score": 7,
            "tier": "critical",
            "event_time": t0.isoformat(),
            "patient_id": "p",
        },
        state,
        config,
    )
    assert state.crossings_above_threshold == 1
    # Simulate operator restart with restored keyed state
    restored = deepcopy(state)
    d = evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": (t0 + timedelta(minutes=35)).isoformat(),
            "patient_id": "p",
        },
        restored,
        config,
    )
    assert restored.crossings_above_threshold >= 2
    assert d.emit is True


def test_score_after_restart_matches_pre_restart_snapshot() -> None:
    state = PatientState()
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    for inp in (
        SofaComponentInput(name=SofaComponentName.COAGULATION, platelets_10e9_l=40),
        SofaComponentInput(name=SofaComponentName.LIVER, bilirubin_mg_dl=2.5),
        SofaComponentInput(name=SofaComponentName.RENAL, creatinine_mg_dl=2.1),
        SofaComponentInput(name=SofaComponentName.CARDIOVASCULAR, map_mmhg=80),
        SofaComponentInput(name=SofaComponentName.CNS, gcs=15),
        SofaComponentInput(name=SofaComponentName.RESPIRATION, pao2_fio2=450),
    ):
        state.apply(inp, t0)

    before = compute_sofa_score(
        patient_id="p",
        event_time=t0,
        inputs=list(state.latest.values()),
        rule_bundle_id="sepsis-sofa",
        rule_version="0.2.0",
    )
    restored: PatientState = pickle.loads(pickle.dumps(state))
    after = compute_sofa_score(
        patient_id="p",
        event_time=t0,
        inputs=list(restored.latest.values()),
        rule_bundle_id="sepsis-sofa",
        rule_version="0.2.0",
    )
    assert before.total_score == after.total_score == 7


def test_observation_spo2_alone_not_ratio_until_fio2() -> None:
    spo2 = observation_to_input(
        {
            "resourceType": "Observation",
            "id": "s1",
            "code": {"coding": [{"code": "2708-6"}]},
            "valueQuantity": {"value": 98, "unit": "%"},
        }
    )
    assert spo2 is not None
    assert spo2.spo2_percent == 98
    assert spo2.spo2_fio2 is None
    fio2 = observation_to_input(
        {
            "resourceType": "Observation",
            "id": "f1",
            "code": {"coding": [{"code": "3150-0"}]},
            "valueQuantity": {"value": 40, "unit": "%"},
        }
    )
    assert fio2 is not None
    assert fio2.fio2_fraction == 0.4
