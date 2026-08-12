"""CURIE-018: security and observability boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from action.api.app.logging_config import hash_identifier, redact_text
from action.api.app.ops import KillSwitchStore, build_ops_status
from action.api.app.security import get_security_settings, reset_security_settings
from action.api.app.store import MemoryAlertStore, seed_demo_alerts


@pytest.fixture()
def restore_security(monkeypatch):
    monkeypatch.delenv("CURIE_ENV", raising=False)
    monkeypatch.delenv("CURIE_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("CURIE_API_KEYS", raising=False)
    monkeypatch.delenv("CURIE_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("CURIE_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("CURIE_TLS_TERMINATED", raising=False)
    monkeypatch.delenv("CURIE_BIND_HOST", raising=False)
    reset_security_settings()
    yield
    reset_security_settings()


def test_development_cors_is_not_wildcard(restore_security, monkeypatch) -> None:
    monkeypatch.setenv("CURIE_ENV", "development")
    reset_security_settings()
    origins = get_security_settings().cors_origin_list()
    assert "*" not in origins
    assert any("127.0.0.1" in o or "localhost" in o for o in origins)


def test_production_refuses_wildcard_cors_and_missing_auth(
    restore_security, monkeypatch
) -> None:
    monkeypatch.setenv("CURIE_ENV", "production")
    monkeypatch.setenv("CURIE_CORS_ORIGINS", "*")
    monkeypatch.setenv("CURIE_API_KEYS", "")
    monkeypatch.setenv("CURIE_BIND_HOST", "127.0.0.1")
    reset_security_settings()
    problems = get_security_settings().validate_production_posture()
    assert any("*" in p or "CORS" in p for p in problems)
    assert any("API_KEYS" in p or "OIDC" in p for p in problems)


def test_production_auth_required_blocks_alerts(
    restore_security, monkeypatch
) -> None:
    monkeypatch.setenv("CURIE_ENV", "production")
    monkeypatch.setenv("CURIE_API_KEYS", "ops:secret-key")
    monkeypatch.setenv("CURIE_CORS_ORIGINS", "https://curie.example")
    monkeypatch.setenv("CURIE_TLS_TERMINATED", "true")
    monkeypatch.setenv("CURIE_BIND_HOST", "127.0.0.1")
    reset_security_settings()
    from action.api.app import main as main_mod

    client = TestClient(main_mod.app)
    denied = client.get("/alerts")
    assert denied.status_code == 401
    ok = client.get("/alerts", headers={"X-API-Key": "ops:secret-key"})
    assert ok.status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_ops_status_exposes_bundles_rates_and_lag(restore_security, monkeypatch) -> None:
    monkeypatch.setenv("CURIE_ENV", "development")
    reset_security_settings()
    store = MemoryAlertStore()
    seed_demo_alerts(store)
    from action.api.app.ops import OPS_COUNTERS

    OPS_COUNTERS.set_lag(
        kafka_lag_seconds=1.5, flink_watermark_lag_seconds=2.0, dlq_depth=0
    )
    status = build_ops_status(store, get_security_settings())
    assert "active_bundles" in status
    assert status["alert_metrics"]["total_alerts"] >= 1
    assert "alert_rate_per_hour" in status["alert_metrics"]
    assert "missing_data_rate" in status["alert_metrics"]
    assert status["processing"]["kafka_lag_seconds"] == 1.5


def test_kill_switch_disables_lane_without_redeploy(tmp_path: Path) -> None:
    path = tmp_path / "ks.json"
    store = KillSwitchStore(path)
    assert store.get().interruptive_lane is True
    updated = store.update({"interruptive_lane": False, "indicators": {"aki": False}})
    assert updated.interruptive_lane is False
    assert updated.indicator_enabled("aki") is False
    assert updated.indicator_enabled("sofa-deterioration") is True
    store2 = KillSwitchStore(path)
    assert store2.get().interruptive_lane is False


def test_kill_switch_api(restore_security, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CURIE_ENV", "development")
    monkeypatch.setenv("CURIE_KILL_SWITCH_PATH", str(tmp_path / "ks.json"))
    reset_security_settings()
    from action.api.app import main as main_mod
    from action.api.app import ops as ops_mod

    ops_mod.KILL_SWITCHES.path = tmp_path / "ks.json"
    ops_mod.KILL_SWITCHES.update(
        {
            "alerts_ingest": True,
            "interruptive_lane": True,
            "passive_lane": True,
            "explain_lane": True,
            "extract_lane": True,
            "indicators": {},
            "bundles": {},
        }
    )
    client = TestClient(main_mod.app)
    before = client.get("/ops/kill-switches").json()
    assert before["interruptive_lane"] is True
    after = client.post("/ops/kill-switches", json={"interruptive_lane": False}).json()
    assert after["interruptive_lane"] is False
    client.post("/ops/kill-switches", json={"explain_lane": False})
    alerts = client.get("/alerts").json()
    target = alerts[0]["alert_id"]
    resp = client.post(f"/alerts/{target}/explain", json={"force": True})
    assert resp.status_code == 503
    # Restore for other tests sharing process state
    ops_mod.KILL_SWITCHES.update({"explain_lane": True, "interruptive_lane": True})


def test_phi_safe_redaction() -> None:
    text = "patient Patient/p-48102 encounter Encounter/enc-001"
    assert "p-48102" not in redact_text(text)
    assert hash_identifier("Patient/p-48102") is not None


def test_ready_and_ops_on_default_app(restore_security, monkeypatch) -> None:
    monkeypatch.setenv("CURIE_ENV", "development")
    reset_security_settings()
    from action.api.app.main import app

    client = TestClient(app)
    assert client.get("/ready").json()["status"] == "ready"
    ops = client.get("/ops/status").json()
    assert "kill_switches" in ops
    assert "active_bundles" in ops
