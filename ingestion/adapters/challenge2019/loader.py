"""PhysioNet Challenge 2019 (.psv) → hourly SOFA feature snapshots."""

from __future__ import annotations

import csv
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval.sofa.scoring import SofaComponentInput, SofaComponentName

_FLOAT_COLS = (
    "MAP",
    "Platelets",
    "Bilirubin_total",
    "Creatinine",
    "O2Sat",
    "FiO2",
    "SaO2",
)


@dataclass
class ChallengeHour:
    stay_id: str
    iculos: int
    sepsis_label: int
    inputs: list[SofaComponentInput]
    raw: dict[str, Any] = field(default_factory=dict)


def default_archive_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "archive"


def require_challenge2019_dir(root: Path | None = None) -> Path:
    base = root or Path(os.environ.get("CURIE_CHALLENGE2019_DIR") or default_archive_dir())
    if not base.is_dir():
        raise FileNotFoundError(
            f"Challenge 2019 archive not found at {base}. "
            "Place PhysioNet challenge-2019 under data/archive/ "
            "or set CURIE_CHALLENGE2019_DIR."
        )
    return base


def iter_psv_paths(root: Path, *, set_name: str | None = None) -> Iterator[Path]:
    sets: list[Path] = []
    if set_name:
        candidate = root / set_name
        if not candidate.is_dir():
            raise FileNotFoundError(f"Unknown set directory: {candidate}")
        sets.append(candidate)
    else:
        for name in ("training_setA", "training_setB"):
            p = root / name
            if p.is_dir():
                sets.append(p)
    if not sets:
        training = root / "training"
        if training.is_dir():
            sets.append(training)
    if sets:
        for s in sets:
            yield from sorted(s.rglob("*.psv"))
        return
    # Fixture / flat directory of .psv files
    yield from sorted(root.rglob("*.psv"))


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    v = value.strip()
    if not v or v.upper() == "NAN":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _normalize_fio2(raw: float | None) -> float | None:
    if raw is None:
        return None
    frac = raw / 100.0 if raw > 1.0 else raw
    if frac <= 0 or frac > 1.0:
        return None
    return frac


def load_stay_hours(path: Path) -> list[ChallengeHour]:
    """Load one stay; forward-fill SOFA-relevant fields across ICULOS hours."""
    stay_id = path.stem
    with path.open(newline="") as f:
        reader = csv.DictReader(f, delimiter="|")
        if not reader.fieldnames or "SepsisLabel" not in reader.fieldnames:
            return []
        state: dict[str, float | None] = {c: None for c in _FLOAT_COLS}
        hours: list[ChallengeHour] = []
        for row in reader:
            for c in _FLOAT_COLS:
                parsed = _parse_float(row.get(c))
                if parsed is not None:
                    state[c] = parsed
            iculos_raw = row.get("ICULOS") or row.get("Hour")
            iculos = int(float(iculos_raw)) if iculos_raw not in (None, "") else len(hours) + 1
            label = int(float(row.get("SepsisLabel") or 0))
            hours.append(
                ChallengeHour(
                    stay_id=stay_id,
                    iculos=iculos,
                    sepsis_label=label,
                    inputs=_state_to_inputs(state),
                    raw={k: row.get(k) for k in (reader.fieldnames or [])},
                )
            )
        return hours


def _state_to_inputs(state: dict[str, float | None]) -> list[SofaComponentInput]:
    inputs: list[SofaComponentInput] = []
    if state["MAP"] is not None:
        inputs.append(
            SofaComponentInput(
                name=SofaComponentName.CARDIOVASCULAR, map_mmhg=state["MAP"]
            )
        )
    if state["Platelets"] is not None:
        inputs.append(
            SofaComponentInput(
                name=SofaComponentName.COAGULATION,
                platelets_10e9_l=state["Platelets"],
            )
        )
    if state["Bilirubin_total"] is not None:
        inputs.append(
            SofaComponentInput(
                name=SofaComponentName.LIVER,
                bilirubin_mg_dl=state["Bilirubin_total"],
            )
        )
    if state["Creatinine"] is not None:
        inputs.append(
            SofaComponentInput(
                name=SofaComponentName.RENAL,
                creatinine_mg_dl=state["Creatinine"],
            )
        )
    fio2 = _normalize_fio2(state["FiO2"])
    spo2 = state["O2Sat"] if state["O2Sat"] is not None else state["SaO2"]
    if spo2 is not None or fio2 is not None:
        inputs.append(
            SofaComponentInput(
                name=SofaComponentName.RESPIRATION,
                spo2_percent=spo2,
                fio2_fraction=fio2,
                mechanically_ventilated=False,
            )
        )
    return inputs


def sepsis_onset_iculos(hours: list[ChallengeHour]) -> int | None:
    for h in hours:
        if h.sepsis_label == 1:
            return h.iculos
    return None
