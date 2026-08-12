#!/usr/bin/env bash
# Publish rule bundles to the Kafka `rules` topic (latest sepsis + AKI by default).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLES_DIR="$ROOT/streaming/rule-registry/bundles"

if ! docker ps --format '{{.Names}}' | grep -q '^curie-kafka$'; then
  echo "curie-kafka container not running. Start with: make up" >&2
  exit 1
fi

publish_one() {
  local bundle="$1"
  if [[ ! -f "$bundle" ]]; then
    echo "Rule bundle not found: $bundle" >&2
    exit 1
  fi
  tr -d '\n' < "$bundle" | docker exec -i curie-kafka /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server localhost:9092 \
    --topic rules
  echo "Published $(basename "$bundle") → topic rules"
}

if [[ $# -gt 0 ]]; then
  for b in "$@"; do
    publish_one "$b"
  done
else
  publish_one "$BUNDLES_DIR/sepsis-sofa.v0.2.0.json"
  publish_one "$BUNDLES_DIR/aki-kdigo.v0.2.0.json"
fi
