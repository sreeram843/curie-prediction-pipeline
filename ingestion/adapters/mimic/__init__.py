"""MIMIC-IV adapter (open demo + credentialed 3.1 paths)."""

from ingestion.adapters.mimic.paths import (
    mimic_demo_dir,
    mimic_dir,
    require_mimic_demo_dir,
    require_mimic_dir,
)

__all__ = [
    "mimic_demo_dir",
    "mimic_dir",
    "require_mimic_demo_dir",
    "require_mimic_dir",
]
