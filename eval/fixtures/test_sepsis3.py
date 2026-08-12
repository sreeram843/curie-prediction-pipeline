"""CURIE-008: Sepsis-3 phenotype fixtures (not clinical validation)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from eval.sepsis3.phenotype import InfectionEvent, Sepsis3Input, evaluate_sepsis3

CASES = Path(__file__).resolve().parent / "golden" / "sepsis3_cases.v1.json"


def _parse_inputs(raw: dict) -> Sepsis3Input:
    events = [
        InfectionEvent(
            event_time=datetime.fromisoformat(e["event_time"]),
            kind=e["kind"],
            evidence_id=e["evidence_id"],
        )
        for e in raw.get("infection_events") or []
    ]
    return Sepsis3Input(
        as_of=datetime.fromisoformat(raw["as_of"]),
        current_sofa=raw.get("current_sofa"),
        baseline_sofa=raw.get("baseline_sofa"),
        infection_events=events,
        exclusion_flags=set(raw.get("exclusion_flags") or []),
        window_before_hours=int(raw.get("window_before_hours", 24)),
        window_after_hours=int(raw.get("window_after_hours", 24)),
    )


def test_sepsis3_fixture_cases() -> None:
    data = json.loads(CASES.read_text())
    assert data["phenotype_version"] == "1.0.0"
    assert len(data["cases"]) >= 8
    for case in data["cases"]:
        result = evaluate_sepsis3(_parse_inputs(case["inputs"]))
        expect = case["expect"]
        assert result.met is expect["met"], case["id"]
        assert result.status == expect["status"], case["id"]
        if "sofa_delta" in expect:
            assert result.sofa_delta == expect["sofa_delta"], case["id"]
        if "criteria_met" in expect:
            assert set(result.criteria_met) == set(expect["criteria_met"]), case["id"]
        if "criteria_failed" in expect:
            assert set(result.criteria_failed) >= set(expect["criteria_failed"]), case[
                "id"
            ]
        if "missing_inputs" in expect:
            assert set(result.missing_inputs) == set(expect["missing_inputs"]), case[
                "id"
            ]
        if "exclusions_applied" in expect:
            assert result.exclusions_applied == expect["exclusions_applied"], case["id"]
        if "note_contains" in expect:
            assert expect["note_contains"] in result.note, case["id"]


def test_sofa_alone_is_never_confirmed_sepsis() -> None:
    """Absolute SOFA without infection must not meet sepsis-3."""
    result = evaluate_sepsis3(
        Sepsis3Input(
            as_of=datetime.fromisoformat("2024-06-01T12:00:00+00:00"),
            current_sofa=8,
            baseline_sofa=0,
            infection_events=[],
        )
    )
    assert result.met is False
    assert "infection_suspicion" in result.missing_inputs
