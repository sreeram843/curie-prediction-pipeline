"""Tests for reproducible run manifests (Phase C2/D2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.mimic_study.manifest import (
    MANIFEST_SCHEMA_VERSION,
    active_rule_bundles,
    build_run_manifest,
)


def _fake_index_meta() -> dict[str, Any]:
    return {
        "index_schema_version": "1.0.0",
        "builder_version": "0.1.0",
        "dataset": {"name": "mimic-iv", "version": "3.1", "extract_date": "2026-09-05"},
        "source_files": {
            "hosp/labevents.csv.gz": {"sha256": "a" * 64, "size": 123},
            "icu/chartevents.csv.gz": {"sha256": "b" * 64, "size": 456},
        },
        "config": {"dataset": "mimic", "limit": 0, "items": "mapped"},
        "index_hash": "c" * 64,
    }


def _call(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "dataset": "mimic",
        "index_dir": Path("/tmp/idx"),
        "index_meta": _fake_index_meta(),
        "cohort": {"selection": {"mode": "bounded"}, "stays_replayed": 5},
        "counts": {"events_replayed": 120, "events_by_family": {"lab": 20}},
        "timestamp_failures": {"hosp/labevents.csv.gz": 1},
        "missingness": {"stays_scored": 5, "completeness": {"complete": 5}},
        "runtime_s": 1.234,
        "peak_rss_bytes": 99_000_000,
        "storage_bytes": 400_000,
        "cli_argv": ["python", "-m", "eval.mimic_study.index_replay", "run"],
    }
    params.update(overrides)
    return build_run_manifest(**params)


def test_manifest_schema_and_sections() -> None:
    manifest = _call()
    assert manifest["manifest_schema_version"] == MANIFEST_SCHEMA_VERSION
    for key in (
        "built_at",
        "dataset",
        "source_files",
        "index",
        "code",
        "protocol_id",
        "rule_bundles",
        "labels",
        "cohort",
        "counts",
        "timestamp_failures",
        "missingness",
        "runtime",
        "storage",
        "cli",
        "content_hash",
        "run_id",
    ):
        assert key in manifest, key
    assert len(manifest["run_id"]) == 16


def test_content_hash_excludes_volatile_fields() -> None:
    base = _call()
    changed = _call(runtime_s=999.0, peak_rss_bytes=1)
    assert base["content_hash"] == changed["content_hash"]
    for key in ("built_at", "runtime", "cli", "storage"):
        assert key in base  # recorded but excluded from the hash


def test_content_hash_sensitive_to_deterministic_fields() -> None:
    base = _call()
    meta = _fake_index_meta()
    meta["index_hash"] = "d" * 64
    changed = _call(index_meta=meta)
    assert base["content_hash"] != changed["content_hash"]


def test_rule_bundle_hashes_match_registry_canonicalization() -> None:
    from eval.indicators.registry import content_hash, load_rule_bundle

    bundles = active_rule_bundles()
    assert "sepsis-sofa" in bundles
    for bundle_id, info in bundles.items():
        payload = dict(load_rule_bundle(bundle_id))
        payload.pop("content_hash", None)
        assert info["content_hash"] == content_hash(payload)
        assert info["version"]


def test_manifest_is_json_serializable() -> None:
    manifest = _call()
    json.dumps(manifest, sort_keys=True, default=str)


def test_labels_pin_status_not_pinned() -> None:
    manifest = _call()
    assert manifest["labels"]["status"] == "not_pinned"
