"""Immutable episode snapshot for grounded narrative (CURIE-023)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from eval.episodes.models import Episode, SignalRef
from reasoning.models import AlertContext


class EpisodeSignalSnapshot(BaseModel):
    signal_id: str
    signal_type: str
    severity: str
    score: int | None = None
    routing: str | None = None
    event_time: datetime
    evidence_ids: list[str] = Field(default_factory=list)
    criteria_met: list[str] = Field(default_factory=list)
    missing_note: str | None = None
    rule_bundle_id: str | None = None
    rule_version: str | None = None


class EpisodeContext(BaseModel):
    """Frozen, read-only context passed to GRP — never mutates the episode."""

    episode_id: str
    patient_id: str
    encounter_id: str | None = None
    status: str
    dominant_signal_type: str | None = None
    dominant_severity: str = "none"
    supporting_signal_types: list[str] = Field(default_factory=list)
    routing_rationale: str
    page_count: int = 0
    passive_update_count: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    signals: list[EpisodeSignalSnapshot] = Field(default_factory=list)
    snapshot_hash: str
    prompt_version: str = "episode-narrative.v1"
    # Compatibility surface for claim_validator / deterministic generators
    alert_id: str = ""  # mirrors episode_id for shared GateDecision
    score: int | None = None
    tier: str = "none"
    completeness: str = "partial"
    component_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    rule_bundle_id: str = "episode"
    rule_version: str = "1.0.0"

    def as_alert_context(self) -> AlertContext:
        return AlertContext(
            alert_id=self.episode_id,
            patient_id=self.patient_id,
            score=self.score,
            tier=self.tier,
            completeness=self.completeness,
            evidence_ids=list(self.evidence_ids),
            component_breakdown=list(self.component_breakdown),
            missing_components=list(self.missing_components),
            rule_bundle_id=self.rule_bundle_id,
            rule_version=self.rule_version,
        )


def _routing_rationale(episode: Episode) -> str:
    if episode.page_count > 0 and episode.dominant_severity in {"urgent", "critical"}:
        return (
            f"Interruptive: dominant {episode.dominant_signal_type} at "
            f"{episode.dominant_severity}; page_count={episode.page_count}; "
            f"last_action={episode.last_action.value}:{episode.last_action_reason}."
        )
    if episode.passive_update_count > 0 or episode.dominant_severity == "watch":
        return (
            f"Passive: visible episode without repeat interruptive page; "
            f"passive_updates={episode.passive_update_count}; "
            f"last_action={episode.last_action.value}:{episode.last_action_reason}."
        )
    return (
        f"Routing none/open: status={episode.status.value}; "
        f"severity={episode.dominant_severity}."
    )


def _snapshot_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def build_episode_context(
    episode: Episode | dict[str, Any],
    *,
    prompt_version: str = "episode-narrative.v1",
) -> EpisodeContext:
    """Build an immutable narrative context from an episode (CURIE-023)."""
    if isinstance(episode, dict):
        ep = Episode.model_validate(episode)
    else:
        ep = episode

    signals: list[EpisodeSignalSnapshot] = []
    breakdown: list[dict[str, Any]] = []
    evidence: list[str] = []
    for sig in ep.signals:
        ref = sig if isinstance(sig, SignalRef) else SignalRef.model_validate(sig)
        eids = list(ref.evidence_ids)
        for e in eids:
            if e not in evidence:
                evidence.append(e)
        snap = EpisodeSignalSnapshot(
            signal_id=ref.signal_id,
            signal_type=ref.signal_type,
            severity=ref.severity,
            score=ref.score,
            routing=ref.routing,
            event_time=ref.event_time,
            evidence_ids=eids,
            criteria_met=list(ref.criteria_met),
            rule_bundle_id=ref.rule_bundle_id,
            rule_version=ref.rule_version,
        )
        signals.append(snap)
        breakdown.append(
            {
                "name": ref.signal_type,
                "points": ref.score,
                "missing": False,
                "evidence_ids": eids,
            }
        )

    # Prefer episode-level evidence union when present
    for e in ep.evidence_ids:
        if e not in evidence:
            evidence.append(e)

    missing: list[str] = []
    # Surface suppressed / empty-evidence signals as missing-data disclosure
    for snap in signals:
        if not snap.evidence_ids:
            missing.append(f"{snap.signal_type}:{snap.signal_id}:no_evidence")

    stable = {
        "episode_id": ep.episode_id,
        "patient_id": ep.patient_id,
        "encounter_id": ep.encounter_id,
        "status": ep.status.value if hasattr(ep.status, "value") else str(ep.status),
        "dominant_signal_type": ep.dominant_signal_type,
        "dominant_severity": ep.dominant_severity,
        "supporting_signal_types": list(ep.supporting_signal_types),
        "evidence_ids": evidence,
        "signals": [s.model_dump(mode="json") for s in signals],
        "page_count": ep.page_count,
        "passive_update_count": ep.passive_update_count,
        "last_action": ep.last_action.value if hasattr(ep.last_action, "value") else str(ep.last_action),  # noqa: E501
        "last_action_reason": ep.last_action_reason,
    }
    return EpisodeContext(
        episode_id=ep.episode_id,
        patient_id=ep.patient_id,
        encounter_id=ep.encounter_id,
        status=stable["status"],
        dominant_signal_type=ep.dominant_signal_type,
        dominant_severity=ep.dominant_severity,
        supporting_signal_types=list(ep.supporting_signal_types),
        routing_rationale=_routing_rationale(ep),
        page_count=ep.page_count,
        passive_update_count=ep.passive_update_count,
        evidence_ids=evidence,
        missing_inputs=missing,
        signals=signals,
        snapshot_hash=_snapshot_hash(stable),
        prompt_version=prompt_version,
        alert_id=ep.episode_id,
        score=next((s.score for s in signals if s.signal_type == ep.dominant_signal_type), None),
        tier=ep.dominant_severity,
        completeness="partial" if missing else "complete",
        component_breakdown=breakdown,
        missing_components=missing,
        rule_bundle_id="episode-arbiter",
        rule_version="1.0.0",
    )


def serialize_episode_context_for_model(ctx: EpisodeContext) -> str:
    lines = [
        f"episode_id={ctx.episode_id}",
        f"patient_id={ctx.patient_id}",
        f"status={ctx.status}",
        f"dominant={ctx.dominant_signal_type}@{ctx.dominant_severity}",
        f"supporting={','.join(ctx.supporting_signal_types) or '(none)'}",
        f"routing_rationale={ctx.routing_rationale}",
        f"evidence_ids={','.join(ctx.evidence_ids) or '(none)'}",
        f"missing_inputs={','.join(ctx.missing_inputs) or '(none)'}",
        f"snapshot_hash={ctx.snapshot_hash}",
        f"prompt_version={ctx.prompt_version}",
        "signals:",
    ]
    for s in ctx.signals:
        lines.append(
            f"  - {s.signal_type} id={s.signal_id} sev={s.severity} "
            f"routing={s.routing} evidence={','.join(s.evidence_ids) or '(none)'}"
        )
    return "\n".join(lines)
