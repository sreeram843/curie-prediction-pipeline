"""Itemid maps for MIMIC-IV demo → Curie SOFA/AKI inputs."""

from __future__ import annotations

# hosp/labevents.csv.gz
LAB_CREATININE = {50912, 52546}  # Chemistry / alt
LAB_PLATELETS = {51265, 51704}
LAB_BILIRUBIN_TOTAL = {50885, 53089}

# icu/chartevents.csv.gz
CHART_MAP = {220052}  # Arterial Blood Pressure mean
CHART_SPO2 = {220277}  # O2 saturation pulseoxymetry
CHART_FIO2 = {223835}  # Inspired O2 Fraction (percent)
CHART_GCS_EYE = {220739}
CHART_GCS_VERBAL = {223900}
CHART_GCS_MOTOR = {223901}
CHART_CREATININE = {220615}
CHART_BILIRUBIN = {225690}
CHART_PLATELETS = {225678}

# icu/inputevents.csv.gz — presence implies on_vasopressors
INPUT_VASOPRESSORS = {
    221906: "norepinephrine",
    221289: "epinephrine",
    229617: "epinephrine",
    221662: "dopamine",
    221653: "dobutamine",
}

# icu/outputevents — urine (mL); summed over day for SOFA renal UO
OUTPUT_URINE = {
    226559,  # Foley
    226560,  # Void
    226561,  # Condom Cath
    226563,  # Suprapubic
    226564,  # R Nephrostomy
    226565,  # L Nephrostomy
    226557,  # R Ureteral Stent
    226558,  # L Ureteral Stent
    226567,  # Straight Cath
    226584,  # Ileoconduit
    226627,  # OR Urine
    226631,  # PACU Urine
    226566,  # Urine and GU Irrigant Out
    227489,  # GU Irrigant/Urine Volume Out
}
