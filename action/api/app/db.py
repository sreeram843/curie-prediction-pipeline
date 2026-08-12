"""SQLite schema migrations for the durable alert store (CURIE-017)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      applied_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS alerts (
      alert_id TEXT PRIMARY KEY,
      patient_id TEXT NOT NULL,
      encounter_id TEXT,
      indicator TEXT NOT NULL,
      event_time TEXT NOT NULL,
      tier TEXT NOT NULL,
      acknowledged INTEGER NOT NULL DEFAULT 0,
      acknowledged_at TEXT,
      acknowledge_note TEXT,
      resolution_state TEXT NOT NULL DEFAULT 'open',
      rule_bundle_id TEXT,
      rule_version TEXT,
      payload_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_alerts_patient_event
      ON alerts(patient_id, event_time DESC);
    CREATE INDEX IF NOT EXISTS idx_alerts_event
      ON alerts(event_time DESC);
    CREATE INDEX IF NOT EXISTS idx_alerts_ack
      ON alerts(acknowledged, event_time DESC);

    CREATE TABLE IF NOT EXISTS episodes (
      episode_id TEXT PRIMARY KEY,
      patient_id TEXT NOT NULL,
      encounter_id TEXT,
      status TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      payload_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_episodes_patient
      ON episodes(patient_id, updated_at DESC);

    CREATE TABLE IF NOT EXISTS rule_versions (
      bundle_id TEXT NOT NULL,
      version TEXT NOT NULL,
      content_hash TEXT,
      activated_at TEXT NOT NULL,
      notes TEXT,
      PRIMARY KEY (bundle_id, version)
    );

    CREATE TABLE IF NOT EXISTS audit_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      at TEXT NOT NULL,
      action TEXT NOT NULL,
      entity_type TEXT NOT NULL,
      entity_id TEXT NOT NULL,
      detail_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at DESC);

    CREATE TABLE IF NOT EXISTS kafka_dedupe (
      idempotency_key TEXT PRIMARY KEY,
      alert_id TEXT NOT NULL,
      processed_at TEXT NOT NULL
    );
    """,
}


def connect(path: str | Path) -> sqlite3.Connection:
    """Open SQLite with foreign keys and row factory."""
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if row is None:
        return 0
    ver = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations").fetchone()
    return int(ver["v"]) if ver else 0


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations. Returns resulting schema version."""
    from datetime import UTC, datetime

    applied = current_version(conn)
    for version in sorted(MIGRATIONS):
        if version <= applied:
            continue
        conn.executescript(MIGRATIONS[version])
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, datetime.now(UTC).isoformat()),
        )
        conn.commit()
        applied = version
    return applied
