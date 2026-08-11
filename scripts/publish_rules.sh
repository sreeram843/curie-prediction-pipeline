#!/usr/bin/env bash
# Publish the sepsis-sofa rule bundle to the Kafka `rules` topic.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE="${1:-$ROOT/streaming/rule-registry/bundles/sepsis-sofa.v0.1.0.json}"

if [[ ! -f "$BUNDLE" ]]; then
  echo "Rule bundle not found: $BUNDLE" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q '^curie-kafka$'; then
  echo "curie-kafka container not running. Start with: make up" >&2
  exit 1
fi

tr -d '\n' < "$BUNDLE" | docker exec -i curie-kafka /opt/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic rules

echo "Published $(basename "$BUNDLE") → topic rules"
