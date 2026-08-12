"""API tests for alert list / acknowledge."""

from __future__ import annotations

from fastapi.testclient import TestClient

from action.api.app.main import app
from action.api.app.store import STORE, seed_demo_alerts


def setup_function() -> None:
    STORE.clear()
    seed_demo_alerts(STORE)


def test_health() -> None:
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"


def test_list_and_acknowledge() -> None:
    client = TestClient(app)
    alerts = client.get("/alerts").json()
    assert len(alerts) >= 3
    open_before = client.get("/alerts", params={"include_acknowledged": False}).json()
    assert all(not a["acknowledged"] for a in open_before)

    target = next(a for a in open_before if a["tier"] == "critical")
    resp = client.post(
        f"/alerts/{target['alert_id']}/acknowledge",
        json={"note": "Reviewed in smoke test"},
    )
    assert resp.status_code == 200
    detail = client.get(f"/alerts/{target['alert_id']}").json()
    assert detail["acknowledged"] is True
    assert detail["acknowledge_note"] == "Reviewed in smoke test"


def test_metrics() -> None:
    client = TestClient(app)
    m = client.get("/metrics").json()
    assert m["total_alerts"] >= 3
    assert "critical" in m["by_tier"]


def test_explain_is_additive(monkeypatch) -> None:
    from ingestion.extraction import settings as settings_mod

    # Isolate from local .env (e.g. LM Studio openai_compat).
    monkeypatch.setattr(settings_mod.settings, "enable_grp", True)
    monkeypatch.setattr(settings_mod.settings, "grp_backend", "deterministic")
    monkeypatch.setattr(settings_mod.settings, "grp_model_name", "curie-grp-stub-v1")
    monkeypatch.setattr(settings_mod.settings, "grp_fail_closed", True)

    client = TestClient(app)
    alerts = client.get("/alerts").json()
    target = next(a for a in alerts if a["tier"] == "critical")
    before_score = target["score"]
    before_tier = target["tier"]
    updated = client.post(
        f"/alerts/{target['alert_id']}/explain",
        json={"force": True},
    ).json()
    assert updated["score"] == before_score
    assert updated["tier"] == before_tier
    assert updated["narrative_status"] == "pass"
    assert updated["narrative"]


def test_indicators_include_aki_and_sofa_deterioration() -> None:
    client = TestClient(app)
    rows = client.get("/indicators").json()
    indicators = {i["indicator"] for i in rows}
    assert "sofa-deterioration" in indicators
    assert "aki" in indicators
    assert all(i.get("scorer_installed") is True for i in rows)


def test_plugins_endpoint_lists_sofa_and_aki() -> None:
    client = TestClient(app)
    plugins = {p["score_type"]: p for p in client.get("/plugins").json()}
    assert "sofa" in plugins
    assert "aki_kdigo" in plugins
    assert plugins["sofa"]["runtime_impl"]["java"]


def test_demo_sofa_alerts_not_labeled_sepsis() -> None:
    """CURIE-008: SOFA threshold alone must not read as confirmed sepsis."""
    client = TestClient(app)
    alerts = client.get("/alerts").json()
    sofa = [a for a in alerts if a["indicator"] != "aki"]
    assert sofa
    assert all(a["indicator"] == "sofa-deterioration" for a in sofa)
    assert not any(a["indicator"] == "sepsis" for a in alerts)


def test_aki_demo_alert_present() -> None:
    client = TestClient(app)
    alerts = client.get("/alerts").json()
    aki = [a for a in alerts if a["indicator"] == "aki"]
    assert len(aki) >= 1
    assert aki[0]["rule_bundle_id"] == "aki-kdigo"


def test_alerts_include_shared_signal_contract() -> None:
    client = TestClient(app)
    alerts = client.get("/alerts").json()
    assert alerts
    for alert in alerts:
        assert "signal" in alert
        sig = alert["signal"]
        assert sig["schema_version"] == "1.0.0"
        assert sig["signal_type"] == alert["indicator"]
        assert sig["signal_kind"] in {"risk", "phenotype"}
        assert "resolution_state" in sig
        assert "missing_inputs" in sig
        assert "rule_version" in sig


def test_unknown_indicator_accepted_by_api_store() -> None:
    from datetime import UTC, datetime

    from action.api.app.models import AlertRecord

    STORE.upsert(
        AlertRecord(
            alert_id="alert-future-resp-001",
            patient_id="Patient/p-future",
            patient_name="Future Signal",
            indicator="respiratory-deterioration",
            signal_kind="risk",
            event_time=datetime(2024, 6, 15, 14, 0, tzinfo=UTC),
            score=3,
            completeness="partial",
            tier="watch",
            missing_components=["abg"],
            evidence_ids=["Observation/spo2-1"],
            rule_bundle_id="resp-hypoxemia",
            rule_version="0.1.0",
            routing="passive",
            component_breakdown=[],
        )
    )
    client = TestClient(app)
    detail = client.get("/alerts/alert-future-resp-001").json()
    assert detail["indicator"] == "respiratory-deterioration"
    assert detail["signal"]["signal_type"] == "respiratory-deterioration"
    assert detail["signal"]["missing_inputs"] == ["abg"]
    metrics = client.get("/metrics").json()
    assert metrics["by_indicator"].get("respiratory-deterioration", 0) >= 1


def test_acknowledge_sets_resolution_state() -> None:
    client = TestClient(app)
    target = next(
        a for a in client.get("/alerts").json() if not a["acknowledged"]
    )
    client.post(f"/alerts/{target['alert_id']}/acknowledge", json={"note": "ok"})
    detail = client.get(f"/alerts/{target['alert_id']}").json()
    assert detail["resolution_state"] == "acknowledged"
    assert detail["signal"]["resolution_state"] == "acknowledged"
