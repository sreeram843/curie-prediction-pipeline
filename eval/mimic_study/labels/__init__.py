"""Reference outcome labels for the MIMIC/eICU study (Sepsis-3, KDIGO).

Labels are generated only from an explicitly pinned ``mimic-code`` revision and
recorded SQL file hashes — never from feature replay. The replay path
(`eval.mimic_study.index_replay`) must not import this package; labels attach
to the run manifest as provenance, and their generation is a separate,
operator-run step (Phase C3/A).
"""

from __future__ import annotations

from pathlib import Path

LABELS_SCHEMA_VERSION = "1.0.0"

DEFAULT_PIN_PATH = Path(__file__).resolve().parent / "frozen" / "mimic_code_pin.v1.json"

# Well-known mimic-code SQL files used by the reference label definitions.
# The pin records the exact revision + sha256 of every file actually used.
SEPSIS3_SQL_FILES = {
    "sepsis3_suspicion_of_infection": (
        "mimic-iv/concepts_postgres/sepsis/suspicion_of_infection.sql"
    ),
    "sepsis3": "mimic-iv/concepts_postgres/sepsis/sepsis3.sql",
    "kdigo_creatinine": "mimic-iv/concepts_postgres/organfailure/kdigo_creatinine.sql",
    "kdigo_stages": "mimic-iv/concepts_postgres/organfailure/kdigo_stages.sql",
    "kdigo_uo": "mimic-iv/concepts_postgres/organfailure/kdigo_uo.sql",
    "sofa": "mimic-iv/concepts_postgres/score/sofa.sql",
}


def pin_path() -> Path:
    return DEFAULT_PIN_PATH
