"""Extract Curie SOFA / AKI inputs from a MIMIC-IV demo ICU stay."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from eval.aki.scoring import AkiInput
from eval.sofa.scoring import SofaComponentInput, SofaComponentName
from ingestion.adapters.mimic import item_map as im

VasopressorAgent = Literal[
    "dopamine", "dobutamine", "epinephrine", "norepinephrine", "other"
]


def _parse_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _latest_before(
    rows: list[dict[str, Any]],
    *,
    as_of: datetime,
    itemids: set[int],
    time_key: str = "charttime",
    value_key: str = "valuenum",
) -> tuple[float | None, str | None]:
    best_val: float | None = None
    best_t: datetime | None = None
    best_eid: str | None = None
    for row in rows:
        if int(row["itemid"]) not in itemids:
            continue
        t = _parse_ts(str(row.get(time_key) or ""))
        if t is None or t > as_of:
            continue
        if best_t is None or t >= best_t:
            best_t = t
            best_val = float(row[value_key])
            best_eid = f"MIMIC/{time_key}/{row['itemid']}/{row.get(time_key)}"
    return best_val, best_eid


def _urine_ml_day(
    rows: list[dict[str, Any]],
    *,
    as_of: datetime,
) -> tuple[float | None, list[str]]:
    """Sum urine output over the 24h ending at as_of."""
    total = 0.0
    eids: list[str] = []
    window_start = as_of.timestamp() - 24 * 3600
    for row in rows:
        t = _parse_ts(str(row.get("charttime") or ""))
        if t is None or t > as_of:
            continue
        if t.timestamp() < window_start:
            continue
        total += float(row["value"])
        eids.append(f"MIMIC/outputevents/{row['itemid']}/{row.get('charttime')}")
    if not eids:
        return None, []
    return total, eids


def _pressor_at(
    rows: list[dict[str, Any]],
    *,
    as_of: datetime,
) -> tuple[bool, VasopressorAgent | None, float | None, list[str]]:
    active: list[tuple[str, float | None, str]] = []
    for row in rows:
        start = _parse_ts(str(row.get("starttime") or ""))
        end = _parse_ts(str(row.get("endtime") or "")) or as_of
        if start is None or as_of < start or as_of > end:
            continue
        agent = im.INPUT_VASOPRESSORS.get(int(row["itemid"]), "other")
        rate = row.get("rate")
        # Convert common mcg/kg/min; leave None if unknown unit
        dose = float(rate) if rate is not None else None
        eid = f"MIMIC/inputevents/{row['itemid']}/{row.get('starttime')}"
        active.append((agent, dose, eid))
    if not active:
        return False, None, None, []
    # Prefer highest SOFA band agent/dose present
    priority = {"norepinephrine": 4, "epinephrine": 4, "dopamine": 3, "dobutamine": 2, "other": 1}
    active.sort(key=lambda x: priority.get(x[0], 0), reverse=True)
    agent, dose, eid = active[0]
    return True, agent, dose, [eid]  # type: ignore[return-value]


def build_sofa_inputs(
    *,
    as_of: datetime,
    lab_rows: list[dict[str, Any]],
    chart_rows: list[dict[str, Any]],
    input_rows: list[dict[str, Any]],
    output_rows: list[dict[str, Any]],
) -> list[SofaComponentInput]:
    inputs: list[SofaComponentInput] = []

    spo2, spo2_eid = _latest_before(chart_rows, as_of=as_of, itemids=im.CHART_SPO2)
    fio2_pct, fio2_eid = _latest_before(chart_rows, as_of=as_of, itemids=im.CHART_FIO2)
    spo2_fio2 = None
    resp_eids: list[str] = []
    if spo2 is not None and fio2_pct is not None and fio2_pct > 0:
        spo2_fio2 = spo2 / (fio2_pct / 100.0)
        resp_eids = [e for e in (spo2_eid, fio2_eid) if e]
    inputs.append(
        SofaComponentInput(
            name=SofaComponentName.RESPIRATION,
            spo2_fio2=spo2_fio2,
            mechanically_ventilated=None,
            evidence_ids=resp_eids,
        )
    )

    plt, plt_eid = _latest_before(lab_rows, as_of=as_of, itemids=im.LAB_PLATELETS)
    if plt is None:
        plt, plt_eid = _latest_before(chart_rows, as_of=as_of, itemids=im.CHART_PLATELETS)
    inputs.append(
        SofaComponentInput(
            name=SofaComponentName.COAGULATION,
            platelets_10e9_l=plt,
            evidence_ids=[plt_eid] if plt_eid else [],
        )
    )

    bili, bili_eid = _latest_before(lab_rows, as_of=as_of, itemids=im.LAB_BILIRUBIN_TOTAL)
    if bili is None:
        bili, bili_eid = _latest_before(chart_rows, as_of=as_of, itemids=im.CHART_BILIRUBIN)
    inputs.append(
        SofaComponentInput(
            name=SofaComponentName.LIVER,
            bilirubin_mg_dl=bili,
            evidence_ids=[bili_eid] if bili_eid else [],
        )
    )

    map_v, map_eid = _latest_before(chart_rows, as_of=as_of, itemids=im.CHART_MAP)
    on_pressor, agent, dose, pressor_eids = _pressor_at(input_rows, as_of=as_of)
    cv_eids = [e for e in [map_eid, *pressor_eids] if e]
    inputs.append(
        SofaComponentInput(
            name=SofaComponentName.CARDIOVASCULAR,
            map_mmhg=map_v,
            on_vasopressors=on_pressor or None,
            vasopressor_agent=agent,
            vasopressor_dose_ug_kg_min=dose,
            evidence_ids=cv_eids,
        )
    )

    eye, e1 = _latest_before(chart_rows, as_of=as_of, itemids=im.CHART_GCS_EYE)
    verbal, e2 = _latest_before(chart_rows, as_of=as_of, itemids=im.CHART_GCS_VERBAL)
    motor, e3 = _latest_before(chart_rows, as_of=as_of, itemids=im.CHART_GCS_MOTOR)
    gcs = None
    gcs_eids: list[str] = []
    if eye is not None and verbal is not None and motor is not None:
        gcs = int(eye + verbal + motor)
        gcs_eids = [e for e in (e1, e2, e3) if e]
    inputs.append(
        SofaComponentInput(
            name=SofaComponentName.CNS,
            gcs=gcs,
            evidence_ids=gcs_eids,
        )
    )

    cr, cr_eid = _latest_before(lab_rows, as_of=as_of, itemids=im.LAB_CREATININE)
    if cr is None:
        cr, cr_eid = _latest_before(chart_rows, as_of=as_of, itemids=im.CHART_CREATININE)
    uo, uo_eids = _urine_ml_day(output_rows, as_of=as_of)
    renal_eids = [e for e in [cr_eid, *uo_eids] if e]
    inputs.append(
        SofaComponentInput(
            name=SofaComponentName.RENAL,
            creatinine_mg_dl=cr,
            urine_output_ml_day=uo,
            evidence_ids=renal_eids,
        )
    )
    return inputs


def build_aki_input(
    *,
    as_of: datetime,
    lab_rows: list[dict[str, Any]],
    chart_rows: list[dict[str, Any]],
    baseline_lookback_hours: float = 168.0,
) -> AkiInput:
    """Current Cr at as_of; baseline = earliest Cr in prior lookback window."""
    cr_now, eid_now = _latest_before(lab_rows, as_of=as_of, itemids=im.LAB_CREATININE)
    if cr_now is None:
        cr_now, eid_now = _latest_before(
            chart_rows, as_of=as_of, itemids=im.CHART_CREATININE
        )

    window_start = as_of.timestamp() - baseline_lookback_hours * 3600
    candidates: list[tuple[datetime, float, str]] = []
    for row in lab_rows:
        if int(row["itemid"]) not in im.LAB_CREATININE:
            continue
        t = _parse_ts(str(row.get("charttime") or ""))
        if t is None or t >= as_of:
            continue
        if t.timestamp() < window_start:
            continue
        candidates.append(
            (t, float(row["valuenum"]), f"MIMIC/labevents/{row['itemid']}/{row.get('charttime')}")
        )
    baseline = None
    base_eid = None
    if candidates:
        candidates.sort(key=lambda x: x[0])
        baseline = candidates[0][1]
        base_eid = candidates[0][2]

    return AkiInput(
        creatinine_mg_dl=cr_now,
        baseline_creatinine_mg_dl=baseline,
        evidence_ids=[eid_now] if eid_now else [],
        baseline_evidence_ids=[base_eid] if base_eid else [],
    )
