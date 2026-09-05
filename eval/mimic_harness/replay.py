"""Leakage-safe MIMIC timeline harness (CURIE-015).

Demo-schema fixtures run end-to-end without PhysioNet dumps. Replay orders by
availability_time; discharge diagnoses and future labs must not enter features
before they are available.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from eval.aki.scoring import tier_for_aki_score
from eval.aki.timeline import AkiTimelineState, CreatinineObs, evaluate_aki_timeline
from eval.episodes.arbiter import EpisodeArbiter
from eval.sofa.scoring import (
    SofaComponentInput,
    SofaComponentName,
    compute_sofa_score,
    tier_for_score,
)
from ingestion.adapters.mimic.envelope import events_to_envelopes
from ingestion.adapters.mimic.timeline import (
    MimicTimelineEvent,
    content_hash_events,
    events_from_demo_schema_stay,
    parse_mimic_ts,
    sort_by_availability,
)
from ingestion.adapters.mimic.vasopressors import is_normalized_dose_unit
from ingestion.adapters.respiration import resolve_spo2_fio2_pao2

HARNESS_VERSION = "0.1.0"
FIXTURES_DIR = (
    Path(__file__).resolve().parents[1] / "fixtures" / "mimic_harness"
)

# LOINC / itemid bridges used by demo-schema fixtures
_LOINC_TO_COMPONENT: dict[str, SofaComponentName] = {
    "777-3": SofaComponentName.COAGULATION,
    "1975-2": SofaComponentName.LIVER,
    "2160-0": SofaComponentName.RENAL,
    "8478-0": SofaComponentName.CARDIOVASCULAR,
    "9269-2": SofaComponentName.CNS,
}

# FiO2 / SpO2 / PaO2 are held as running state and composed into RESPIRATION
# at score time (PaO2 preferred over SpO2 when both pair with FiO2).
_FIO2_LOINC = "3150-0"
_PAO2_LOINC = "2703-7"
_SPO2_LOINC = "2708-6"
# How stale a previously observed FiO2 may be before it stops pairing with a
# new SpO2/PaO2 reading. Real charting rarely co-times SpO2/FiO2 (unlike labs,
# which pair readily), so pairing "latest FiO2 at or before this reading"
# (mirrors ingestion.adapters.mimic.extract.build_sofa_inputs) — bounded by a
# lookback window so a ratio is never built from a setting that may no longer hold.
_FIO2_LOOKBACK = timedelta(hours=24)
_URINE_LOINC = "9187-6"
_VASO_CODE = "curie-vasopressor"
_VASO_LOOKBACK = timedelta(hours=4)


class LeakageError(ValueError):
    """Future or unavailable information entered the scoring state."""


@dataclass
class StayReplayState:
    stay_started_at: datetime | None = None
    components: dict[SofaComponentName, SofaComponentInput] = field(default_factory=dict)
    creatinine_mg_dl: float | None = None
    creatinine_evidence: list[str] = field(default_factory=list)
    fio2_fraction: float | None = None
    fio2_evidence_id: str | None = None
    fio2_observed_at: datetime | None = None
    spo2_percent: float | None = None
    spo2_evidence_id: str | None = None
    spo2_observed_at: datetime | None = None
    pao2_mmhg: float | None = None
    pao2_evidence_id: str | None = None
    pao2_observed_at: datetime | None = None
    urine_events: list[tuple[datetime, float, str]] = field(default_factory=list)
    vaso_agent: str | None = None
    vaso_dose_ug_kg_min: float | None = None
    vaso_evidence_id: str | None = None
    vaso_observed_at: datetime | None = None
    vaso_dose_known: bool = False
    vaso_dose_reason: str | None = None
    seen_evidence: set[str] = field(default_factory=set)
    discharge_dx_codes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    missingness: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class VasopressorState:
    """Named, auditable vasopressor state used by cardiovascular scoring."""

    agent: str | None
    dose: float | None
    evidence_id: str | None
    on_pressor: bool


@dataclass
class StayHarnessResult:
    stay_id: str
    subject_id: str
    split_id: str | None
    timeline_hash: str
    envelopes: int
    signals: list[dict[str, Any]]
    episodes: list[dict[str, Any]]
    labels: dict[str, Any]
    errors: list[str]
    missingness: dict[str, int]
    snapshots: list[dict[str, Any]]



def _urine_ml_day(
    state: StayReplayState, *, clock: datetime
) -> tuple[float | None, list[str]]:
    if state.stay_started_at is None or clock - state.stay_started_at < timedelta(hours=24):
        return None, []
    window_start = clock - timedelta(hours=24)
    total = 0.0
    eids: list[str] = []
    for when, volume, eid in state.urine_events:
        if when <= clock and when > window_start:
            total += volume
            eids.append(eid)
    if not eids:
        return None, []
    return total, eids


def _active_vasopressor(
    state: StayReplayState, *, clock: datetime
) -> VasopressorState:
    if state.vaso_observed_at is None or state.vaso_agent is None:
        return VasopressorState(None, None, None, False)
    if clock < state.vaso_observed_at:
        return VasopressorState(None, None, None, False)
    if clock - state.vaso_observed_at > _VASO_LOOKBACK:
        return VasopressorState(None, None, None, False)
    dose = state.vaso_dose_ug_kg_min if state.vaso_dose_known else None
    return VasopressorState(state.vaso_agent, dose, state.vaso_evidence_id, True)


def _set_renal(
    state: StayReplayState, *, clock: datetime, extra_eids: list[str] | None = None
) -> None:
    uo, uo_eids = _urine_ml_day(state, clock=clock)
    eids = list(state.creatinine_evidence)
    eids.extend(uo_eids)
    if extra_eids:
        eids.extend(extra_eids)
    if state.creatinine_mg_dl is None and uo is None:
        return
    state.components[SofaComponentName.RENAL] = SofaComponentInput(
        name=SofaComponentName.RENAL,
        creatinine_mg_dl=state.creatinine_mg_dl,
        urine_output_ml_day=uo,
        evidence_ids=eids,
    )


def _set_cardiovascular(
    state: StayReplayState,
    *,
    clock: datetime,
    map_mmhg: float | None = None,
    map_eid: str | None = None,
) -> None:
    prev = state.components.get(SofaComponentName.CARDIOVASCULAR)
    if map_mmhg is None and prev is not None:
        map_mmhg = prev.map_mmhg
        if map_eid is None and prev.evidence_ids:
            map_eid = prev.evidence_ids[0]
    pressor = _active_vasopressor(state, clock=clock)
    if map_mmhg is None and not pressor.on_pressor:
        return
    eids: list[str] = []
    if map_eid:
        eids.append(map_eid)
    if pressor.evidence_id:
        eids.append(pressor.evidence_id)
    state.components[SofaComponentName.CARDIOVASCULAR] = SofaComponentInput(
        name=SofaComponentName.CARDIOVASCULAR,
        map_mmhg=map_mmhg,
        on_vasopressors=True if pressor.on_pressor else None,
        vasopressor_agent=pressor.agent,
        vasopressor_dose_ug_kg_min=pressor.dose,
        evidence_ids=eids,
    )


def _set_respiration(state: StayReplayState, *, clock: datetime) -> None:
    """Compose RESPIRATION from latest PaO2/SpO2 + FiO2 (C-SAFE-3: no ambient FiO2)."""
    resolved = resolve_spo2_fio2_pao2(
        pao2_mmhg=state.pao2_mmhg,
        pao2_observed_at=state.pao2_observed_at,
        pao2_evidence_id=state.pao2_evidence_id,
        spo2_percent=state.spo2_percent,
        spo2_observed_at=state.spo2_observed_at,
        spo2_evidence_id=state.spo2_evidence_id,
        fio2_fraction=state.fio2_fraction,
        fio2_observed_at=state.fio2_observed_at,
        fio2_evidence_id=state.fio2_evidence_id,
        as_of=clock,
        lookback=_FIO2_LOOKBACK,
    )
    if resolved.source is not None:
        state.components[SofaComponentName.RESPIRATION] = SofaComponentInput(
            name=SofaComponentName.RESPIRATION,
            pao2_fio2=resolved.pao2_fio2,
            spo2_fio2=resolved.spo2_fio2,
            evidence_ids=list(resolved.evidence_ids),
        )
        return
    # Incomplete without FiO2 — leave prior incomplete/missing; clear scoreable resp.
    state.components.pop(SofaComponentName.RESPIRATION, None)


def _apply_observation(

    state: StayReplayState,
    event: MimicTimelineEvent,
    *,
    clock: datetime,
) -> None:
    if event.availability_time > clock:
        raise LeakageError(
            f"Applied {event.evidence_id} at {clock.isoformat()} before "
            f"availability {event.availability_time.isoformat()}"
        )
    if event.is_discharge_diagnosis:
        # Discharge diagnoses are never features for scoring in this harness.
        state.discharge_dx_codes.append(str(event.code or event.evidence_id))
        return

    state.seen_evidence.add(event.evidence_id)
    code = event.code or ""
    if code == "2160-0" or event.itemid in {50912, 52546, 220615}:
        if event.valuenum is not None:
            state.creatinine_mg_dl = float(event.valuenum)
            state.creatinine_evidence = [event.evidence_id]
            _set_renal(state, clock=clock)
        return

    if code == _URINE_LOINC:
        if event.valuenum is not None:
            when = event.event_time or clock
            state.urine_events.append((when, float(event.valuenum), event.evidence_id))
            _set_renal(state, clock=clock, extra_eids=[event.evidence_id])
        return

    if code == _VASO_CODE:
        agent = (event.display or "other").strip().lower() or "other"
        state.vaso_agent = agent
        state.vaso_evidence_id = event.evidence_id
        state.vaso_observed_at = event.event_time or clock
        pressor_meta = (event.extras or {}).get("pressor") or {}
        state.vaso_dose_reason = str(
            pressor_meta.get("reason") or "harness_event"
        )
        # Fail closed: a positive valuenum is only a known mcg/kg/min dose when
        # the event unit is a normalized dose unit. Any other non-empty unit
        # (mcg/min, units/hour, mL/hour, ...) is never silently re-read as
        # mcg/kg/min — pressor stays present with an explicit unknown dose.
        if (
            event.valuenum is not None
            and event.valuenum > 0
            and is_normalized_dose_unit(event.unit)
        ):
            state.vaso_dose_ug_kg_min = float(event.valuenum)
            state.vaso_dose_known = True
        else:
            state.vaso_dose_ug_kg_min = None
            state.vaso_dose_known = False
        _set_cardiovascular(state, clock=clock)
        return

    if code == _FIO2_LOINC:
        # FiO2 is percent-scale on this path (ingestion.adapters.syn_icu.convert);
        # never store a non-positive fraction — effective_resp_ratio treats that
        # as "no FiO2 known" (C-SAFE-3: never assume ambient-air FiO2).
        if event.valuenum is not None and event.valuenum > 0:
            state.fio2_fraction = float(event.valuenum) / 100.0
            state.fio2_evidence_id = event.evidence_id
            state.fio2_observed_at = event.event_time or clock
            _set_respiration(state, clock=clock)
        return

    if code == _PAO2_LOINC:
        if event.valuenum is not None and event.valuenum > 0:
            state.pao2_mmhg = float(event.valuenum)
            state.pao2_evidence_id = event.evidence_id
            state.pao2_observed_at = event.event_time or clock
            _set_respiration(state, clock=clock)
        return

    if code == _SPO2_LOINC:
        if event.valuenum is not None:
            state.spo2_percent = float(event.valuenum)
            state.spo2_evidence_id = event.evidence_id
            state.spo2_observed_at = event.event_time or clock
            _set_respiration(state, clock=clock)
        return

    component = _LOINC_TO_COMPONENT.get(code)
    if component is None:
        state.missingness["unmapped_observation"] = (
            state.missingness.get("unmapped_observation", 0) + 1
        )
        return

    kwargs: dict[str, Any] = {
        "name": component,
        "evidence_ids": [event.evidence_id],
    }
    if component == SofaComponentName.COAGULATION:
        kwargs["platelets_10e9_l"] = event.valuenum
    elif component == SofaComponentName.LIVER:
        kwargs["bilirubin_mg_dl"] = event.valuenum
    elif component == SofaComponentName.RENAL:
        kwargs["creatinine_mg_dl"] = event.valuenum
    elif component == SofaComponentName.CARDIOVASCULAR:
        _set_cardiovascular(
            state,
            clock=clock,
            map_mmhg=float(event.valuenum) if event.valuenum is not None else None,
            map_eid=event.evidence_id,
        )
        return
    elif component == SofaComponentName.CNS:
        kwargs["gcs"] = int(event.valuenum) if event.valuenum is not None else None

    state.components[component] = SofaComponentInput(**kwargs)


def assert_snapshot_leakage_free(
    *,
    events_by_id: dict[str, MimicTimelineEvent],
    snapshot: dict[str, Any],
) -> None:
    """Fail closed if any evidence used in a snapshot was not yet available."""
    clock = datetime.fromisoformat(snapshot["availability_clock"])
    for eid in snapshot.get("evidence_ids") or []:
        event = events_by_id.get(eid)
        if event is None:
            raise LeakageError(f"Unknown evidence_id in snapshot: {eid}")
        if event.availability_time > clock:
            raise LeakageError(
                f"Leakage: evidence {eid} available at "
                f"{event.availability_time.isoformat()} used at {clock.isoformat()}"
            )
        if event.is_discharge_diagnosis:
            raise LeakageError(
                f"Leakage: discharge diagnosis {eid} used as scoring evidence"
            )


def _parse_stay_datetime(raw: Any) -> datetime | None:
    return parse_mimic_ts(str(raw)) if raw else None


def replay_stay(
    stay: dict[str, Any],
    *,
    check_leakage: bool = True,
    score_every_event: bool = True,
) -> StayHarnessResult:
    """Replay a demo-schema stay.

    When ``score_every_event`` is false, observations are applied for the full
    timeline but SOFA/AKI are scored once at the end. That matches final-snapshot
    missingness cards (Milestone 11) at much lower cost.
    """
    events = events_from_demo_schema_stay(stay)
    events = sort_by_availability(events)
    events_by_id = {e.evidence_id: e for e in events}
    envelopes = events_to_envelopes(events)
    state = StayReplayState(stay_started_at=_parse_stay_datetime(stay.get("intime")))
    arb = EpisodeArbiter()
    signals: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    patient_id = f"Patient/{stay['subject_id']}"
    encounter_id = f"Encounter/{stay.get('hadm_id') or stay['stay_id']}"
    aki_timeline = AkiTimelineState(patient_id=patient_id, encounter_id=encounter_id)

    def _score_at(clock: datetime) -> None:
        sofa_inputs = list(state.components.values())
        if not sofa_inputs and any(
            value is not None
            for value in (state.pao2_mmhg, state.spo2_percent, state.fio2_fraction)
        ):
            sofa_inputs.append(
                SofaComponentInput(
                    name=SofaComponentName.RESPIRATION,
                    evidence_ids=[
                        evidence_id
                        for evidence_id in (
                            state.pao2_evidence_id,
                            state.spo2_evidence_id,
                            state.fio2_evidence_id,
                        )
                        if evidence_id
                    ],
                )
            )
        if state.creatinine_mg_dl is not None and SofaComponentName.RENAL not in state.components:
            sofa_inputs.append(
                SofaComponentInput(
                    name=SofaComponentName.RENAL,
                    creatinine_mg_dl=state.creatinine_mg_dl,
                    evidence_ids=list(state.creatinine_evidence),
                )
            )

        if not sofa_inputs and state.creatinine_mg_dl is None:
            return

        sofa = compute_sofa_score(
            patient_id=patient_id,
            event_time=clock,
            inputs=sofa_inputs,
            encounter_id=encounter_id,
            rule_bundle_id="sepsis-sofa",
            rule_version="0.3.0",
            min_components_required=1,
        )
        tier = tier_for_score(sofa.total_score)
        evidence = list(sofa.evidence_ids or [])
        snap = {
            "availability_clock": clock.isoformat(),
            "evidence_ids": evidence,
            "score": sofa.total_score,
            "tier": tier.value,
            "completeness": sofa.completeness.value,
            "missing_components": [
                m.value if hasattr(m, "value") else str(m)
                for m in (sofa.missing_components or [])
            ],
        }
        if check_leakage:
            assert_snapshot_leakage_free(events_by_id=events_by_id, snapshot=snap)
        snapshots.append(snap)

        if tier.value in {"watch", "urgent", "critical"}:
            alert = {
                "alert_id": f"mimic-{stay['stay_id']}-{len(signals)}",
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "indicator": "sofa-deterioration",
                "tier": tier.value,
                "routing": (
                    "interruptive" if tier.value in {"urgent", "critical"} else "passive"
                ),
                "score": sofa.total_score,
                "event_time": clock,
                "evidence_ids": evidence,
            }
            arb.ingest(alert)
            signals.append(
                {
                    "signal_type": "sofa-deterioration",
                    "score": sofa.total_score,
                    "severity": tier.value,
                    "event_time": clock.isoformat(),
                    "evidence_ids": evidence,
                    "completeness": sofa.completeness.value,
                }
            )

        if aki_timeline.creatinine:
            aki_tl = evaluate_aki_timeline(aki_timeline, as_of=clock)
            aki = aki_tl.score
            aki_tier = tier_for_aki_score(aki.total_score)
            if (
                aki_tl.status == "scored"
                and aki_tier.value in {"watch", "urgent", "critical"}
            ):
                arb.ingest(
                    {
                        "alert_id": f"mimic-aki-{stay['stay_id']}-{len(signals)}",
                        "patient_id": patient_id,
                        "encounter_id": encounter_id,
                        "indicator": "aki",
                        "tier": aki_tier.value,
                        "routing": (
                            "interruptive"
                            if aki_tier.value in {"urgent", "critical"}
                            else "passive"
                        ),
                        "score": aki.total_score,
                        "event_time": clock,
                        "evidence_ids": list(aki.evidence_ids or []),
                    }
                )
                signals.append(
                    {
                        "signal_type": "aki",
                        "score": aki.total_score,
                        "severity": aki_tier.value,
                        "event_time": clock.isoformat(),
                        "evidence_ids": list(aki.evidence_ids or []),
                        "completeness": aki.completeness.value,
                        "pipeline": "aki-kdigo-timeline",
                    }
                )

    last_clock: datetime | None = None
    for event in events:
        clock = event.availability_time
        last_clock = clock
        try:
            _apply_observation(state, event, clock=clock)
        except LeakageError:
            raise
        except Exception as exc:  # noqa: BLE001 — capture per-event errors
            state.errors.append(f"{event.evidence_id}: {exc}")
            continue

        code = event.code or ""
        if (
            (code == "2160-0" or event.itemid in {50912, 52546, 220615})
            and event.valuenum is not None
        ):
            aki_timeline.ingest_creatinine(
                CreatinineObs(
                    event_time=event.event_time or clock,
                    value_mg_dl=float(event.valuenum),
                    evidence_id=event.evidence_id,
                    status="final",
                )
            )

        if score_every_event:
            _score_at(clock)

    if not score_every_event and last_clock is not None:
        _score_at(last_clock)

    episodes = [e.model_dump(mode="json") for e in arb.list_for_patient(patient_id)]
    # Deterministic episode ids for content hashing (arbiter uses uuid4 at runtime).
    for idx, ep in enumerate(episodes):
        ep["episode_id"] = f"episode-{stay['stay_id']}-{idx}"
    labels = dict(stay.get("labels") or {})
    # Never treat discharge DX codes as labels before availability — only fixture labels.
    return StayHarnessResult(
        stay_id=str(stay["stay_id"]),
        subject_id=str(stay["subject_id"]),
        split_id=stay.get("split_id"),
        timeline_hash=content_hash_events(events),
        envelopes=len(envelopes),
        signals=signals,
        episodes=episodes,
        labels=labels,
        errors=list(state.errors),
        missingness=dict(state.missingness),
        snapshots=snapshots,
    )



def result_to_public_dict(result: StayHarnessResult) -> dict[str, Any]:
    return {
        "stay_id": result.stay_id,
        "subject_id": result.subject_id,
        "split_id": result.split_id,
        "timeline_hash": result.timeline_hash,
        "envelopes": result.envelopes,
        "signals": result.signals,
        "episodes": result.episodes,
        "labels": result.labels,
        "errors": result.errors,
        "missingness": result.missingness,
        "snapshot_count": len(result.snapshots),
        "final_snapshot": result.snapshots[-1] if result.snapshots else None,
    }


def stable_report_hash(report: dict[str, Any]) -> str:
    """Hash report without volatile keys (none expected — still canonicalize)."""
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_demo_schema_harness(
    *,
    fixtures_dir: Path | None = None,
    check_leakage: bool = True,
) -> dict[str, Any]:
    root = fixtures_dir or FIXTURES_DIR
    stays_path = root / "demo_schema_stays.v1.json"
    data = json.loads(stays_path.read_text())
    stays = list(data.get("stays") or [])
    results = [
        result_to_public_dict(replay_stay(stay, check_leakage=check_leakage))
        for stay in stays
    ]
    report = {
        "harness_version": HARNESS_VERSION,
        "schema": "mimic-iv-demo-schema",
        "fixture": str(stays_path.name),
        "fixture_schema_version": data.get("schema_version"),
        "dataset_pin": data.get("dataset_pin")
        or {
            "name": "demo-schema-fixtures",
            "note": "Synthetic MIMIC-IV-shaped stays; not PhysioNet patient data",
        },
        "code_pins": {
            "harness_version": HARNESS_VERSION,
            "protocol_id": "mimic-iv-governance-study.v1",
            "derived_concept_sql": data.get("derived_concept_sql_pin")
            or "pending-mimic-code-sha",
        },
        "stays_scored": len(results),
        "stays": results,
    }
    report["content_hash"] = stable_report_hash(
        {k: v for k, v in report.items() if k != "content_hash"}
    )
    return report


def load_leaky_snapshots_example() -> tuple[list[MimicTimelineEvent], dict[str, Any]]:
    """Intentionally leaky snapshot for negative tests."""
    stay = {
        "stay_id": "leak-1",
        "subject_id": "9",
        "hadm_id": "9",
        "labs": [
            {
                "itemid": 51265,
                "code": "777-3",
                "valuenum": 40,
                "unit": "10*9/L",
                "charttime": "2019-01-01 10:00:00",
                "storetime": "2019-01-01 14:00:00",
                "evidence_id": "lab/plt-late",
            }
        ],
    }
    events = events_from_demo_schema_stay(stay)
    # Snapshot claims the lab at charttime — before storetime availability.
    snap = {
        "availability_clock": "2019-01-01T10:00:00",
        "evidence_ids": ["lab/plt-late"],
    }
    return events, snap
