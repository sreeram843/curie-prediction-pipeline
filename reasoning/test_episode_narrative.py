"""CURIE-023 grounded patient-episode narrative tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from action.api.app.main import app
from action.api.app.models import AlertRecord, ComponentBreakdown
from action.api.app.store import STORE, seed_demo_alerts
from eval.episodes.models import Episode, EpisodeStatus, SignalRef
from ingestion.extraction import settings as settings_mod
from reasoning.pipeline import explain_episode


@pytest.fixture(autouse=True)
def _grp_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_mod.settings, "enable_grp", False)
    monkeypatch.setattr(settings_mod.settings, "grp_backend", "deterministic")
    monkeypatch.setattr(settings_mod.settings, "grp_model_name", "curie-grp-stub-v1")
    monkeypatch.setattr(settings_mod.settings, "grp_fail_closed", True)
    monkeypatch.setattr(settings_mod.settings, "grp_timeout_s", 5.0)


def _sample_episode() -> Episode:
    t0 = datetime(2024, 6, 15, 14, 0, tzinfo=UTC)
    return Episode(
        episode_id="episode-narr-1",
        patient_id="Patient/ep-narr",
        encounter_id="Encounter/enc-narr",
        status=EpisodeStatus.UPDATED,
        opened_at=t0,
        updated_at=t0,
        dominant_signal_type="sofa-deterioration",
        dominant_severity="critical",
        supporting_signal_types=["aki"],
        page_count=1,
        passive_update_count=1,
        signals=[
            SignalRef(
                signal_id="sig-sofa",
                signal_type="sofa-deterioration",
                severity="critical",
                score=7,
                routing="interruptive",
                event_time=t0,
                evidence_ids=["Observation/map-1", "Observation/cr-1"],
                rule_bundle_id="sepsis-sofa",
                rule_version="0.2.0",
            ),
            SignalRef(
                signal_id="sig-aki",
                signal_type="aki",
                severity="urgent",
                score=3,
                routing="interruptive",
                event_time=t0,
                evidence_ids=["Observation/cr-aki"],
                rule_bundle_id="aki-kdigo",
                rule_version="0.4.0",
            ),
        ],
        evidence_ids=["Observation/map-1", "Observation/cr-1", "Observation/cr-aki"],
    )


def test_episode_narrative_pass_grounded() -> None:
    ep = _sample_episode()
    decision = explain_episode(ep, force=True)
    assert decision.status == "pass"
    assert decision.narrative
    assert decision.episode_id == ep.episode_id
    assert decision.prompt_version == "episode-narrative.v1"
    assert decision.snapshot_hash
    assert all(c.grounded for c in decision.claims)
    assert all(c.evidence_ids for c in decision.claims)
    for claim in decision.claims:
        for eid in claim.evidence_ids:
            assert eid in ep.evidence_ids
    assert decision.score_unchanged is True
    assert decision.routing_unchanged is True


def test_episode_narrative_failure_does_not_change_episode() -> None:
    ep = _sample_episode()
    before = ep.model_dump(mode="json")
    decision = explain_episode(ep, force=True, inject_prompt_injection=True)
    assert decision.status == "quarantine"
    assert decision.narrative is None
    after = ep.model_dump(mode="json")
    assert after["status"] == before["status"]
    assert after["page_count"] == before["page_count"]
    assert after["dominant_signal_type"] == before["dominant_signal_type"]


def test_malformed_and_timeout_quarantine_or_error() -> None:
    ep = _sample_episode()
    malformed = explain_episode(ep, force=True, inject_malformed=True)
    assert malformed.status == "quarantine"
    timed = explain_episode(ep, force=True, simulate_timeout=True)
    assert timed.status == "error"
    assert "timeout" in (timed.quarantine_reason or "").lower()


def test_api_episode_explain_additive() -> None:
    STORE.clear()
    seed_demo_alerts(STORE)
    client = TestClient(app)
    episodes = client.get("/episodes").json()
    target = next(e for e in episodes if len(e.get("signals") or []) >= 2)
    before = client.get(f"/episodes/{target['episode_id']}").json()
    resp = client.post(
        f"/episodes/{target['episode_id']}/explain",
        json={"force": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["page_count"] == before["page_count"]
    assert body["dominant_signal_type"] == before["dominant_signal_type"]
    assert body["status"] == before["status"]
    assert body["narrative_status"] in {"pass", "abstain", "quarantine"}
    if body["narrative_status"] == "pass":
        assert body["narrative"]
        assert body["prompt_version"]
        assert body["narrative_snapshot_hash"]
