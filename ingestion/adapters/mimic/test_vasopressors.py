"""B1 pressor unit policy tests (CURIE-051): conversion matrix + weight rule."""

from __future__ import annotations

from datetime import datetime, timedelta

from ingestion.adapters.mimic.vasopressors import (
    PressorDose,
    WeightResolution,
    convert_pressor_dose,
    is_bolus_order_category,
    is_normalized_dose_unit,
    latest_weight_before,
    pressor_agent_for_itemid,
    valid_weight_kg,
)


def _conv(rate, unit, weight=None, available=True, **kw):
    return convert_pressor_dose(
        rate=rate, rate_uom=unit, weight_kg=weight, weight_available=available, **kw
    )


# --- positive conversions ---------------------------------------------------

def test_mcg_kg_min_passthrough() -> None:
    out = _conv(0.05, "mcg/kg/min")
    assert out.dose_ug_kg_min == 0.05
    assert out.known
    assert out.reason == "rate_already_weight_normalized"
    assert out.source_unit == "mcg/kg/min"


def test_mcg_min_divides_by_weight() -> None:
    out = _conv(5.0, "mcg/min", weight=50.0)
    assert out.known
    assert out.dose_ug_kg_min == 0.1
    assert out.reason == "divided_by_weight_kg"
    assert out.weight_kg == 50.0


def test_mg_kg_min_multiplies_by_1000() -> None:
    out = _conv(0.001, "mg/kg/min")
    assert out.known
    assert out.dose_ug_kg_min == 1.0
    assert out.reason == "mg_to_mcg_x1000"


def test_mg_min_multiplies_then_divides() -> None:
    out = _conv(0.5, "mg/min", weight=100.0)
    assert out.known
    assert out.dose_ug_kg_min == 5.0
    assert out.reason == "mg_to_mcg_then_divided_by_weight_kg"


def test_case_spacing_and_spelling_variants() -> None:
    assert _conv(0.05, "MCG/KG/MIN").known
    assert _conv(0.05, " mcg / kg / min ").known
    assert _conv(0.05, "mcg/kg/minute").known
    assert _conv(0.05, "ug/kg/min").known
    assert _conv(5.0, "μg/min", weight=50.0).known


def test_dose_boundary_values() -> None:
    assert _conv(0.0001, "mcg/kg/min").known
    big = _conv(1000.0, "mg/kg/min")
    assert big.known and big.dose_ug_kg_min == 1_000_000.0


# --- negative / boundary / missing-input branches ---------------------------

def test_missing_unit_is_unknown() -> None:
    out = _conv(0.05, None)
    assert not out.known
    assert out.dose_ug_kg_min is None
    assert out.reason == "missing_unit"


def test_unsupported_units_are_unknown() -> None:
    for unit in ("units/hour", "units/min", "ng/kg/min", "mcg/hr", "grams"):
        out = _conv(0.05, unit)
        assert not out.known, unit
        assert out.reason.startswith("unsupported_unit:"), unit
        assert out.source_unit == f"unsupported:{''.join(unit.split())}"


def test_volume_rate_without_concentration_is_unknown() -> None:
    out = _conv(10.0, "mL/hour", weight=70.0)
    assert not out.known
    assert out.reason == "volume_rate_without_concentration"


def test_missing_rate_is_unknown() -> None:
    out = _conv(None, "mcg/kg/min")
    assert not out.known
    assert out.reason == "missing_rate"


def test_non_finite_and_non_positive_rate_is_unknown() -> None:
    assert _conv(float("nan"), "mcg/kg/min").reason == "non_finite_rate"
    assert _conv(float("inf"), "mcg/kg/min").reason == "non_finite_rate"
    assert _conv(0.0, "mcg/kg/min").reason == "non_positive_rate"
    assert _conv(-1.0, "mcg/kg/min").reason == "non_positive_rate"


def test_missing_weight_is_unknown() -> None:
    out = _conv(5.0, "mcg/min", weight=None)
    assert not out.known
    assert out.reason == "invalid_or_missing_weight"


def test_invalid_weight_is_unknown() -> None:
    assert not _conv(5.0, "mcg/min", weight=0.0).known
    assert not _conv(5.0, "mcg/min", weight=600.0).known
    assert not _conv(5.0, "mcg/min", weight=float("nan")).known
    assert not _conv(5.0, "mcg/min", weight=float("inf")).known


def test_future_only_weight_is_unknown() -> None:
    out = _conv(5.0, "mcg/min", weight=70.0, available=False)
    assert not out.known
    assert out.reason == "weight_unavailable_or_only_future"


# --- provenance preservation ------------------------------------------------

def test_provenance_fields_preserved() -> None:
    out = _conv(
        0.2,
        "mcg/kg/min",
        evidence_id="MIMIC/inputevents/221906/2020-01-01 00:00:00",
        agent="norepinephrine",
    )
    assert out.evidence_id == "MIMIC/inputevents/221906/2020-01-01 00:00:00"
    assert out.agent == "norepinephrine"
    assert out.source_rate == 0.2
    assert isinstance(out, PressorDose)


# --- weight resolution ------------------------------------------------------

def _wt(hours: float, itemid: int = 224639, value: float = 70.0):
    base = datetime(2020, 1, 1, 12, 0, 0)
    return (base + timedelta(hours=hours), itemid, value)


def test_latest_weight_before_uses_most_recent_prior() -> None:
    res = latest_weight_before(
        weight_rows=[_wt(-10), _wt(-1, value=80.0), _wt(+2)],
        as_of=datetime(2020, 1, 1, 12, 0, 0),
    )
    assert res.status == "resolved"
    assert res.weight_kg == 80.0
    assert res.evidence_id


def test_weight_only_future_is_reported_not_used() -> None:
    res = latest_weight_before(
        weight_rows=[_wt(+1)], as_of=datetime(2020, 1, 1, 12, 0, 0)
    )
    assert res.status == "only_future"
    assert res.weight_kg is None


def test_weight_missing_when_no_rows() -> None:
    res = latest_weight_before(weight_rows=[], as_of=datetime(2020, 1, 1))
    assert res.status == "missing"
    assert isinstance(res, WeightResolution)


def test_lbs_weight_converted_to_kg() -> None:
    res = latest_weight_before(
        weight_rows=[_wt(-1, itemid=226531, value=220.46)],
        as_of=datetime(2020, 1, 1, 12, 0, 0),
    )
    assert res.status == "resolved"
    assert abs(res.weight_kg - 100.0) < 0.01


def test_invalid_charted_weight_is_reported() -> None:
    res = latest_weight_before(
        weight_rows=[_wt(-1, value=0.5)],
        as_of=datetime(2020, 1, 1, 12, 0, 0),
    )
    assert res.status == "invalid"


# --- itemid map + guards ----------------------------------------------------

def test_itemid_map_includes_other_pressors_not_milrinone() -> None:
    assert pressor_agent_for_itemid(221906) == "norepinephrine"
    assert pressor_agent_for_itemid(221749) == "other"  # phenylephrine
    assert pressor_agent_for_itemid(222315) == "other"  # vasopressin
    assert pressor_agent_for_itemid(229764) == "other"  # angiotensin II
    assert pressor_agent_for_itemid(221986) is None  # milrinone: not a SOFA pressor
    assert pressor_agent_for_itemid(999999) is None


def test_normalized_dose_units_only() -> None:
    assert is_normalized_dose_unit("mcg/kg/min")
    assert is_normalized_dose_unit(" ug/kg/min ")
    assert is_normalized_dose_unit("")
    assert is_normalized_dose_unit(None)
    assert not is_normalized_dose_unit("mcg/min")
    assert not is_normalized_dose_unit("mL/hour")
    assert not is_normalized_dose_unit("units/hour")


def test_bolus_order_category_detected() -> None:
    assert is_bolus_order_category("05-Med Bolus")
    assert not is_bolus_order_category("01-Drips")
    assert not is_bolus_order_category(None)


def test_valid_weight_kg_bounds() -> None:
    assert valid_weight_kg(70.0)
    assert not valid_weight_kg(None)
    assert not valid_weight_kg(0.9)
    assert not valid_weight_kg(500.1)
    assert not valid_weight_kg(float("nan"))
