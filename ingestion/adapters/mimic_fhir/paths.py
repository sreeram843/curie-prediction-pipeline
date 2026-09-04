"""MIMIC-IV Clinical Database Demo on FHIR paths."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MIMIC_FHIR_DEMO_DIR = (
    Path(__file__).resolve().parents[3] / "data" / "mimic-iv-fhir-demo"
)


def mimic_fhir_demo_dir() -> Path:
    raw = os.environ.get("CURIE_MIMIC_FHIR_DEMO_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_MIMIC_FHIR_DEMO_DIR.resolve()


def require_mimic_fhir_demo_dir() -> Path:
    root = mimic_fhir_demo_dir()
    fhir = root / "fhir"
    if not (fhir / "MimicEncounterICU.ndjson.gz").is_file():
        raise FileNotFoundError(
            f"MIMIC-IV FHIR demo not found at {root}. Place PhysioNet "
            "mimic-iv-fhir-demo under data/mimic-iv-fhir-demo or set "
            "CURIE_MIMIC_FHIR_DEMO_DIR."
        )
    return root
