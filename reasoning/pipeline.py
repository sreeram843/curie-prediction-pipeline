"""Guarded Reasoning Pipeline — additive post-alert / post-episode narrative only.

Never creates, suppresses, or changes a deterministic alert score or routing.
"""

from __future__ import annotations

import time
from typing import Any

from ingestion.extraction.settings import settings
from reasoning.claim_validator import validate_draft
from reasoning.context_builder import build_alert_context
from reasoning.episode_context import build_episode_context
from reasoning.episode_narrative import (
    generate_deterministic_episode,
    generate_episode_injection_attack,
    generate_malformed_episode_draft,
)
from reasoning.model_client import (
    generate_deterministic,
    generate_openai_compat,
    generate_ungrounded_hallucination,
)
from reasoning.models import GateDecision
from reasoning.policy_gate import apply_policy_gate


def explain_alert(
    alert: dict[str, Any] | Any,
    *,
    force: bool = False,
    inject_ungrounded: bool = False,
) -> GateDecision:
    """Run GRP for an already-fired alert.

    ``force`` bypasses the feature flag for tests/eval.
    ``inject_ungrounded`` is test-only to prove quarantine.
    """
    data = alert.model_dump(mode="json") if hasattr(alert, "model_dump") else dict(alert)
    alert_id = str(data.get("alert_id") or "unknown")

    if not settings.enable_grp and not force:
        return GateDecision(
            status="disabled",
            narrative=None,
            quarantine_reason="GRP disabled (CURIE_ENABLE_GRP=false).",
            alert_id=alert_id,
            model_name=settings.grp_model_name,
        )

    ctx = build_alert_context(data)
    try:
        if inject_ungrounded:
            draft = generate_ungrounded_hallucination(ctx, model_name=settings.grp_model_name)
        elif settings.grp_backend == "deterministic":
            draft = generate_deterministic(ctx, model_name=settings.grp_model_name)
        elif settings.grp_backend == "openai_compat":
            draft = generate_openai_compat(
                ctx,
                model_name=settings.grp_model_name,
                base_url=settings.grp_base_url,
                api_key=settings.grp_api_key,
                timeout_s=settings.grp_timeout_s,
                max_tokens=settings.grp_max_tokens,
                temperature=settings.grp_temperature,
            )
        else:
            return GateDecision(
                status="error",
                narrative=None,
                quarantine_reason=f"Unsupported GRP backend: {settings.grp_backend}",
                alert_id=alert_id,
                model_name=settings.grp_model_name,
            )
    except Exception as exc:  # noqa: BLE001 — fail closed to API, never mutate score
        return GateDecision(
            status="error",
            narrative=None,
            quarantine_reason=f"GRP model error: {exc}",
            alert_id=alert_id,
            model_name=settings.grp_model_name,
        )

    validated = validate_draft(draft, ctx)
    return apply_policy_gate(
        alert_id=alert_id,
        draft=draft,
        validated=validated,
        fail_closed=settings.grp_fail_closed,
    )


def explain_episode(
    episode: dict[str, Any] | Any,
    *,
    force: bool = False,
    inject_ungrounded: bool = False,
    inject_prompt_injection: bool = False,
    inject_malformed: bool = False,
    simulate_timeout: bool = False,
    timeout_s: float | None = None,
) -> GateDecision:
    """Additive episode narrative over an immutable snapshot (CURIE-023).

    Narrative failure never changes episode status, routing, scores, or alert delivery.
    """
    data = episode.model_dump(mode="json") if hasattr(episode, "model_dump") else dict(episode)
    episode_id = str(data.get("episode_id") or "unknown")

    if not settings.enable_grp and not force:
        return GateDecision(
            status="disabled",
            narrative=None,
            quarantine_reason="GRP disabled (CURIE_ENABLE_GRP=false).",
            alert_id=episode_id,
            episode_id=episode_id,
            model_name=settings.grp_model_name,
            prompt_version="episode-narrative.v1",
        )

    ctx = build_episode_context(data)
    limit = settings.grp_timeout_s if timeout_s is None else timeout_s
    started = time.monotonic()

    try:
        if simulate_timeout:
            raise TimeoutError(f"GRP episode narrative exceeded {limit}s")
        if inject_prompt_injection:
            draft = generate_episode_injection_attack(ctx, model_name=settings.grp_model_name)
        elif inject_malformed:
            draft = generate_malformed_episode_draft(ctx, model_name=settings.grp_model_name)
        elif inject_ungrounded:
            draft = generate_episode_injection_attack(ctx, model_name=settings.grp_model_name)
        elif settings.grp_backend in {"deterministic", "openai_compat"}:
            # Episode path uses deterministic grounded generator even when alert path
            # uses openai_compat — keeps episode narrative reproducible/offline-safe.
            # Optional LLM can be layered later behind the same validator/gate.
            draft = generate_deterministic_episode(ctx, model_name=settings.grp_model_name)
        else:
            return GateDecision(
                status="error",
                narrative=None,
                quarantine_reason=f"Unsupported GRP backend: {settings.grp_backend}",
                alert_id=episode_id,
                episode_id=episode_id,
                model_name=settings.grp_model_name,
                prompt_version=ctx.prompt_version,
                snapshot_hash=ctx.snapshot_hash,
            )
        if time.monotonic() - started > limit:
            raise TimeoutError(f"GRP episode narrative exceeded {limit}s")
    except TimeoutError as exc:
        return GateDecision(
            status="error",
            narrative=None,
            quarantine_reason=f"GRP timeout: {exc}",
            alert_id=episode_id,
            episode_id=episode_id,
            model_name=settings.grp_model_name,
            prompt_version=ctx.prompt_version,
            snapshot_hash=ctx.snapshot_hash,
        )
    except Exception as exc:  # noqa: BLE001
        return GateDecision(
            status="error",
            narrative=None,
            quarantine_reason=f"GRP model error: {exc}",
            alert_id=episode_id,
            episode_id=episode_id,
            model_name=settings.grp_model_name,
            prompt_version=ctx.prompt_version,
            snapshot_hash=ctx.snapshot_hash,
        )

    validated = validate_draft(draft, ctx)
    return apply_policy_gate(
        alert_id=episode_id,
        draft=draft,
        validated=validated,
        fail_closed=settings.grp_fail_closed,
        episode_id=episode_id,
        prompt_version=ctx.prompt_version,
        snapshot_hash=ctx.snapshot_hash,
    )
