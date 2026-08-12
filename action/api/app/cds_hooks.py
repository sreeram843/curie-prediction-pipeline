"""CDS Hooks–compatible presentation and feedback boundary (CURIE-019).

Maps governed alerts onto CDS Hooks cards and routes feedback into the existing
acknowledge path. Does not alter scores, tiers, or routing decisions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from action.api.app.fhir_evidence import fhir_references_for_alert, patient_reference
from action.api.app.models import AlertRecord

SERVICE_ID = "curie-patient-view"
HOOK_NAME = "patient-view"


class CdsPrefetch(BaseModel):
    """Optional prefetch placeholders — EHR adapters populate these."""

    patient: dict[str, Any] | None = None
    encounter: dict[str, Any] | None = None


class CdsHookRequest(BaseModel):
    hookInstance: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hook: str = HOOK_NAME
    fhirServer: str | None = None
    fhirAuthorization: dict[str, Any] | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    prefetch: CdsPrefetch | dict[str, Any] | None = None


class CdsOverrideReason(BaseModel):
    code: str | None = None
    display: str | None = None
    system: str | None = None
    userSelected: bool | None = None


class CdsFeedbackItem(BaseModel):
    card: str
    outcome: Literal["accepted", "overridden"]
    acceptedSuggestions: list[dict[str, Any]] = Field(default_factory=list)
    overrideReason: CdsOverrideReason | None = None
    overrideReasons: list[CdsOverrideReason] = Field(default_factory=list)
    outcomeTimestamp: datetime | None = None


class CdsFeedbackRequest(BaseModel):
    feedback: list[CdsFeedbackItem]


def discovery_services(*, base_url: str = "") -> dict[str, Any]:
    """CDS Hooks discovery document (STU1 / 1.0 shape)."""
    prefix = base_url.rstrip("/")
    return {
        "services": [
            {
                "hook": HOOK_NAME,
                "id": SERVICE_ID,
                "title": "Curie clinical deterioration signals",
                "description": (
                    "Presents governed Curie alerts for the in-context patient. "
                    "Prototype only — not for clinical use."
                ),
                "prefetch": {
                    "patient": "Patient/{{context.patientId}}",
                    "encounter": "Encounter/{{context.encounterId}}",
                },
                "extension": {
                    "curieServicePath": f"{prefix}/cds-services/{SERVICE_ID}",
                    "curieFeedbackPath": f"{prefix}/cds-services/{SERVICE_ID}/feedback",
                    "curieClaims": "demonstrated-presentation-boundary-only",
                },
            }
        ]
    }


def _indicator_for_tier(tier: str, routing: str | None) -> str:
    t = (tier or "none").lower()
    if t == "critical" or routing == "interruptive":
        return "critical"
    if t in {"urgent", "watch"}:
        return "warning"
    return "info"


def _summary(alert: AlertRecord) -> str:
    score_bit = f" score={alert.score}" if alert.score is not None else ""
    stage_bit = f" stage={alert.stage}" if alert.stage is not None else ""
    return (
        f"{alert.indicator} · {alert.tier}{score_bit}{stage_bit} "
        f"({alert.completeness})"
    ).strip()


def _detail(alert: AlertRecord) -> str:
    lines = [
        f"**Signal:** `{alert.indicator}` ({alert.signal_kind})",
        f"**Tier / routing:** {alert.tier} / {alert.routing or 'none'}",
        f"**Rule:** `{alert.rule_bundle_id}`@{alert.rule_version}",
    ]
    if alert.rule_bundle_hash:
        lines.append(f"**Rule hash:** `{alert.rule_bundle_hash}`")
    if alert.criteria_met:
        lines.append("**Criteria met:** " + ", ".join(alert.criteria_met))
    if alert.missing_components:
        lines.append("**Missing:** " + ", ".join(alert.missing_components))
    if alert.narrative:
        lines.append(f"**Narrative (additive):** {alert.narrative}")
    refs = fhir_references_for_alert(alert)
    if refs:
        lines.append("**Evidence:**")
        for ref in refs[:12]:
            label = ref.get("reference") or ref.get("display") or "?"
            lines.append(f"- {label}")
    lines.append(
        "_Prototype CDS Hooks card — scoring and governance remain outside the EHR adapter._"
    )
    return "\n".join(lines)


def alert_to_card(alert: AlertRecord) -> dict[str, Any]:
    """Project one AlertRecord onto a CDS Hooks Card."""
    card_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"curie-alert:{alert.alert_id}"))
    suggestion_id = f"ack-{alert.alert_id}"
    return {
        "uuid": card_uuid,
        "summary": _summary(alert)[:140],
        "detail": _detail(alert),
        "indicator": _indicator_for_tier(alert.tier, alert.routing),
        "source": {
            "label": "Curie Signal",
            "url": "https://github.com/sreeram843/curie-prediction-pipeline",
        },
        "suggestions": [
            {
                "label": "Acknowledge alert",
                "uuid": suggestion_id,
                "isRecommended": True,
                "actions": [
                    {
                        "type": "create",
                        "description": "Acknowledge Curie alert (local store)",
                        "resource": {
                            "resourceType": "Communication",
                            "status": "completed",
                            "category": [
                                {
                                    "coding": [
                                        {
                                            "system": "urn:curie:feedback",
                                            "code": "acknowledge",
                                        }
                                    ]
                                }
                            ],
                            "payload": [
                                {
                                    "contentString": f"acknowledge:{alert.alert_id}",
                                }
                            ],
                            "about": [{"reference": patient_reference(alert.patient_id)}],
                        },
                    }
                ],
            }
        ],
        "links": [
            {
                "label": "FHIR evidence references",
                "url": f"/alerts/{alert.alert_id}/fhir-evidence",
                "type": "absolute",
            }
        ],
        "extension": {
            "curieAlertId": alert.alert_id,
            "curieIndicator": alert.indicator,
            "curieTier": alert.tier,
            "curieRouting": alert.routing,
            "curieRuleBundleId": alert.rule_bundle_id,
            "curieRuleVersion": alert.rule_version,
            "curieRuleBundleHash": alert.rule_bundle_hash,
            "curieEvidence": fhir_references_for_alert(alert),
            "curieResolutionState": alert.resolution_state,
        },
    }


def cards_for_patient(
    alerts: list[AlertRecord],
    *,
    patient_id: str,
    encounter_id: str | None = None,
    include_acknowledged: bool = False,
) -> dict[str, Any]:
    """Build a CDS Hooks response for patient-view."""
    selected: list[AlertRecord] = []
    for alert in alerts:
        if alert.patient_id != patient_id:
            continue
        if encounter_id and alert.encounter_id and alert.encounter_id != encounter_id:
            continue
        if alert.suppressed or alert.routing == "none":
            continue
        if alert.acknowledged and not include_acknowledged:
            continue
        selected.append(alert)
    selected.sort(key=lambda a: a.event_time, reverse=True)
    return {"cards": [alert_to_card(a) for a in selected]}


def apply_feedback(
    body: CdsFeedbackRequest,
    *,
    acknowledge_fn,
) -> dict[str, Any]:
    """Map CDS Hooks feedback onto acknowledge; never changes score/tier."""
    results: list[dict[str, Any]] = []
    for item in body.feedback:
        alert_id = _alert_id_from_feedback(item)
        if not alert_id:
            results.append(
                {
                    "card": item.card,
                    "status": "ignored",
                    "reason": "no curieAlertId / suggestion mapping",
                }
            )
            continue
        note = _note_from_feedback(item)
        updated = acknowledge_fn(alert_id, note)
        if updated is None:
            results.append(
                {"card": item.card, "alert_id": alert_id, "status": "not_found"}
            )
            continue
        results.append(
            {
                "card": item.card,
                "alert_id": alert_id,
                "status": "acknowledged",
                "outcome": item.outcome,
                "acknowledged_at": (
                    updated.acknowledged_at.isoformat()
                    if updated.acknowledged_at
                    else datetime.now(UTC).isoformat()
                ),
            }
        )
    return {"processed": results}


def _alert_id_from_feedback(item: CdsFeedbackItem) -> str | None:
    for suggestion in item.acceptedSuggestions:
        sid = str(suggestion.get("uuid") or suggestion.get("id") or "")
        if sid.startswith("ack-"):
            return sid[4:]
        actions = suggestion.get("actions") or []
        for action in actions:
            resource = action.get("resource") or {}
            for payload in resource.get("payload") or []:
                content = str(payload.get("contentString") or "")
                if content.startswith("acknowledge:"):
                    return content.split(":", 1)[1]
    # Card uuid is uuid5 of alert id — reverse via extension is preferred;
    # callers may put alert id in override reason display as fallback.
    if item.overrideReason and item.overrideReason.display:
        display = item.overrideReason.display
        if display.startswith("alert:"):
            return display.split(":", 1)[1]
    return None


def _note_from_feedback(item: CdsFeedbackItem) -> str:
    parts: list[str] = [f"cds-hooks:{item.outcome}"]
    reasons = list(item.overrideReasons)
    if item.overrideReason:
        reasons = [item.overrideReason, *reasons]
    for reason in reasons:
        label = reason.display or reason.code
        if label:
            parts.append(str(label))
    return " | ".join(parts)[:500]
