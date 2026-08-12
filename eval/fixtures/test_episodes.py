"""CURIE-012: episode aggregation + arbitration fixtures."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from eval.episodes.arbiter import EpisodeArbiter, EpisodeConfig, select_dominant
from eval.episodes.models import SignalRef

CASES = Path(__file__).resolve().parent / "golden" / "episode_cases.v1.json"


def _alert(patient_id: str, encounter_id: str, raw: dict) -> dict:
    return {
        "alert_id": raw["alert_id"],
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "indicator": raw["indicator"],
        "tier": raw["tier"],
        "routing": raw.get("routing"),
        "score": raw.get("score"),
        "event_time": datetime.fromisoformat(raw["event_time"]),
        "evidence_ids": list(raw.get("evidence_ids") or []),
        "suppressed": bool(raw.get("suppressed", False)),
    }


def test_episode_fixture_cases() -> None:
    data = json.loads(CASES.read_text())
    cfg = EpisodeConfig(**data["config"])
    for case in data["cases"]:
        arb = EpisodeArbiter(cfg)
        pid = case["patient_id"]
        enc = case["encounter_id"]
        page_actions = 0
        passive_actions = 0
        for raw in case["events"]:
            result = arb.ingest(_alert(pid, enc, raw))
            if result.should_page:
                page_actions += 1
            elif result.action.value == "passive":
                passive_actions += 1
        if case.get("resolve_at"):
            ep = arb.list_for_patient(pid)[0]
            arb.resolve(
                ep.episode_id,
                at=datetime.fromisoformat(case["resolve_at"]),
            )
        reopen_paged = False
        for raw in case.get("after_resolve") or []:
            result = arb.ingest(_alert(pid, enc, raw))
            if result.should_page:
                page_actions += 1
                reopen_paged = True
            elif result.action.value == "passive":
                passive_actions += 1
        episodes = arb.list_for_patient(pid)
        expect = case["expect"]
        assert len(episodes) == expect["episode_count"], case["id"]
        if "page_actions" in expect:
            assert page_actions == expect["page_actions"], case["id"]
        if "passive_actions" in expect:
            assert passive_actions == expect["passive_actions"], case["id"]
        primary = episodes[0]
        if "dominant_signal_type" in expect:
            assert primary.dominant_signal_type == expect["dominant_signal_type"], case[
                "id"
            ]
        if "supporting_contains" in expect:
            for t in expect["supporting_contains"]:
                assert t in primary.supporting_signal_types, case["id"]
        if "final_page_count" in expect:
            assert primary.page_count == expect["final_page_count"], case["id"]
        if "final_passive_update_count" in expect:
            assert (
                primary.passive_update_count == expect["final_passive_update_count"]
            ), case["id"]
        if "final_status" in expect:
            assert primary.status.value == expect["final_status"], case["id"]
        if expect.get("reopen_paged"):
            assert reopen_paged is True, case["id"]


def test_select_dominant_prefers_higher_severity_then_priority() -> None:
    t0 = datetime.fromisoformat("2024-07-01T10:00:00+00:00")
    signals = [
        SignalRef(
            signal_id="1",
            signal_type="aki",
            severity="urgent",
            event_time=t0,
        ),
        SignalRef(
            signal_id="2",
            signal_type="sofa-deterioration",
            severity="urgent",
            event_time=t0,
        ),
        SignalRef(
            signal_id="3",
            signal_type="hypotension",
            severity="critical",
            event_time=t0,
        ),
    ]
    dom = select_dominant(signals)
    assert dom is not None
    assert dom.signal_type == "hypotension"


def test_deterministic_replay_same_actions() -> None:
    data = json.loads(CASES.read_text())
    case = data["cases"][0]
    cfg = EpisodeConfig(**data["config"])

    def run() -> list[tuple[str, bool, str]]:
        arb = EpisodeArbiter(cfg)
        out = []
        for raw in case["events"]:
            r = arb.ingest(
                _alert(case["patient_id"], case["encounter_id"], raw)
            )
            out.append((r.action.value, r.should_page, r.reason))
        return out

    assert run() == run()
