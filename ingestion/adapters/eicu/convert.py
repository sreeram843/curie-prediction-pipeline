"""eICU demo CSVs → demo-schema stays.

Offsets are minutes from unit admit. We synthesize a naive epoch so scoring
windows are consistent; calendar dates in the demo are incomplete (year +
time-of-day only).
"""

from __future__ import annotations

import csv
import gzip
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ingestion.adapters.demo_schema import downsample_hourly
from ingestion.adapters.eicu.paths import require_eicu_demo_dir, require_eicu_dir
from ingestion.adapters.syn_icu import concepts as c
from ingestion.adapters.syn_icu.convert import _emit_stay
from ingestion.completeness import filter_eicu_protocol_cohort, seeded_sample

SCHEMA_VERSION = "1.0.0"
EPOCH = datetime(2015, 1, 1, 0, 0, 0)

_LAB_NAMES: dict[str, str] = {
    "creatinine": c.CREATININE,
    "platelets x 1000": c.PLATELETS,
    # SOFA liver needs total bilirubin only (CURIE-048). "direct bilirubin" is not a substitute.
    "total bilirubin": c.BILIRUBIN_TOTAL,
    "fio2": c.FIO2,
    "pao2": c.PAO2,  # eICU blood-gas PaO2 (mmHg)
}

# respiratoryCharting FiO2 label variants (exact match after lower/strip).
_RESP_FIO2_LABELS = frozenset({
    "fio2",
    "fio2 (%)",
    "fio2(%)",
    "o2 percentage",
    "o2 %",
})


def _mechanical_ventilation_value(label: str, value: str) -> bool | None:
    """Parse explicit invasive-ventilation charting without guessing from FiO2."""
    label_norm = re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()
    value_norm = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    known_label = any(
        marker in label_norm
        for marker in (
            "ventilator mode",
            "ventilator type",
            "vent mode",
            "mechanical ventilation",
            "ventilation status",
            "airway type",
            "intubated",
            "rt vent on off",
        )
    )
    if not known_label or not value_norm:
        return None
    if any(
        marker in value_norm
        for marker in (
            "invasive",
            "mechanical",
            "ventilator",
            "intubat",
            "endotracheal",
            "ett",
        )
    ):
        return True
    if "rt vent on off" in label_norm and value_norm in {"on", "yes", "active", "continued"}:
        return True
    if any(
        marker in value_norm
        for marker in (
            "room air",
            "nasal cannula",
            "face mask",
            "simple mask",
            "high flow",
            "non invasive",
            "noninvasive",
            "cpap",
            "bipap",
            "extubat",
            "off",
            "none",
        )
    ):
        return False
    if value_norm in {"no", "off", "none"}:
        return False
    if "ventilator mode" in label_norm or "vent mode" in label_norm:
        if value_norm not in {"unknown", "not documented", "not available", "na"}:
            return True
    return None

def _iter_csv_gz(path: Path) -> Iterator[dict[str, str]]:
    with gzip.open(path, "rt", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield {k: (v if v is not None else "") for k, v in row.items()}


def _to_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _offset_ts(offset_min: Any) -> str | None:
    minutes = _to_float(offset_min)
    if minutes is None:
        return None
    clock = EPOCH + timedelta(minutes=minutes)
    return clock.strftime("%Y-%m-%d %H:%M:%S")


def _event(
    *,
    concept: str,
    itemid: str,
    valuenum: float | None,
    unit: str,
    charttime: str,
) -> dict[str, Any]:
    return {
        "concept": concept,
        "itemid": itemid,
        "valuenum": valuenum,
        "unit": unit,
        "charttime": charttime,
        "storetime": charttime,
    }


def _derive_map_event(
    *,
    sbp: float | None,
    dbp: float | None,
    itemid: str,
    charttime: str,
) -> dict[str, Any] | None:
    """Derive MAP = (SBP + 2*DBP) / 3 only when SBP and DBP are temporally
    pairable — i.e. present in the *same* observation row. Unrelated latest
    values are never combined, and pulmonary-artery columns are never used."""
    if sbp is None or dbp is None:
        return None
    if sbp <= 0 or dbp <= 0 or dbp > sbp:
        return None
    event = _event(
        concept=c.MAP,
        itemid=itemid,
        valuenum=(sbp + 2 * dbp) / 3.0,
        unit="mmHg",
        charttime=charttime,
    )
    event["extras"] = {
        "map_derivation": {
            "source": "sbp_dbp_same_row",
            "sbp_mmhg": sbp,
            "dbp_mmhg": dbp,
        }
    }
    return event


def _maybe_fio2_percent(value: float) -> float:
    # eICU FiO2 is usually percent; a fraction in (0, 1] is scaled up.
    if 0 < value <= 1.0:
        return value * 100.0
    return value


_VASO_AGENTS = (
    "norepinephrine",
    "epinephrine",
    "dopamine",
    "dobutamine",
    "phenylephrine",
    "vasopressin",
)


@dataclass(frozen=True)
class ParsedVasopressor:
    agent: str
    dose: float | None
    unit: str
    source_unit: str | None = None
    reason: str = "unknown"


def _parse_vasopressor(row: dict[str, str]) -> ParsedVasopressor | None:
    """Convert an eICU infusionDrug row to (agent, dose_ug_kg_min, ...).

    Same frozen B1 unit policy as the MIMIC adapter:
    - mcg/kg/min unchanged; mg/kg/min x1000;
    - mcg/min and mg/min divide by a valid contemporaneous row weight;
    - volume rates (ml/hr, ml) and units/hour|min stay unknown (no
      concentration column exists) — never a silent conversion.
    """
    from ingestion.adapters.mimic.vasopressors import (
        convert_pressor_dose,
        valid_weight_kg,
    )

    name = (row.get("drugname") or "").strip().lower()
    if not name:
        return None
    agent = None
    for key in _VASO_AGENTS:
        if key in name:
            agent = "other" if key in {"phenylephrine", "vasopressin"} else key
            break
    if agent is None:
        return None
    rate = _to_float(row.get("drugrate"))
    weight = _to_float(row.get("patientweight"))
    unit = ""
    if "(" in name and ")" in name:
        unit = name[name.rfind("(") + 1 : name.rfind(")")].strip()
    conv = convert_pressor_dose(
        rate=rate,
        rate_uom=unit or None,
        weight_kg=weight,
        weight_available=valid_weight_kg(weight),
        agent=agent,
    )
    dose = conv.dose_ug_kg_min if conv.known else None
    return ParsedVasopressor(
        agent=agent,
        dose=dose,
        unit="mcg/kg/min" if conv.known else (unit or "infusion"),
        source_unit=conv.source_unit or unit or None,
        reason=conv.reason,
    )



def _is_gcs_total_label(label: str, name: str) -> bool:
    """True when nurseCharting row is a total GCS (not a component)."""
    lab = label.lower().strip()
    nam = name.lower().strip()
    blob = f"{lab} {nam}".strip()
    if "gcs total" in blob:
        return True
    if "glasgow coma" in lab and nam in {"value", "total", "score", "gcs total", ""}:
        return True
    if lab == "score (glasgow coma scale)" and nam in {"value", ""}:
        return True
    return False


def _gcs_component_from_nurse(label: str, name: str) -> str | None:
    """Return gcs_eye / gcs_verbal / gcs_motor concept, or None."""
    lab = label.lower()
    nam = name.lower()
    if "glasgow" not in lab and "gcs" not in lab and "glasgow" not in nam:
        return None
    if nam in {"eyes", "eye"} or nam.startswith("eye"):
        return c.GCS_EYE
    if nam.startswith("verbal"):
        return c.GCS_VERBAL
    if nam.startswith("motor"):
        return c.GCS_MOTOR
    return None


_PHYS_GCS_COMPONENT = re.compile(
    r"/gcs/(eyes?|motor|verbal)\s*score/(\d+)",
    re.IGNORECASE,
)
_PHYS_GCS_TOTAL = re.compile(r"/gcs/(\d{1,2})(?:\s|/|$)", re.IGNORECASE)


def _gcs_events_from_physical_exam(row: dict[str, str]) -> list[tuple[str, float, str]]:
    """Parse physicalExam paths into (concept, value, itemid) tuples."""
    path = row.get("physicalexampath") or ""
    path_l = path.lower()
    if "/gcs/" not in path_l and "glasgow" not in path_l:
        return []
    out: list[tuple[str, float, str]] = []
    m = _PHYS_GCS_COMPONENT.search(path_l)
    if m:
        kind = m.group(1).lower()
        val = float(m.group(2))
        if kind.startswith("eye"):
            out.append((c.GCS_EYE, val, "phys-gcs-eye"))
        elif kind.startswith("verbal"):
            out.append((c.GCS_VERBAL, val, "phys-gcs-verbal"))
        elif kind.startswith("motor"):
            out.append((c.GCS_MOTOR, val, "phys-gcs-motor"))
        return out
    # Prefer numeric value column when path is a scored total marker.
    val = _to_float(row.get("physicalexamvalue"))
    if val is None:
        val = _to_float(row.get("physicalexamtext"))
    m_tot = _PHYS_GCS_TOTAL.search(path_l)
    if m_tot and "/score/" not in path_l:
        out.append((c.GCS_TOTAL, float(m_tot.group(1)), "phys-gcs-total"))
        return out
    if val is not None and 3 <= val <= 15 and "score" in path_l and "eyes" not in path_l:
        # rare: numeric total in value with score path
        if "motor" not in path_l and "verbal" not in path_l and "eye" not in path_l:
            out.append((c.GCS_TOTAL, val, "phys-gcs-total"))
    return out


def convert_eicu_rows(
    *,
    patients: Iterable[dict[str, str]],
    labs: Iterable[dict[str, str]],
    vital_periodic: Iterable[dict[str, str]],
    vital_aperiodic: Iterable[dict[str, str]],
    nurse_charting: Iterable[dict[str, str]],
    respiratory_charting: Iterable[dict[str, str]] | None = None,
    intake_output: Iterable[dict[str, str]] | None = None,
    infusion_drug: Iterable[dict[str, str]] | None = None,
    physical_exam: Iterable[dict[str, str]] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    stays_meta: dict[str, dict[str, Any]] = {}
    for row in patients:
        stay_id = (row.get("patientunitstayid") or "").strip()
        if not stay_id:
            continue
        subject_id = (
            row.get("uniquepid") or row.get("patienthealthsystemstayid") or stay_id
        ).strip()
        out_off = _to_float(row.get("unitdischargeoffset"))
        stays_meta[stay_id] = {
            "stay_id": stay_id,
            "subject_id": subject_id,
            "hadm_id": (row.get("patienthealthsystemstayid") or "").strip(),
            "intime": EPOCH.strftime("%Y-%m-%d %H:%M:%S"),
            "outtime": (EPOCH + timedelta(minutes=out_off or 0)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        if limit is not None and len(stays_meta) >= limit:
            break

    wanted = set(stays_meta)
    lab_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    chart_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)

    def add_chart(stay_id: str, ev: dict[str, Any]) -> None:
        chart_events[stay_id].append(ev)
        counts[ev["concept"]] += 1

    def add_lab(stay_id: str, ev: dict[str, Any]) -> None:
        lab_events[stay_id].append(ev)
        counts[ev["concept"]] += 1

    for row in labs:
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        name = (row.get("labname") or "").strip().lower()
        concept = _LAB_NAMES.get(name)
        if concept is None:
            continue
        val = _to_float(row.get("labresult"))
        if val is None:
            continue
        ts = _offset_ts(row.get("labresultoffset"))
        if ts is None:
            continue
        if concept == c.FIO2:
            val = _maybe_fio2_percent(val)
            add_chart(
                stay_id,
                _event(
                    concept=concept, itemid="lab-fio2", valuenum=val, unit="%", charttime=ts
                ),
            )
        else:
            unit = row.get("labmeasurenamesystem") or ""
            if concept == c.PAO2 and not unit:
                unit = "mmHg"
            add_lab(
                stay_id,
                _event(
                    concept=concept, itemid=name, valuenum=val, unit=unit, charttime=ts
                ),
            )

    for row in vital_periodic:
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        ts = _offset_ts(row.get("observationoffset"))
        if ts is None:
            continue
        sao2 = _to_float(row.get("sao2"))
        if sao2 is not None:
            add_chart(
                stay_id,
                _event(concept=c.SPO2, itemid="sao2", valuenum=sao2, unit="%", charttime=ts),
            )
        mean_bp = _to_float(row.get("systemicmean"))
        if mean_bp is not None:
            add_chart(
                stay_id,
                _event(
                    concept=c.MAP,
                    itemid="systemicmean",
                    valuenum=mean_bp,
                    unit="mmHg",
                    charttime=ts,
                ),
            )
        else:
            derived = _derive_map_event(
                sbp=_to_float(row.get("systemicsystolic")),
                dbp=_to_float(row.get("systemicdiastolic")),
                itemid="systemic-derived-map",
                charttime=ts,
            )
            if derived is not None:
                add_chart(stay_id, derived)

    for row in vital_aperiodic:
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        ts = _offset_ts(row.get("observationoffset"))
        if ts is None:
            continue
        nibp = _to_float(row.get("noninvasivemean"))
        if nibp is not None:
            add_chart(
                stay_id,
                _event(
                    concept=c.MAP,
                    itemid="nibp-mean",
                    valuenum=nibp,
                    unit="mmHg",
                    charttime=ts,
                ),
            )
        else:
            derived = _derive_map_event(
                sbp=_to_float(row.get("noninvasivesystolic")),
                dbp=_to_float(row.get("noninvasivediastolic")),
                itemid="nibp-derived-map",
                charttime=ts,
            )
            if derived is not None:
                add_chart(stay_id, derived)

    for row in nurse_charting:
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        ts = _offset_ts(row.get("nursingchartoffset"))
        if ts is None:
            continue
        label = (row.get("nursingchartcelltypevallabel") or "").strip()
        name = (row.get("nursingchartcelltypevalname") or "").strip()
        val = _to_float(row.get("nursingchartvalue"))
        if val is None:
            continue
        blob = f"{label} {name}".lower()
        if _is_gcs_total_label(label, name):
            add_chart(
                stay_id,
                _event(
                    concept=c.GCS_TOTAL,
                    itemid="gcs-total",
                    valuenum=val,
                    unit="",
                    charttime=ts,
                ),
            )
        else:
            component = _gcs_component_from_nurse(label, name)
            if component is not None:
                add_chart(
                    stay_id,
                    _event(
                        concept=component,
                        itemid=f"gcs-{component}",
                        valuenum=val,
                        unit="",
                        charttime=ts,
                    ),
                )
        if label.lower() == "o2 saturation":
            add_chart(
                stay_id,
                _event(concept=c.SPO2, itemid="o2sat", valuenum=val, unit="%", charttime=ts),
            )
        elif "map (mmhg)" in blob:
            add_chart(
                stay_id,
                _event(
                    concept=c.MAP,
                    itemid="nurse-map",
                    valuenum=val,
                    unit="mmHg",
                    charttime=ts,
                ),
            )

    for row in physical_exam or ():
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        ts = _offset_ts(row.get("physicalexamoffset"))
        if ts is None:
            continue
        for concept, valuenum, itemid in _gcs_events_from_physical_exam(row):
            add_chart(
                stay_id,
                _event(
                    concept=concept,
                    itemid=itemid,
                    valuenum=valuenum,
                    unit="",
                    charttime=ts,
                ),
            )

    for row in respiratory_charting or ():
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        label = (row.get("respchartvaluelabel") or "").strip().lower()
        ventilation = _mechanical_ventilation_value(
            label, (row.get("respchartvalue") or "").strip()
        )
        if ventilation is not None:
            ts = _offset_ts(row.get("respchartoffset"))
            if ts is not None:
                add_chart(
                    stay_id,
                    {
                        **_event(
                            concept=c.MECHANICALLY_VENTILATED,
                            itemid="resp-ventilation",
                            valuenum=1.0 if ventilation else 0.0,
                            unit="",
                            charttime=ts,
                        ),
                        "display": "mechanically_ventilated",
                        "extras": {
                            "ventilation": {
                                "source_label": label,
                                "source_value": row.get("respchartvalue") or "",
                            }
                        },
                    },
                )
        if label not in _RESP_FIO2_LABELS:
            continue
        val = _to_float(row.get("respchartvalue"))
        if val is None:
            continue
        ts = _offset_ts(row.get("respchartoffset"))
        if ts is None:
            continue
        val = _maybe_fio2_percent(val)
        add_chart(
            stay_id,
            _event(
                concept=c.FIO2,
                itemid="resp-fio2",
                valuenum=val,
                unit="%",
                charttime=ts,
            ),
        )

    for row in intake_output or ():
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        label = (row.get("celllabel") or "").strip().lower()
        if label != "urine":
            continue
        val = _to_float(row.get("cellvaluenumeric"))
        if val is None or val < 0:
            continue
        ts = _offset_ts(row.get("intakeoutputoffset"))
        if ts is None:
            continue
        add_chart(
            stay_id,
            _event(
                concept=c.URINE_OUTPUT,
                itemid="urine",
                valuenum=val,
                unit="mL",
                charttime=ts,
            ),
        )

    for row in infusion_drug or ():
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        parsed = _parse_vasopressor(row)
        if parsed is None:
            continue
        agent, dose, unit = parsed.agent, parsed.dose, parsed.unit
        ts = _offset_ts(row.get("infusionoffset"))
        if ts is None:
            continue
        # Unknown dose stays missing; replay handles pressor presence separately.
        add_chart(
            stay_id,
            {
                **_event(
                    concept=c.VASOPRESSOR,
                    itemid=agent,
                    valuenum=float(dose) if dose is not None else None,
                    unit=unit,
                    charttime=ts,
                ),
                "display": agent,
                "extras": {
                    "pressor": {
                        "known": dose is not None,
                        "reason": parsed.reason,
                        "source_unit": parsed.source_unit,
                        "source_rate": _to_float(row.get("drugrate")),
                        "source_row": f"eicu/infusionDrug/{row.get('infusiondrugid')}",
                    }
                },
            },
        )

    stays = []
    for stay_id, meta in stays_meta.items():
        labs_ds = downsample_hourly(lab_events.get(stay_id, []))
        charts_ds = downsample_hourly(chart_events.get(stay_id, []))
        stays.append(
            _emit_stay(
                stay_meta=meta,
                lab_events=labs_ds,
                chart_events=charts_ds,
                diagnoses=[],
                evidence_prefix="eicu",
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_pin": {
            "name": "eicu-crd",
            "version": "2.0",
            "note": (
                "PhysioNet eICU-CRD. Plumbing / coverage only; no Sepsis-3 onset "
                "labels. Default convert_eicu applies adult/first-stay/LOS>=4h "
                "cohort + seeded sample (CURIE-049). Vitals downsampled hourly."
            ),
        },
        "coverage": {"concepts": dict(counts), "stays": len(stays)},
        "stays": stays,
        "warnings": [],
    }


def convert_eicu(
    root: Path | None = None,
    *,
    limit: int | None = None,
    apply_protocol_cohort: bool = True,
    sample_seed: int = 42,
) -> dict[str, Any]:
    """Load eICU stays.

    When ``apply_protocol_cohort`` is true (default), keep adult / first-stay /
    LOS>=4h rows and draw ``limit`` stays with a seeded shuffle (CURIE-049).
    Pass ``apply_protocol_cohort=False`` only for raw plumbing smoke tests.
    """
    root = root or (require_eicu_dir() if apply_protocol_cohort else require_eicu_demo_dir())
    patients = list(_iter_csv_gz(root / "patient.csv.gz"))
    if apply_protocol_cohort:
        patients = filter_eicu_protocol_cohort(patients)
    if limit is not None:
        if apply_protocol_cohort:
            patients = seeded_sample(patients, limit, seed=sample_seed)
        else:
            patients = patients[:limit]
    wanted = {(p.get("patientunitstayid") or "").strip() for p in patients}

    def _filter(path: Path) -> Iterator[dict[str, str]]:
        if not path.is_file():
            return
        yield from (
            row
            for row in _iter_csv_gz(path)
            if (row.get("patientunitstayid") or "").strip() in wanted
        )

    return convert_eicu_rows(
        patients=patients,
        labs=_filter(root / "lab.csv.gz"),
        vital_periodic=_filter(root / "vitalPeriodic.csv.gz"),
        vital_aperiodic=_filter(root / "vitalAperiodic.csv.gz"),
        nurse_charting=_filter(root / "nurseCharting.csv.gz"),
        respiratory_charting=_filter(root / "respiratoryCharting.csv.gz"),
        intake_output=_filter(root / "intakeOutput.csv.gz"),
        infusion_drug=_filter(root / "infusionDrug.csv.gz"),
        physical_exam=_filter(root / "physicalExam.csv.gz"),
        limit=None,
    )
