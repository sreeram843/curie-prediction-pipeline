"""Reproducible run manifests for indexed MIMIC/eICU replays (Phase C2/D2).

Every reported number traces to one manifest: dataset/version + extract date,
source-file hashes, index hash, code revision, protocol ID, rule-bundle IDs +
content hashes, cohort/event counts, timestamp failures, missingness, runtime
and peak-storage info, and the command-line configuration.

``content_hash`` covers only deterministic content: repeated runs with the same
inputs, config, and code revision produce the same hash. Volatile fields
(wall-clock runtime, peak RSS, built_at, raw argv, absolute local paths) are
excluded from the hash but recorded in the manifest body.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.mimic_study.indexing import sha256_hex
from eval.mimic_study.protocol import load_protocol

MANIFEST_SCHEMA_VERSION = "1.0.0"

# Fields excluded from content_hash (volatile or machine-local).
_VOLATILE_KEYS = {
    "built_at",
    "runtime",
    "cli",
    "manifest_path",
    "storage",  # index bytes vary with zstd/parquet writer versions
}


def _canonical(payload: Any) -> str:
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _code_revision() -> dict[str, str]:
    import subprocess

    repo_root = Path(__file__).resolve().parents[2]
    commit = "unknown"
    branch = "unknown"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
            cwd=repo_root,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True,
            check=True, cwd=repo_root,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        pass
    module_paths = [
        Path(__file__).resolve(),
        Path(__file__).resolve().parent / "indexing.py",
        Path(__file__).resolve().parent / "index_replay.py",
    ]
    return {
        "git_commit": commit,
        "git_branch": branch,
        "module_sha256": {
            path.name: sha256_hex(path.read_bytes()) for path in module_paths if path.is_file()
        },
    }


def active_rule_bundles() -> dict[str, dict[str, str]]:
    """Active rule bundles → {version, content_hash} (same canonicalization as publish)."""
    from eval.indicators.registry import content_hash, load_activation, load_rule_bundle

    bundles: dict[str, dict[str, str]] = {}
    for bundle_id in sorted(load_activation()):
        bundle = load_rule_bundle(bundle_id)
        payload = dict(bundle)
        payload.pop("content_hash", None)
        bundles[bundle_id] = {
            "version": bundle["version"],
            "content_hash": content_hash(payload),
        }
    return bundles


def _labels_pin_record() -> dict[str, Any]:
    """Record the pinned mimic-code label revision (separate from feature replay)."""
    from eval.mimic_study.labels.pins import DEFAULT_PIN_PATH, load_pin

    path = DEFAULT_PIN_PATH
    if not path.is_file():
        return {"status": "not_pinned", "pin_path": str(path)}
    pin = load_pin()
    return {"status": "pinned", "pin": pin}


def build_run_manifest(
    *,
    dataset: str,
    index_dir: Path,
    index_meta: dict[str, Any],
    cohort: dict[str, Any],
    counts: dict[str, Any],
    timestamp_failures: dict[str, int],
    missingness: dict[str, Any],
    runtime_s: float,
    peak_rss_bytes: int,
    storage_bytes: int,
    cli_argv: list[str],
    protocol_id: str | None = None,
    labels_path: Path | None = None,
) -> dict[str, Any]:
    protocol_id = protocol_id or load_protocol()["protocol_id"]
    labels = _labels_pin_record()
    if labels_path is not None:
        from eval.mimic_study.labels.materialize import load_label_artifact

        artifact = load_label_artifact(labels_path)
        labels["artifact"] = {
            "schema_version": artifact["schema_version"],
            "protocol_id": artifact["protocol_id"],
            "content_hash": artifact["content_hash"],
            "stays": len(artifact["stays"]),
        }
    body: dict[str, Any] = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        "dataset": dict(index_meta.get("dataset") or {}),
        "source_files": {
            src: {k: v for k, v in info.items() if k in {"sha256", "size"}}
            for src, info in sorted((index_meta.get("source_files") or {}).items())
        },
        "index": {
            "index_schema_version": index_meta.get("index_schema_version"),
            "builder_version": index_meta.get("builder_version"),
            "index_hash": index_meta.get("index_hash"),
            "build_config": index_meta.get("config"),
        },
        "code": _code_revision(),
        "protocol_id": protocol_id,
        "rule_bundles": active_rule_bundles(),
        "labels": labels,
        "cohort": cohort,
        "counts": counts,
        "timestamp_failures": dict(sorted(timestamp_failures.items())),
        "missingness": missingness,
        "runtime": {
            "replay_seconds": round(runtime_s, 3),
            "peak_rss_bytes": int(peak_rss_bytes),
        },
        "storage": {"index_bytes": int(storage_bytes)},
        "cli": {
            "argv": list(cli_argv),
            "dataset": dataset,
        },
    }
    deterministic = {
        k: v
        for k, v in body.items()
        if k not in _VOLATILE_KEYS and k != "index_dir" and k != "source_root"
    }
    body["content_hash"] = sha256_hex(_canonical(deterministic).encode("utf-8"))
    body["run_id"] = body["content_hash"][:16]
    return body
