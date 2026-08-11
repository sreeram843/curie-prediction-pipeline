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
