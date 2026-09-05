"""Shared cohort-selection helpers for credentialed ICU adapters.

This module deliberately has no dependency on evaluation or replay code.  It
contains only deterministic input filtering and sampling used by adapters and
by the completeness study.
"""

from __future__ import annotations

import csv
import gzip
import random
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

MIN_LOS_HOURS = 4.0
DEFAULT_SAMPLE_SEED = 42


def seeded_sample(rows: Sequence[T], limit: int, *, seed: int = DEFAULT_SAMPLE_SEED) -> list[T]:
    """Return a deterministic shuffle-then-take sample, never a file prefix."""
    if limit < 0:
        raise ValueError("limit must be >= 0")
    items = list(rows)
    rng = random.Random(seed)
    rng.shuffle(items)
    return items[:limit]


def _to_float(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_eicu_age_years(raw: str | None) -> int | None:
    """Parse eICU's age string; ``> 89`` is represented as age 89."""
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith(">"):
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else None
    try:
        return int(float(text))
    except ValueError:
        return None


def eicu_protocol_eligible(row: dict[str, str]) -> bool:
    age = parse_eicu_age_years(row.get("age"))
    if age is None or age < 18:
        return False
    los_min = _to_float(row.get("unitdischargeoffset"))
    return los_min is not None and los_min >= MIN_LOS_HOURS * 60


def filter_eicu_protocol_cohort(patients: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Keep adult eICU stays >=4h and first unit visit per hospital stay."""
    eligible = [p for p in patients if eicu_protocol_eligible(p)]
    best: dict[str, dict[str, str]] = {}
    for row in eligible:
        hadm = (row.get("patienthealthsystemstayid") or "").strip()
        if not hadm:
            continue
        visit = _to_float(row.get("unitvisitnumber")) or 1e9
        prev = best.get(hadm)
        if prev is None:
            best[hadm] = row
            continue
        prev_visit = _to_float(prev.get("unitvisitnumber")) or 1e9
        if visit < prev_visit or (
            visit == prev_visit
            and (row.get("patientunitstayid") or "") < (prev.get("patientunitstayid") or "")
        ):
            best[hadm] = row
    return list(best.values())


def _parse_mimic_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def filter_mimic_protocol_cohort(
    *,
    icustays: Iterable[dict[str, str]],
    patients: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    """Keep adult MIMIC stays >=4h and first ICU stay per hospital admission."""
    age_by_subject: dict[str, int] = {}
    for row in patients:
        sid = (row.get("subject_id") or "").strip()
        if not sid:
            continue
        try:
            age_by_subject[sid] = int(row.get("anchor_age") or "")
        except ValueError:
            continue

    eligible: list[tuple[dict[str, str], datetime]] = []
    for row in icustays:
        sid = (row.get("subject_id") or "").strip()
        age = age_by_subject.get(sid)
        if age is None or age < 18:
            continue
        intime = _parse_mimic_ts(row.get("intime"))
        outtime = _parse_mimic_ts(row.get("outtime"))
        if intime is None or outtime is None:
            continue
        if (outtime - intime).total_seconds() / 3600.0 < MIN_LOS_HOURS:
            continue
        eligible.append((row, intime))

    best: dict[str, tuple[dict[str, str], datetime]] = {}
    for row, intime in eligible:
        hadm = (row.get("hadm_id") or "").strip()
        if not hadm:
            continue
        prev = best.get(hadm)
        if prev is None or intime < prev[1]:
            best[hadm] = (row, intime)
    return [row for row, _ in best.values()]


def sample_eicu_protocol_patients(
    root: Path,
    *,
    limit: int,
    seed: int = DEFAULT_SAMPLE_SEED,
) -> list[dict[str, str]]:
    patients = load_csv_gz(root / "patient.csv.gz")
    return seeded_sample(filter_eicu_protocol_cohort(patients), limit, seed=seed)


def sample_mimic_protocol_stays(
    root: Path,
    *,
    limit: int,
    seed: int = DEFAULT_SAMPLE_SEED,
) -> list[dict[str, str]]:
    stays = load_csv_gz(root / "icu" / "icustays.csv.gz")
    patients = load_csv_gz(root / "hosp" / "patients.csv.gz")
    cohort = filter_mimic_protocol_cohort(icustays=stays, patients=patients)
    return seeded_sample(cohort, limit, seed=seed)


def load_csv_gz(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="") as fh:
        return [
            {k: (v if v is not None else "") for k, v in row.items()}
            for row in csv.DictReader(fh)
        ]
