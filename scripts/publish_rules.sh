#!/usr/bin/env bash
# Publish rule bundles to the Kafka `rules` topic.
# Default: versions from streaming/rule-registry/activation.json (not lexical "latest").
# Requires CURIE-007 parity gate unless SKIP_PARITY=1 (emergency only).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLES_DIR="$ROOT/streaming/rule-registry/bundles"
ACTIVATION="$ROOT/streaming/rule-registry/activation.json"

if [[ "${SKIP_PARITY:-}" != "1" ]]; then
  echo "Running cross-runtime parity gate (CURIE-007)…"
  (cd "$ROOT" && python -m eval.parity.gate)
else
  echo "WARNING: SKIP_PARITY=1 — publishing without parity gate" >&2
fi

echo "Validating activation has installed scorers (CURIE-011)…"
(cd "$ROOT" && python -c "from eval.indicators.registry import validate_activation; validate_activation(); print('activation ok')")

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
  # Inject content_hash so Flink alerts carry provenance
  local payload
  payload="$(python3 - "$bundle" <<'PY'
import hashlib, json, sys
path = sys.argv[1]
data = json.loads(open(path).read())
data.pop("content_hash", None)
canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
data["content_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
print(json.dumps(data, separators=(",", ":"), ensure_ascii=True))
PY
)"
  printf '%s' "$payload" | docker exec -i curie-kafka /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server localhost:9092 \
    --topic rules
  echo "Published $(basename "$bundle") → topic rules"
}

if [[ $# -gt 0 ]]; then
  for b in "$@"; do
    publish_one "$b"
  done
else
  while IFS= read -r b; do
    [[ -n "$b" ]] || continue
    publish_one "$b"
  done < <(python3 - "$ACTIVATION" "$BUNDLES_DIR" <<'PY'
import json, sys
from pathlib import Path
act = json.loads(Path(sys.argv[1]).read_text())["active"]
root = Path(sys.argv[2])
for bid, ver in sorted(act.items()):
    path = root / f"{bid}.v{ver}.json"
    if not path.exists():
        raise SystemExit(f"Active bundle missing: {path}")
    print(path)
PY
)
fi
