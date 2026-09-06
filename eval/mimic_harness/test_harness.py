"""CURIE-015: leakage-safe MIMIC timeline harness."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from eval.mimic_harness.replay import (
    LeakageError,
    StayReplayState,
    VasopressorState,
    _active_vasopressor,
    _apply_observation,
    _urine_ml_day,
    assert_snapshot_leakage_free,
    load_leaky_snapshots_example,
    replay_stay,
    result_to_public_dict,
    run_demo_schema_harness,
    stable_report_hash,
)
from eval.mimic_harness.runner import main
from ingestion.adapters.mimic.envelope import events_to_envelopes
from ingestion.adapters.mimic.timeline import (
    MimicTimelineEvent,
    events_from_demo_schema_stay,
    sort_by_availability,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "mimic_harness"
    / "demo_schema_stays.v1.json"
)


def test_demo_schema_e2e_completes() -> None:
    report = run_demo_schema_harness()
    assert report["stays_scored"] >= 3
    assert report["content_hash"]
    assert report["code_pins"]["protocol_id"] == "mimic-iv-governance-study.v1"
    stays = {s["stay_id"]: s for s in report["stays"]}
    assert "stay-demo-002" in stays
    # Deteriorating stay should emit at least one signal and one episode
    assert stays["stay-demo-002"]["signals"]
    assert stays["stay-demo-002"]["episodes"]
    assert stays["stay-demo-002"]["envelopes"] >= 1


def test_repeated_runs_identical_content_hash() -> None:
    a = run_demo_schema_harness()
    b = run_demo_schema_harness()
    assert a["content_hash"] == b["content_hash"]
    assert stable_report_hash({k: v for k, v in a.items() if k != "content_hash"}) == a[
        "content_hash"
    ]


def test_availability_orders_storetime_after_charttime() -> None:
    data = json.loads(FIXTURE.read_text())
    stay = next(s for s in data["stays"] if s["stay_id"] == "stay-demo-002")
    events = events_from_demo_schema_stay(stay)
    ordered = sort_by_availability(events)
    # MAP chart at 13:00 before labs that store later
    assert ordered[0].evidence_id == "chart/map-low"
    plt = next(e for e in ordered if e.evidence_id == "lab/plt-low")
    assert plt.event_time.hour == 14
    assert plt.availability_time.hour == 16
    # Discharge DX last (availability at discharge)
    assert ordered[-1].is_discharge_diagnosis


def test_chart_availability_orders_storetime_after_charttime() -> None:
    """Chart events (MAP, GCS, SpO2, FiO2, ventilation, ...) must defer to a later
    storetime the same way lab events already do — a value cannot be scoreable
    before it was actually knowable, regardless of source table."""
    stay = {
        "stay_id": "u1",
        "subject_id": "s1",
        "hadm_id": "h1",
        "intime": "2019-01-01 00:00:00",
        "outtime": "2019-01-02 00:00:00",
        "labels": {"sepsis3_onset": None, "aki_kdigo_stage_ge_1": None},
        "labs": [],
        "charts": [
            {
                "itemid": 220052,
                "valuenum": 58,
                "unit": "mmHg",
                "charttime": "2019-01-01 13:00:00",
                "storetime": "2019-01-01 16:00:00",
                "evidence_id": "chart/map-late-store",
            }
        ],
        "conditions": [],
    }
    events = events_from_demo_schema_stay(stay)
    (event,) = events
    assert event.event_time.hour == 13
    assert event.availability_time.hour == 16


def test_envelopes_carry_availability_time() -> None:
    data = json.loads(FIXTURE.read_text())
    events = events_from_demo_schema_stay(data["stays"][1])
    envs = events_to_envelopes(events)
    assert envs
    assert all(e.availability_time is not None for e in envs)
    assert envs == sorted(
        envs, key=lambda e: (e.effective_availability_time(), e.idempotency_key)
    )


def test_discharge_diagnosis_never_in_scoring_evidence() -> None:
    data = json.loads(FIXTURE.read_text())
    stay = next(s for s in data["stays"] if s["stay_id"] == "stay-demo-002")
    result = replay_stay(stay)
    for snap in result.snapshots:
        assert "dx/sepsis-discharge" not in snap["evidence_ids"]
    for sig in result.signals:
        assert "dx/sepsis-discharge" not in sig["evidence_ids"]


def test_leakage_detector_fails_on_future_lab() -> None:
    events, snap = load_leaky_snapshots_example()
    by_id = {e.evidence_id: e for e in events}
    with pytest.raises(LeakageError, match="Leakage"):
        assert_snapshot_leakage_free(events_by_id=by_id, snapshot=snap)


def test_cli_runner_exits_zero(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    assert main(["--json-out", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["stays_scored"] >= 1
    assert report["content_hash"]


def test_public_dict_omits_raw_snapshots_by_default() -> None:
    data = json.loads(FIXTURE.read_text())
    result = replay_stay(data["stays"][0])
    public = result_to_public_dict(result)
    assert "snapshots" not in public
    assert "final_snapshot" in public


def test_harness_urine_only_scores_renal() -> None:
    from eval.mimic_harness.replay import replay_stay

    stay = {
        "stay_id": "u1",
        "subject_id": "s1",
        "hadm_id": "h1",
        "intime": "2019-01-01 00:00:00",
        "outtime": "2019-01-02 12:00:00",
        "labels": {"sepsis3_onset": None, "aki_kdigo_stage_ge_1": None},
        "labs": [],
        "charts": [
            {
                "itemid": "urine",
                "code": "9187-6",
                "display": "Urine output",
                "valuenum": 400.0,
                "unit": "mL",
                "charttime": "2019-01-02 00:00:00",
                "evidence_id": "uo/1",
            }
        ],
        "conditions": [],
    }
    result = replay_stay(stay)
    assert result.snapshots
    assert "renal" not in (result.snapshots[-1].get("missing_components") or [])


def test_urine_is_missing_until_full_24_hour_stay_window() -> None:
    start = datetime(2019, 1, 1)
    state = StayReplayState(stay_started_at=start)
    state.urine_events.append((start + timedelta(hours=10), 400.0, "uo/1"))
    assert _urine_ml_day(state, clock=start + timedelta(hours=23, minutes=59)) == (None, [])
    assert _urine_ml_day(state, clock=start + timedelta(hours=24)) == (400.0, ["uo/1"])


def test_harness_vasopressor_only_scores_cardiovascular() -> None:
    from eval.mimic_harness.replay import replay_stay

    stay = {
        "stay_id": "u1",
        "subject_id": "s1",
        "hadm_id": "h1",
        "intime": "2019-01-01 00:00:00",
        "outtime": "2019-01-02 00:00:00",
        "labels": {"sepsis3_onset": None, "aki_kdigo_stage_ge_1": None},
        "labs": [],
        "charts": [
            {
                "itemid": "norepinephrine",
                "code": "curie-vasopressor",
                "display": "norepinephrine",
                "valuenum": 0.2,
                "unit": "mcg/kg/min",
                "charttime": "2019-01-01 10:00:00",
                "evidence_id": "vaso/1",
            }
        ],
        "conditions": [],
    }
    result = replay_stay(stay)
    assert result.snapshots
    assert "cardiovascular" not in (result.snapshots[-1].get("missing_components") or [])


def test_unknown_vasopressor_dose_is_explicit_and_uses_fallback_points() -> None:
    clock = datetime(2019, 1, 1, 1)
    event = MimicTimelineEvent(
        stay_id="u1",
        subject_id="s1",
        hadm_id="h1",
        kind="chart",
        itemid="norepinephrine",
        valuenum=None,
        unit="mcg/kg/min",
        event_time=clock,
        availability_time=clock,
        evidence_id="vaso/unknown",
        code="curie-vasopressor",
        display="norepinephrine",
    )
    state = StayReplayState(stay_started_at=datetime(2019, 1, 1))
    _apply_observation(state, event, clock=clock)
    pressor = _active_vasopressor(state, clock=clock)
    assert isinstance(pressor, VasopressorState)
    assert state.vaso_dose_known is False
    assert pressor.dose is None
    component = state.components[
        next(name for name in state.components if name.value == "cardiovascular")
    ]
    from eval.sofa.scoring import compute_sofa_score

    score = compute_sofa_score(
        patient_id="Patient/s1",
        event_time=clock,
        inputs=[component],
        rule_bundle_id="sepsis-sofa",
        rule_version="0.3.0",
        min_components_required=1,
    )
    cardiovascular = next(
        component for component in score.components if component.name.value == "cardiovascular"
    )
    assert cardiovascular.points == 3


def test_non_normalized_pressor_unit_never_reads_dose() -> None:
    """A positive valuenum with a non-normalized unit (e.g. mcg/min) must not be
    silently read as mcg/kg/min (CURIE-051 fail-closed replay guard)."""
    clock = datetime(2019, 1, 1, 1)
    event = MimicTimelineEvent(
        stay_id="u1",
        subject_id="s1",
        hadm_id="h1",
        kind="chart",
        itemid="221906",
        valuenum=5.0,  # would be 5 mcg/kg/min if misread — an absurd dose
        unit="mcg/min",
        event_time=clock,
        availability_time=clock,
        evidence_id="vaso/mcg-min",
        code="curie-vasopressor",
        display="norepinephrine",
    )
    state = StayReplayState(stay_started_at=datetime(2019, 1, 1))
    _apply_observation(state, event, clock=clock)
    pressor = _active_vasopressor(state, clock=clock)
    assert pressor.on_pressor
    assert pressor.dose is None
    assert state.vaso_dose_known is False


def test_normalized_pressor_unit_reads_dose() -> None:
    clock = datetime(2019, 1, 1, 1)
    event = MimicTimelineEvent(
        stay_id="u1",
        subject_id="s1",
        hadm_id="h1",
        kind="chart",
        itemid="221906",
        valuenum=0.2,
        unit="mcg/kg/min",
        event_time=clock,
        availability_time=clock,
        evidence_id="vaso/ok",
        code="curie-vasopressor",
        display="norepinephrine",
    )
    state = StayReplayState(stay_started_at=datetime(2019, 1, 1))
    _apply_observation(state, event, clock=clock)
    pressor = _active_vasopressor(state, clock=clock)
    assert pressor.on_pressor
    assert pressor.dose == 0.2


def test_pressor_extras_reason_recorded() -> None:
    clock = datetime(2019, 1, 1, 1)
    event = MimicTimelineEvent(
        stay_id="u1",
        subject_id="s1",
        hadm_id="h1",
        kind="chart",
        itemid="222315",
        valuenum=None,
        unit="units/hour",
        event_time=clock,
        availability_time=clock,
        evidence_id="vaso/units-hour",
        code="curie-vasopressor",
        display="other",
        extras={"pressor": {"known": False, "reason": "unsupported_unit:units/hour"}},
    )
    state = StayReplayState(stay_started_at=datetime(2019, 1, 1))
    _apply_observation(state, event, clock=clock)
    assert state.vaso_dose_reason == "unsupported_unit:units/hour"


def test_late_fio2_pairs_with_prior_spo2() -> None:
    """FiO2 after SpO2 still forms a ratio (re-pair on FiO2 arrival)."""
    stay = {
        "stay_id": "stay-resp-1",
        "subject_id": "s1",
        "hadm_id": "h1",
        "intime": "2150-01-01 00:00:00",
        "outtime": "2150-01-01 06:00:00",
        "labs": [],
        "charts": [
            {
                "code_system": "http://loinc.org",
                "code": "2708-6",
                "display": "SpO2",
                "valuenum": 88,
                "unit": "%",
                "charttime": "2150-01-01 01:00:00",
                "storetime": "2150-01-01 01:00:00",
                "evidence_id": "chart/spo2",
                "itemid": 220277,
            },
            {
                "code_system": "http://loinc.org",
                "code": "3150-0",
                "display": "FiO2",
                "valuenum": 40,
                "unit": "%",
                "charttime": "2150-01-01 01:30:00",
                "storetime": "2150-01-01 01:30:00",
                "evidence_id": "chart/fio2",
                "itemid": 223835,
            },
        ],
        "conditions": [],
        "labels": {},
    }
    result = replay_stay(stay)
    assert result.snapshots
    missing = result.snapshots[-1].get("missing_components") or []
    assert "respiration" not in missing


def test_pao2_with_fio2_scores_respiration() -> None:
    stay = {
        "stay_id": "stay-resp-2",
        "subject_id": "s1",
        "hadm_id": "h1",
        "intime": "2150-01-01 00:00:00",
        "outtime": "2150-01-01 06:00:00",
        "labs": [
            {
                "code_system": "http://loinc.org",
                "code": "2703-7",
                "display": "PaO2",
                "valuenum": 55,
                "unit": "mmHg",
                "charttime": "2150-01-01 02:00:00",
                "storetime": "2150-01-01 02:00:00",
                "evidence_id": "lab/pao2",
                "itemid": 50821,
            }
        ],
        "charts": [
            {
                "code_system": "http://loinc.org",
                "code": "3150-0",
                "display": "FiO2",
                "valuenum": 50,
                "unit": "%",
                "charttime": "2150-01-01 01:00:00",
                "storetime": "2150-01-01 01:00:00",
                "evidence_id": "chart/fio2",
                "itemid": 223835,
            }
        ],
        "conditions": [],
        "labels": {},
    }
    result = replay_stay(stay)
    assert result.snapshots
    missing = result.snapshots[-1].get("missing_components") or []
    assert "respiration" not in missing
