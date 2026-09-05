"""Reference-comparator scaffolding (Phase C3 / A2): disagreement classification.

Curie-vs-reference disagreements are classified into the pre-specified categories:
unit, timing, missingness, mapping, and definition. Classification is an analysis
result: nothing here mutates Curie scores to match the reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DisagreementCategory(StrEnum):
    UNIT = "unit"
    TIMING = "timing"
    MISSINGNESS = "missingness"
    MAPPING = "mapping"
    DEFINITION = "definition"
    UNCLASSIFIED = "unclassified"


@dataclass
class ComponentComparison:
    component: str
    curie_points: int | None
    reference_points: int | None
    curie_missing: bool = False
    reference_missing: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @property
    def agrees(self) -> bool:
        return self.curie_points == self.reference_points

    def classify(self) -> DisagreementCategory:
        """Classify a component-level disagreement without mutating either side."""
        if self.agrees:
            raise ValueError("classification only applies to disagreements")
        if self.curie_missing or self.reference_missing:
            return DisagreementCategory.MISSINGNESS
        if self.evidence.get("curie_unit") != self.evidence.get("reference_unit"):
            return DisagreementCategory.UNIT
        if self.evidence.get("curie_event_time") != self.evidence.get(
            "reference_event_time"
        ):
            return DisagreementCategory.TIMING
        if self.evidence.get("curie_itemid") != self.evidence.get("reference_itemid"):
            return DisagreementCategory.MAPPING
        if self.evidence.get("definition_id") != self.evidence.get(
            "reference_definition_id"
        ):
            return DisagreementCategory.DEFINITION
        return DisagreementCategory.UNCLASSIFIED


@dataclass
class StayComparison:
    stay_id: str
    components: list[ComponentComparison]
    curie_max_sofa: int | None = None
    reference_max_sofa: int | None = None

    def disagreeing_components(self) -> list[ComponentComparison]:
        return [c for c in self.components if not c.agrees]


def summarize_concordance(stays: list[StayComparison]) -> dict[str, Any]:
    """Component/stay-level concordance summary with disagreement category counts."""
    from collections import Counter

    n_stays = len(stays)
    component_agree = 0
    component_total = 0
    category_counts: Counter[str] = Counter()
    stay_agree = 0
    stay_scored = 0
    for stay in stays:
        comps = [c for c in stay.components if not (c.curie_missing and c.reference_missing)]
        if comps:
            stay_scored += 1
            if all(c.agrees for c in comps):
                stay_agree += 1
        for c in stay.components:
            if c.curie_missing and c.reference_missing:
                continue
            component_total += 1
            if c.agrees:
                component_agree += 1
            else:
                category_counts[c.classify().value] += 1
    return {
        "stays": n_stays,
        "stays_with_scorable_components": stay_scored,
        "stay_level_agreement": stay_agree,
        "stay_level_agreement_rate": stay_agree / stay_scored if stay_scored else 0.0,
        "component_pairs": component_total,
        "component_agreements": component_agree,
        "component_agreement_rate": component_agree / component_total
        if component_total
        else 0.0,
        "disagreement_categories": dict(sorted(category_counts.items())),
    }
