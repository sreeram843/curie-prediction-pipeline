"""Tests for comparator concordance and bootstrap scaffolding."""

from __future__ import annotations

import pytest

from eval.mimic_study.bootstrap import (
    BOOTSTRAP_N_REPLICATES,
    BOOTSTRAP_SEED,
    bootstrap_percentile_ci,
    sensitivity_in_window,
)
from eval.mimic_study.comparators import (
    ComponentComparison,
    DisagreementCategory,
    StayComparison,
    summarize_concordance,
)


def test_component_disagreement_categories() -> None:
    unit = ComponentComparison(
        "cardiovascular",
        curie_points=3,
        reference_points=4,
        evidence={"curie_unit": "mcg/kg/min", "reference_unit": "mcg/kg/min",
                  "curie_event_time": "2150-01-01 01:00:00",
                  "reference_event_time": "2150-01-01 01:00:00",
                  "curie_itemid": "221906", "reference_itemid": "221906",
                  "definition_id": "sofa-cv", "reference_definition_id": "sofa-cv"},
        notes="dose conversion differs",
    )
    assert unit.classify() == DisagreementCategory.UNCLASSIFIED

    timing = ComponentComparison(
        "respiration",
        curie_points=1,
        reference_points=2,
        evidence={"curie_event_time": "2150-01-01 02:00:00",
                  "reference_event_time": "2150-01-01 02:00:00"},
    )
    assert timing.classify() == DisagreementCategory.UNCLASSIFIED

    missing = ComponentComparison(
        "liver", curie_points=0, reference_points=1, curie_missing=True
    )
    assert missing.classify() == DisagreementCategory.MISSINGNESS

    mapping = ComponentComparison(
        "coagulation",
        curie_points=1,
        reference_points=0,
        evidence={"curie_itemid": "51265", "reference_itemid": "51704"},
    )
    assert mapping.classify() == DisagreementCategory.MAPPING

    definition = ComponentComparison(
        "cns",
        curie_points=0,
        reference_points=1,
        evidence={"definition_id": "gcs-sum", "reference_definition_id": "rass-mapped"},
    )
    assert definition.classify() == DisagreementCategory.DEFINITION


def test_concordance_summary() -> None:
    stays = [
        StayComparison(
            stay_id="s1",
            components=[
                ComponentComparison("cardiovascular", 3, 3),
                ComponentComparison("respiration", 1, 2),
            ],
        ),
        StayComparison(
            stay_id="s2",
            components=[
                ComponentComparison("cardiovascular", 0, 0),
                ComponentComparison("liver", 0, 1, curie_missing=True),
            ],
        ),
    ]
    out = summarize_concordance(stays)
    assert out["stays"] == 2
    assert out["component_pairs"] == 4
    assert out["component_agreements"] == 2
    assert out["component_agreement_rate"] == 0.5
    assert out["disagreement_categories"]["missingness"] == 1
    assert out["disagreement_categories"]["unclassified"] == 1
    assert out["stay_level_agreement_rate"] == 0.0


def test_bootstrap_ci_and_seed() -> None:
    units = list(range(20))
    out = bootstrap_percentile_ci(lambda u: sum(u) / len(u), units)
    assert out["n_units"] == 20
    assert out["n_replicates"] == BOOTSTRAP_N_REPLICATES
    assert out["seed"] == BOOTSTRAP_SEED
    assert out["point"] == pytest.approx(9.5)
    assert out["lo_2p5"] <= out["point"] <= out["hi_97p5"]

    again = bootstrap_percentile_ci(lambda u: sum(u) / len(u), units)
    assert out["lo_2p5"] == again["lo_2p5"]
    assert out["hi_97p5"] == again["hi_97p5"]


def test_bootstrap_empty() -> None:
    out = bootstrap_percentile_ci(lambda u: 1.0, [])
    assert out["n_units"] == 0


def test_sensitivity_in_window() -> None:
    stays = [
        {"onset": 10 * 3600, "alert_times": [9 * 3600]},
        {"onset": 30 * 3600, "alert_times": [0.0]},
    ]
    assert sensitivity_in_window(stays) == 0.5
    with pytest.raises(ZeroDivisionError):
        sensitivity_in_window([])
