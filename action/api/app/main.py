"""Curie alert API — list, detail, acknowledge. Prototype only."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from action.api.app.models import (
    AcknowledgeRequest,
    AcknowledgeResponse,
    AlertRecord,
    MetricsSummary,
)
from action.api.app.store import STORE

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"

app = FastAPI(
    title="Curie Prediction Pipeline API",
    version="0.1.0",
    description="Prototype only — synthetic data, not for clinical use.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "curie-api"}


@app.get("/alerts", response_model=list[AlertRecord])
def list_alerts(
    include_acknowledged: bool = Query(default=True),
    patient_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[AlertRecord]:
    return STORE.list(
        include_acknowledged=include_acknowledged,
        patient_id=patient_id,
        limit=limit,
    )


@app.get("/alerts/{alert_id}", response_model=AlertRecord)
def get_alert(alert_id: str) -> AlertRecord:
    alert = STORE.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@app.post("/alerts/{alert_id}/acknowledge", response_model=AcknowledgeResponse)
def acknowledge_alert(alert_id: str, body: AcknowledgeRequest | None = None) -> AcknowledgeResponse:
    note = body.note if body else None
    alert = STORE.acknowledge(alert_id, note=note)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    assert alert.acknowledged_at is not None
    return AcknowledgeResponse(
        alert_id=alert.alert_id,
        acknowledged=True,
        acknowledged_at=alert.acknowledged_at,
    )


@app.get("/metrics", response_model=MetricsSummary)
def metrics() -> MetricsSummary:
    return STORE.metrics()


@app.get("/")
def dashboard_index() -> FileResponse:
    index = DASHBOARD_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Dashboard not built")
    return FileResponse(index)


if DASHBOARD_DIR.exists():
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")
