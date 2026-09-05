"""Pin the exact mimic-code revision + SQL file hashes used for reference labels.

The pin is an operator-generated frozen artifact: run
``python scripts/pin_mimic_code_labels.py --repo /path/to/mimic-code`` on a
local checkout of https://github.com/MIT-LCP/mimic-code, then commit the
produced JSON deliberately. Until a pin exists, label generation fails closed
and the run manifest records ``labels.status == "not_pinned"``.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.mimic_study.indexing import sha256_hex
from eval.mimic_study.labels import DEFAULT_PIN_PATH, LABELS_SCHEMA_VERSION


class LabelPinError(ValueError):
    """Missing or invalid mimic-code label pin."""


def load_pin(path: Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_PIN_PATH
    if not target.is_file():
        raise LabelPinError(
            f"no mimic-code label pin at {target}; run scripts/pin_mimic_code_labels.py "
            "on a local mimic-code checkout, then commit the produced pin JSON"
        )
    pin = json.loads(target.read_text())
    validate_pin(pin)
    return pin


def validate_pin(pin: dict[str, Any]) -> None:
    if pin.get("schema_version") != LABELS_SCHEMA_VERSION:
        raise LabelPinError(
            f"pin schema {pin.get('schema_version')!r} != {LABELS_SCHEMA_VERSION}"
        )
    code = pin.get("mimic_code") or {}
    if not code.get("revision") or not code.get("resolved_commit"):
        raise LabelPinError("pin is missing mimic_code.revision/resolved_commit")
    files = code.get("files") or {}
    for rel, info in files.items():
        if not info.get("sha256"):
            raise LabelPinError(f"pin entry {rel} is missing sha256")


def _git_resolved_commit(repo: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=repo
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise LabelPinError(f"cannot resolve git commit under {repo}: {exc}") from exc


def pin_from_repo(
    repo: Path,
    *,
    git_ref: str = "HEAD",
    sql_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record revision + sha256 of the SQL files that define reference labels."""
    files = sql_files or {}
    for rel in files.values():
        path = repo / rel
        if not path.is_file():
            raise LabelPinError(f"missing SQL file in mimic-code checkout: {path}")
    return {
        "schema_version": LABELS_SCHEMA_VERSION,
        "pinned_at": datetime.now(UTC).isoformat(),
        "mimic_code": {
            "repository": "https://github.com/MIT-LCP/mimic-code",
            "revision": git_ref,
            "resolved_commit": _git_resolved_commit(repo),
            "files": {
                rel: {
                    "sha256": sha256_hex((repo / rel).read_bytes()),
                    "size": (repo / rel).stat().st_size,
                }
                for rel in sorted(files.values())
            },
        },
        "note": (
            "Reference label definitions (Sepsis-3 / KDIGO concepts). Labels are "
            "generated separately from feature replay and are not on the alert path."
        ),
    }


def write_pin(pin: dict[str, Any], out: Path | None = None) -> Path:
    validate_pin(pin)
    target = Path(out) if out else DEFAULT_PIN_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(pin, indent=2) + "\n")
    return target
