"""MIMIC stay events → availability-aware timeline (CURIE-015)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

ADAPTER_VERSION = "0.1.0"

EventKind = Literal[
    "lab",
    "chart",
    "input",
    "output",
    "condition",
    "encounter",
]


@dataclass(frozen=True)
class MimicTimelineEvent:
    """One MIMIC-derived clinical fact with distinct clinical vs availability clocks."""

    stay_id: str
    subject_id: str
    hadm_id: str
    kind: EventKind
    itemid: int | None
    valuenum: float | None
    unit: str | None
    event_time: datetime
    availability_time: datetime
    evidence_id: str
    code_system: str | None = None
    code: str | None = None
    display: str | None = None
    status: str = "final"
    # Discharge / billing codes must never enter features before availability.
    is_discharge_diagnosis: bool = False
    raw_ref: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def sort_key(self) -> tuple[datetime, datetime, str]:
        return (self.availability_time, self.event_time, self.evidence_id)


def parse_mimic_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text.replace("Z", "+0000"), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def availability_for_lab(
    *,
    charttime: datetime,
    storetime: datetime | None,
) -> datetime:
    """Labs become knowable at storetime when present; never earlier than charttime."""
    if storetime is None:
        return charttime
    return max(charttime, storetime)


def sort_by_availability(
    events: list[MimicTimelineEvent],
) -> list[MimicTimelineEvent]:
    return sorted(events, key=lambda e: e.sort_key())


def content_hash_events(events: list[MimicTimelineEvent]) -> str:
    """Stable hash of the ordered timeline (no PHI beyond synthetic IDs)."""
    lines: list[str] = []
    for e in sort_by_availability(events):
        lines.append(
            "|".join(
                [
                    e.stay_id,
                    e.kind,
                    e.evidence_id,
                    e.event_time.isoformat(),
                    e.availability_time.isoformat(),
                    str(e.itemid),
                    "" if e.valuenum is None else f"{e.valuenum:.6g}",
                    "1" if e.is_discharge_diagnosis else "0",
                ]
            )
        )
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return digest


def events_from_demo_schema_stay(stay: dict[str, Any]) -> list[MimicTimelineEvent]:
    """Build a timeline from a demo-schema stay fixture (no PhysioNet dump required)."""
    stay_id = str(stay["stay_id"])
    subject_id = str(stay["subject_id"])
    hadm_id = str(stay.get("hadm_id") or "")
    events: list[MimicTimelineEvent] = []

    for raw in stay.get("labs") or []:
        chart = parse_mimic_ts(raw.get("charttime"))
        store = parse_mimic_ts(raw.get("storetime"))
        if chart is None:
            continue
        avail = availability_for_lab(charttime=chart, storetime=store)
        eid = str(raw.get("evidence_id") or f"lab/{raw.get('itemid')}/{raw.get('charttime')}")
        events.append(
            MimicTimelineEvent(
                stay_id=stay_id,
                subject_id=subject_id,
                hadm_id=hadm_id,
                kind="lab",
                itemid=int(raw["itemid"]) if raw.get("itemid") is not None else None,
                valuenum=float(raw["valuenum"]) if raw.get("valuenum") is not None else None,
                unit=raw.get("unit"),
                event_time=chart,
                availability_time=avail,
                evidence_id=eid,
                code_system=raw.get("code_system", "http://loinc.org"),
                code=raw.get("code"),
                display=raw.get("display"),
                status=str(raw.get("status") or "final"),
                raw_ref=raw.get("raw_ref"),
            )
        )

    for raw in stay.get("charts") or []:
        chart = parse_mimic_ts(raw.get("charttime"))
        if chart is None:
            continue
        eid = str(
            raw.get("evidence_id") or f"chart/{raw.get('itemid')}/{raw.get('charttime')}"
        )
        events.append(
            MimicTimelineEvent(
                stay_id=stay_id,
                subject_id=subject_id,
                hadm_id=hadm_id,
                kind="chart",
                itemid=int(raw["itemid"]) if raw.get("itemid") is not None else None,
                valuenum=float(raw["valuenum"]) if raw.get("valuenum") is not None else None,
                unit=raw.get("unit"),
                event_time=chart,
                availability_time=chart,
                evidence_id=eid,
                code_system=raw.get("code_system", "http://loinc.org"),
                code=raw.get("code"),
                display=raw.get("display"),
                status=str(raw.get("status") or "final"),
                raw_ref=raw.get("raw_ref"),
            )
        )

    for raw in stay.get("conditions") or []:
        onset = parse_mimic_ts(raw.get("onset") or raw.get("charttime"))
        avail = parse_mimic_ts(raw.get("availability_time") or raw.get("storetime"))
        if onset is None:
            continue
        if avail is None:
            avail = onset
        eid = str(raw.get("evidence_id") or f"condition/{raw.get('code')}/{onset.isoformat()}")
        events.append(
            MimicTimelineEvent(
                stay_id=stay_id,
                subject_id=subject_id,
                hadm_id=hadm_id,
                kind="condition",
                itemid=None,
                valuenum=None,
                unit=None,
                event_time=onset,
                availability_time=avail,
                evidence_id=eid,
                code_system=raw.get("code_system", "http://hl7.org/fhir/sid/icd-10"),
                code=raw.get("code"),
                display=raw.get("display"),
                status=str(raw.get("status") or "final"),
                is_discharge_diagnosis=bool(raw.get("is_discharge_diagnosis", False)),
                raw_ref=raw.get("raw_ref"),
            )
        )

    return sort_by_availability(events)
