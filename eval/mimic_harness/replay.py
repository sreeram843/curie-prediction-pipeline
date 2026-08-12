"""Leakage-safe MIMIC timeline harness (CURIE-015).

Demo-schema fixtures run end-to-end without PhysioNet dumps. Replay orders by
availability_time; discharge diagnoses and future labs must not enter features
before they are available.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
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
    sort_by_availability,
)

HARNESS_VERSION = "0.1.0"
FIXTURES_DIR = (
    Path(__file__).resolve().parents[1] / "fixtures" / "mimic_harness"
)

# LOINC / itemid bridges used by demo-schema fixtures
_LOINC_TO_COMPONENT: dict[str, SofaComponentName] = {
    "777-3": SofaComponentName.COAGULATION,
    "1975-2": SofaComponentName.LIVER,
    "2160-0": SofaComponentName.RENAL,
    "2708-6": SofaComponentName.RESPIRATION,
    "8478-0": SofaComponentName.CARDIOVASCULAR,
    "9269-2": SofaComponentName.CNS,
}


class LeakageError(ValueError):
    """Future or unavailable information entered the scoring state."""


@dataclass
class StayReplayState:
    components: dict[SofaComponentName, SofaComponentInput] = field(default_factory=dict)
    creatinine_mg_dl: float | None = None
    creatinine_evidence: list[str] = field(default_factory=list)
    seen_evidence: set[str] = field(default_factory=set)
    discharge_dx_codes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    missingness: dict[str, int] = field(default_factory=dict)


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
    elif component == SofaComponentName.RESPIRATION:
        if (event.unit or "").lower() in {"%", "percent"}:
            kwargs["spo2_percent"] = event.valuenum
        else:
            kwargs["spo2_percent"] = event.valuenum
    elif component == SofaComponentName.CARDIOVASCULAR:
        kwargs["map_mmhg"] = event.valuenum
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


def replay_stay(
    stay: dict[str, Any],
    *,
    check_leakage: bool = True,
) -> StayHarnessResult:
    events = events_from_demo_schema_stay(stay)
    events = sort_by_availability(events)
    events_by_id = {e.evidence_id: e for e in events}
    envelopes = events_to_envelopes(events)
    state = StayReplayState()
    arb = EpisodeArbiter()
    signals: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    patient_id = f"Patient/{stay['subject_id']}"
    encounter_id = f"Encounter/{stay.get('hadm_id') or stay['stay_id']}"
    aki_timeline = AkiTimelineState(patient_id=patient_id, encounter_id=encounter_id)

    for event in events:
        clock = event.availability_time
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

        # Score after each availability tick that updates features
        sofa_inputs = list(state.components.values())
        if state.creatinine_mg_dl is not None and SofaComponentName.RENAL not in state.components:
            sofa_inputs.append(
                SofaComponentInput(
                    name=SofaComponentName.RENAL,
                    creatinine_mg_dl=state.creatinine_mg_dl,
                    evidence_ids=list(state.creatinine_evidence),
                )
            )

        if not sofa_inputs and state.creatinine_mg_dl is None:
            continue

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
