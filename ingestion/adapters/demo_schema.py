"""Helpers for converting source tables into demo-schema stays.

The MIMIC leakage-safe harness (`eval.mimic_harness.replay`) consumes stays
shaped like `eval/fixtures/mimic_harness/demo_schema_stays.v1.json`. Adapters
map source-specific rows onto concept-tagged events, then
`ingestion.adapters.syn_icu.convert._emit_stay` emits that fixture.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ingestion.adapters.mimic.timeline import parse_mimic_ts


def downsample_hourly(
    events: list[dict[str, Any]],
    *,
    time_key: str = "charttime",
    concept_key: str = "concept",
) -> list[dict[str, Any]]:
    """Keep the last observation per (concept, clock-hour).

    High-frequency vitals would otherwise explode harness replay cost.
    """
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for ev in events:
        raw = ev.get(time_key)
        clock = parse_mimic_ts(str(raw) if raw is not None else None)
        if clock is None:
            continue
        hour = clock.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        key = (str(ev.get(concept_key) or ""), hour)
        prev = buckets.get(key)
        if prev is None:
            buckets[key] = ev
            continue
        prev_clock = parse_mimic_ts(str(prev.get(time_key) or ""))
        if prev_clock is None or clock >= prev_clock:
            buckets[key] = ev
    return sorted(
        buckets.values(),
        key=lambda e: (str(e.get(time_key) or ""), str(e.get("itemid") or "")),
    )


def naive_iso(raw: str | datetime | None) -> str | None:
    """Parse a timestamp and drop tzinfo so harness clocks stay naive."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        clock = raw.replace(tzinfo=None) if raw.tzinfo else raw
        return clock.strftime("%Y-%m-%d %H:%M:%S")
    text = str(raw).strip()
    if not text:
        return None
    clock = parse_mimic_ts(text)
    if clock is None:
        try:
            clock = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if clock.tzinfo is not None:
        clock = clock.replace(tzinfo=None)
    return clock.strftime("%Y-%m-%d %H:%M:%S")
