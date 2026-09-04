"""MIMIC-IV Clinical Database Demo on FHIR adapter.

NDJSON resources → demo-schema stays. Same 100-patient open demo as the CSV
MIMIC-IV demo, in FHIR R4. Plumbing only — no outcome labels.
"""

from ingestion.adapters.mimic_fhir.paths import (
    mimic_fhir_demo_dir,
    require_mimic_fhir_demo_dir,
)

__all__ = ["mimic_fhir_demo_dir", "require_mimic_fhir_demo_dir"]
