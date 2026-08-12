"""Richer T3 cases: malformed inputs, late events, rule-version awareness."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from eval.indicators.registry import load_rule_bundle
from eval.replay_harness.governance import GovernanceConfig, PatientGovState, evaluate
from eval.sofa.scoring import SofaComponentInput, SofaComponentName, compute_sofa_score
from eval.sofa.stream_scorer import PatientState
from eval.sofa.thresholds import SofaThresholds


def test_late_event_after_newer_observation_ignored() -> None:
    state = PatientState()
    t_new = datetime(2024, 1, 1, 14, 0, tzinfo=UTC)
    t_old = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    state.apply(
        SofaComponentInput(
            name=SofaComponentName.COAGULATION,
            platelets_10e9_l=180,
            evidence_ids=["new"],
        ),
        t_new,
    )
    assert (
        state.apply(
            SofaComponentInput(
                name=SofaComponentName.COAGULATION,
                platelets_10e9_l=20,
                evidence_ids=["late"],
            ),
            t_old,
        )
        is False
    )
    assert state.latest[SofaComponentName.COAGULATION].platelets_10e9_l == 180


def test_rule_version_change_can_alter_score() -> None:
    bundle = load_rule_bundle("sepsis-sofa")
    mutated = deepcopy(bundle)
    mutated["score"]["component_thresholds"]["coagulation"]["bands"] = [
        {"points": 4, "max_exclusive": 30},
        {"points": 3, "max_exclusive": 50},
        {"points": 2, "max_exclusive": 100},
        {"points": 1, "max_exclusive": 150},
        {"points": 0, "min_inclusive": 150},
    ]
    inputs = [
        SofaComponentInput(name=SofaComponentName.COAGULATION, platelets_10e9_l=25),
        SofaComponentInput(name=SofaComponentName.LIVER, bilirubin_mg_dl=0.8),
        SofaComponentInput(name=SofaComponentName.RENAL, creatinine_mg_dl=0.9),
        SofaComponentInput(name=SofaComponentName.CARDIOVASCULAR, map_mmhg=80),
        SofaComponentInput(name=SofaComponentName.CNS, gcs=15),
        SofaComponentInput(name=SofaComponentName.RESPIRATION, pao2_fio2=450),
    ]
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    a = compute_sofa_score(
        patient_id="p",
        event_time=t0,
        inputs=inputs,
        rule_bundle_id="sepsis-sofa",
        rule_version="0.2.0",
        rule_bundle=bundle,
    )
    b = compute_sofa_score(
        patient_id="p",
        event_time=t0,
        inputs=inputs,
        rule_bundle_id="sepsis-sofa",
        rule_version="0.2.0-mut",
        rule_bundle=mutated,
    )
    # platelets 25 → points 3 under default (<50), points 4 under mutated (<30)
    coag_a = next(c.points for c in a.components if c.name == SofaComponentName.COAGULATION)
    coag_b = next(c.points for c in b.components if c.name == SofaComponentName.COAGULATION)
    assert coag_a == 3
    assert coag_b == 4


def test_resolution_gap_allows_fresh_trajectory() -> None:
    config = GovernanceConfig(
        baseline_enabled=False,
        min_crossings=2,
        trajectory_persistence_minutes=30,
        resolution_gap_minutes=60,
    )
    state = PatientGovState()
    t0 = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    evaluate(
        {"score": 7, "tier": "critical", "event_time": t0.isoformat(), "patient_id": "p"},
        state,
        config,
    )
    # Gap > resolution → streak resets
    later = t0 + timedelta(hours=2)
    d = evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": later.isoformat(),
            "patient_id": "p",
        },
        state,
        config,
    )
    assert d.emit is False
    assert state.crossings_above_threshold == 1


def test_thresholds_from_bundle_match_defaults() -> None:
    bundle = load_rule_bundle("sepsis-sofa")
    th = SofaThresholds.from_bundle(bundle)
    assert th.resp_p4_lt == 100
    assert th.map_lt == 70
    assert th.coag[0].max_exclusive == 20
