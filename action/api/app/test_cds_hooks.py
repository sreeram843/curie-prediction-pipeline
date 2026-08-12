"""CURIE-019 FHIR evidence + CDS Hooks boundary tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from action.api.app.cds_hooks import alert_to_card
from action.api.app.fhir_evidence import parse_evidence_id
from action.api.app.main import app
from action.api.app.models import AlertRecord
from action.api.app.store import STORE, seed_demo_alerts


def setup_function() -> None:
    STORE.clear()
    seed_demo_alerts(STORE)


def test_parse_fhir_shaped_evidence_id() -> None:
    ref = parse_evidence_id("Observation/cr-1")
    assert ref["reference"] == "Observation/cr-1"
    assert ref["type"] == "Observation"


def test_parse_noncanonical_evidence_id() -> None:
    ref = parse_evidence_id("lab/plt-1")
    assert "reference" not in ref
    assert ref["identifier"]["value"] == "lab/plt-1"
    assert ref["type"] == "Observation"


def test_fhir_evidence_endpoint() -> None:
    client = TestClient(app)
    alerts = client.get("/alerts").json()
    target = next(a for a in alerts if a.get("evidence_ids"))
    # Ensure at least one FHIR-shaped id for richer coverage
    alert = STORE.get(target["alert_id"])
    assert alert is not None
    data = alert.model_dump()
    data["evidence_ids"] = ["Observation/map-1", "lab/cr-rise", *data["evidence_ids"]]
    data["signal"] = None
    STORE.upsert(AlertRecord.model_validate(data))

    resp = client.get(f"/alerts/{target['alert_id']}/fhir-evidence")
    assert resp.status_code == 200
    body = resp.json()
    assert body["alert_id"] == target["alert_id"]
    assert any(r.get("reference") == "Observation/map-1" for r in body["references"])
    assert any(
        r.get("identifier", {}).get("value") == "lab/cr-rise" for r in body["references"]
    )
    assert body["bundle"]["resourceType"] == "Bundle"
    assert body["bundle"]["type"] == "collection"


def test_cds_discovery() -> None:
    client = TestClient(app)
    body = client.get("/cds-services").json()
    assert len(body["services"]) == 1
    svc = body["services"][0]
    assert svc["hook"] == "patient-view"
    assert svc["id"] == "curie-patient-view"


def test_cds_patient_view_cards() -> None:
    client = TestClient(app)
    alerts = client.get("/alerts").json()
    patient_id = alerts[0]["patient_id"]
    resp = client.post(
        "/cds-services/curie-patient-view",
        json={
            "hook": "patient-view",
            "hookInstance": "test-1",
            "context": {"patientId": patient_id},
        },
    )
    assert resp.status_code == 200
    cards = resp.json()["cards"]
    assert len(cards) >= 1
    card = cards[0]
    assert card["summary"]
    assert card["indicator"] in {"info", "warning", "critical"}
    assert card["extension"]["curieAlertId"]
    assert "curieEvidence" in card["extension"]


def test_cds_feedback_acknowledges_without_score_change() -> None:
    client = TestClient(app)
    open_alerts = client.get("/alerts", params={"include_acknowledged": False}).json()
    target = open_alerts[0]
    before = client.get(f"/alerts/{target['alert_id']}").json()
    card = alert_to_card(STORE.get(target["alert_id"]))  # type: ignore[arg-type]
    suggestion = card["suggestions"][0]

    resp = client.post(
        "/cds-services/curie-patient-view/feedback",
        json={
            "feedback": [
                {
                    "card": card["uuid"],
                    "outcome": "accepted",
                    "acceptedSuggestions": [
                        {"uuid": suggestion["uuid"], "actions": suggestion["actions"]}
                    ],
                }
            ]
        },
    )
    assert resp.status_code == 200
    processed = resp.json()["processed"]
    assert processed[0]["status"] == "acknowledged"
    assert processed[0]["alert_id"] == target["alert_id"]

    after = client.get(f"/alerts/{target['alert_id']}").json()
    assert after["acknowledged"] is True
    assert after["score"] == before["score"]
    assert after["tier"] == before["tier"]
    assert "cds-hooks:accepted" in (after["acknowledge_note"] or "")


def test_cds_requires_patient_id() -> None:
    client = TestClient(app)
    resp = client.post(
        "/cds-services/curie-patient-view",
        json={"hook": "patient-view", "context": {}},
    )
    assert resp.status_code == 400
