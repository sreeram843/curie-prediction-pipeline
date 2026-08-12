"""Shadow-mode execution harness (CURIE-034).

Runs scoring/governance normally but never calls interruptive delivery adapters.
Pages land in a durable ``would_have_paged`` audit stream instead.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


class InterruptiveDeliveryAdapter(Protocol):
    def deliver_page(self, record: dict[str, Any]) -> None: ...


class ForbiddenInterruptiveAdapter:
    """Fail closed: shadow mode must not page."""

    def deliver_page(self, record: dict[str, Any]) -> None:
        raise RuntimeError("shadow mode forbids interruptive delivery")


@dataclass(frozen=True)
class DeploymentMode:
    name: str  # active | shadow

    @property
    def is_shadow(self) -> bool:
        return self.name == "shadow"

    @classmethod
    def from_env(cls, raw: str | None) -> DeploymentMode:
        name = (raw or "active").strip().lower()
        if name not in {"active", "shadow"}:
            raise ValueError(f"Unknown deployment mode {raw!r}")
        return cls(name=name)


class WouldHavePagedStore:
    """SQLite-backed idempotent would_have_paged audit (restart/dedupe safe)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS would_have_paged (
              idempotency_key TEXT PRIMARY KEY,
              alert_id TEXT NOT NULL,
              patient_id TEXT,
              indicator TEXT,
              routing TEXT,
              reason TEXT,
              policy_hash TEXT,
              bundle_id TEXT,
              bundle_version TEXT,
              recorded_at TEXT NOT NULL,
              payload_json TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def record(
        self,
        *,
        idempotency_key: str,
        alert: dict[str, Any],
        policy_hash: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Insert once. Returns (row, inserted_new)."""
        now = datetime.now(UTC).isoformat()
        payload = dict(alert)
        payload["shadow"] = True
        payload["would_have_paged"] = True
        with self._lock:
            existing = self._conn.execute(
                "SELECT payload_json FROM would_have_paged WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return json.loads(existing["payload_json"]), False
            row = {
                "idempotency_key": idempotency_key,
                "alert_id": str(alert.get("alert_id") or ""),
                "patient_id": alert.get("patient_id"),
                "indicator": alert.get("indicator"),
                "routing": alert.get("routing"),
                "reason": alert.get("page_deferred_reason") or alert.get("suppression_reason"),
                "policy_hash": policy_hash,
                "bundle_id": alert.get("rule_bundle_id"),
                "bundle_version": alert.get("rule_version"),
                "recorded_at": now,
                "payload": payload,
            }
            self._conn.execute(
                """
                INSERT INTO would_have_paged (
                  idempotency_key, alert_id, patient_id, indicator, routing, reason,
                  policy_hash, bundle_id, bundle_version, recorded_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["idempotency_key"],
                    row["alert_id"],
                    row["patient_id"],
                    row["indicator"],
                    row["routing"],
                    row["reason"],
                    row["policy_hash"],
                    row["bundle_id"],
                    row["bundle_version"],
                    row["recorded_at"],
                    json.dumps(payload, default=str),
                ),
            )
            self._conn.commit()
            return payload, True

    def list_recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload_json FROM would_have_paged ORDER BY recorded_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM would_have_paged").fetchone()
        return int(row["n"]) if row else 0

    def close(self) -> None:
        self._conn.close()


def apply_delivery(
    *,
    mode: DeploymentMode,
    alert: dict[str, Any],
    adapter: InterruptiveDeliveryAdapter | None,
    shadow_store: WouldHavePagedStore | None,
    idempotency_key: str,
    policy_hash: str | None = None,
) -> dict[str, Any]:
    """Route an interruptive decision through active or shadow delivery."""
    routing = (alert.get("routing") or "").lower()
    if routing != "interruptive":
        return {"delivered": False, "shadow": False, "alert": alert}

    if mode.is_shadow:
        if adapter is not None:
            # Explicit guard — even a miswired adapter must not be callable.
            ForbiddenInterruptiveAdapter().deliver_page(alert)
        if shadow_store is None:
            raise RuntimeError("shadow mode requires WouldHavePagedStore")
        recorded, inserted = shadow_store.record(
            idempotency_key=idempotency_key,
            alert=alert,
            policy_hash=policy_hash,
        )
        return {
            "delivered": False,
            "shadow": True,
            "inserted": inserted,
            "alert": recorded,
        }

    if adapter is None:
        raise RuntimeError("active mode requires interruptive delivery adapter")
    adapter.deliver_page(alert)
    return {"delivered": True, "shadow": False, "alert": alert}


def shadow_day_report(
    records: list[dict[str, Any]],
    *,
    site_id: str,
    indicator: str | None = None,
) -> dict[str, Any]:
    filtered = [
        r
        for r in records
        if indicator is None or r.get("indicator") == indicator
    ]
    by_indicator: dict[str, int] = {}
    for r in filtered:
        key = str(r.get("indicator") or "unknown")
        by_indicator[key] = by_indicator.get(key, 0) + 1
    return {
        "schema_version": "1.0.0",
        "site_id": site_id,
        "n_would_have_paged": len(filtered),
        "by_indicator": by_indicator,
        "notes": [
            "Shadow report — no interruptive notifications were delivered.",
            "SHADOW-PROD remains under_evaluation until partner-site evidence exists.",
        ],
    }
