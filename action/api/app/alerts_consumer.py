"""Optional Kafka consumer: alerts topic → durable store (manual commit)."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from typing import Any

from action.api.app.models import AlertRecord, alert_from_dict
from action.api.app.store import STORE

logger = logging.getLogger(__name__)

_consumer_thread: threading.Thread | None = None
_stop = threading.Event()


def _parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def kafka_alert_to_record(payload: dict[str, Any]) -> AlertRecord | None:
    """Map Flink AlertEvent JSON into AlertRecord (best-effort)."""
    alert_id = payload.get("alert_id")
    patient_id = payload.get("patient_id")
    event_time = _parse_iso(payload.get("event_time"))
    if not alert_id or not patient_id or event_time is None:
        return None
    data = dict(payload)
    data["event_time"] = event_time
    if data.get("ingest_time"):
        data["ingest_time"] = _parse_iso(data["ingest_time"])
    if not data.get("routing"):
        data.pop("routing", None)
    try:
        return alert_from_dict(data)
    except Exception:
        logger.exception("Failed to parse alert %s", alert_id)
        return None


def _idempotency_key(msg: Any, payload: dict[str, Any], record: AlertRecord) -> str:
    """Stable key for at-least-once Kafka delivery dedupe."""
    explicit = payload.get("idempotency_key") or payload.get("alert_id")
    topic = msg.topic() if hasattr(msg, "topic") else "alerts"
    partition = msg.partition() if hasattr(msg, "partition") else 0
    offset = msg.offset() if hasattr(msg, "offset") else None
    if offset is not None:
        return f"{topic}:{partition}:{offset}"
    return str(explicit or record.alert_id)


def _loop(bootstrap: str, group_id: str, clear_demo: bool) -> None:
    try:
        from confluent_kafka import Consumer, KafkaException
    except ImportError:
        logger.warning("confluent-kafka not installed; alerts consumer disabled")
        return

    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            # CURIE-017: commit only after durable upsert succeeds.
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(["alerts"])
    logger.info("Alerts consumer started bootstrap=%s group=%s", bootstrap, group_id)
    cleared = False
    try:
        while not _stop.is_set():
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.warning("Kafka error: %s", msg.error())
                continue
            try:
                payload = json.loads(msg.value().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("Skipping non-JSON alert message")
                # Poison pill: commit to avoid infinite retry loops on bad payload.
                consumer.commit(message=msg, asynchronous=False)
                continue
            record = kafka_alert_to_record(payload)
            if record is None:
                consumer.commit(message=msg, asynchronous=False)
                continue
            if clear_demo and not cleared:
                STORE.clear()
                cleared = True
                logger.info("Cleared demo alerts before first live upsert")
            key = _idempotency_key(msg, payload, record)
            try:
                STORE.ingest_kafka(record, idempotency_key=key)
            except Exception:
                logger.exception(
                    "Durable upsert failed for %s; not committing offset",
                    record.alert_id,
                )
                continue
            consumer.commit(message=msg, asynchronous=False)
    except KafkaException:
        logger.exception("Kafka consumer failed")
    finally:
        consumer.close()
        logger.info("Alerts consumer stopped")


def start_alerts_consumer_if_configured() -> None:
    """Start background consumer when CURIE_KAFKA_ALERTS_CONSUMER=true."""
    global _consumer_thread
    enabled = os.getenv("CURIE_KAFKA_ALERTS_CONSUMER", "").lower() in {"1", "true", "yes"}
    if not enabled:
        return
    if _consumer_thread and _consumer_thread.is_alive():
        return
    bootstrap = os.getenv(
        "KAFKA_BOOTSTRAP", os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    )
    group_id = os.getenv("CURIE_KAFKA_ALERTS_GROUP", "curie-api-alerts-v1")
    clear_demo = os.getenv("CURIE_CLEAR_DEMO_ON_LIVE", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    _stop.clear()
    _consumer_thread = threading.Thread(
        target=_loop,
        args=(bootstrap, group_id, clear_demo),
        name="curie-alerts-consumer",
        daemon=True,
    )
    _consumer_thread.start()


def stop_alerts_consumer() -> None:
    _stop.set()
