"""SYN-ICU (Synthetic K-MIMIC) adapter.

Reads the 15-table KHDP `.xlsx` bundle and converts it into the same
demo-schema-stays fixture shape the MIMIC harness consumes. Synthetic only —
not a clinical-validity source.
"""

from ingestion.adapters.syn_icu.paths import require_syn_icu_dir, syn_icu_dir

__all__ = ["syn_icu_dir", "require_syn_icu_dir"]
