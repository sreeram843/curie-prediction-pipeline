"""Build deterministic, pinned Stage B label artifacts from SQL exports.

The SQL itself is intentionally run outside this package by the data custodian.
This module only normalizes exported rows, joins them to the cohort, and records
the provenance needed to reproduce a study run. It never queries a database or
places labels on the alert path.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from eval.mimic_study.indexing import canonical_json_bytes, sha256_hex
from eval.mimic_study.labels import LABELS_SCHEMA_VERSION
from eval.mimic_study.labels.pins import validate_pin

LABEL_ARTIFACT_TYPE = "mimic_stage_b_labels"


class LabelMaterializationError(ValueError):
    """Invalid or incomplete exported label inputs."""


def _timestamp(raw: Any) -> str | None:
    if raw is None or str(raw).strip() == "":
        return None
    value = str(raw).strip().replace(" ", "T", 1)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LabelMaterializationError(f"invalid label timestamp: {raw!r}") from exc
    return parsed.isoformat().replace("+00:00", "Z")


def _truthy(raw: Any) -> bool:
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y"}


def _stay_id(row: dict[str, Any]) -> str:
    value = str(row.get("stay_id") or row.get("icustay_id") or "").strip()
    if not value:
        raise LabelMaterializationError("label row is missing stay_id/icustay_id")
    return value


def _first(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _base_rows(stay_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for raw in stay_ids:
        stay_id = str(raw).strip()
        if stay_id:
            rows.setdefault(stay_id, {"stay_id": stay_id})
    return rows


def build_label_artifact(
    *,
    cohort_stay_ids: Iterable[str],
    sepsis_rows: Iterable[dict[str, Any]],
    kdigo_rows: Iterable[dict[str, Any]],
    protocol_id: str,
    dataset_pin: dict[str, Any],
    source_pin: dict[str, Any],
) -> dict[str, Any]:
    """Materialize one deterministic label row per cohort stay.

    A stay absent from an export remains ``None`` (unknown), rather than being
    silently converted into a negative label. Positive Sepsis-3 rows use the
    earliest supplied completion time; KDIGO uses the maximum stage and its
    earliest stage-onset time.
    """
    if not protocol_id:
        raise LabelMaterializationError("protocol_id is required")
    if not isinstance(dataset_pin, dict) or not dataset_pin.get("name"):
        raise LabelMaterializationError("dataset_pin.name is required")
    if not dataset_pin.get("version") or not dataset_pin.get("extract_date"):
        raise LabelMaterializationError("dataset_pin.version and extract_date are required")
    try:
        validate_pin(source_pin)
    except ValueError as exc:
        raise LabelMaterializationError(f"invalid source pin: {exc}") from exc

    rows = _base_rows(cohort_stay_ids)
    sepsis_seen: set[str] = set()
    sepsis_times: dict[str, list[str]] = {}
    evidence: dict[str, list[str]] = {}
    for ordinal, raw in enumerate(sepsis_rows):
        row = dict(raw)
        stay_id = _stay_id(row)
        if stay_id not in rows:
            continue
        evidence.setdefault(stay_id, []).append(f"sepsis3:{ordinal}")
        if not _truthy(_first(row, ("sepsis3", "sepsis3_onset", "label"))):
            continue
        sepsis_seen.add(stay_id)
        onset = _timestamp(
            _first(row, ("availability_time", "sofa_time", "onset_time", "event_time"))
        )
        if onset is not None:
            sepsis_times.setdefault(stay_id, []).append(onset)

    kdigo_stages: dict[str, list[int]] = {}
    kdigo_times: dict[str, list[str]] = {}
    for ordinal, raw in enumerate(kdigo_rows):
        row = dict(raw)
        stay_id = _stay_id(row)
        if stay_id not in rows:
            continue
        evidence.setdefault(stay_id, []).append(f"kdigo:{ordinal}")
        raw_stage = _first(row, ("kdigo_stage", "aki_stage", "stage"))
        try:
            stage = int(float(raw_stage)) if raw_stage not in (None, "") else None
        except (TypeError, ValueError) as exc:
            raise LabelMaterializationError(
                f"invalid KDIGO stage for stay {stay_id}: {raw_stage!r}"
            ) from exc
        if stage is None:
            continue
        if stage < 0:
            raise LabelMaterializationError(f"negative KDIGO stage for stay {stay_id}")
        kdigo_stages.setdefault(stay_id, []).append(stage)
        onset = _timestamp(_first(row, ("availability_time", "event_time", "onset_time")))
        if onset is not None and stage >= 1:
            kdigo_times.setdefault(stay_id, []).append(onset)

    for stay_id, row in rows.items():
        sepsis_onsets = sorted(sepsis_times.get(stay_id, []))
        stages = kdigo_stages.get(stay_id, [])
        kdigo_onsets = sorted(kdigo_times.get(stay_id, []))
        row.update(
            {
                "sepsis3_onset": sepsis_onsets[0] if sepsis_onsets else None,
                "sepsis3_label_observed": stay_id in sepsis_seen,
                "aki_kdigo_max_stage": max(stages) if stages else None,
                "aki_kdigo_stage_ge_1": max(stages) >= 1 if stages else None,
                "aki_kdigo_onset": kdigo_onsets[0] if kdigo_onsets else None,
                "label_evidence_ids": sorted(evidence.get(stay_id, [])),
            }
        )

    artifact: dict[str, Any] = {
        "schema_version": LABELS_SCHEMA_VERSION,
        "artifact_type": LABEL_ARTIFACT_TYPE,
        "protocol_id": protocol_id,
        "dataset_pin": dataset_pin,
        "source_pin": source_pin,
        "label_definitions": {
            "sepsis3_onset": "Earliest availability-time row marked sepsis3 by the pinned export.",
            "aki_kdigo_stage_ge_1": "Maximum exported KDIGO stage >= 1; absent export remains unknown.",
        },
        "stays": [rows[stay_id] for stay_id in sorted(rows)],
    }
    artifact["content_hash"] = sha256_hex(canonical_json_bytes(artifact))
    return artifact


def validate_label_artifact(artifact: dict[str, Any]) -> None:
    if artifact.get("schema_version") != LABELS_SCHEMA_VERSION:
        raise LabelMaterializationError("unsupported label artifact schema")
    if artifact.get("artifact_type") != LABEL_ARTIFACT_TYPE:
        raise LabelMaterializationError("unexpected label artifact type")
    if not artifact.get("protocol_id") or not isinstance(artifact.get("stays"), list):
        raise LabelMaterializationError("label artifact is missing protocol_id or stays")
    validate_pin(artifact.get("source_pin") or {})
    expected = artifact.get("content_hash")
    body = {key: value for key, value in artifact.items() if key != "content_hash"}
    if expected != sha256_hex(canonical_json_bytes(body)):
        raise LabelMaterializationError("label artifact content_hash does not match contents")


def write_label_artifact(artifact: dict[str, Any], out: Path) -> Path:
    validate_label_artifact(artifact)
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(artifact, indent=2) + "\n")
    return target


def load_label_artifact(path: Path) -> dict[str, Any]:
    target = Path(path)
    try:
        artifact = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise LabelMaterializationError(f"cannot read label artifact {target}: {exc}") from exc
    validate_label_artifact(artifact)
    return artifact
