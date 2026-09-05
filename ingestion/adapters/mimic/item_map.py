"""Itemid maps for MIMIC-IV demo → Curie SOFA/AKI inputs."""

from __future__ import annotations

# hosp/labevents.csv.gz
LAB_CREATININE = {50912, 52546}  # Chemistry / alt
LAB_PLATELETS = {51265, 51704}
LAB_BILIRUBIN_TOTAL = {50885, 53089}  # total only (CURIE-048); not direct/fluid
LAB_PAO2 = {50821, 52042}  # arterial pO2 mmHg (not body fluid)

# icu/chartevents.csv.gz
CHART_MAP = {220052, 220181}  # Arterial / Non-Invasive Blood Pressure mean
CHART_SPO2 = {220277}  # O2 saturation pulseoxymetry
CHART_FIO2 = {
    223835,  # Inspired O2 Fraction (percent)
    226754,  # FiO2ApacheIIValue
    227009,  # FiO2_ApacheIV_old
    227010,  # FiO2_ApacheIV
    229280,  # FiO2 (ECMO)
    229841,  # FiO2 (CH)
}
CHART_GCS_EYE = {220739}
CHART_GCS_VERBAL = {223900}
CHART_GCS_MOTOR = {223901}
CHART_CREATININE = {220615}
CHART_BILIRUBIN = {225690}  # Total Bilirubin; not Direct/Apache (CURIE-048)
CHART_PLATELETS = {225678}

# icu/chartevents.csv.gz — invasive mechanical-ventilation settings. Presence
# within the ventilation lookback window is the SOFA respiration-band evidence
# (verified against d_items.csv category "Respiratory"). Explicitly excluded:
# 225794 (Non-invasive Ventilation, procedureevents — not MV), 226260
# ("Mechanically Ventilated" flag, ambiguous active-vs-ever semantics).
CHART_VENTILATION = {
    223848,  # Ventilator Type
    223849,  # Ventilator Mode
    229314,  # Ventilator Mode (Hamilton)
    230045,  # Intellivent (Hamilton Vent Mode)
    220339,  # PEEP set
    224699,  # ZAuto Peep Level
    224700,  # Total PEEP Level
    224684,  # Tidal Volume (set)
    224685,  # Tidal Volume (observed)
    224686,  # Tidal Volume (spontaneous)
    224695,  # Peak Insp. Pressure
    224696,  # Plateau Pressure
}

# icu/inputevents.csv.gz — presence implies on_vasopressors.
# SOFA dose-ladder agents plus "other" pressors (phenylephrine, vasopressin,
# angiotensin II) that mark pressor support but rarely have mcg/kg/min doses
# (e.g. vasopressin is charted in units/hour -> dose unknown, fallback points).
# Milrinone (221986) is intentionally NOT mapped: inotrope, not a SOFA pressor.
INPUT_VASOPRESSORS = {
    221906: "norepinephrine",
    221289: "epinephrine",
    229617: "epinephrine",
    221662: "dopamine",
    221653: "dobutamine",
    221749: "other",  # Phenylephrine
    229630: "other",  # Phenylephrine (50/250)
    229631: "other",  # Phenylephrine (200/250)_OLD_1
    229632: "other",  # Phenylephrine (200/250)
    229789: "other",  # Phenylephrine (Intubation)
    222315: "other",  # Vasopressin
    229709: "other",  # Angiotensin II (Giapreza)
    229764: "other",  # Angiotensin II (Giapreza)
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
