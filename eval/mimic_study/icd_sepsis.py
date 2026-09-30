"""Independent ICD sepsis positive-stay flags (secondary fairness scorecard).

Discharge diagnosis codes are never primary onset and must not enter scoring
features. This module only builds an ICD+ denominator for exploratory metrics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ingestion.adapters.mimic.loader import iter_csv_gz

FROZEN_DIR = Path(__file__).resolve().parent / "labels" / "frozen"
DEFAULT_PIN = FROZEN_DIR / "icd_sepsis_codes.v1.json"


def load_icd_sepsis_pin(path: Path | None = None) -> dict[str, Any]:
    pin_path = path or DEFAULT_PIN
    payload = json.loads(pin_path.read_text())
    matching = payload.get("matching") or {}
    exact = {_norm_code(c) for c in matching.get("exact") or [] if _norm_code(c)}
    prefixes = tuple(
        sorted(
            {_norm_code(c) for c in matching.get("prefixes") or [] if _norm_code(c)},
            key=len,
            reverse=True,
        )
    )
    if not exact and not prefixes:
        raise ValueError(f"ICD sepsis pin has empty matching sets: {pin_path}")
    return {
        **payload,
        "_exact": exact,
        "_prefixes": prefixes,
        "_path": str(pin_path),
    }


def _norm_code(raw: str | None) -> str:
    return (raw or "").strip().replace(".", "").upper()


def code_matches_sepsis(code: str, pin: dict[str, Any] | None = None) -> bool:
    """Return True if a normalized ICD code matches the frozen sepsis pin."""
    resolved = pin or load_icd_sepsis_pin()
    norm = _norm_code(code)
    if not norm:
        return False
    if norm in resolved["_exact"]:
        return True
    return any(norm.startswith(prefix) for prefix in resolved["_prefixes"])


def load_icd_sepsis_hadm_ids(
    root: Path,
    *,
    pin: dict[str, Any] | None = None,
) -> set[str]:
    """Return ``hadm_id`` strings with ≥1 pinned sepsis ICD code on the admission."""
    resolved = pin or load_icd_sepsis_pin()
    path = root / "hosp" / "diagnoses_icd.csv.gz"
    if not path.is_file():
        raise FileNotFoundError(f"diagnoses_icd missing under {root}")
    positives: set[str] = set()
    for row in iter_csv_gz(path):
        code = row.get("icd_code")
        if not code_matches_sepsis(str(code), resolved):
            continue
        hadm = (row.get("hadm_id") or "").strip()
        if hadm:
            positives.add(hadm)
    return positives


def annotate_icd_sepsis_positive(
    stay_rows: list[dict[str, Any]],
    *,
    icd_positive_hadm_ids: set[str],
    hadm_by_stay: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Attach ``icd_sepsis_positive`` from hadm_id (row field or stay→hadm map)."""
    out: list[dict[str, Any]] = []
    for row in stay_rows:
        stay_id = str(row.get("stay_id") or "")
        hadm = str(row.get("hadm_id") or "").strip()
        if not hadm and hadm_by_stay is not None:
            hadm = str(hadm_by_stay.get(stay_id) or "").strip()
        flagged = bool(hadm) and hadm in icd_positive_hadm_ids
        enriched = dict(row)
        if hadm and not enriched.get("hadm_id"):
            enriched["hadm_id"] = hadm
        enriched["icd_sepsis_positive"] = flagged
        out.append(enriched)
    return out
