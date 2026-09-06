"""eICU demo converter tests — no PhysioNet dump required."""

from __future__ import annotations

import pytest

from eval.mimic_harness.replay import replay_stay
from ingestion.adapters.eicu.convert import convert_eicu_rows
from ingestion.adapters.syn_icu import concepts as c


def _patient() -> dict[str, str]:
    return {
        "patientunitstayid": "1",
        "uniquepid": "u1",
        "patienthealthsystemstayid": "h1",
        "unitdischargeoffset": "180",
    }


def test_eicu_rows_emit_demo_schema_and_replay() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[
            {
                "patientunitstayid": "1",
                "labname": "creatinine",
                "labresult": "2.8",
                "labresultoffset": "60",
                "labmeasurenamesystem": "mg/dL",
            },
            {
                "patientunitstayid": "1",
                "labname": "platelets x 1000",
                "labresult": "40",
                "labresultoffset": "60",
                "labmeasurenamesystem": "",
            },
            {
                "patientunitstayid": "1",
                "labname": "FiO2",
                "labresult": "0.4",
                "labresultoffset": "70",
                "labmeasurenamesystem": "",
            },
        ],
        vital_periodic=[
            {
                "patientunitstayid": "1",
                "observationoffset": "65",
                "sao2": "88",
                "systemicmean": "52",
            }
        ],
        vital_aperiodic=[],
        nurse_charting=[
            {
                "patientunitstayid": "1",
                "nursingchartoffset": "80",
                "nursingchartcelltypevallabel": "Glasgow coma score",
                "nursingchartcelltypevalname": "GCS Total",
                "nursingchartvalue": "8",
            }
        ],
    )
    assert converted["stays"]
    stay = converted["stays"][0]
    assert stay["stay_id"] == "1"
    assert stay["labels"]["sepsis3_onset"] is None
    lab_concepts = {lab["code"] for lab in stay["labs"]}
    assert c.CREATININE_LOINC in lab_concepts
    assert c.PLATELETS_LOINC in lab_concepts
    result = replay_stay(stay)
    assert not result.errors
    assert result.signals


def test_respiratory_charting_fio2_emits_chart_event() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        respiratory_charting=[
            {
                "patientunitstayid": "1",
                "respchartoffset": "30",
                "respcharttypecat": "respFlowSettings",
                "respchartvaluelabel": "FiO2",
                "respchartvalue": "40",
            }
        ],
    )
    assert converted["coverage"]["concepts"][c.FIO2] == 1
    codes = {e["code"] for e in converted["stays"][0]["charts"]}
    assert c.FIO2_LOINC in codes


def test_respiratory_charting_fio2_pairs_with_spo2_in_replay() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[
            {
                "patientunitstayid": "1",
                "observationoffset": "65",
                "sao2": "88",
                "systemicmean": "",
            }
        ],
        vital_aperiodic=[],
        nurse_charting=[],
        respiratory_charting=[
            {
                "patientunitstayid": "1",
                "respchartoffset": "30",
                "respcharttypecat": "respFlowSettings",
                "respchartvaluelabel": "FiO2",
                "respchartvalue": "40",
            }
        ],
    )
    result = replay_stay(converted["stays"][0])
    assert not result.errors
    assert result.snapshots
    missing = result.snapshots[-1].get("missing_components") or []
    assert "respiration" not in missing


def test_respiratory_charting_missing_arg_is_ok() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
    )
    assert converted["coverage"]["concepts"].get(c.FIO2, 0) == 0


def test_respiratory_charting_ignores_non_fio2_labels() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        respiratory_charting=[
            {
                "patientunitstayid": "1",
                "respchartoffset": "30",
                "respcharttypecat": "respFlowSettings",
                "respchartvaluelabel": "Vent Rate",
                "respchartvalue": "14",
            },
            {
                "patientunitstayid": "1",
                "respchartoffset": "30",
                "respcharttypecat": "respFlowCareData",
                "respchartvaluelabel": "RT Vent On/Off",
                "respchartvalue": "Continued",
            },
        ],
    )
    assert converted["coverage"]["concepts"].get(c.FIO2, 0) == 0


def test_respiratory_charting_emits_explicit_invasive_ventilation() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[
            {
                "patientunitstayid": "1",
                "observationoffset": "31",
                "sao2": "80",
                "systemicmean": "55",
            }
        ],
        vital_aperiodic=[],
        nurse_charting=[],
        respiratory_charting=[
            {
                "patientunitstayid": "1",
                "respchartoffset": "30",
                "respcharttypecat": "respFlowCareData",
                "respchartvaluelabel": "Ventilator Mode",
                "respchartvalue": "AC/VC",
            },
            {
                "patientunitstayid": "1",
                "respchartoffset": "30",
                "respcharttypecat": "respFlowSettings",
                "respchartvaluelabel": "FiO2",
                "respchartvalue": "40",
            },
        ],
    )

    charts = converted["stays"][0]["charts"]
    vent = [event for event in charts if event["code"] == c.MECHANICALLY_VENTILATED_CODE]
    assert len(vent) == 1
    assert vent[0]["valuenum"] == 1
    assert converted["coverage"]["concepts"][c.MECHANICALLY_VENTILATED] == 1

    result = replay_stay(converted["stays"][0])
    assert not result.errors
    assert result.snapshots[-1]["score"] >= 3


def test_respiratory_charting_does_not_guess_ventilation_from_unknown_value() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        respiratory_charting=[
            {
                "patientunitstayid": "1",
                "respchartoffset": "30",
                "respcharttypecat": "respFlowCareData",
                "respchartvaluelabel": "Ventilator Mode",
                "respchartvalue": "Not documented",
            }
        ],
    )

    assert converted["coverage"]["concepts"].get(c.MECHANICALLY_VENTILATED, 0) == 0


def test_urine_only_scores_renal_without_creatinine() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        intake_output=[
            {
                "patientunitstayid": "1",
                "intakeoutputoffset": "1440",
                "celllabel": "Urine",
                "cellvaluenumeric": "200",
            },
            {
                "patientunitstayid": "1",
                "intakeoutputoffset": "1500",
                "celllabel": "Urine",
                "cellvaluenumeric": "150",
            },
        ],
    )
    assert converted["coverage"]["concepts"][c.URINE_OUTPUT] == 2
    result = replay_stay(converted["stays"][0])
    assert result.snapshots
    missing = result.snapshots[-1].get("missing_components") or []
    assert "renal" not in missing


def test_vasopressor_only_scores_cardiovascular_without_map() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        infusion_drug=[
            {
                "patientunitstayid": "1",
                "infusionoffset": "30",
                "drugname": "Norepinephrine (mcg/kg/min)",
                "drugrate": "0.12",
                "patientweight": "80",
            }
        ],
    )
    assert converted["coverage"]["concepts"][c.VASOPRESSOR] == 1
    result = replay_stay(converted["stays"][0])
    assert result.snapshots
    missing = result.snapshots[-1].get("missing_components") or []
    assert "cardiovascular" not in missing
    assert result.snapshots[-1].get("score", 0) >= 3


def test_unknown_vasopressor_dose_emits_null_not_zero() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        infusion_drug=[
            {
                "patientunitstayid": "1",
                "infusionoffset": "30",
                "drugname": "Norepinephrine (units/hr)",
                "drugrate": "1.0",
                "patientweight": "80",
            }
        ],
    )
    vaso = [
        event
        for event in converted["stays"][0]["charts"]
        if event["code"] == c.VASOPRESSOR_CODE
    ]
    assert len(vaso) == 1
    assert vaso[0]["valuenum"] is None


def test_mg_kg_min_pressor_converted_x1000() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        infusion_drug=[
            {
                "patientunitstayid": "1",
                "infusionoffset": "30",
                "drugname": "Epinephrine (mg/kg/min)",
                "drugrate": "0.001",
                "patientweight": "80",
            }
        ],
    )
    vaso = [
        event
        for event in converted["stays"][0]["charts"]
        if event["code"] == c.VASOPRESSOR_CODE
    ]
    assert len(vaso) == 1
    assert vaso[0]["valuenum"] == 1.0
    assert vaso[0]["unit"] == "mcg/kg/min"  # normalized unit after conversion


def test_mg_min_pressor_without_valid_weight_is_unknown() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        infusion_drug=[
            {
                "patientunitstayid": "1",
                "infusionoffset": "30",
                "drugname": "Norepinephrine (mg/min)",
                "drugrate": "0.5",
                "patientweight": "",  # no weight on the row
            }
        ],
    )
    vaso = [
        event
        for event in converted["stays"][0]["charts"]
        if event["code"] == c.VASOPRESSOR_CODE
    ]
    assert len(vaso) == 1
    assert vaso[0]["valuenum"] is None


def test_volume_rate_pressor_unknown_without_concentration() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        infusion_drug=[
            {
                "patientunitstayid": "1",
                "infusionoffset": "30",
                "drugname": "Norepinephrine (ml/hr)",
                "drugrate": "10",
                "patientweight": "80",
            }
        ],
    )
    vaso = [
        event
        for event in converted["stays"][0]["charts"]
        if event["code"] == c.VASOPRESSOR_CODE
    ]
    assert len(vaso) == 1
    assert vaso[0]["valuenum"] is None
    assert vaso[0]["extras"]["pressor"]["reason"] == "volume_rate_without_concentration"


def test_mcg_min_pressor_with_valid_weight_converted_and_normalized_unit() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        infusion_drug=[
            {
                "patientunitstayid": "1",
                "infusionoffset": "30",
                "drugname": "Norepinephrine (mcg/min)",
                "drugrate": "5",
                "patientweight": "50",
            }
        ],
    )
    vaso = [
        event
        for event in converted["stays"][0]["charts"]
        if event["code"] == c.VASOPRESSOR_CODE
    ]
    assert len(vaso) == 1
    assert vaso[0]["valuenum"] == pytest.approx(0.1)
    assert vaso[0]["unit"] == "mcg/kg/min"


def test_non_urine_intake_ignored() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        intake_output=[
            {
                "patientunitstayid": "1",
                "intakeoutputoffset": "60",
                "celllabel": "Stool",
                "cellvaluenumeric": "200",
            }
        ],
    )
    assert converted["coverage"]["concepts"].get(c.URINE_OUTPUT, 0) == 0


def test_nurse_score_glasgow_coma_scale_value_emits_gcs() -> None:
    """CURIE-047: Score (Glasgow Coma Scale) / Value is a numeric total."""
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[
            {
                "patientunitstayid": "1",
                "nursingchartoffset": "40",
                "nursingchartcelltypevallabel": "Score (Glasgow Coma Scale)",
                "nursingchartcelltypevalname": "Value",
                "nursingchartvalue": "12",
            }
        ],
    )
    assert converted["coverage"]["concepts"][c.GCS_TOTAL] == 1
    codes = {e["code"] for e in converted["stays"][0]["charts"]}
    assert c.GCS_LOINC in codes


def test_nurse_gcs_components_sum_to_total() -> None:
    """CURIE-047: Eyes/Verbal/Motor at one offset become a summed GCS total."""
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[
            {
                "patientunitstayid": "1",
                "nursingchartoffset": "50",
                "nursingchartcelltypevallabel": "Glasgow coma score",
                "nursingchartcelltypevalname": "Eyes",
                "nursingchartvalue": "4",
            },
            {
                "patientunitstayid": "1",
                "nursingchartoffset": "50",
                "nursingchartcelltypevallabel": "Glasgow coma score",
                "nursingchartcelltypevalname": "Verbal",
                "nursingchartvalue": "5",
            },
            {
                "patientunitstayid": "1",
                "nursingchartoffset": "50",
                "nursingchartcelltypevallabel": "Glasgow coma score",
                "nursingchartcelltypevalname": "Motor",
                "nursingchartvalue": "6",
            },
        ],
    )
    charts = converted["stays"][0]["charts"]
    gcs = [e for e in charts if e["code"] == c.GCS_LOINC]
    assert gcs
    assert gcs[0]["valuenum"] == 15.0


def test_physical_exam_gcs_path_emits_components_and_sum() -> None:
    """CURIE-047: physicalExam neurologic/gcs/... paths feed CNS."""
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        physical_exam=[
            {
                "patientunitstayid": "1",
                "physicalexamoffset": "60",
                "physicalexampath": "notes/Progress Notes/Neurologic/GCS/Eyes Score/4",
                "physicalexamvalue": "4",
                "physicalexamtext": "Eyes Score/4",
            },
            {
                "patientunitstayid": "1",
                "physicalexamoffset": "60",
                "physicalexampath": "notes/Progress Notes/Neurologic/GCS/Verbal Score/5",
                "physicalexamvalue": "5",
                "physicalexamtext": "Verbal Score/5",
            },
            {
                "patientunitstayid": "1",
                "physicalexamoffset": "60",
                "physicalexampath": "notes/Progress Notes/Neurologic/GCS/Motor Score/6",
                "physicalexamvalue": "6",
                "physicalexamtext": "Motor Score/6",
            },
        ],
    )
    gcs = [e for e in converted["stays"][0]["charts"] if e["code"] == c.GCS_LOINC]
    assert gcs
    assert gcs[0]["valuenum"] == 15.0


def test_physical_exam_gcs_total_in_path() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        physical_exam=[
            {
                "patientunitstayid": "1",
                "physicalexamoffset": "70",
                "physicalexampath": "notes/Progress Notes/Neurologic/GCS/14 14 14",
                "physicalexamvalue": "",
                "physicalexamtext": "14 14 14",
            },
        ],
    )
    assert converted["coverage"]["concepts"][c.GCS_TOTAL] >= 1
    codes = {e["code"] for e in converted["stays"][0]["charts"]}
    assert c.GCS_LOINC in codes


def test_eicu_pao2_lab_emits() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[
            {
                "patientunitstayid": "1",
                "labname": "paO2",
                "labresult": "62",
                "labresultoffset": "60",
                "labmeasurenamesystem": "mmHg",
            }
        ],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
    )
    assert converted["coverage"]["concepts"][c.PAO2] == 1
    codes = {e["code"] for e in converted["stays"][0]["labs"]}
    assert c.PAO2_LOINC in codes


def test_respiratory_charting_fio2_percent_label() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        respiratory_charting=[
            {
                "patientunitstayid": "1",
                "respchartoffset": "30",
                "respcharttypecat": "respFlowSettings",
                "respchartvaluelabel": "FIO2 (%)",
                "respchartvalue": "45",
            }
        ],
    )
    assert converted["coverage"]["concepts"][c.FIO2] == 1


def test_eicu_pao2_with_fio2_scores_respiration() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[
            {
                "patientunitstayid": "1",
                "labname": "paO2",
                "labresult": "55",
                "labresultoffset": "90",
                "labmeasurenamesystem": "mmHg",
            }
        ],
        vital_periodic=[],
        vital_aperiodic=[],
        nurse_charting=[],
        respiratory_charting=[
            {
                "patientunitstayid": "1",
                "respchartoffset": "60",
                "respcharttypecat": "respFlowSettings",
                "respchartvaluelabel": "FiO2",
                "respchartvalue": "40",
            }
        ],
    )
    result = replay_stay(converted["stays"][0])
    assert not result.errors
    missing = result.snapshots[-1].get("missing_components") or []
    assert "respiration" not in missing


# --- MAP derivation: SBP+DBP pairable only (plan B req 8) ----------------------

def _vital_aperiodic_row(**overrides) -> dict[str, str]:
    row = {
        "patientunitstayid": "1",
        "observationoffset": "100",
        "noninvasivesystolic": "",
        "noninvasivediastolic": "",
        "noninvasivemean": "",
    }
    row.update(overrides)
    return row


def _charts_of(converted) -> list[dict]:
    return converted["stays"][0]["charts"]


def test_map_derived_when_sbp_and_dbp_paired_and_mean_missing() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[
            _vital_aperiodic_row(noninvasivesystolic="120", noninvasivediastolic="80")
        ],
        nurse_charting=[],
    )
    maps = [ev for ev in _charts_of(converted) if ev["code"] == c.MAP_LOINC]
    assert len(maps) == 1
    # MAP = (SBP + 2*DBP) / 3
    assert maps[0]["valuenum"] == pytest.approx((120 + 2 * 80) / 3)
    assert maps[0]["itemid"] == "nibp-derived-map"


def test_map_not_derived_when_only_sbp_present() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[_vital_aperiodic_row(noninvasivesystolic="120")],
        nurse_charting=[],
    )
    assert not [ev for ev in _charts_of(converted) if ev["code"] == c.MAP_LOINC]


def test_map_not_derived_when_only_dbp_present() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[_vital_aperiodic_row(noninvasivediastolic="80")],
        nurse_charting=[],
    )
    assert not [ev for ev in _charts_of(converted) if ev["code"] == c.MAP_LOINC]


def test_documented_mean_wins_over_derivation() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[],
        vital_aperiodic=[
            _vital_aperiodic_row(
                noninvasivesystolic="120",
                noninvasivediastolic="80",
                noninvasivemean="77",
            )
        ],
        nurse_charting=[],
    )
    maps = [ev for ev in _charts_of(converted) if ev["code"] == c.MAP_LOINC]
    assert len(maps) == 1
    assert maps[0]["valuenum"] == 77.0
    assert maps[0]["itemid"] == "nibp-mean"


def test_map_derivation_never_uses_pulmonary_artery_columns() -> None:
    # PA mean is not systemic MAP; systemic SBP/DBP absent → nothing to derive.
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[
            {
                "patientunitstayid": "1",
                "observationoffset": "100",
                "pasystolic": "30",
                "padiastolic": "15",
                "pamean": "20",
                "systemicsystolic": "",
                "systemicdiastolic": "",
                "systemicmean": "",
            }
        ],
        vital_aperiodic=[],
        nurse_charting=[],
    )
    assert not [ev for ev in _charts_of(converted) if ev["code"] == c.MAP_LOINC]


def test_map_derivation_vital_periodic_systemic_pair() -> None:
    converted = convert_eicu_rows(
        patients=[_patient()],
        labs=[],
        vital_periodic=[
            {
                "patientunitstayid": "1",
                "observationoffset": "100",
                "systemicsystolic": "150",
                "systemicdiastolic": "90",
                "systemicmean": "",
            }
        ],
        vital_aperiodic=[],
        nurse_charting=[],
    )
    maps = [ev for ev in _charts_of(converted) if ev["code"] == c.MAP_LOINC]
    assert len(maps) == 1
    assert maps[0]["valuenum"] == pytest.approx((150 + 2 * 90) / 3)
    assert maps[0]["itemid"] == "systemic-derived-map"
