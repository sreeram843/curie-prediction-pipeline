"""OpenAI-compatible GRP client (LM Studio, vLLM, etc.).

Still fail-closed: every claim must cite evidence IDs already on the alert.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from reasoning.context_builder import serialize_context_for_model
from reasoning.models import AlertContext, Claim, NarrativeDraft

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

SYSTEM_PROMPT = """You explain clinical deterioration alerts that already fired.
Reply with ONLY valid JSON matching this schema:
{
  "summary": string,
  "claims": [{"text": string, "evidence_ids": [string]}],
  "abstain": boolean,
  "abstain_reason": string or null
}

Rules:
- Use ONLY facts in the alert context.
- Every claim MUST include evidence_ids drawn from the allowed list.
- Do not invent labs, vitals, diagnoses, or evidence IDs.
- Do not give treatment recommendations or orders.
- If evidence is insufficient, set abstain=true and explain why.
- No markdown, no prose outside JSON.
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    fence = _JSON_FENCE.search(raw)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model response did not contain a JSON object")
    return json.loads(raw[start : end + 1])


def _draft_from_payload(payload: dict[str, Any], *, model_name: str) -> NarrativeDraft:
    abstain = bool(payload.get("abstain"))
    claims_raw = payload.get("claims") or []
    claims: list[Claim] = []
    if isinstance(claims_raw, list):
        for item in claims_raw:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            eids = item.get("evidence_ids") or []
            if not isinstance(eids, list):
                eids = []
            eids = [str(e).strip() for e in eids if str(e).strip()]
            if text:
                claims.append(Claim(text=text, evidence_ids=eids))

    summary = str(payload.get("summary") or "").strip()
    reason = payload.get("abstain_reason")
    abstain_reason = str(reason).strip() if reason is not None else None

    if abstain:
        return NarrativeDraft(
            summary="",
            claims=[],
            abstain=True,
            abstain_reason=abstain_reason
            or "Model abstained: insufficient grounded evidence.",
            model_name=model_name,
        )

    if not summary and not claims:
        return NarrativeDraft(
            summary="",
            claims=[],
            abstain=True,
            abstain_reason="Model returned empty narrative.",
            model_name=model_name,
        )

    return NarrativeDraft(
        summary=summary,
        claims=claims,
        abstain=False,
        model_name=model_name,
    )


def generate_openai_compat(
    ctx: AlertContext,
    *,
    model_name: str,
    base_url: str,
    api_key: str,
    timeout_s: float = 120.0,
    max_tokens: int = 512,
    temperature: float = 0.0,
) -> NarrativeDraft:
    """Call an OpenAI-compatible /chat/completions endpoint."""
    if not ctx.evidence_ids:
        return NarrativeDraft(
            summary="",
            claims=[],
            abstain=True,
            abstain_reason="Insufficient grounded evidence for a narrative explanation.",
            model_name=model_name,
        )

    user_prompt = (
        f"Allowed evidence_ids: {', '.join(ctx.evidence_ids)}\n\n"
        f"Alert context:\n{serialize_context_for_model(ctx)}\n\n"
        "Return JSON only."
    )

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    with httpx.Client(timeout=timeout_s) as client:
        resp = client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"unexpected chat completion shape: {exc}") from exc

    payload = _extract_json_object(str(content))
    return _draft_from_payload(payload, model_name=model_name)
