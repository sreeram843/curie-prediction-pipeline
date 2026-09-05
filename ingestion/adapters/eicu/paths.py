"""eICU Collaborative Research Database Demo paths."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_EICU_DEMO_DIR = Path(__file__).resolve().parents[3] / "data" / "eicu-crd-demo"


def eicu_demo_dir() -> Path:
    raw = os.environ.get("CURIE_EICU_DEMO_DIR") or os.environ.get("EICU_DEMO_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_EICU_DEMO_DIR.resolve()


def require_eicu_demo_dir() -> Path:
    root = eicu_demo_dir()
    if not (root / "patient.csv.gz").is_file() or not (root / "lab.csv.gz").is_file():
        raise FileNotFoundError(
            f"eICU demo not found at {root}. Place PhysioNet eicu-crd-demo under "
            "data/eicu-crd-demo or set CURIE_EICU_DEMO_DIR."
        )
    return root


def eicu_dir() -> Path:
    """Return the full credentialed eICU root from explicit environment config."""
    raw = os.environ.get("CURIE_EICU_DIR") or os.environ.get("EICU_DIR")
    if not raw:
        raise FileNotFoundError(
            "Full credentialed eICU requires CURIE_EICU_DIR (or EICU_DIR); "
            "the demo path is intentionally not used as a fallback."
        )
    return Path(raw).expanduser().resolve()


def require_eicu_dir() -> Path:
    """Validate and return the full credentialed eICU root."""
    root = eicu_dir()
    required = (root / "patient.csv.gz", root / "lab.csv.gz")
    if not all(path.is_file() for path in required):
        raise FileNotFoundError(
            f"Full eICU data not found at {root}; expected patient.csv.gz and lab.csv.gz."
        )
    return root
