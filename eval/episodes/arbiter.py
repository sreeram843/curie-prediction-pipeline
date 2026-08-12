"""Cross-condition episode arbiter (CURIE-012).

Prototype only — not clinically validated.

Groups correlated signals within a configurable window, picks a dominant
problem, and pages only on meaningful escalation or new actionability.
Passive updates stay visible without repeat interruptive pages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from eval.episodes.models import (
    SEVERITY_RANK,
    SIGNAL_PRIORITY,
    Episode,
    EpisodeAction,
    EpisodeAuditEntry,
    EpisodeStatus,
    SignalRef,
)


@dataclass
class EpisodeConfig:
    """Arbitration knobs (deterministic; frozen per study when needed)."""

    window_minutes: int = 120
    """Signals within this gap of the episode's last update join the same episode."""

    page_refractory_minutes: int = 60
    """Minimum gap between interruptive pages for the same episode."""

    resolve_quiet_minutes: int = 180
    """If all active signals are none/watch-only quiet and quiet period elapses → resolve."""

    reopen_after_resolve_minutes: int = 30
    """A new actionable signal after resolve opens REOPENED (then OPEN semantics)."""

    signal_priority: tuple[str, ...] = SIGNAL_PRIORITY


@dataclass
class ArbiterResult:
    episode: Episode
    action: EpisodeAction
    reason: str
    should_page: bool
    """True only when an interruptive page should be emitted for this step."""


def _rank(severity: str) -> int:
    return SEVERITY_RANK.get((severity or "none").lower(), 0)


def _priority_index(signal_type: str, order: tuple[str, ...]) -> int:
    try:
        return order.index(signal_type)
    except ValueError:
        return len(order) + 1


def _is_actionable(sig: SignalRef) -> bool:
    if sig.suppressed:
        return False
    return _rank(sig.severity) >= _rank("urgent") or (
        sig.routing == "interruptive"
    )


def _is_passive_visible(sig: SignalRef) -> bool:
    if sig.suppressed:
        return False
    return _rank(sig.severity) >= _rank("watch") or sig.routing == "passive"


def select_dominant(
    signals: list[SignalRef],
    *,
    priority: tuple[str, ...] = SIGNAL_PRIORITY,
) -> SignalRef | None:
    """Highest severity wins; ties broken by configured signal priority then time."""
    active = [s for s in signals if not s.suppressed]
    if not active:
        return None
    return min(
        active,
        key=lambda s: (
            -_rank(s.severity),
            _priority_index(s.signal_type, priority),
            -s.event_time.timestamp(),
        ),
    )


def signal_ref_from_alert(alert: dict[str, Any] | Any) -> SignalRef:
    if hasattr(alert, "model_dump"):
        data = alert.model_dump()
    else:
        data = dict(alert)
    sig = data.get("signal") if isinstance(data.get("signal"), dict) else {}
    return SignalRef(
        signal_id=str(data.get("alert_id") or data.get("signal_id") or uuid4()),
        signal_type=str(
            sig.get("signal_type") or data.get("indicator") or "unknown"
        ),
        signal_kind=str(sig.get("signal_kind") or data.get("signal_kind") or "risk"),
        severity=str(sig.get("severity") or data.get("tier") or "none"),
        score=sig.get("score", data.get("score")),
        routing=data.get("routing"),
        event_time=data["event_time"]
        if isinstance(data["event_time"], datetime)
        else datetime.fromisoformat(str(data["event_time"]).replace("Z", "+00:00")),
        evidence_ids=list(
            sig.get("evidence_ids") or data.get("evidence_ids") or []
        ),
        suppressed=bool(data.get("suppressed")),
        suppression_reason=data.get("suppression_reason"),
        exclusions=list(sig.get("exclusions") or data.get("exclusions") or []),
        criteria_met=list(sig.get("criteria_met") or data.get("criteria_met") or []),
        rule_bundle_id=data.get("rule_bundle_id"),
        rule_version=data.get("rule_version"),
    )


class EpisodeArbiter:
    """Stateful per-patient (encounter-scoped) episode aggregator."""

    def __init__(self, config: EpisodeConfig | None = None) -> None:
        self.config = config or EpisodeConfig()
        self._episodes: dict[str, Episode] = {}
        # key: patient_id|encounter_id → episode_id of active episode
        self._active: dict[str, str] = {}

    def _key(self, patient_id: str, encounter_id: str | None) -> str:
        return f"{patient_id}|{encounter_id or ''}"

    def get(self, episode_id: str) -> Episode | None:
        return self._episodes.get(episode_id)

    def list_for_patient(self, patient_id: str) -> list[Episode]:
        return sorted(
            (e for e in self._episodes.values() if e.patient_id == patient_id),
            key=lambda e: e.updated_at,
            reverse=True,
        )

    def list_all(self) -> list[Episode]:
        return sorted(
            self._episodes.values(), key=lambda e: e.updated_at, reverse=True
        )

    def _append_audit(
        self,
        episode: Episode,
        *,
        at: datetime,
        action: EpisodeAction,
        status: EpisodeStatus,
        reason: str,
        signal_id: str | None,
    ) -> None:
        episode.audit.append(
            EpisodeAuditEntry(
                at=at,
                action=action,
                status=status,
                reason=reason,
                signal_id=signal_id,
                dominant_signal_type=episode.dominant_signal_type,
            )
        )

    def _refresh_dominance(self, episode: Episode) -> None:
        dominant = select_dominant(
            episode.signals, priority=self.config.signal_priority
        )
        if dominant is None:
            episode.dominant_signal_type = None
            episode.dominant_severity = "none"
            episode.supporting_signal_types = []
            return
        episode.dominant_signal_type = dominant.signal_type
        episode.dominant_severity = dominant.severity
        types = []
        for s in episode.signals:
            if s.suppressed:
                continue
            if s.signal_type == dominant.signal_type:
                continue
            if s.signal_type not in types:
                types.append(s.signal_type)
        episode.supporting_signal_types = types
        evidence: list[str] = []
        for s in episode.signals:
            for e in s.evidence_ids:
                if e not in evidence:
                    evidence.append(e)
        episode.evidence_ids = evidence

    def _open_new(
        self, ref: SignalRef, *, patient_id: str, encounter_id: str | None
    ) -> ArbiterResult:
        episode_id = f"episode-{uuid4()}"
        status = EpisodeStatus.OPEN
        action = EpisodeAction.PAGE if _is_actionable(ref) else EpisodeAction.PASSIVE
        reason = (
            "new_episode_interruptive"
            if action == EpisodeAction.PAGE
            else "new_episode_passive"
        )
        episode = Episode(
            episode_id=episode_id,
            patient_id=patient_id,
            encounter_id=encounter_id,
            status=status,
            opened_at=ref.event_time,
            updated_at=ref.event_time,
            signals=[ref],
            last_action=action,
            last_action_reason=reason,
        )
        if action == EpisodeAction.PAGE:
            episode.page_count = 1
            episode.last_page_at = ref.event_time
            episode.status = EpisodeStatus.OPEN
        else:
            episode.passive_update_count = 1
        self._refresh_dominance(episode)
        self._append_audit(
            episode,
            at=ref.event_time,
            action=action,
            status=episode.status,
            reason=reason,
            signal_id=ref.signal_id,
        )
        self._episodes[episode_id] = episode
        self._active[self._key(patient_id, encounter_id)] = episode_id
        return ArbiterResult(
            episode=episode,
            action=action,
            reason=reason,
            should_page=action == EpisodeAction.PAGE,
        )

    def ingest(
        self,
        alert: dict[str, Any] | Any,
        *,
        patient_id: str | None = None,
        encounter_id: str | None = None,
    ) -> ArbiterResult:
        """Fold one alert/signal into the patient's active episode."""
        ref = signal_ref_from_alert(alert)
        if hasattr(alert, "model_dump"):
            data = alert.model_dump()
        else:
            data = dict(alert)
        pid = patient_id or str(data.get("patient_id") or "")
        enc = encounter_id if encounter_id is not None else data.get("encounter_id")
        if not pid:
            raise ValueError("patient_id is required")

        key = self._key(pid, enc)
        active_id = self._active.get(key)
        episode = self._episodes.get(active_id) if active_id else None

        # Resolved episode: reopen or start fresh based on timing
        if episode is not None and episode.status == EpisodeStatus.RESOLVED:
            assert episode.resolved_at is not None
            gap = ref.event_time - episode.resolved_at
            if gap <= timedelta(minutes=self.config.reopen_after_resolve_minutes) and (
                _is_actionable(ref) or _is_passive_visible(ref)
            ):
                return self._reopen(episode, ref)
            # Too long after resolve — new episode
            episode = None
            self._active.pop(key, None)

        if episode is None:
            return self._open_new(ref, patient_id=pid, encounter_id=enc)

        # Window membership
        gap = ref.event_time - episode.updated_at
        if gap > timedelta(minutes=self.config.window_minutes):
            # Close prior as resolved if still open-ish, then open new
            if episode.status not in {
                EpisodeStatus.RESOLVED,
                EpisodeStatus.ACKNOWLEDGED,
            }:
                episode.status = EpisodeStatus.RESOLVED
                episode.resolved_at = episode.updated_at
                self._append_audit(
                    episode,
                    at=episode.updated_at,
                    action=EpisodeAction.RESOLVE,
                    status=EpisodeStatus.RESOLVED,
                    reason="episode_window_elapsed",
                    signal_id=None,
                )
            return self._open_new(ref, patient_id=pid, encounter_id=enc)

        return self._update(episode, ref)

    def _reopen(self, episode: Episode, ref: SignalRef) -> ArbiterResult:
        episode.signals.append(ref)
        episode.updated_at = ref.event_time
        episode.resolved_at = None
        episode.status = EpisodeStatus.REOPENED
        prev_sev = _rank(episode.dominant_severity)
        self._refresh_dominance(episode)
        actionable = _is_actionable(ref)
        escalated = _rank(episode.dominant_severity) > prev_sev
        if actionable and (
            episode.last_page_at is None
            or (ref.event_time - episode.last_page_at)
            >= timedelta(minutes=self.config.page_refractory_minutes)
        ):
            action = EpisodeAction.PAGE
            reason = "reopened_with_actionable_signal"
            episode.page_count += 1
            episode.last_page_at = ref.event_time
            if escalated:
                episode.status = EpisodeStatus.ESCALATED
                reason = "reopened_escalated"
        else:
            action = EpisodeAction.PASSIVE
            reason = "reopened_passive_update"
            episode.passive_update_count += 1
        episode.last_action = action
        episode.last_action_reason = reason
        self._append_audit(
            episode,
            at=ref.event_time,
            action=action,
            status=episode.status,
            reason=reason,
            signal_id=ref.signal_id,
        )
        self._active[self._key(episode.patient_id, episode.encounter_id)] = (
            episode.episode_id
        )
        return ArbiterResult(
            episode=episode,
            action=action,
            reason=reason,
            should_page=action == EpisodeAction.PAGE,
        )

    def _update(self, episode: Episode, ref: SignalRef) -> ArbiterResult:
        # Dedup identical signal_id
        if any(s.signal_id == ref.signal_id for s in episode.signals):
            episode.updated_at = max(episode.updated_at, ref.event_time)
            episode.last_action = EpisodeAction.NONE
            episode.last_action_reason = "duplicate_signal_id"
            self._append_audit(
                episode,
                at=ref.event_time,
                action=EpisodeAction.NONE,
                status=episode.status,
                reason="duplicate_signal_id",
                signal_id=ref.signal_id,
            )
            return ArbiterResult(
                episode=episode,
                action=EpisodeAction.NONE,
                reason="duplicate_signal_id",
                should_page=False,
            )

        prev_sev = _rank(episode.dominant_severity)
        prev_dom = episode.dominant_signal_type
        episode.signals.append(ref)
        episode.updated_at = ref.event_time
        self._refresh_dominance(episode)
        new_sev = _rank(episode.dominant_severity)
        escalated = new_sev > prev_sev
        new_dominant_type = (
            episode.dominant_signal_type != prev_dom and prev_dom is not None
        )

        if episode.status == EpisodeStatus.ACKNOWLEDGED and (
            escalated or _is_actionable(ref)
        ):
            # Re-deteriorate after ack → treat as escalation candidate
            episode.status = EpisodeStatus.ESCALATED

        should_consider_page = _is_actionable(ref) or escalated
        within_refractory = (
            episode.last_page_at is not None
            and (ref.event_time - episode.last_page_at)
            < timedelta(minutes=self.config.page_refractory_minutes)
        )

        if should_consider_page and not within_refractory:
            action = EpisodeAction.PAGE
            if escalated:
                episode.status = EpisodeStatus.ESCALATED
                reason = "severity_escalation"
            elif new_dominant_type and _is_actionable(ref):
                episode.status = EpisodeStatus.UPDATED
                reason = "new_actionable_supporting_or_dominant"
            else:
                episode.status = EpisodeStatus.UPDATED
                reason = "new_actionable_signal"
            episode.page_count += 1
            episode.last_page_at = ref.event_time
        elif _is_passive_visible(ref) or escalated or new_dominant_type:
            action = EpisodeAction.PASSIVE
            reason = (
                "passive_update_within_page_refractory"
                if within_refractory and should_consider_page
                else "passive_update"
            )
            if episode.status not in {
                EpisodeStatus.ESCALATED,
                EpisodeStatus.ACKNOWLEDGED,
                EpisodeStatus.RESOLVED,
            }:
                episode.status = EpisodeStatus.UPDATED
            episode.passive_update_count += 1
        else:
            action = EpisodeAction.NONE
            reason = "non_actionable_or_suppressed"
            episode.passive_update_count += 1

        episode.last_action = action
        episode.last_action_reason = reason
        self._append_audit(
            episode,
            at=ref.event_time,
            action=action,
            status=episode.status,
            reason=reason,
            signal_id=ref.signal_id,
        )
        return ArbiterResult(
            episode=episode,
            action=action,
            reason=reason,
            should_page=action == EpisodeAction.PAGE,
        )

    def acknowledge(
        self, episode_id: str, *, at: datetime, note: str | None = None
    ) -> Episode:
        episode = self._episodes[episode_id]
        episode.status = EpisodeStatus.ACKNOWLEDGED
        episode.acknowledged_at = at
        episode.updated_at = at
        episode.last_action = EpisodeAction.ACK
        episode.last_action_reason = note or "acknowledged"
        self._append_audit(
            episode,
            at=at,
            action=EpisodeAction.ACK,
            status=EpisodeStatus.ACKNOWLEDGED,
            reason=episode.last_action_reason,
            signal_id=None,
        )
        return episode

    def resolve(self, episode_id: str, *, at: datetime, reason: str = "resolved") -> Episode:
        episode = self._episodes[episode_id]
        episode.status = EpisodeStatus.RESOLVED
        episode.resolved_at = at
        episode.updated_at = at
        episode.last_action = EpisodeAction.RESOLVE
        episode.last_action_reason = reason
        self._append_audit(
            episode,
            at=at,
            action=EpisodeAction.RESOLVE,
            status=EpisodeStatus.RESOLVED,
            reason=reason,
            signal_id=None,
        )
        # Keep _active pointing here so re-deterioration can reopen deterministically.
        return episode
