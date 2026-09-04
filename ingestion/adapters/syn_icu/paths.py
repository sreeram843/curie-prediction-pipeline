"""SYN-ICU (Synthetic K-MIMIC) paths and config.

SYN-ICU is a synthetic, GAN-generated Korean ICU dataset distributed as
15 MIMIC-IV-shaped `.xlsx` tables via the KHDP portal. It is a *plumbing*
stand-in only — never a clinical-validity source. See
`docs/research/mimic-data-sources.md`.
"""

from __future__ import annotations

import os
from pathlib import Path

# Preferred layout: data/syn-icu/{syn_patients,syn_admissions,...}.xlsx
DEFAULT_SYN_ICU_DIR = Path(__file__).resolve().parents[3] / "data" / "syn-icu"

# The 15 tables of the SYN-ICU bundle (MIMIC-IV-like schema).
TABLE_NAMES = (
    "syn_patients",
    "syn_admissions",
    "syn_transfers",
    "syn_icustays",
    "syn_d_labitems",
    "syn_diagnoses_icd",
    "syn_labevents",
    "syn_d_items",
    "syn_chartevents",
    "syn_inputevents",
    "syn_outputevents",
    "syn_procedureevents",
    "syn_procedures_icd",
    "syn_emar",
    "syn_emar_detail",
)

# Minimum set required for a SOFA/AKI smoke path.
CORE_TABLES = (
    "syn_patients",
    "syn_admissions",
    "syn_icustays",
    "syn_d_labitems",
    "syn_labevents",
    "syn_d_items",
    "syn_chartevents",
    "syn_outputevents",
    "syn_inputevents",
    "syn_diagnoses_icd",
)


def syn_icu_dir() -> Path:
    raw = os.environ.get("CURIE_SYN_ICU_DIR") or os.environ.get("SYN_ICU_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_SYN_ICU_DIR.resolve()


def require_syn_icu_dir() -> Path:
    root = syn_icu_dir()
    if not root.is_dir():
        raise FileNotFoundError(
            f"SYN-ICU data not found at {root}. Download the 15 .xlsx tables "
            "from the KHDP SYN-ICU page and place them under data/syn-icu, "
            "or set CURIE_SYN_ICU_DIR."
        )
    return root
