"""CURIE-034 shadow harness tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.shadow.harness import (
    DeploymentMode,
    ForbiddenInterruptiveAdapter,
    WouldHavePagedStore,
    apply_delivery,
    shadow_day_report,
)


class RecordingAdapter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def deliver_page(self, record: dict) -> None:
        self.calls.append(record)


def test_shadow_forbids_interruptive_adapter(tmp_path: Path) -> None:
    store = WouldHavePagedStore(tmp_path / "shadow.db")
    alert = {
        "alert_id": "a1",
        "routing": "interruptive",
        "patient_id": "Patient/1",
        "indicator": "sofa-deterioration",
    }
    with pytest.raises(RuntimeError, match="forbids"):
        apply_delivery(
            mode=DeploymentMode(name="shadow"),
            alert=alert,
            adapter=RecordingAdapter(),
            shadow_store=store,
            idempotency_key="k1",
        )


def test_shadow_records_idempotent(tmp_path: Path) -> None:
    store = WouldHavePagedStore(tmp_path / "shadow.db")
    alert = {
        "alert_id": "a1",
        "routing": "interruptive",
        "patient_id": "Patient/1",
        "indicator": "aki",
    }
    r1 = apply_delivery(
        mode=DeploymentMode(name="shadow"),
        alert=alert,
        adapter=None,
        shadow_store=store,
        idempotency_key="dup",
        policy_hash="abc",
    )
    r2 = apply_delivery(
        mode=DeploymentMode(name="shadow"),
        alert=alert,
        adapter=None,
        shadow_store=store,
        idempotency_key="dup",
        policy_hash="abc",
    )
    assert r1["inserted"] is True
    assert r2["inserted"] is False
    assert store.count() == 1
    report = shadow_day_report(store.list_recent(), site_id="dev")
    assert report["n_would_have_paged"] == 1


def test_active_delivers() -> None:
    adapter = RecordingAdapter()
    alert = {"alert_id": "a1", "routing": "interruptive"}
    out = apply_delivery(
        mode=DeploymentMode(name="active"),
        alert=alert,
        adapter=adapter,
        shadow_store=None,
        idempotency_key="k",
    )
    assert out["delivered"] is True
    assert len(adapter.calls) == 1


def test_forbidden_adapter_raises() -> None:
    with pytest.raises(RuntimeError):
        ForbiddenInterruptiveAdapter().deliver_page({})
