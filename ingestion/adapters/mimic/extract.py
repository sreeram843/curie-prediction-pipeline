"""Extract Curie SOFA / AKI inputs from a MIMIC-IV demo ICU stay."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from eval.aki.scoring import AkiInput
from eval.sofa.scoring import SofaComponentInput, SofaComponentName
from ingestion.adapters.mimic import item_map as im
from ingestion.adapters.mimic.vasopressors import (
    PressorDose,
    convert_pressor_dose,
    is_bolus_order_category,
    latest_weight_before,
)
from ingestion.adapters.respiration import resolve_spo2_fio2_pao2

VasopressorAgent = Literal[
    "dopamine", "dobutamine", "epinephrine", "norepinephrine", "other"
]

_PRIORITY = {
    "norepinephrine": 4,
    "epinephrine": 4,
    "dopamine": 3,
    "dobutamine": 2,
    "other": 1,
}


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
    value, _observed_at, evidence_id = _latest_before_measurement(
        rows,
        as_of=as_of,
        itemids=itemids,
        time_key=time_key,
        value_key=value_key,
    )
    return value, evidence_id


def _latest_before_measurement(
    rows: list[dict[str, Any]],
    *,
    as_of: datetime,
    itemids: set[int],
    time_key: str = "charttime",
    value_key: str = "valuenum",
) -> tuple[float | None, datetime | None, str | None]:
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
    return best_val, best_t, best_eid


def _urine_ml_day(
    rows: list[dict[str, Any]],
    *,
    as_of: datetime,
    stay_intime: datetime | None = None,
) -> tuple[float | None, list[str]]:
    """Sum urine output over the 24h ending at as_of.

    Returns (None, []) before the stay has 24 hours of window (a partial-day
    total must never masquerade as a full 24-hour daily volume).
    """
    if stay_intime is not None and (as_of - stay_intime).total_seconds() < 24 * 3600:
        return None, []
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


@dataclass(frozen=True)
class PressorAtResult:
    """Cardiovascular pressor state at one replay instant."""

    present: bool
    agent: VasopressorAgent | None
    dose: float | None
    evidence_ids: list[str]
    details: list[dict[str, Any]] = field(default_factory=list)


def _pressor_at(
    rows: list[dict[str, Any]],
    *,
    weight_rows: list[tuple[datetime, int, float]],
    as_of: datetime,
) -> PressorAtResult:
    """Active pressor rows at ``as_of`` under the frozen B1 unit policy.

    - Active = starttime <= as_of <= endtime (missing endtime stays open).
    - Every active row is converted with :func:`convert_pressor_dose`; unknown
      doses are explicit (never a silent mcg/kg/min assumption).
    - Bolus orders count as "pressor present" but never fabricate a continuous
      dose (fail closed).
    - The winning agent is the highest SOFA-band agent; ties prefer a known
      dose, then the earlier starttime (deterministic).
    - All active rows' evidence IDs are preserved for auditability.
    """
    active: list[tuple[datetime, str, PressorDose]] = []
    details: list[dict[str, Any]] = []
    for row in rows:
        start = _parse_ts(str(row.get("starttime") or ""))
        end = _parse_ts(str(row.get("endtime") or ""))
        if start is None or as_of < start or (end is not None and as_of > end):
            continue
        agent = im.INPUT_VASOPRESSORS.get(int(row["itemid"]))
        if agent is None:
            continue
        eid = f"MIMIC/inputevents/{row['itemid']}/{row.get('starttime')}"
        weight = latest_weight_before(weight_rows=weight_rows, as_of=start)
        rate = row.get("rate")
        if is_bolus_order_category(row.get("ordercategoryname")):
            conv = PressorDose(
                None,
                False,
                "bolus_order_dose_not_applicable",
                row.get("rateuom") or None,
                source_rate=rate,
                weight_kg=None,
                weight_evidence_id=None,
                evidence_id=eid,
                agent=agent,
            )
        else:
            conv = convert_pressor_dose(
                rate=rate,
                rate_uom=row.get("rateuom") or None,
                weight_kg=weight.weight_kg,
                weight_available=weight.status == "resolved",
                weight_evidence_id=weight.evidence_id,
                evidence_id=eid,
                agent=agent,
            )
        details.append(
            {
                "agent": agent,
                "itemid": row["itemid"],
                "starttime": row.get("starttime"),
                "endtime": row.get("endtime") or None,
                "source_unit": conv.source_unit,
                "source_rate": conv.source_rate,
                "dose_ug_kg_min": conv.dose_ug_kg_min,
                "known": conv.known,
                "reason": conv.reason,
                "weight_kg": conv.weight_kg,
                "weight_evidence_id": conv.weight_evidence_id,
                "weight_status": weight.status,
                "evidence_id": eid,
                "ordercategoryname": row.get("ordercategoryname") or "",
                "statusdescription": row.get("statusdescription") or "",
            }
        )
        active.append((start, agent, conv))
    if not active:
        return PressorAtResult(False, None, None, [], details)

    def sort_key(item: tuple[datetime, str, PressorDose]) -> tuple:
        start, agent, conv = item
        return (-_PRIORITY.get(agent, 0), not conv.known, start)

    active.sort(key=sort_key)
    _, agent, winner = active[0]
    dose = winner.dose_ug_kg_min if winner.known else None
    eids = [c.evidence_id for (_, _, c) in active if c.evidence_id]
    return PressorAtResult(True, agent, dose, eids, details)  # type: ignore[arg-type]


def build_sofa_inputs(
    *,
    as_of: datetime,
    lab_rows: list[dict[str, Any]],
    chart_rows: list[dict[str, Any]],
    input_rows: list[dict[str, Any]],
    output_rows: list[dict[str, Any]],
    weight_rows: list[tuple[datetime, int, float]] | None = None,
    stay_intime: datetime | None = None,
    return_pressor_details: bool = False,
) -> list[SofaComponentInput] | tuple[list[SofaComponentInput], list[dict[str, Any]]]:
    """Build per-component SOFA inputs at ``as_of``.

    ``weight_rows``: (charttime, itemid, valuenum) weight chart rows for the
    availability-time pressor weight rule. ``stay_intime`` gates urine output
    eligibility (a partial-day sum is never a 24h total).
    """
    inputs: list[SofaComponentInput] = []
    weight_rows = weight_rows or []
    pressor_details: list[dict[str, Any]] = []

    spo2, spo2_at, spo2_eid = _latest_before_measurement(
        chart_rows, as_of=as_of, itemids=im.CHART_SPO2
    )
    fio2_pct, fio2_at, fio2_eid = _latest_before_measurement(
        chart_rows, as_of=as_of, itemids=im.CHART_FIO2
    )
    pao2, pao2_at, pao2_eid = _latest_before_measurement(
        lab_rows, as_of=as_of, itemids=im.LAB_PAO2
    )
    fio2_frac = (fio2_pct / 100.0) if fio2_pct is not None and fio2_pct > 0 else None
    resolved = resolve_spo2_fio2_pao2(
        pao2_mmhg=pao2,
        pao2_observed_at=pao2_at,
        pao2_evidence_id=pao2_eid,
        spo2_percent=spo2,
        spo2_observed_at=spo2_at,
        spo2_evidence_id=spo2_eid,
        fio2_fraction=fio2_frac,
        fio2_observed_at=fio2_at,
        fio2_evidence_id=fio2_eid,
        as_of=as_of,
    )
    inputs.append(
        SofaComponentInput(
            name=SofaComponentName.RESPIRATION,
            pao2_fio2=resolved.pao2_fio2,
            spo2_fio2=resolved.spo2_fio2,
            mechanically_ventilated=None,
            evidence_ids=list(resolved.evidence_ids),
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
    pressor = _pressor_at(input_rows, weight_rows=weight_rows, as_of=as_of)
    pressor_details = pressor.details
    cv_eids = [e for e in [map_eid, *pressor.evidence_ids] if e]
    inputs.append(
        SofaComponentInput(
            name=SofaComponentName.CARDIOVASCULAR,
            map_mmhg=map_v,
            on_vasopressors=pressor.present or None,
            vasopressor_agent=pressor.agent,
            vasopressor_dose_ug_kg_min=pressor.dose,
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
    uo, uo_eids = _urine_ml_day(output_rows, as_of=as_of, stay_intime=stay_intime)
    renal_eids = [e for e in [cr_eid, *uo_eids] if e]
    inputs.append(
        SofaComponentInput(
            name=SofaComponentName.RENAL,
            creatinine_mg_dl=cr,
            urine_output_ml_day=uo,
            evidence_ids=renal_eids,
        )
    )
    if return_pressor_details:
        return inputs, pressor_details
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
