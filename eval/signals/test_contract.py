"""CURIE-010: shared clinical-signal contract."""

from __future__ import annotations

from datetime import UTC, datetime

from eval.aki.scoring import AkiInput, compute_aki_score, tier_for_aki_score
from eval.sepsis3.phenotype import InfectionEvent, Sepsis3Input, evaluate_sepsis3
from eval.signals.contract import (
    SIGNAL_CONTRACT_VERSION,
    ClinicalSignal,
    SignalKind,
    signal_from_aki,
    signal_from_alert_record,
    signal_from_sepsis3,
    signal_from_sofa,
)
from eval.sofa.scoring import (
    ScoreCompleteness,
    SofaComponentInput,
    SofaComponentName,
    SofaScoreResult,
    compute_sofa_score,
    tier_for_score,
)

T0 = datetime(2024, 7, 1, 12, 0, tzinfo=UTC)


def _sofa_result() -> SofaScoreResult:
    return compute_sofa_score(
        patient_id="Patient/s",
        event_time=T0,
        inputs=[
            SofaComponentInput(
                name=SofaComponentName.COAGULATION,
                platelets_10e9_l=40,
                evidence_ids=["Observation/plt"],
            ),
            SofaComponentInput(
                name=SofaComponentName.RENAL,
                creatinine_mg_dl=3.5,
                evidence_ids=["Observation/cr"],
            ),
            SofaComponentInput(
                name=SofaComponentName.LIVER,
                bilirubin_mg_dl=4.0,
                evidence_ids=["Observation/bili"],
            ),
        ],
        encounter_id="Encounter/1",
        rule_bundle_id="sepsis-sofa",
        rule_version="0.3.0",
        min_components_required=3,
    )


def test_sofa_and_aki_share_top_level_schema_keys() -> None:
    sofa = _sofa_result()
    sofa_sig = signal_from_sofa(
        alert_id="alert-sofa",
        score_result=sofa,
        severity=tier_for_score(sofa.total_score).value,
    )
    aki = compute_aki_score(
        patient_id="Patient/a",
        event_time=T0,
        inputs=AkiInput(
            creatinine_mg_dl=2.2,
            baseline_creatinine_mg_dl=1.0,
            evidence_ids=["Observation/cr-now"],
            baseline_evidence_ids=["Observation/cr-base"],
        ),
        encounter_id="Encounter/2",
    )
    aki_sig = signal_from_aki(
        alert_id="alert-aki",
        score_result=aki,
        severity=tier_for_aki_score(aki.total_score).value,
        onset_time=T0,
        criteria_met=["cr_ge_2_0x_baseline"],
    )
    from eval.respiratory.scoring import RespInput, compute_resp_score, tier_for_resp_score
    from eval.signals.contract import signal_from_respiratory

    resp = compute_resp_score(
        patient_id="Patient/r",
        event_time=T0,
        inputs=RespInput(spo2_fio2=220, respiratory_rate=28, oxygen_device="high_flow"),
        encounter_id="Encounter/3",
    )
    resp_sig = signal_from_respiratory(
        alert_id="alert-resp",
        score_result=resp,
        severity=tier_for_resp_score(resp.total_score).value,
    )

    sofa_keys = set(sofa_sig.model_dump().keys())
    aki_keys = set(aki_sig.model_dump().keys())
    resp_keys = set(resp_sig.model_dump().keys())
    assert sofa_keys == aki_keys == resp_keys
    required = {
        "schema_version",
        "signal_id",
        "signal_type",
        "signal_kind",
        "patient_id",
        "score",
        "completeness",
        "severity",
        "onset_time",
        "required_inputs",
        "missing_inputs",
        "evidence_ids",
        "exclusions",
        "rule_bundle_id",
        "rule_version",
        "rule_bundle_hash",
        "resolution_state",
        "components",
    }
    assert required <= sofa_keys
    assert sofa_sig.schema_version == SIGNAL_CONTRACT_VERSION
    assert sofa_sig.signal_type == "sofa-deterioration"
    assert sofa_sig.signal_kind == SignalKind.RISK
    assert aki_sig.signal_type == "aki"
    assert aki_sig.stage == 2


def test_sepsis3_projects_as_phenotype() -> None:
    result = evaluate_sepsis3(
        Sepsis3Input(
            as_of=T0,
            current_sofa=4,
            baseline_sofa=1,
            infection_events=[
                InfectionEvent(
                    event_time=T0,
                    kind="culture",
                    evidence_id="Procedure/bcx",
                )
            ],
        )
    )
    sig = signal_from_sepsis3(
        alert_id="alert-s3",
        patient_id="Patient/s3",
        result=result,
        event_time=T0,
    )
    assert sig.signal_kind == SignalKind.PHENOTYPE
    assert sig.signal_type == "sepsis-3"
    assert sig.score == 1
    assert "infection_culture" in sig.criteria_met


def test_unknown_signal_type_round_trips_without_special_casing() -> None:
    raw = {
        "alert_id": "alert-future-1",
        "patient_id": "Patient/x",
        "indicator": "respiratory-deterioration",
        "signal_kind": "risk",
        "event_time": T0,
        "score": 3,
        "completeness": "partial",
        "tier": "watch",
        "missing_components": ["abg"],
        "evidence_ids": ["Observation/spo2"],
        "rule_bundle_id": "resp-v0",
        "rule_version": "0.1.0",
        "component_breakdown": [
            {
                "name": "spo2_fio2",
                "points": 3,
                "missing": False,
                "evidence_ids": ["Observation/spo2"],
            }
        ],
    }
    sig = signal_from_alert_record(raw)
    assert sig.signal_type == "respiratory-deterioration"
    assert isinstance(sig, ClinicalSignal)
    fields = sig.to_alert_fields()
    assert fields["indicator"] == "respiratory-deterioration"
    assert fields["signal"]["signal_type"] == "respiratory-deterioration"
    assert fields["missing_components"] == ["abg"]


def test_insufficient_sofa_keeps_completeness() -> None:
    result = SofaScoreResult(
        patient_id="Patient/p",
        event_time=T0,
        total_score=None,
        completeness=ScoreCompleteness.INSUFFICIENT_DATA,
        components=[],
        missing_components=[],
        evidence_ids=[],
        rule_bundle_id="sepsis-sofa",
        rule_version="0.3.0",
    )
    sig = signal_from_sofa(alert_id="a", score_result=result, severity="none")
    assert sig.completeness == "insufficient_data"
    assert sig.score is None
