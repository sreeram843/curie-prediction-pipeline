"""CURIE-009: stateful KDIGO timeline fixtures."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from eval.aki.timeline import (
    AkiTimelineState,
    CreatinineObs,
    UrineObs,
    WeightObs,
    evaluate_aki_timeline,
)

CASES = Path(__file__).resolve().parent / "golden" / "aki_timeline_cases.v1.json"


def _load_state(events: list[dict]) -> AkiTimelineState:
    state = AkiTimelineState(patient_id="Patient/aki-tl")
    for e in events:
        etype = e["type"]
        if etype == "creatinine":
            state.ingest_creatinine(
                CreatinineObs(
                    event_time=datetime.fromisoformat(e["event_time"]),
                    value_mg_dl=float(e["value"]),
                    evidence_id=e["evidence_id"],
                    status=e.get("status", "final"),
                    as_baseline=bool(e.get("as_baseline", False)),
                )
            )
        elif etype == "urine_volume":
            state.ingest_urine(
                UrineObs(
                    end_time=datetime.fromisoformat(e["event_time"]),
                    evidence_id=e["evidence_id"],
                    volume_ml=float(e["volume_ml"]),
                    duration_hours=float(e["duration_hours"]),
                )
            )
        elif etype == "urine_rate":
            state.ingest_urine(
                UrineObs(
                    end_time=datetime.fromisoformat(e["event_time"]),
                    evidence_id=e["evidence_id"],
                    ml_kg_h=float(e["ml_kg_h"]),
                    duration_hours=float(e["duration_hours"]),
                )
            )
        elif etype == "anuria":
            state.ingest_urine(
                UrineObs(
                    end_time=datetime.fromisoformat(e["event_time"]),
                    evidence_id=e["evidence_id"],
                    duration_hours=float(e["duration_hours"]),
                    anuria=True,
                )
            )
        elif etype == "weight":
            state.ingest_weight(
                WeightObs(
                    event_time=datetime.fromisoformat(e["event_time"]),
                    weight_kg=float(e["value"]),
                    evidence_id=e["evidence_id"],
                )
            )
        elif etype == "flag":
            state.set_flag(e["name"], bool(e.get("present", True)))
        else:
            raise AssertionError(f"unknown event type {etype}")
    return state


def test_aki_timeline_fixture_cases() -> None:
    data = json.loads(CASES.read_text())
    assert data["timeline_version"] == "1.0.0"
    assert len(data["cases"]) >= 10
    for case in data["cases"]:
        state = _load_state(case["events"])
        result = evaluate_aki_timeline(
            state, as_of=datetime.fromisoformat(case["as_of"])
        )
        expect = case["expect"]
        if "status" in expect:
            assert result.status == expect["status"], case["id"]
        if "stage" in expect:
            assert result.score.stage == expect["stage"], case["id"]
        if "urine_stage" in expect:
            assert result.score.urine_stage == expect["urine_stage"], case["id"]
        if "baseline_7d_mg_dl" in expect:
            assert result.baseline_7d_mg_dl == expect["baseline_7d_mg_dl"], case["id"]
        if "reference_48h_mg_dl" in expect:
            assert result.reference_48h_mg_dl == expect["reference_48h_mg_dl"], case[
                "id"
            ]
        if "weight_kg" in expect:
            assert result.weight_kg == expect["weight_kg"], case["id"]
        if "completeness" in expect:
            assert result.score.completeness.value == expect["completeness"], case["id"]
        if "criteria_contains" in expect:
            for c in expect["criteria_contains"]:
                assert c in result.criteria_met, (case["id"], c, result.criteria_met)
        if "criteria_excludes" in expect:
            for c in expect["criteria_excludes"]:
                assert c not in result.criteria_met, case["id"]
        if "missing_contains" in expect:
            for m in expect["missing_contains"]:
                assert m in result.score.missing_components, case["id"]


def test_permutation_ingest_order_invariant() -> None:
    events_a = [
        CreatinineObs(
            event_time=datetime.fromisoformat("2024-07-01T00:00:00+00:00"),
            value_mg_dl=1.0,
            evidence_id="Observation/a",
        ),
        CreatinineObs(
            event_time=datetime.fromisoformat("2024-07-02T00:00:00+00:00"),
            value_mg_dl=2.0,
            evidence_id="Observation/b",
        ),
    ]
    events_b = list(reversed(events_a))
    as_of = datetime.fromisoformat("2024-07-02T00:00:00+00:00")

    sa = AkiTimelineState(patient_id="Patient/p")
    sb = AkiTimelineState(patient_id="Patient/p")
    for e in events_a:
        sa.ingest_creatinine(e)
    for e in events_b:
        sb.ingest_creatinine(e)

    ra = evaluate_aki_timeline(sa, as_of=as_of)
    rb = evaluate_aki_timeline(sb, as_of=as_of)
    assert ra.score.stage == rb.score.stage == 2
    assert ra.baseline_7d_mg_dl == rb.baseline_7d_mg_dl
    assert ra.criteria_met == rb.criteria_met


def test_restart_replay_preserves_stage() -> None:
    """Serialize-by-reingest (restart) yields same stage."""
    raw = [
        {
            "type": "creatinine",
            "event_time": "2024-07-01T00:00:00+00:00",
            "value": 1.0,
            "evidence_id": "Observation/cr-0",
        },
        {
            "type": "creatinine",
            "event_time": "2024-07-02T16:00:00+00:00",
            "value": 1.5,
            "evidence_id": "Observation/cr-1",
        },
    ]
    as_of = datetime.fromisoformat("2024-07-02T16:00:00+00:00")
    first = evaluate_aki_timeline(_load_state(raw), as_of=as_of)
    second = evaluate_aki_timeline(_load_state(raw), as_of=as_of)
    assert first.score.model_dump() == second.score.model_dump()
    assert first.onset_time == second.onset_time


def test_onset_time_is_first_stage_ge_1() -> None:
    state = AkiTimelineState(patient_id="Patient/onset")
    t0 = datetime.fromisoformat("2024-07-01T00:00:00+00:00")
    t1 = datetime.fromisoformat("2024-07-01T20:00:00+00:00")
    t2 = datetime.fromisoformat("2024-07-02T00:00:00+00:00")
    state.ingest_creatinine(
        CreatinineObs(event_time=t0, value_mg_dl=1.0, evidence_id="Observation/a")
    )
    state.ingest_creatinine(
        CreatinineObs(event_time=t1, value_mg_dl=1.1, evidence_id="Observation/b")
    )
    state.ingest_creatinine(
        CreatinineObs(event_time=t2, value_mg_dl=1.5, evidence_id="Observation/c")
    )
    result = evaluate_aki_timeline(state, as_of=t2)
    assert result.score.stage == 1
    assert result.onset_time == t2
