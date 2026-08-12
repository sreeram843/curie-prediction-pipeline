"""Store contract + tenant isolation helpers (CURIE-037)."""

from __future__ import annotations

from typing import Any, Protocol

from action.api.app.models import AlertRecord


class AlertStoreContract(Protocol):
    def upsert(self, alert: AlertRecord) -> AlertRecord: ...

    def get(self, alert_id: str) -> AlertRecord | None: ...

    def list(
        self,
        *,
        include_acknowledged: bool = True,
        patient_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AlertRecord]: ...

    def acknowledge(self, alert_id: str, note: str | None = None) -> AlertRecord | None: ...


def assert_tenant_match(
    *,
    record_tenant: str | None,
    caller_tenant: str,
    action: str,
) -> None:
    """Fail closed on cross-tenant access."""
    if record_tenant is None:
        raise PermissionError(f"{action} denied: record missing tenant_id")
    if record_tenant != caller_tenant:
        raise PermissionError(
            f"{action} denied: cross-tenant access "
            f"(caller={caller_tenant!r} record={record_tenant!r})"
        )


def stamp_tenant(alert: AlertRecord, *, tenant_id: str, site_id: str) -> AlertRecord:
    data = alert.model_dump()
    data["tenant_id"] = tenant_id
    data["site_id"] = site_id
    # AlertRecord may not declare fields yet — keep extras via model_validate if configured.
    try:
        return AlertRecord.model_validate(data)
    except Exception:
        # Fallback: attach as private attrs for contract tests using dict payloads.
        alert.__dict__["tenant_id"] = tenant_id
        alert.__dict__["site_id"] = site_id
        return alert


def filter_rows_for_tenant(
    rows: list[dict[str, Any]], *, tenant_id: str
) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if row.get("tenant_id") != tenant_id:
            continue
        out.append(row)
    return out
