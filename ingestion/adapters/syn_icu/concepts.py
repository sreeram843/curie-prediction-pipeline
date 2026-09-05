"""SYN-ICU item/label → Curie SOFA/AKI concept mapping.

SYN-ICU uses Korean EDI/KCD codes and its own `d_items` / `d_labitems`
dictionaries, not MIMIC `itemid`s. We map by label (case-insensitive substring)
to the same canonical LOINC codes the demo-schema harness consumes, so the
harness needs no SYN-ICU-specific code.

The label tables below are *best-effort defaults*; SYN-ICU's exact labels may
differ. `build_concept_index` reports unmapped itemids so gaps can be filled in
once the real dictionaries are inspected.
"""

from __future__ import annotations

from typing import Any

# Canonical LOINC codes used by the demo-schema harness (`_LOINC_TO_COMPONENT`).
CREATININE_LOINC = "2160-0"
PLATELETS_LOINC = "777-3"
BILIRUBIN_LOINC = "1975-2"
MAP_LOINC = "8478-0"
SPO2_LOINC = "2708-6"
FIO2_LOINC = "3150-0"
PAO2_LOINC = "2703-7"
GCS_LOINC = "9269-2"
URINE_LOINC = "9187-6"
VASOPRESSOR_CODE = "curie-vasopressor"

# Concept keys shared across the adapter.
CREATININE = "creatinine"
PLATELETS = "platelets"
BILIRUBIN_TOTAL = "bilirubin_total"
MAP = "map"
SPO2 = "spo2"
FIO2 = "fio2"
PAO2 = "pao2"
GCS_EYE = "gcs_eye"
GCS_VERBAL = "gcs_verbal"
GCS_MOTOR = "gcs_motor"
GCS_TOTAL = "gcs_total"
URINE_OUTPUT = "urine_output"
VASOPRESSOR = "vasopressor"

# label substrings (lowercase) → concept, matched against d_items/d_labitems labels.
# Order matters: more specific first.
LABEL_MAP: tuple[tuple[str, str], ...] = (
    ("creatinine", CREATININE),
    ("crea", CREATININE),
    ("platelet", PLATELETS),
    ("plt count", PLATELETS),
    ("plt(", PLATELETS),
    ("bilirubin total", BILIRUBIN_TOTAL),
    ("total bilirubin", BILIRUBIN_TOTAL),
    ("bilirubin, total", BILIRUBIN_TOTAL),
    ("tbil", BILIRUBIN_TOTAL),
    ("bilirubin", BILIRUBIN_TOTAL),
    ("arterial blood pressure mean", MAP),
    ("mean arterial", MAP),
    ("abp mean", MAP),
    ("arterial bp mean", MAP),
    ("mean abp", MAP),
    ("mean bp", MAP),
    ("spo2", SPO2),
    ("o2 saturation", SPO2),
    ("oxygen saturation", SPO2),
    ("pulse oximetry", SPO2),
    ("pulseoxymetry", SPO2),
    ("fio2", FIO2),
    ("inspired o2", FIO2),
    ("inspired oxygen", FIO2),
    ("pao2", PAO2),
    ("arterial po2", PAO2),
    ("po2 arterial", PAO2),
    ("gcs - eye", GCS_EYE),
    ("gcs eye", GCS_EYE),
    ("eye opening", GCS_EYE),
    ("glasgow coma scale(eye)", GCS_EYE),
    ("gcs - verbal", GCS_VERBAL),
    ("gcs verbal", GCS_VERBAL),
    ("verbal response", GCS_VERBAL),
    ("glasgow coma scale(verbal)", GCS_VERBAL),
    ("gcs - motor", GCS_MOTOR),
    ("gcs motor", GCS_MOTOR),
    ("motor response", GCS_MOTOR),
    ("glasgow coma scale(motor)", GCS_MOTOR),
    ("glasgow coma scale", GCS_TOTAL),
    ("gcs total", GCS_TOTAL),
)


def match_concept(label: str) -> str | None:
    """Return the concept key for a d_item/d_labitem label, or None."""
    text = (label or "").lower()
    if not text:
        return None
    for needle, concept in LABEL_MAP:
        if needle in text:
            return concept
    return None


def build_concept_index(
    *,
    d_labitems: list[dict[str, Any]] | None = None,
    d_items: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Build itemid → concept and concept → itemids maps.

    Returns ``(itemid_to_concept, concept_to_itemids)``. ``itemid`` values are
    coerced to ``str`` so EDI codes (which may be numeric or alphanumeric) are
    handled uniformly.
    """
    itemid_to_concept: dict[str, str] = {}
    concept_to_itemids: dict[str, set[str]] = {}

    def register(itemid: Any, label: str) -> None:
        concept = match_concept(label)
        if concept is None:
            return
        key = str(itemid).strip()
        if not key or key in {"", "nan", "None"}:
            return
        itemid_to_concept[key] = concept
        concept_to_itemids.setdefault(concept, set()).add(key)

    for row in d_items or []:
        register(row.get("itemid"), str(row.get("label") or ""))
    for row in d_labitems or []:
        register(row.get("itemid"), str(row.get("label") or ""))

    return itemid_to_concept, concept_to_itemids
