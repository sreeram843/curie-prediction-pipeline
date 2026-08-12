"""Canonical alert-id algorithm (matches Java AlertIds / UUID.nameUUIDFromBytes)."""

from __future__ import annotations

import hashlib
import uuid


def name_uuid_from_bytes(name: str) -> uuid.UUID:
    digest = bytearray(hashlib.md5(name.encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30  # version 3
    digest[8] = (digest[8] & 0x3F) | 0x80  # IETF variant
    return uuid.UUID(bytes=bytes(digest))


def alert_id(
    patient_id: str,
    encounter_id: str | None,
    indicator: str,
    score: int | None,
    event_time_ms: int,
    version: str,
) -> str:
    raw = (
        f"{patient_id}|{encounter_id or ''}|{indicator}|{score}|{event_time_ms}|{version}"
    )
    return "alert-" + str(name_uuid_from_bytes(raw))
