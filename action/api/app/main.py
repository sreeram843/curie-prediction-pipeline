"""Curie alert API — list, detail, acknowledge, additive GRP explain. Prototype only."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from action.api.app.models import (
    AcknowledgeRequest,
    AcknowledgeResponse,
    AlertRecord,
    MetricsSummary,
)
from action.api.app.store import STORE
from ingestion.extraction.adapter import extract_note_to_fhir
from ingestion.extraction.models import ExtractionResult
from ingestion.extraction.settings import settings
from reasoning.pipeline import explain_alert

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"

app = FastAPI(
    title="Curie Prediction Pipeline API",
    version="0.2.0",
    description="Prototype only — synthetic data, not for clinical use.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractRequest(BaseModel):
    note_id: str
    note_text: str
    patient_id: str | None = None
    force: bool = False


class ExplainRequest(BaseModel):
    force: bool = Field(
        default=False,
        description="Bypass CURIE_ENABLE_GRP for local eval/demo only.",
    )


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "curie-api",
        "flags": {
            "enable_extraction": settings.enable_extraction,
            "enable_grp": settings.enable_grp,
        },
    }


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


@app.post("/alerts/{alert_id}/explain", response_model=AlertRecord)
def explain_alert_endpoint(alert_id: str, body: ExplainRequest | None = None) -> AlertRecord:
    """Additive GRP narrative. Does not change score/tier. Feature-flagged."""
    alert = STORE.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    force = body.force if body else False
    decision = explain_alert(alert, force=force)
    claims = [c.model_dump(mode="json") for c in decision.claims]
    updated = STORE.attach_narrative(
        alert_id,
        status=decision.status,
        narrative=decision.narrative,
        claims=claims,
        quarantine_reason=decision.quarantine_reason,
        model_name=decision.model_name,
    )
    assert updated is not None
    # Hard invariant: score unchanged
    assert updated.score == alert.score
    assert updated.tier == alert.tier
    return updated


@app.post("/extract", response_model=ExtractionResult)
def extract_endpoint(body: ExtractRequest) -> ExtractionResult:
    """Text→FHIR extraction. Never fires alerts."""
    return extract_note_to_fhir(
        body.note_text,
        note_id=body.note_id,
        patient_id=body.patient_id,
        force=body.force,
    )


@app.get("/indicators")
def list_indicator_bundles() -> list[dict[str, str]]:
    """Registered rule bundles (sepsis, aki, …) — plugin surface for Phase 3+."""
    from eval.indicators.registry import list_indicators

    return list_indicators()


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
