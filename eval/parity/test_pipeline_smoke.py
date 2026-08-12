"""End-to-end pipeline smoke: score → governance → episode identity.

This is a Python-side path covering the same contracts Flink must honor
(deterministic alert/episode IDs, governance routing, arbiter merge). Full
Kafka → Flink JVM integration remains a separate harness.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from action.api.app.durable_store import DurableAlertStore
from action.api.app.models import AlertRecord, ComponentBreakdown
from eval.episodes.arbiter import EpisodeArbiter
from eval.replay_harness.governance import GovernanceConfig, PatientGovState, evaluate
from eval.sofa.alert_ids import alert_id
from eval.sofa.scoring import (
    SofaComponentInput,
    SofaComponentName,
    compute_sofa_score,
    tier_for_score,
)


def _sofa_alert(*, patient: str, encounter: str, minutes: int, score_hint: int) -> AlertRecord:
    event_time = datetime(2024, 6, 15, 12, 0, tzinfo=UTC) - timedelta(minutes=minutes)
    event_ms = int(event_time.timestamp() * 1000)
    sofa = compute_sofa_score(
        patient_id=patient,
        event_time=event_time,
        encounter_id=encounter,
        inputs=[
            SofaComponentInput(
                name=SofaComponentName.RESPIRATION,
                spo2_percent=88.0,
                fio2_fraction=0.5,
                evidence_ids=["Observation/spo2-1"],
            ),
            SofaComponentInput(
                name=SofaComponentName.CARDIOVASCULAR,
                map_mmhg=55.0,
                evidence_ids=["Observation/map-1"],
            ),
            SofaComponentInput(
                name=SofaComponentName.RENAL,
                creatinine_mg_dl=2.4,
                evidence_ids=["Observation/cr-1"],
            ),
        ],
        rule_bundle_id="sepsis-sofa",
        rule_version="0.3.0",
        min_components_required=2,
    )
    tier = tier_for_score(sofa.total_score)
    aid = alert_id(
        patient,
        encounter,
        "sofa-deterioration",
        sofa.total_score,
        event_ms,
        "0.3.0",
    )
    return AlertRecord(
        alert_id=aid,
        patient_id=patient,
        encounter_id=encounter,
        indicator="sofa-deterioration",
        event_time=event_time,
        score=sofa.total_score if sofa.total_score is not None else score_hint,
        tier=tier.value,
        completeness=sofa.completeness.value,
        routing="interruptive" if tier.value in {"urgent", "critical"} else "passive",
        evidence_ids=list(sofa.evidence_ids or []),
        component_breakdown=[
            ComponentBreakdown(
                name=c.name.value if hasattr(c.name, "value") else str(c.name),
                points=c.points,
                missing=c.missing,
                evidence_ids=list(c.evidence_ids or []),
            )
            for c in sofa.components
        ],
        rule_bundle_id="sepsis-sofa",
        rule_version="0.3.0",
        rule_bundle_hash="smoke-hash",
    )


def test_score_gov_episode_restart_identity(tmp_path: Path) -> None:
    patient = "Patient/e2e-smoke"
    encounter = "Encounter/e2e-1"
    raw = _sofa_alert(patient=patient, encounter=encounter, minutes=0, score_hint=4)
    assert raw.score is not None and raw.score >= 2

    cfg = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=1,
        baseline_enabled=False,
        refractory_minutes=0,
    )
    gov = PatientGovState()
    decision = evaluate(
        {
            "alert_id": raw.alert_id,
            "patient_id": raw.patient_id,
            "encounter_id": raw.encounter_id,
            "indicator": raw.indicator,
            "tier": raw.tier,
            "score": raw.score,
            "event_time": raw.event_time.isoformat(),
            "evidence_ids": raw.evidence_ids,
            "positive_components": 2,
        },
        gov,
        cfg,
    )
    assert decision.emit is True

    path = tmp_path / "e2e.sqlite"
    s1 = DurableAlertStore(path)
    s1.upsert(raw)
    # Second correlated signal into same episode window
    aki = AlertRecord(
        alert_id="alert-aki-smoke-1",
        patient_id=patient,
        encounter_id=encounter,
        indicator="aki",
        event_time=raw.event_time + timedelta(minutes=5),
        score=4,
        tier="urgent",
        completeness="partial",
        routing="interruptive",
        evidence_ids=["Observation/cr-2"],
        rule_bundle_id="aki-kdigo",
        rule_version="0.4.0",
    )
    s1.upsert(aki)
    before_eps = s1.list_episodes(patient_id=patient)
    assert len(before_eps) == 1
    before_id = before_eps[0].episode_id
    assert before_id.startswith("episode-")
    s1.close()

    s2 = DurableAlertStore(path)
    after_eps = s2.list_episodes(patient_id=patient)
    assert len(after_eps) == 1
    assert after_eps[0].episode_id == before_id
    assert {s.signal_type for s in after_eps[0].signals} >= {
        "sofa-deterioration",
        "aki",
    }
    s2.close()

    # Pure arbiter also yields the same deterministic id for the same first signal.
    arb = EpisodeArbiter()
    arb.ingest(raw)
    again = arb.ingest(aki)
    assert again.episode.episode_id == before_id
