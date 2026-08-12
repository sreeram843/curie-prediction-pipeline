"""CURIE-015: leakage-safe MIMIC timeline harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.mimic_harness.replay import (
    LeakageError,
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
