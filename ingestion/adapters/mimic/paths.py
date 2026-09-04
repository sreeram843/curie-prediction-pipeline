"""MIMIC-IV paths: open demo vs credentialed 3.1."""

from __future__ import annotations

import os
from pathlib import Path

# Preferred layout after local install / move:
#   data/mimic-iv-demo/{hosp,icu}/...
DEFAULT_MIMIC_DEMO_DIR = (
    Path(__file__).resolve().parents[3] / "data" / "mimic-iv-demo"
)

# Credentialed MIMIC-IV 3.1 lives outside the repo (never commit).
# wget -r may nest files under physionet.org/files/mimiciv/3.1/.
DEFAULT_MIMIC_DIR = Path(__file__).resolve().parents[3] / "data" / "mimic-iv"
_WGET_NESTED = Path("physionet.org") / "files" / "mimiciv" / "3.1"


def mimic_demo_dir() -> Path:
    raw = os.environ.get("CURIE_MIMIC_DEMO_DIR") or os.environ.get("MIMIC_DEMO_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_MIMIC_DEMO_DIR.resolve()


def require_mimic_demo_dir() -> Path:
    root = mimic_demo_dir()
    if not (root / "hosp").is_dir() or not (root / "icu").is_dir():
        raise FileNotFoundError(
            f"MIMIC-IV demo not found at {root}. "
            "Place PhysioNet mimic-iv-clinical-database-demo under data/mimic-iv-demo "
            "or set CURIE_MIMIC_DEMO_DIR."
        )
    return root


def mimic_dir() -> Path:
    raw = os.environ.get("CURIE_MIMIC_DIR") or os.environ.get("MIMIC_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_MIMIC_DIR.resolve()


def _is_mimic_iv_root(root: Path) -> bool:
    return (root / "hosp" / "labevents.csv.gz").is_file() and (
        root / "icu" / "icustays.csv.gz"
    ).is_file()


def require_mimic_dir() -> Path:
    configured = mimic_dir()
    candidates = [configured, configured / _WGET_NESTED]
    if not (os.environ.get("CURIE_MIMIC_DIR") or os.environ.get("MIMIC_DIR")):
        physionet = Path(
            os.environ.get("PHYSIONET_DATA_ROOT", "/Users/srirammentey/PhysioNet")
        )
        candidates.extend(
            (
                physionet / _WGET_NESTED,
                physionet / "mimiciv-v3.1" / _WGET_NESTED,
            )
        )
    for candidate in candidates:
        if _is_mimic_iv_root(candidate):
            return candidate.resolve()
    raise FileNotFoundError(
        f"MIMIC-IV 3.1 not found at {configured}. "
        "Set CURIE_MIMIC_DIR to the folder that contains hosp/ and icu/ "
        "(or the wget -r dest whose physionet.org/files/mimiciv/3.1/ subtree has them)."
    )
