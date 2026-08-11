"""Replay Synthea FHIR files onto Kafka with controlled event-time ordering.

Usage:
  python -m ingestion.adapters.synthea.replay_producer --fhir-dir data/synthea/fhir --dry-run
  python -m ingestion.adapters.synthea.replay_producer --fhir-dir data/synthea/fhir
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import orjson

from ingestion.adapters.synthea.bundle_loader import load_envelopes_from_dir, topic_for_resource


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay Synthea FHIR → Kafka")
    parser.add_argument(
        "--fhir-dir",
        type=Path,
        default=Path("data/synthea/fhir"),
        help="Directory of Synthea FHIR JSON bundles",
    )
    parser.add_argument(
        "--bootstrap",
        default="localhost:9092",
        help="Kafka bootstrap servers (host producers)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print envelope counts without producing",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max envelopes to emit (0 = all)",
    )
    args = parser.parse_args(argv)

    if not args.fhir_dir.is_dir():
        print(f"FHIR dir not found: {args.fhir_dir}", file=sys.stderr)
        print("Run: make synthea N=10", file=sys.stderr)
        return 1

    ingest_time = datetime.now(UTC)
    envelopes = load_envelopes_from_dir(args.fhir_dir, ingest_time=ingest_time)
    if args.limit > 0:
        envelopes = envelopes[: args.limit]

    by_topic: dict[str, int] = {}
    for env in envelopes:
        topic = topic_for_resource(env.resource_type)
        by_topic[topic] = by_topic.get(topic, 0) + 1

    print(f"Loaded {len(envelopes)} envelopes from {args.fhir_dir}")
    for topic, count in sorted(by_topic.items()):
        print(f"  {topic}: {count}")

    if args.dry_run:
        if envelopes:
            sample = envelopes[0].model_dump(mode="json")
            print("Sample envelope keys:", sorted(sample.keys()))
        return 0

    try:
        from confluent_kafka import Producer
    except ImportError:
        print("Install kafka extras: pip install -e '.[kafka]'", file=sys.stderr)
        return 1

    producer = Producer({"bootstrap.servers": args.bootstrap})
    delivered = 0

    def _ack(err, _msg) -> None:  # noqa: ANN001
        nonlocal delivered
        if err is not None:
            print(f"delivery failed: {err}", file=sys.stderr)
        else:
            delivered += 1

    for env in envelopes:
        topic = topic_for_resource(env.resource_type)
        payload = orjson.dumps(env.model_dump(mode="json"))
        producer.produce(
            topic,
            key=env.patient_id.encode(),
            value=payload,
            on_delivery=_ack,
        )
        producer.poll(0)

    producer.flush()
    print(f"Produced {delivered}/{len(envelopes)} messages to {args.bootstrap}")
    return 0 if delivered == len(envelopes) else 2


if __name__ == "__main__":
    raise SystemExit(main())
