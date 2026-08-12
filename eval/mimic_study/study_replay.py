"""Governed stay replay for MIMIC ablation study (CURIE-016).

SOFA and AKI are evaluated as independent indicator pipelines on the same
availability-time clock. AKI uses the stateful KDIGO timeline (CURIE-009),
not a point-in-time Cr snapshot nested under a SOFA emit decision.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from eval.aki.scoring import tier_for_aki_score
from eval.aki.timeline import (
    AkiTimelineState,
    CreatinineObs,
    evaluate_aki_timeline,
)
from eval.episodes.arbiter import EpisodeArbiter
from eval.mimic_harness.replay import (
    StayReplayState,
    _apply_observation,
    assert_snapshot_leakage_free,
)
from eval.mimic_study.ablations import knobs_to_config, uses_episode_arbitration
from eval.replay_harness.governance import GovernanceConfig, PatientGovState, evaluate
from eval.sofa.scoring import (
    SofaComponentInput,
    SofaComponentName,
    compute_sofa_score,
    tier_for_score,
)
from ingestion.adapters.mimic.timeline import (
    content_hash_events,
    events_from_demo_schema_stay,
    sort_by_availability,
)


def _patient_days(stay: dict[str, Any]) -> float:
    intime = stay.get("intime")
    outtime = stay.get("outtime")
    if not intime or not outtime:
        return 1.0
    try:
        a = datetime.strptime(str(intime), "%Y-%m-%d %H:%M:%S")
        b = datetime.strptime(str(outtime), "%Y-%m-%d %H:%M:%S")
        return max((b - a).total_seconds() / 86400.0, 1.0 / 24.0)
    except ValueError:
        return 1.0


def _is_creatinine_event(event: Any) -> bool:
    code = event.code or ""
    return code == "2160-0" or event.itemid in {50912, 52546, 220615}


def replay_stay_ablation(
    stay: dict[str, Any],
    *,
    knobs: dict[str, Any] | None,
    check_leakage: bool = True,
) -> dict[str, Any]:
    """Replay one stay under naive + optional governed ablation knobs."""
    events = sort_by_availability(events_from_demo_schema_stay(stay))
    events_by_id = {e.evidence_id: e for e in events}
    state = StayReplayState()
    patient_id = f"Patient/{stay['subject_id']}"
    encounter_id = f"Encounter/{stay.get('hadm_id') or stay['stay_id']}"
    aki_timeline = AkiTimelineState(patient_id=patient_id, encounter_id=encounter_id)

    gov_cfg: GovernanceConfig | None = None
    min_components = 1
    if knobs is not None:
        bundle, gov_cfg = knobs_to_config(knobs)
        min_components = int(
            (bundle.get("score") or {}).get("min_components_required") or 1
        )

    # Independent governance state per indicator (no shared mute across pipelines).
    sofa_gov = PatientGovState()
    aki_gov = PatientGovState()
    use_episodes = uses_episode_arbitration(knobs)
    arb = EpisodeArbiter() if use_episodes else None

    naive_times: list[str] = []
    naive_interruptive = 0
    gov_times: list[str] = []
    page_times: list[str] = []
    gov_alert_count = 0
    page_alert_count = 0
    partial = False
    signal_count = 0
    aki_signal_count = 0

    def _emit_signal(
        *,
        alert: dict[str, Any],
        gov_state: PatientGovState,
        clock: datetime,
    ) -> None:
        nonlocal gov_alert_count, page_alert_count
        if knobs is None or gov_cfg is None:
            gov_times.append(clock.isoformat())
            gov_alert_count += 1
            if alert["tier"] in {"urgent", "critical"}:
                page_times.append(clock.isoformat())
                page_alert_count += 1
            return

        decision = evaluate(alert, gov_state, gov_cfg)
        if not decision.emit:
            return
        routed = decision.routing
        out = decision.alert
        gov_times.append(clock.isoformat())
        gov_alert_count += 1
        if routed == "interruptive":
            page_times.append(clock.isoformat())
            page_alert_count += 1
        if arb is not None:
            arb.ingest(
                {
                    **out,
                    "routing": routed,
                    "event_time": clock,
                }
            )

    for event in events:
        clock = event.availability_time
        try:
            _apply_observation(state, event, clock=clock)
        except Exception as exc:  # noqa: BLE001
            state.errors.append(f"{event.evidence_id}: {exc}")
            continue

        if _is_creatinine_event(event) and event.valuenum is not None:
            aki_timeline.ingest_creatinine(
                CreatinineObs(
                    event_time=event.event_time or clock,
                    value_mg_dl=float(event.valuenum),
                    evidence_id=event.evidence_id,
                    status="final",
                )
            )

        # --- Independent SOFA pipeline ---
        sofa_inputs = list(state.components.values())
        if (
            state.creatinine_mg_dl is not None
            and SofaComponentName.RENAL not in state.components
        ):
            sofa_inputs.append(
                SofaComponentInput(
                    name=SofaComponentName.RENAL,
                    creatinine_mg_dl=state.creatinine_mg_dl,
                    evidence_ids=list(state.creatinine_evidence),
                )
            )
        if sofa_inputs:
            sofa = compute_sofa_score(
                patient_id=patient_id,
                event_time=clock,
                inputs=sofa_inputs,
                encounter_id=encounter_id,
                rule_bundle_id="sepsis-sofa",
                rule_version="0.3.0",
                min_components_required=min_components,
            )
            tier = tier_for_score(sofa.total_score)
            evidence = list(sofa.evidence_ids or [])
            if sofa.completeness.value == "partial":
                partial = True
            if check_leakage:
                assert_snapshot_leakage_free(
                    events_by_id=events_by_id,
                    snapshot={
                        "availability_clock": clock.isoformat(),
                        "evidence_ids": evidence,
                    },
                )
            if tier.value in {"watch", "urgent", "critical"}:
                pos = sum(1 for c in sofa.components if c.points and c.points > 0)
                naive_times.append(clock.isoformat())
                if tier.value in {"urgent", "critical"}:
                    naive_interruptive += 1
                alert = {
                    "alert_id": f"mimic-sofa-{stay['stay_id']}-{signal_count}",
                    "patient_id": patient_id,
                    "encounter_id": encounter_id,
                    "indicator": "sofa-deterioration",
                    "tier": tier.value,
                    "score": sofa.total_score,
                    "event_time": clock.isoformat(),
                    "evidence_ids": evidence,
                    "positive_components": pos,
                }
                signal_count += 1
                _emit_signal(alert=alert, gov_state=sofa_gov, clock=clock)

        # --- Independent AKI timeline pipeline (not nested under SOFA emit) ---
        if aki_timeline.creatinine:
            aki_tl = evaluate_aki_timeline(aki_timeline, as_of=clock)
            aki = aki_tl.score
            aki_tier = tier_for_aki_score(aki.total_score)
            if (
                aki_tl.status == "scored"
                and aki_tier.value in {"watch", "urgent", "critical"}
            ):
                aki_alert = {
                    "alert_id": f"mimic-aki-{stay['stay_id']}-{aki_signal_count}",
                    "patient_id": patient_id,
                    "encounter_id": encounter_id,
                    "indicator": "aki",
                    "tier": aki_tier.value,
                    "score": aki.total_score,
                    "event_time": clock.isoformat(),
                    "evidence_ids": list(aki.evidence_ids or []),
                    "positive_components": 1 if (aki.total_score or 0) > 0 else 0,
                }
                aki_signal_count += 1
                # Naive AKI count is tracked separately from SOFA naive_times.
                _emit_signal(alert=aki_alert, gov_state=aki_gov, clock=clock)

    episode_count = 0
    if arb is not None:
        episode_count = len(arb.list_for_patient(patient_id))
    elif gov_alert_count:
        episode_count = gov_alert_count

    return {
        "stay_id": str(stay["stay_id"]),
        "subject_id": str(stay["subject_id"]),
        "split_id": stay.get("split_id"),
        "labels": dict(stay.get("labels") or {}),
        "timeline_hash": content_hash_events(events),
        "patient_days": _patient_days(stay),
        "naive_alert_count": len(naive_times),
        "naive_interruptive_count": naive_interruptive,
        "naive_alert_times": naive_times,
        "governed_alert_count": gov_alert_count,
        "governed_alert_times": gov_times,
        "interruptive_alert_count": page_alert_count,
        "interruptive_alert_times": page_times,
        "episode_count": episode_count,
        "aki_signal_count": aki_signal_count,
        "completeness_partial": partial,
        "pipelines": ["sofa-deterioration", "aki-kdigo-timeline"],
    }
