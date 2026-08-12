"""CURIE-037 tenant isolation + store contract."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from action.api.app.models import AlertRecord
from action.api.app.postgres_store import POSTGRES_DDL, TenantAwareMemoryStore
from action.api.app.store_contract import assert_tenant_match


def _alert(aid: str) -> AlertRecord:
    return AlertRecord(
        alert_id=aid,
        patient_id="Patient/p1",
        encounter_id="Encounter/e1",
        indicator="sofa-deterioration",
        event_time=datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
        score=4,
        tier="urgent",
        completeness="complete",
        routing="interruptive",
        rule_bundle_id="sepsis-sofa",
        rule_version="0.3.0",
    )


def test_cross_tenant_get_fails_closed() -> None:
    store = TenantAwareMemoryStore(tenant_id="hospital-a", site_id="icu")
    store.upsert(_alert("a1"))
    with pytest.raises(PermissionError, match="cross-tenant"):
        store.get("a1", caller_tenant="hospital-b")


def test_kafka_dedupe_and_ddl_present() -> None:
    store = TenantAwareMemoryStore(tenant_id="hospital-a", site_id="icu")
    a, inserted = store.ingest_kafka(_alert("k1"), idempotency_key="t:0:1")
    b, inserted2 = store.ingest_kafka(_alert("k1"), idempotency_key="t:0:1")
    assert inserted is True
    assert inserted2 is False
    assert a.alert_id == b.alert_id
    assert "tenant_id TEXT NOT NULL" in POSTGRES_DDL
    assert "PRIMARY KEY (tenant_id, idempotency_key)" in POSTGRES_DDL
    job = store.retention_job(dry_run=True, requested_by="ops:alice")
    assert job["dry_run"] is True
    assert len(store._retention_audit) == 1


def test_assert_tenant_match() -> None:
    assert_tenant_match(record_tenant="a", caller_tenant="a", action="ack")
    with pytest.raises(PermissionError):
        assert_tenant_match(record_tenant="a", caller_tenant="b", action="ack")
