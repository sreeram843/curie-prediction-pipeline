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
