"""Postgres-oriented durable store adapter (CURIE-037).

Local demos keep SQLite. When ``CURIE_ALERT_DB`` starts with ``postgresql://``,
operators should deploy Postgres using ``POSTGRES_DDL``. CI exercises tenant
isolation via ``TenantAwareMemoryStore`` without requiring a live database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from action.api.app.models import AlertRecord
from action.api.app.store_contract import assert_tenant_match

POSTGRES_DDL = """
-- CURIE-037 production-shaped durable store (Postgres)
CREATE TABLE IF NOT EXISTS alerts (
  alert_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  patient_id TEXT NOT NULL,
  encounter_id TEXT,
  indicator TEXT NOT NULL,
  event_time TIMESTAMPTZ NOT NULL,
  tier TEXT NOT NULL,
  acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_tenant_event
  ON alerts(tenant_id, event_time DESC);

CREATE TABLE IF NOT EXISTS episodes (
  episode_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  patient_id TEXT NOT NULL,
  encounter_id TEXT,
  status TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  payload_json JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS kafka_dedupe (
  tenant_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  alert_id TEXT NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS retention_jobs (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  dry_run BOOLEAN NOT NULL,
  requested_by TEXT NOT NULL,
  detail JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _to_record(row: dict[str, Any]) -> AlertRecord:
    payload = {k: v for k, v in row.items() if k in AlertRecord.model_fields}
    return AlertRecord.model_validate(payload)


@dataclass
class TenantAwareMemoryStore:
    """Contract stand-in: enforces tenant isolation in queries and writes."""

    tenant_id: str
    site_id: str
    _alerts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _dedupe: dict[str, str] = field(default_factory=dict)
    _retention_audit: list[dict[str, Any]] = field(default_factory=list)

    def upsert(self, alert: AlertRecord) -> AlertRecord:
        data = alert.model_dump()
        data["tenant_id"] = self.tenant_id
        data["site_id"] = self.site_id
        self._alerts[alert.alert_id] = data
        return alert

    def get(self, alert_id: str, *, caller_tenant: str | None = None) -> AlertRecord | None:
        row = self._alerts.get(alert_id)
        if row is None:
            return None
        assert_tenant_match(
            record_tenant=row.get("tenant_id"),
            caller_tenant=caller_tenant or self.tenant_id,
            action="get",
        )
        return _to_record(row)

    def list(self, *, caller_tenant: str | None = None, limit: int = 100) -> list[AlertRecord]:
        tenant = caller_tenant or self.tenant_id
        rows = [_to_record(row) for row in self._alerts.values() if row.get("tenant_id") == tenant]
        rows.sort(key=lambda a: a.event_time, reverse=True)
        return rows[:limit]

    def ingest_kafka(
        self, alert: AlertRecord, *, idempotency_key: str
    ) -> tuple[AlertRecord, bool]:
        if idempotency_key in self._dedupe:
            existing_id = self._dedupe[idempotency_key]
            existing = self.get(existing_id)
            assert existing is not None
            return existing, False
        self.upsert(alert)
        self._dedupe[idempotency_key] = alert.alert_id
        # Offset commit happens only after this durable write succeeds.
        return alert, True

    def retention_job(self, *, dry_run: bool, requested_by: str) -> dict[str, Any]:
        detail = {
            "tenant_id": self.tenant_id,
            "dry_run": dry_run,
            "would_delete": 0,
            "requested_by": requested_by,
            "at": datetime.now(UTC).isoformat(),
        }
        self._retention_audit.append(detail)
        return detail
