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


def test_indicators_include_aki_and_sepsis() -> None:
    client = TestClient(app)
    indicators = {i["indicator"] for i in client.get("/indicators").json()}
    assert "sepsis" in indicators
    assert "aki" in indicators


def test_aki_demo_alert_present() -> None:
    client = TestClient(app)
    alerts = client.get("/alerts").json()
    aki = [a for a in alerts if a["indicator"] == "aki"]
    assert len(aki) >= 1
    assert aki[0]["rule_bundle_id"] == "aki-kdigo"


def test_demo_alerts_use_human_names() -> None:
    client = TestClient(app)
    alerts = client.get("/alerts").json()
    assert all(a.get("patient_name") for a in alerts)
    assert not any("synthea" in (a.get("patient_name") or "").lower() for a in alerts)
    assert not any("synthea" in a["patient_id"].lower() for a in alerts)
