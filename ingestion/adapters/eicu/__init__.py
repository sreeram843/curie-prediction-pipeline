"""eICU Collaborative Research Database Demo adapter.

Converts open PhysioNet eICU demo CSVs into demo-schema stays for the MIMIC
harness. Plumbing / coverage only — the demo has no Sepsis-3 onset labels.
"""

from ingestion.adapters.eicu.paths import eicu_demo_dir, require_eicu_demo_dir

__all__ = ["eicu_demo_dir", "require_eicu_demo_dir"]
