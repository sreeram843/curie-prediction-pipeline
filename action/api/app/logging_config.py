"""PHI-safe structured logging helpers (CURIE-018)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

_PATIENT_RE = re.compile(r"Patient/[A-Za-z0-9._-]+")
_ENCOUNTER_RE = re.compile(r"Encounter/[A-Za-z0-9._-]+")


def redact_text(text: str) -> str:
    text = _PATIENT_RE.sub("Patient/<redacted>", text)
    text = _ENCOUNTER_RE.sub("Encounter/<redacted>", text)
    return text


def hash_identifier(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def configure_phi_safe_logging(*, level: int = logging.INFO) -> None:
    """Install a JSON formatter that redacts common FHIR identifiers."""

    class _PhiSafeJsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            payload = {
                "level": record.levelname,
                "logger": record.name,
                "message": redact_text(record.getMessage()),
            }
            if record.exc_info:
                payload["exc_info"] = redact_text(
                    self.formatException(record.exc_info)
                )
            return json.dumps(payload, sort_keys=True)

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_PhiSafeJsonFormatter())
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.setFormatter(_PhiSafeJsonFormatter())
    root.setLevel(level)


def ops_log_extra(*, tenant_id: str, site_id: str, **fields: Any) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "site_id": site_id,
        **{k: v for k, v in fields.items() if v is not None},
    }
