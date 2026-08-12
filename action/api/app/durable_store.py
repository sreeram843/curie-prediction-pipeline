"""SQLite-backed durable alert / episode store (CURIE-017)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any

from action.api.app.db import connect, migrate
from action.api.app.models import AlertRecord, MetricsSummary
from eval.episodes.arbiter import EpisodeArbiter, EpisodeConfig
from eval.episodes.models import Episode


class DurableAlertStore:
    """Persistent alerts, episodes, rule versions, audit, and Kafka dedupe."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        arbiter: EpisodeArbiter | None = None,
        retention_days: int | None = None,
    ) -> None:
        self.db_path = str(db_path)
        self._lock = RLock()
        self.arbiter = arbiter or EpisodeArbiter(EpisodeConfig())
        self.retention_days = retention_days
        self._conn = connect(self.db_path)
        migrate(self._conn)
        self._rebuild_arbiter_from_db()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _audit(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO audit_log(at, action, entity_type, entity_id, detail_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(),
                action,
                entity_type,
                entity_id,
                json.dumps(detail or {}, sort_keys=True),
            ),
        )

    def _rebuild_arbiter_from_db(self) -> None:
        self.arbiter = EpisodeArbiter(EpisodeConfig())
        rows = self._conn.execute(
            "SELECT payload_json FROM alerts ORDER BY event_time ASC, alert_id ASC"
        ).fetchall()
        for row in rows:
            alert = AlertRecord.model_validate_json(row["payload_json"])
            self.arbiter.ingest(alert)
        self._persist_episodes()

    def _persist_episodes(self) -> None:
        self._conn.execute("DELETE FROM episodes")
        for ep in self.arbiter.list_all():
            self._conn.execute(
                """
                INSERT INTO episodes(
                  episode_id, patient_id, encounter_id, status, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ep.episode_id,
                    ep.patient_id,
                    ep.encounter_id,
                    ep.status.value if hasattr(ep.status, "value") else str(ep.status),
                    ep.updated_at.isoformat(),
                    json.dumps(ep.model_dump(mode="json"), sort_keys=True),
                ),
            )

    def _write_alert(self, alert: AlertRecord, *, action: str) -> None:
        now = datetime.now(UTC).isoformat()
        payload = alert.model_dump_json()
        self._conn.execute(
            """
            INSERT INTO alerts(
              alert_id, patient_id, encounter_id, indicator, event_time, tier,
              acknowledged, acknowledged_at, acknowledge_note, resolution_state,
              rule_bundle_id, rule_version, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(alert_id) DO UPDATE SET
              patient_id=excluded.patient_id,
              encounter_id=excluded.encounter_id,
              indicator=excluded.indicator,
              event_time=excluded.event_time,
              tier=excluded.tier,
              acknowledged=excluded.acknowledged,
              acknowledged_at=excluded.acknowledged_at,
              acknowledge_note=excluded.acknowledge_note,
              resolution_state=excluded.resolution_state,
              rule_bundle_id=excluded.rule_bundle_id,
              rule_version=excluded.rule_version,
              payload_json=excluded.payload_json,
              updated_at=excluded.updated_at
            """,
            (
                alert.alert_id,
                alert.patient_id,
                alert.encounter_id,
                alert.indicator,
                alert.event_time.isoformat(),
                alert.tier,
                1 if alert.acknowledged else 0,
                alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                alert.acknowledge_note,
                alert.resolution_state,
                alert.rule_bundle_id,
                alert.rule_version,
                payload,
                now,
                now,
            ),
        )
        self._audit(action, "alert", alert.alert_id, {"tier": alert.tier})

    def upsert(self, alert: AlertRecord) -> AlertRecord:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM alerts WHERE alert_id = ?",
                (alert.alert_id,),
            ).fetchone()
            if row:
                existing = AlertRecord.model_validate_json(row["payload_json"])
                if existing.acknowledged:
                    alert.acknowledged = True
                    alert.acknowledged_at = existing.acknowledged_at
                    alert.acknowledge_note = existing.acknowledge_note
                    alert.resolution_state = "acknowledged"
            self._write_alert(alert, action="upsert")
            self.arbiter.ingest(alert)
            self._persist_episodes()
            self._conn.commit()
            return alert

    def ingest_kafka(
        self,
        alert: AlertRecord,
        *,
        idempotency_key: str,
    ) -> tuple[AlertRecord, bool]:
        """Idempotent Kafka ingest inside one transaction.

        Returns (alert, inserted_new). Duplicate keys do not create a second alert
        or episode transition.
        """
        with self._lock:
            existing = self._conn.execute(
                "SELECT alert_id FROM kafka_dedupe WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                alert_row = self._conn.execute(
                    "SELECT payload_json FROM alerts WHERE alert_id = ?",
                    (existing["alert_id"],),
                ).fetchone()
                if alert_row:
                    return AlertRecord.model_validate_json(alert_row["payload_json"]), False
                return alert, False

            row = self._conn.execute(
                "SELECT payload_json FROM alerts WHERE alert_id = ?",
                (alert.alert_id,),
            ).fetchone()
            if row:
                existing_alert = AlertRecord.model_validate_json(row["payload_json"])
                if existing_alert.acknowledged:
                    alert.acknowledged = True
                    alert.acknowledged_at = existing_alert.acknowledged_at
                    alert.acknowledge_note = existing_alert.acknowledge_note
                    alert.resolution_state = "acknowledged"

            self._write_alert(alert, action="kafka_upsert")
            self._conn.execute(
                """
                INSERT INTO kafka_dedupe(idempotency_key, alert_id, processed_at)
                VALUES (?, ?, ?)
                """,
                (idempotency_key, alert.alert_id, datetime.now(UTC).isoformat()),
            )
            self.arbiter.ingest(alert)
            self._persist_episodes()
            if alert.rule_bundle_id and alert.rule_version:
                self.record_rule_version(
                    alert.rule_bundle_id,
                    alert.rule_version,
                    commit=False,
                )
            self._conn.commit()
            return alert, True

    def list(
        self,
        *,
        include_acknowledged: bool = True,
        patient_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AlertRecord]:
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
        clauses = ["1=1"]
        params: list[Any] = []
        if patient_id:
            clauses.append("patient_id = ?")
            params.append(patient_id)
        if not include_acknowledged:
            clauses.append("acknowledged = 0")
        sql = (
            f"SELECT payload_json FROM alerts WHERE {' AND '.join(clauses)} "
            "ORDER BY event_time DESC, alert_id DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [AlertRecord.model_validate_json(r["payload_json"]) for r in rows]

    def count(
        self,
        *,
        include_acknowledged: bool = True,
        patient_id: str | None = None,
    ) -> int:
        clauses = ["1=1"]
        params: list[Any] = []
        if patient_id:
            clauses.append("patient_id = ?")
            params.append(patient_id)
        if not include_acknowledged:
            clauses.append("acknowledged = 0")
        sql = f"SELECT COUNT(*) AS n FROM alerts WHERE {' AND '.join(clauses)}"
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return int(row["n"]) if row else 0

    def get(self, alert_id: str) -> AlertRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM alerts WHERE alert_id = ?",
                (alert_id,),
            ).fetchone()
        if row is None:
            return None
        return AlertRecord.model_validate_json(row["payload_json"])

    def acknowledge(self, alert_id: str, note: str | None = None) -> AlertRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM alerts WHERE alert_id = ?",
                (alert_id,),
            ).fetchone()
            if row is None:
                return None
            data = AlertRecord.model_validate_json(row["payload_json"]).model_dump()
            data.update(
                {
                    "acknowledged": True,
                    "acknowledged_at": datetime.now(UTC),
                    "acknowledge_note": note,
                    "resolution_state": "acknowledged",
                    "signal": None,
                }
            )
            updated = AlertRecord.model_validate(data)
            self._write_alert(updated, action="acknowledge")
            self._conn.commit()
            return updated

    def metrics(self) -> MetricsSummary:
        """Full-table metrics — never silently truncated at 10k."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT tier, payload_json FROM alerts"
            ).fetchall()
        by_tier: dict[str, int] = {}
        by_routing: dict[str, int] = {}
        by_indicator: dict[str, int] = {}
        ack = 0
        for row in rows:
            alert = AlertRecord.model_validate_json(row["payload_json"])
            by_tier[alert.tier] = by_tier.get(alert.tier, 0) + 1
            route = alert.routing or "unset"
            by_routing[route] = by_routing.get(route, 0) + 1
            by_indicator[alert.indicator] = by_indicator.get(alert.indicator, 0) + 1
            if alert.acknowledged:
                ack += 1
        total = len(rows)
        return MetricsSummary(
            total_alerts=total,
            open_alerts=total - ack,
            acknowledged_alerts=ack,
            by_tier=by_tier,
            by_routing=by_routing,
            by_indicator=by_indicator,
        )

    def attach_narrative(
        self,
        alert_id: str,
        *,
        status: str,
        narrative: str | None,
        claims: list[dict],
        quarantine_reason: str | None,
        model_name: str | None,
    ) -> AlertRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM alerts WHERE alert_id = ?",
                (alert_id,),
            ).fetchone()
            if row is None:
                return None
            alert = AlertRecord.model_validate_json(row["payload_json"])
            updated = alert.model_copy(
                update={
                    "narrative_status": status,
                    "narrative": narrative,
                    "narrative_claims": claims,
                    "quarantine_reason": quarantine_reason,
                    "grp_model_name": model_name,
                }
            )
            self._write_alert(updated, action="attach_narrative")
            self._conn.commit()
            return updated

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM alerts")
            self._conn.execute("DELETE FROM episodes")
            self._conn.execute("DELETE FROM kafka_dedupe")
            self._conn.execute("DELETE FROM audit_log")
            self.arbiter = EpisodeArbiter(EpisodeConfig())
            self._conn.commit()

    def list_episodes(self, *, patient_id: str | None = None, limit: int = 100):
        limit = max(1, min(int(limit), 1000))
        with self._lock:
            if patient_id:
                rows = self._conn.execute(
                    """
                    SELECT payload_json FROM episodes
                    WHERE patient_id = ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (patient_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT payload_json FROM episodes ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [Episode.model_validate_json(r["payload_json"]) for r in rows]

    def get_episode(self, episode_id: str) -> Episode | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM episodes WHERE episode_id = ?",
                (episode_id,),
            ).fetchone()
        if row is None:
            # Fall back to in-memory arbiter (ids may differ after rebuild)
            return self.arbiter.get(episode_id)
        return Episode.model_validate_json(row["payload_json"])

    def attach_episode_narrative(
        self,
        episode_id: str,
        *,
        status: str,
        narrative: str | None,
        claims: list[dict],
        quarantine_reason: str | None,
        model_name: str | None,
        prompt_version: str | None = None,
        snapshot_hash: str | None = None,
    ) -> Episode | None:
        with self._lock:
            episode = self.get_episode(episode_id)
            if episode is None:
                return None
            before = (
                episode.status,
                episode.page_count,
                episode.dominant_signal_type,
                episode.dominant_severity,
            )
            updated = episode.model_copy(
                update={
                    "narrative_status": status,
                    "narrative": narrative,
                    "narrative_claims": claims,
                    "quarantine_reason": quarantine_reason,
                    "grp_model_name": model_name,
                    "prompt_version": prompt_version,
                    "narrative_snapshot_hash": snapshot_hash,
                }
            )
            assert (
                updated.status,
                updated.page_count,
                updated.dominant_signal_type,
                updated.dominant_severity,
            ) == before
            self.arbiter._episodes[episode_id] = updated  # noqa: SLF001
            self._persist_episodes()
            self._audit(
                "attach_episode_narrative",
                "episode",
                episode_id,
                {"status": status, "snapshot_hash": snapshot_hash},
            )
            self._conn.commit()
            return updated

    def record_rule_version(
        self,
        bundle_id: str,
        version: str,
        *,
        content_hash: str | None = None,
        notes: str | None = None,
        commit: bool = True,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO rule_versions(bundle_id, version, content_hash, activated_at, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(bundle_id, version) DO UPDATE SET
                  content_hash=COALESCE(excluded.content_hash, rule_versions.content_hash),
                  notes=COALESCE(excluded.notes, rule_versions.notes)
                """,
                (
                    bundle_id,
                    version,
                    content_hash,
                    datetime.now(UTC).isoformat(),
                    notes,
                ),
            )
            if commit:
                self._conn.commit()

    def apply_retention(self, *, now: datetime | None = None) -> int:
        """Delete alerts older than retention_days. Returns deleted count."""
        if not self.retention_days or self.retention_days <= 0:
            return 0
        cutoff = (now or datetime.now(UTC)) - timedelta(days=self.retention_days)
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM alerts WHERE event_time < ?",
                (cutoff.isoformat(),),
            )
            deleted = cur.rowcount
            if deleted:
                self._rebuild_arbiter_from_db()
                self._audit(
                    "retention",
                    "alerts",
                    "*",
                    {"deleted": deleted, "cutoff": cutoff.isoformat()},
                )
            self._conn.commit()
        return deleted
