"""Curie alert API — secure ops boundaries (CURIE-018). Prototype only."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from action.api.app.alerts_consumer import (
    start_alerts_consumer_if_configured,
    stop_alerts_consumer,
)
from action.api.app.cds_hooks import (
    SERVICE_ID as CDS_SERVICE_ID,
)
from action.api.app.cds_hooks import (
    CdsFeedbackRequest,
    CdsHookRequest,
    apply_feedback,
    cards_for_patient,
    discovery_services,
)
from action.api.app.fhir_evidence import evidence_bundle_for_alert, fhir_references_for_alert
from action.api.app.logging_config import configure_phi_safe_logging
from action.api.app.models import (
    AcknowledgeRequest,
    AcknowledgeResponse,
    AlertRecord,
    MetricsSummary,
)
from action.api.app.ops import (
    KILL_SWITCHES,
    OPS_COUNTERS,
    build_ops_status,
)
from action.api.app.security import (
    PUBLIC_PATHS,
    constant_time_key_match,
    get_security_settings,
    reset_security_settings,
    role_for_principal,
)
from action.api.app.store import STORE
from ingestion.extraction.adapter import extract_note_to_fhir
from ingestion.extraction.models import ExtractionResult
from ingestion.extraction.settings import settings
from reasoning.pipeline import explain_alert, explain_episode

logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"

app = FastAPI(
    title="Curie Prediction Pipeline API",
    version="0.5.0",
    description="Prototype only — synthetic data, not for clinical use.",
)


def _principal_from_headers(
    authorization: str | None,
    x_api_key: str | None,
) -> str | None:
    sec = get_security_settings()
    keys = sec.api_key_set()
    token = None
    if x_api_key:
        token = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if token and constant_time_key_match(token, keys):
        return token
    # Optional OIDC: accept Bearer tokens only when issuer configured and token
    # matches an allowlisted key OR insecure-dev JWT decode is enabled.
    if token and sec.oidc_issuer and _oidc_token_acceptable(token):
        return f"oidc:{hash(token) & 0xFFFFFFFF:x}"
    return None


def _oidc_token_acceptable(token: str) -> bool:
    """Prototype OIDC gate — full JWKS verification is a deployment concern."""
    import os

    sec = get_security_settings()
    # Allowlisted opaque tokens still work via api_keys; here we only do a
    # structural JWT check when insecure-dev is explicitly enabled.
    if os.getenv("CURIE_OIDC_INSECURE_DEV", "").lower() not in {"1", "true", "yes"}:
        return False
    parts = token.split(".")
    if len(parts) != 3:
        return False
    try:
        import base64
        import json

        pad = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    except Exception:
        return False
    if sec.oidc_issuer and payload.get("iss") != sec.oidc_issuer:
        return False
    if sec.oidc_audience and payload.get("aud") not in {
        sec.oidc_audience,
        [sec.oidc_audience],
    }:
        aud = payload.get("aud")
        if aud != sec.oidc_audience and (
            not isinstance(aud, list) or sec.oidc_audience not in aud
        ):
            return False
    return True


class Principal(BaseModel):
    id: str
    role: str


async def require_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Principal | None:
    sec = get_security_settings()
    if not sec.auth_required:
        return None
    principal = _principal_from_headers(authorization, x_api_key)
    if not principal:
        raise HTTPException(status_code=401, detail="Authentication required")
    return Principal(id=principal, role=role_for_principal(principal))


def require_ops(principal: Principal | None = Depends(require_auth)) -> Principal | None:
    sec = get_security_settings()
    if not sec.auth_required:
        return principal
    assert principal is not None
    if principal.role not in {"ops", "admin"}:
        raise HTTPException(status_code=403, detail="Ops role required")
    return principal


@app.on_event("startup")
def _startup() -> None:
    configure_phi_safe_logging()
    reset_security_settings()
    sec = get_security_settings()
    problems = sec.validate_production_posture()
    if problems:
        msg = "; ".join(problems)
        logger.error("Production security posture invalid: %s", msg)
        raise RuntimeError(f"CURIE-018 security gate: {msg}")
    KILL_SWITCHES.reload()
    start_alerts_consumer_if_configured()
    logger.info(
        "API started env=%s auth_required=%s cors=%s tenant=%s site=%s",
        sec.env,
        sec.auth_required,
        sec.cors_origin_list(),
        sec.tenant_id,
        sec.site_id,
    )


@app.on_event("shutdown")
def _shutdown() -> None:
    stop_alerts_consumer()


_sec_boot = get_security_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_sec_boot.cors_origin_list(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "X-API-Key", "Content-Type"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'",
    )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response


@app.middleware("http")
async def enforce_auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/static"):
        return await call_next(request)
    # Dashboard HTML is local-only; still require auth in production for API JSON.
    sec = get_security_settings()
    if not sec.auth_required:
        return await call_next(request)
    if path == "/" and request.method == "GET" and not sec.is_production:
        return await call_next(request)
    principal = _principal_from_headers(
        request.headers.get("authorization"),
        request.headers.get("x-api-key"),
    )
    if not principal:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    request.state.principal = principal
    request.state.role = role_for_principal(principal)
    return await call_next(request)


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


class KillSwitchPatch(BaseModel):
    alerts_ingest: bool | None = None
    interruptive_lane: bool | None = None
    passive_lane: bool | None = None
    explain_lane: bool | None = None
    extract_lane: bool | None = None
    indicators: dict[str, bool] | None = None
    bundles: dict[str, bool] | None = None


class LagUpdate(BaseModel):
    kafka_lag_seconds: float | None = None
    flink_watermark_lag_seconds: float | None = None
    dlq_depth: int | None = None


@app.get("/health")
def health() -> dict[str, object]:
    """Liveness probe — no auth, no dependency checks."""
    return {"status": "ok", "service": "curie-api"}


@app.get("/ready")
def ready() -> dict[str, object]:
    """Readiness — store reachable + kill switches loaded."""
    try:
        _ = STORE.metrics()
        switches = KILL_SWITCHES.get()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"not ready: {exc}") from exc
    sec = get_security_settings()
    return {
        "status": "ready",
        "service": "curie-api",
        "env": sec.env,
        "auth_required": sec.auth_required,
        "kill_switches_loaded": True,
        "alerts_ingest_enabled": switches.alerts_ingest,
        "flags": {
            "enable_extraction": settings.enable_extraction,
            "enable_grp": settings.enable_grp,
            "grp_backend": settings.grp_backend,
            "grp_model_name": settings.grp_model_name,
        },
    }


@app.get("/ops/status")
def ops_status(_auth: Principal | None = Depends(require_auth)) -> dict:
    """Operator snapshot: active bundles, lag, rates, kill switches, alarms."""
    return build_ops_status(STORE, get_security_settings())


@app.get("/ops/kill-switches")
def get_kill_switches(_auth: Principal | None = Depends(require_ops)) -> dict:
    return KILL_SWITCHES.get().to_dict()


@app.post("/ops/kill-switches")
def patch_kill_switches(
    body: KillSwitchPatch,
    _auth: Principal | None = Depends(require_ops),
) -> dict:
    """Disable/enable lanes or indicators without redeploying."""
    patch = body.model_dump(exclude_none=True)
    updated = KILL_SWITCHES.update(patch)
    logger.info("Kill switches updated keys=%s", sorted(patch.keys()))
    return updated.to_dict()


@app.post("/ops/lag")
def update_lag(
    body: LagUpdate,
    _auth: Principal | None = Depends(require_ops),
) -> dict:
    """Ingest lag gauges from an external scraper / Flink sidecar."""
    OPS_COUNTERS.set_lag(
        kafka_lag_seconds=body.kafka_lag_seconds,
        flink_watermark_lag_seconds=body.flink_watermark_lag_seconds,
        dlq_depth=body.dlq_depth,
    )
    return {
        "kafka_lag_seconds": OPS_COUNTERS.kafka_lag_seconds,
        "flink_watermark_lag_seconds": OPS_COUNTERS.flink_watermark_lag_seconds,
        "dlq_depth": OPS_COUNTERS.dlq_depth,
    }


@app.get("/alerts", response_model=list[AlertRecord])
def list_alerts(
    include_acknowledged: bool = Query(default=True),
    patient_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _auth: Principal | None = Depends(require_auth),
) -> list[AlertRecord]:
    return STORE.list(
        include_acknowledged=include_acknowledged,
        patient_id=patient_id,
        limit=limit,
        offset=offset,
    )


@app.get("/alerts/{alert_id}", response_model=AlertRecord)
def get_alert(
    alert_id: str, _auth: Principal | None = Depends(require_auth)
) -> AlertRecord:
    alert = STORE.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@app.get("/alerts/{alert_id}/fhir-evidence")
def alert_fhir_evidence(
    alert_id: str, _auth: Principal | None = Depends(require_auth)
) -> dict:
    """FHIR-compatible evidence references + collection Bundle (CURIE-019)."""
    alert = STORE.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        "alert_id": alert.alert_id,
        "patient_id": alert.patient_id,
        "references": fhir_references_for_alert(alert),
        "bundle": evidence_bundle_for_alert(alert),
    }


@app.get("/cds-services")
def cds_services_discovery(
    request: Request, _auth: Principal | None = Depends(require_auth)
) -> dict:
    """CDS Hooks service discovery — presentation boundary only."""
    base = str(request.base_url).rstrip("/")
    return discovery_services(base_url=base)


@app.post(f"/cds-services/{CDS_SERVICE_ID}")
def cds_patient_view(
    body: CdsHookRequest,
    include_acknowledged: bool = Query(default=False),
    _auth: Principal | None = Depends(require_auth),
) -> dict:
    """patient-view hook: governed alerts → CDS Cards (no scoring)."""
    if body.hook and body.hook != "patient-view":
        raise HTTPException(status_code=400, detail=f"Unsupported hook: {body.hook}")
    patient_id = str(
        (body.context or {}).get("patientId")
        or (body.context or {}).get("patient_id")
        or ""
    ).strip()
    if not patient_id:
        raise HTTPException(status_code=400, detail="context.patientId required")
    encounter_id = (body.context or {}).get("encounterId") or (
        body.context or {}
    ).get("encounter_id")
    encounter_id = str(encounter_id).strip() if encounter_id else None
    alerts = STORE.list(include_acknowledged=include_acknowledged, patient_id=patient_id)
    return cards_for_patient(
        alerts,
        patient_id=patient_id,
        encounter_id=encounter_id,
        include_acknowledged=include_acknowledged,
    )


@app.post(f"/cds-services/{CDS_SERVICE_ID}/feedback")
def cds_feedback(
    body: CdsFeedbackRequest, _auth: Principal | None = Depends(require_auth)
) -> dict:
    """CDS Hooks feedback → acknowledge path (does not change score/tier)."""
    return apply_feedback(body, acknowledge_fn=STORE.acknowledge)


@app.post("/alerts/{alert_id}/acknowledge", response_model=AcknowledgeResponse)
def acknowledge_alert(
    alert_id: str,
    body: AcknowledgeRequest | None = None,
    _auth: Principal | None = Depends(require_auth),
) -> AcknowledgeResponse:
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
def explain_alert_endpoint(
    alert_id: str,
    body: ExplainRequest | None = None,
    _auth: Principal | None = Depends(require_auth),
) -> AlertRecord:
    """Additive GRP narrative. Does not change score/tier. Feature-flagged."""
    if not KILL_SWITCHES.get().explain_lane:
        raise HTTPException(status_code=503, detail="explain_lane disabled by kill switch")
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
    assert updated.score == alert.score
    assert updated.tier == alert.tier
    return updated


@app.post("/extract", response_model=ExtractionResult)
def extract_endpoint(
    body: ExtractRequest, _auth: Principal | None = Depends(require_auth)
) -> ExtractionResult:
    """Text→FHIR extraction. Never fires alerts."""
    if not KILL_SWITCHES.get().extract_lane:
        raise HTTPException(status_code=503, detail="extract_lane disabled by kill switch")
    return extract_note_to_fhir(
        body.note_text,
        note_id=body.note_id,
        patient_id=body.patient_id,
        force=body.force,
    )


@app.get("/indicators")
def list_indicator_bundles(_auth: Principal | None = Depends(require_auth)) -> list[dict]:
    from eval.indicators.registry import list_indicators

    return list_indicators(installed_only=True)


@app.get("/plugins")
def list_indicator_plugins(_auth: Principal | None = Depends(require_auth)) -> list[dict]:
    from eval.indicators.plugin import list_plugins

    return [p.to_public_dict() for p in list_plugins()]


@app.get("/episodes")
def list_episodes(
    patient_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    _auth: Principal | None = Depends(require_auth),
) -> list[dict]:
    return [
        e.to_public_dict()
        for e in STORE.list_episodes(patient_id=patient_id, limit=limit)
    ]


@app.get("/episodes/{episode_id}")
def get_episode(
    episode_id: str, _auth: Principal | None = Depends(require_auth)
) -> dict:
    episode = STORE.get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode.to_public_dict()


@app.post("/episodes/{episode_id}/explain")
def explain_episode_endpoint(
    episode_id: str,
    body: ExplainRequest | None = None,
    _auth: Principal | None = Depends(require_auth),
) -> dict:
    """Additive episode GRP narrative. Never changes routing, scores, or delivery."""
    if not KILL_SWITCHES.get().explain_lane:
        raise HTTPException(status_code=503, detail="explain_lane disabled by kill switch")
    episode = STORE.get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    before = episode.model_dump(mode="json")
    force = body.force if body else False
    decision = explain_episode(episode, force=force)
    claims = [c.model_dump(mode="json") for c in decision.claims]
    updated = STORE.attach_episode_narrative(
        episode_id,
        status=decision.status,
        narrative=decision.narrative,
        claims=claims,
        quarantine_reason=decision.quarantine_reason,
        model_name=decision.model_name,
        prompt_version=decision.prompt_version,
        snapshot_hash=decision.snapshot_hash,
    )
    assert updated is not None
    assert updated.status.value == before["status"] or updated.status == before["status"]
    assert updated.page_count == before["page_count"]
    assert updated.dominant_signal_type == before["dominant_signal_type"]
    assert decision.score_unchanged is True
    assert decision.routing_unchanged is True
    return updated.to_public_dict()


@app.get("/metrics", response_model=MetricsSummary)
def metrics(_auth: Principal | None = Depends(require_auth)) -> MetricsSummary:
    return STORE.metrics()


@app.get("/claims-matrix")
def get_claims_matrix(_auth: Principal | None = Depends(require_auth)) -> dict:
    """Investor/demo claims matrix (CURIE-021) — not a regulatory matrix."""
    from eval.investor_demo.claims import load_claims_matrix

    return load_claims_matrix()


@app.get("/benchmarks")
def get_benchmarks(_auth: Principal | None = Depends(require_auth)) -> dict:
    """Frozen benchmark cards with plain-language explanations for the dashboard."""
    from eval.benchmarks.summary import build_benchmarks_summary

    return build_benchmarks_summary()


@app.get("/investor-demo")
def get_investor_demo(_auth: Principal | None = Depends(require_auth)) -> dict:
    """Frozen investor demo report (timeline, volume, chaos)."""
    from eval.investor_demo.scenario import REPORT_PATH, run_demo

    if REPORT_PATH.is_file():
        import json

        return json.loads(REPORT_PATH.read_text())
    return run_demo(write=False)


class StewardshipClassifyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    feedback_id: str | None = None
    alert_id: str | None = None
    site_id: str = "local"
    service: str | None = None
    indicator: str | None = None
    rule_bundle_id: str | None = None
    rule_version: str | None = None
    routing: str | None = None


class StewardshipApproveRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=200)


@app.get("/stewardship/taxonomy")
def stewardship_taxonomy(_auth: Principal | None = Depends(require_auth)) -> list[dict]:
    from eval.stewardship.taxonomy import taxonomy_public

    return taxonomy_public()


@app.post("/stewardship/classify")
def stewardship_classify(
    body: StewardshipClassifyRequest,
    _auth: Principal | None = Depends(require_auth),
) -> dict:
    """Classify acknowledgement/dismissal text — never mutates rules."""
    from eval.stewardship.classifier import FeedbackRecord, classify_record

    record = FeedbackRecord(
        feedback_id=body.feedback_id or "adhoc",
        text=body.text,
        alert_id=body.alert_id,
        site_id=body.site_id,
        service=body.service,
        indicator=body.indicator,
        rule_bundle_id=body.rule_bundle_id,
        rule_version=body.rule_version,
        routing=body.routing,  # type: ignore[arg-type]
    )
    result = classify_record(record)
    assert result.mutates_active_rules is False
    return result.model_dump(mode="json")


@app.get("/stewardship/report")
def stewardship_report(_auth: Principal | None = Depends(require_auth)) -> dict:
    """Dual-reviewed fixture metrics + offline proposals (CURIE-024)."""
    import json
    from pathlib import Path

    from eval.stewardship.classifier import (
        FeedbackRecord,
        aggregate_classifications,
        agreement_metrics,
        classify_record,
    )
    from eval.stewardship.proposals import build_proposals, evaluate_proposal_against_manifest

    fixtures = Path("eval/stewardship/fixtures/dual_reviewed.v1.json")
    records = [FeedbackRecord.model_validate(r) for r in json.loads(fixtures.read_text())]
    preds = [classify_record(r) for r in records]
    proposals = build_proposals(records, preds)
    return {
        "metrics": agreement_metrics(records, preds),
        "aggregates": aggregate_classifications(records, preds),
        "proposals": [
            {
                **p.model_dump(mode="json"),
                "replay_binding": evaluate_proposal_against_manifest(p),
            }
            for p in proposals
        ],
        "mutates_active_rules": False,
    }


@app.post("/stewardship/proposals/{proposal_id}/approve")
def stewardship_approve_proposal(
    proposal_id: str,
    body: StewardshipApproveRequest,
    _auth: Principal | None = Depends(require_ops),
) -> dict:
    """Human approval only — still does not activate rule changes."""
    import json
    from pathlib import Path

    from eval.stewardship.proposals import (
        PROPOSALS_PATH,
        ExperimentProposal,
        approve_proposal,
        assert_no_active_rule_mutation,
        evaluate_proposal_against_manifest,
    )

    path = PROPOSALS_PATH if PROPOSALS_PATH.is_file() else Path(
        "eval/stewardship/frozen/proposals.v1.json"
    )
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="No proposals; run: python -m eval.stewardship.runner run --write",
        )
    rows = json.loads(path.read_text())
    updated_rows = []
    approved = None
    for row in rows:
        prop = ExperimentProposal.model_validate(row)
        if prop.proposal_id == proposal_id:
            prop = approve_proposal(prop, approved_by=body.approved_by)
            assert_no_active_rule_mutation(prop)
            bind = evaluate_proposal_against_manifest(prop)
            if not bind["ok"]:
                raise HTTPException(status_code=409, detail=bind)
            approved = prop
        updated_rows.append(prop.model_dump(mode="json"))
    if approved is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    path.write_text(json.dumps(updated_rows, indent=2) + "\n")
    return {
        "proposal": approved.model_dump(mode="json"),
        "mutates_active_rules": False,
        "note": "Approved for offline evaluation queue only — active rules unchanged.",
    }


@app.get("/")
def dashboard_index() -> FileResponse:
    index = DASHBOARD_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Dashboard not built")
    return FileResponse(
        index,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


if DASHBOARD_DIR.exists():
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")
