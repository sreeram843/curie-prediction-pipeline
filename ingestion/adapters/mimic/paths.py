"""MIMIC-IV Clinical Database Demo paths and config."""

from __future__ import annotations

import os
from pathlib import Path

# Preferred layout after local install / move:
#   data/mimic-iv-demo/{hosp,icu}/...
DEFAULT_MIMIC_DEMO_DIR = (
    Path(__file__).resolve().parents[3] / "data" / "mimic-iv-demo"
)


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
