from datetime import UTC, datetime

from eval.sepsis3.phenotype import (
    InfectionEvent,
    Sepsis3Input,
    evaluate_sepsis3,
)

AS_OF = datetime(2024, 1, 1, 12, tzinfo=UTC)


def _infection() -> list[InfectionEvent]:
    return [InfectionEvent(AS_OF, "culture", "Procedure/bcx")]


def test_missing_baseline_remains_insufficient_under_strict_policy() -> None:
    result = evaluate_sepsis3(
        Sepsis3Input(as_of=AS_OF, current_sofa=2, baseline_sofa=None, infection_events=_infection())
    )
    assert result.status == "insufficient_data"
    assert result.missing_inputs == ["baseline_sofa"]


def test_authorized_zero_baseline_meets_delta_and_records_provenance() -> None:
    result = evaluate_sepsis3(
        Sepsis3Input(
            as_of=AS_OF,
            current_sofa=2,
            baseline_sofa=None,
            infection_events=_infection(),
            baseline_policy="assume_zero_if_no_known_dysfunction",
            no_known_preexisting_dysfunction=True,
            baseline_evidence_id="protocol/no-known-dysfunction",
        )
    )
    assert result.status == "met"
    assert result.sofa_delta == 2
    assert result.baseline_assumed is True
    assert result.baseline_source == "protocol/no-known-dysfunction"
    assert "baseline_assumed_zero" in result.criteria_met
    assert "protocol/no-known-dysfunction" in result.evidence_ids


def test_zero_baseline_policy_requires_explicit_no_dysfunction_flag() -> None:
    result = evaluate_sepsis3(
        Sepsis3Input(
            as_of=AS_OF,
            current_sofa=2,
            baseline_sofa=None,
            infection_events=_infection(),
            baseline_policy="assume_zero_if_no_known_dysfunction",
        )
    )
    assert result.status == "insufficient_data"
    assert "baseline_sofa" in result.missing_inputs


def test_known_preexisting_dysfunction_without_acute_rise_is_not_sepsis() -> None:
    result = evaluate_sepsis3(
        Sepsis3Input(
            as_of=AS_OF,
            current_sofa=2,
            baseline_sofa=2,
            infection_events=_infection(),
        )
    )
    assert result.status == "not_met"
    assert "pre_existing_dysfunction_without_acute_rise" in result.criteria_failed
    assert result.met is False
