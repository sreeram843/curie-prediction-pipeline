"""MIMIC-IV Clinical Database Demo adapter (PhysioNet open demo)."""

from ingestion.adapters.mimic.paths import mimic_demo_dir, require_mimic_demo_dir

__all__ = ["mimic_demo_dir", "require_mimic_demo_dir"]
