"""Runtime kill switches and operator observability (CURIE-018)."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.indicators.registry import list_indicators, validate_activation

DEFAULT_KILL_SWITCH_PATH = Path("data/curie_kill_switches.json")


@dataclass
class KillSwitches:
    """Runtime gates — flip without redeploying code."""

    alerts_ingest: bool = True
    interruptive_lane: bool = True
    passive_lane: bool = True
    explain_lane: bool = True
    extract_lane: bool = True
    # indicator → enabled
    indicators: dict[str, bool] = field(default_factory=dict)
    # bundle_id → enabled
    bundles: dict[str, bool] = field(default_factory=dict)
    updated_at: str | None = None

    def indicator_enabled(self, indicator: str) -> bool:
        if not self.alerts_ingest:
            return False
        if indicator in self.indicators:
            return bool(self.indicators[indicator])
        return True

    def bundle_enabled(self, bundle_id: str) -> bool:
        if bundle_id in self.bundles:
            return bool(self.bundles[bundle_id])
        return True

    def routing_allowed(self, routing: str | None) -> bool:
        route = (routing or "").lower()
        if route == "interruptive":
            return self.interruptive_lane
        if route == "passive":
            return self.passive_lane
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "alerts_ingest": self.alerts_ingest,
            "interruptive_lane": self.interruptive_lane,
            "passive_lane": self.passive_lane,
            "explain_lane": self.explain_lane,
            "extract_lane": self.extract_lane,
            "indicators": dict(self.indicators),
            "bundles": dict(self.bundles),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KillSwitches:
        return cls(
            alerts_ingest=bool(data.get("alerts_ingest", True)),
            interruptive_lane=bool(data.get("interruptive_lane", True)),
            passive_lane=bool(data.get("passive_lane", True)),
            explain_lane=bool(data.get("explain_lane", True)),
            extract_lane=bool(data.get("extract_lane", True)),
            indicators={str(k): bool(v) for k, v in (data.get("indicators") or {}).items()},
            bundles={str(k): bool(v) for k, v in (data.get("bundles") or {}).items()},
            updated_at=data.get("updated_at"),
        )


class KillSwitchStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(
            os.getenv("CURIE_KILL_SWITCH_PATH", str(DEFAULT_KILL_SWITCH_PATH))
        )
        self._lock = threading.RLock()
        self._switches = KillSwitches()
        self.reload()

    def reload(self) -> KillSwitches:
        with self._lock:
            if self.path.is_file():
                data = json.loads(self.path.read_text())
                self._switches = KillSwitches.from_dict(data)
            return self._switches

    def get(self) -> KillSwitches:
        with self._lock:
            return KillSwitches.from_dict(self._switches.to_dict())

    def update(self, patch: dict[str, Any]) -> KillSwitches:
        with self._lock:
            current = self._switches.to_dict()
            for key in (
                "alerts_ingest",
                "interruptive_lane",
                "passive_lane",
                "explain_lane",
                "extract_lane",
            ):
                if key in patch:
                    current[key] = bool(patch[key])
            if "indicators" in patch and isinstance(patch["indicators"], dict):
                merged = dict(current.get("indicators") or {})
                merged.update({str(k): bool(v) for k, v in patch["indicators"].items()})
                current["indicators"] = merged
            if "bundles" in patch and isinstance(patch["bundles"], dict):
                merged = dict(current.get("bundles") or {})
                merged.update({str(k): bool(v) for k, v in patch["bundles"].items()})
                current["bundles"] = merged
            current["updated_at"] = datetime.now(UTC).isoformat()
            self._switches = KillSwitches.from_dict(current)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._switches.to_dict(), indent=2) + "\n")
            return self.get()


@dataclass
class OpsCounters:
    """In-process counters for operator dashboards (reset on process restart)."""

    started_at: float = field(default_factory=time.time)
    alerts_ingested: int = 0
    alerts_suppressed_kill_switch: int = 0
    kafka_lag_seconds: float | None = None
    flink_watermark_lag_seconds: float | None = None
    dlq_depth: int | None = None
    last_alert_at: float | None = None

    def note_ingest(self, *, suppressed: bool = False) -> None:
        if suppressed:
            self.alerts_suppressed_kill_switch += 1
        else:
            self.alerts_ingested += 1
            self.last_alert_at = time.time()

    def set_lag(
        self,
        *,
        kafka_lag_seconds: float | None = None,
        flink_watermark_lag_seconds: float | None = None,
        dlq_depth: int | None = None,
    ) -> None:
        if kafka_lag_seconds is not None:
            self.kafka_lag_seconds = kafka_lag_seconds
        if flink_watermark_lag_seconds is not None:
            self.flink_watermark_lag_seconds = flink_watermark_lag_seconds
        if dlq_depth is not None:
            self.dlq_depth = dlq_depth


KILL_SWITCHES = KillSwitchStore()
OPS_COUNTERS = OpsCounters()


def active_bundles_snapshot() -> dict[str, Any]:
    try:
        report = validate_activation()
        return {
            "ok": bool(report.get("ok", True)),
            "active": report.get("active") or {},
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "active": {}}


def alert_rate_per_hour(store: Any) -> float | None:
    metrics = store.metrics()
    uptime_h = max((time.time() - OPS_COUNTERS.started_at) / 3600.0, 1e-6)
    # Prefer process counters when present; else approximate from store size / uptime.
    if OPS_COUNTERS.alerts_ingested:
        return OPS_COUNTERS.alerts_ingested / uptime_h
    return metrics.total_alerts / uptime_h


def missing_data_rate(store: Any) -> float | None:
    alerts = store.list(limit=1000, offset=0)
    if not alerts:
        return None
    partial = sum(1 for a in alerts if a.completeness == "partial")
    return partial / len(alerts)


def build_ops_status(store: Any, security: Any) -> dict[str, Any]:
    bundles = active_bundles_snapshot()
    metrics = store.metrics()
    switches = KILL_SWITCHES.get()
    return {
        "service": "curie-api",
        "env": security.env,
        "tenant_id": security.tenant_id,
        "site_id": security.site_id,
        "tls_terminated": security.tls_terminated,
        "auth_required": security.auth_required,
        "active_bundles": bundles,
        "installed_indicators": [
            {"indicator": r["indicator"], "bundle_id": r.get("bundle_id"), "version": r.get("version")}  # noqa: E501
            for r in list_indicators(installed_only=True)
        ],
        "alert_metrics": {
            "total_alerts": metrics.total_alerts,
            "open_alerts": metrics.open_alerts,
            "acknowledged_alerts": metrics.acknowledged_alerts,
            "by_tier": metrics.by_tier,
            "by_routing": metrics.by_routing,
            "by_indicator": metrics.by_indicator,
            "alert_rate_per_hour": alert_rate_per_hour(store),
            "missing_data_rate": missing_data_rate(store),
        },
        "processing": {
            "kafka_lag_seconds": OPS_COUNTERS.kafka_lag_seconds,
            "flink_watermark_lag_seconds": OPS_COUNTERS.flink_watermark_lag_seconds,
            "dlq_depth": OPS_COUNTERS.dlq_depth,
            "alerts_ingested_process": OPS_COUNTERS.alerts_ingested,
            "alerts_suppressed_kill_switch": OPS_COUNTERS.alerts_suppressed_kill_switch,
        },
        "kill_switches": switches.to_dict(),
        "alarms": _alarms(metrics, switches),
    }


def _alarms(metrics: Any, switches: KillSwitches) -> list[dict[str, str]]:
    alarms: list[dict[str, str]] = []
    rate = alert_rate_per_hour_from_metrics(metrics)
    if rate is not None and rate > 500:
        alarms.append(
            {
                "severity": "warning",
                "code": "alert_volume_high",
                "message": f"Alert rate ~{rate:.0f}/hour exceeds prototype threshold 500",
            }
        )
    if not switches.alerts_ingest:
        alarms.append(
            {
                "severity": "critical",
                "code": "ingest_disabled",
                "message": "alerts_ingest kill switch is OFF",
            }
        )
    if not switches.interruptive_lane:
        alarms.append(
            {
                "severity": "warning",
                "code": "interruptive_disabled",
                "message": "interruptive_lane kill switch is OFF",
            }
        )
    if OPS_COUNTERS.dlq_depth is not None and OPS_COUNTERS.dlq_depth > 0:
        alarms.append(
            {
                "severity": "warning",
                "code": "dlq_nonempty",
                "message": f"DLQ depth={OPS_COUNTERS.dlq_depth}",
            }
        )
    return alarms


def alert_rate_per_hour_from_metrics(metrics: Any) -> float | None:
    uptime_h = max((time.time() - OPS_COUNTERS.started_at) / 3600.0, 1e-6)
    if OPS_COUNTERS.alerts_ingested:
        return OPS_COUNTERS.alerts_ingested / uptime_h
    return metrics.total_alerts / uptime_h
