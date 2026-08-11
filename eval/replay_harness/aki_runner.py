"""AKI T2 replay — proves shared governance reduces naive AKI alerts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from eval.aki.scoring import AkiInput, compute_aki_score, tier_for_aki_score
from eval.indicators.registry import governance_config_from_bundle, load_rule_bundle
from eval.replay_harness.governance import (
    GovernanceConfig,
    PatientGovState,
    alert_reduction_ratio,
    evaluate,
)
from eval.sofa.scoring import AcuityTier


@dataclass
class AkiEvent:
    offset_minutes: int
    creatinine_mg_dl: float | None
    baseline_creatinine_mg_dl: float | None
    evidence_id: str
    baseline_evidence_id: str | None = None


@dataclass
class AkiScenario:
    scenario_id: str
    patient_id: str
    description: str
    expected_label: str
    events: list[AkiEvent]


def built_in_aki_scenarios() -> list[AkiScenario]:
    return [
        AkiScenario(
            scenario_id="t2-aki-rising",
            patient_id="Patient/aki-pos-001",
            description="Sustained creatinine rise over 45 minutes",
            expected_label="positive",
            events=[
                AkiEvent(0, 1.0, 1.0, "Observation/cr-a0", "Observation/cr-base"),
                AkiEvent(15, 1.5, 1.0, "Observation/cr-a1", "Observation/cr-base"),
                AkiEvent(35, 2.1, 1.0, "Observation/cr-a2", "Observation/cr-base"),
                AkiEvent(50, 2.3, 1.0, "Observation/cr-a3", "Observation/cr-base"),
            ],
        ),
        AkiScenario(
            scenario_id="t2-aki-stable",
            patient_id="Patient/aki-neg-001",
            description="Stable creatinine near baseline",
            expected_label="negative",
            events=[
                AkiEvent(0, 1.1, 1.0, "Observation/cr-n0", "Observation/cr-base"),
                AkiEvent(20, 1.15, 1.0, "Observation/cr-n1", "Observation/cr-base"),
            ],
        ),
        AkiScenario(
            scenario_id="t2-aki-flicker",
            patient_id="Patient/aki-bord-001",
            description="Single-tick spike then recovery — governance should suppress",
            expected_label="borderline",
            events=[
                AkiEvent(0, 1.0, 1.0, "Observation/cr-b0", "Observation/cr-base"),
                AkiEvent(5, 2.2, 1.0, "Observation/cr-b1", "Observation/cr-base"),
                AkiEvent(12, 1.05, 1.0, "Observation/cr-b2", "Observation/cr-base"),
            ],
        ),
    ]


def replay_aki_scenario(
    scenario: AkiScenario, config: GovernanceConfig | None = None
) -> dict:
    if config is None:
        bundle = load_rule_bundle("aki-kdigo")
        knobs = governance_config_from_bundle(bundle)
        # For reduction demo vs naive threshold, disable patient baseline gate
        # (trajectory/dedup still apply — the platform differentiator).
        config = GovernanceConfig(
            trajectory_persistence_minutes=knobs["trajectory_persistence_minutes"],
            min_crossings=knobs["min_crossings"],
            baseline_enabled=False,
            refractory_minutes=knobs["refractory_minutes"],
            suppression_flags=knobs["suppression_flags"],
            interruptive_tiers=knobs["interruptive_tiers"],
            passive_tiers=knobs["passive_tiers"],
        )

    start = datetime(2024, 2, 1, 9, 0, tzinfo=UTC)
    naive_alerts: list[dict] = []
    governed_alerts: list[dict] = []
    gov_state = PatientGovState()
    threshold = int(load_rule_bundle("aki-kdigo")["alert"]["naive_threshold"])

    for event in scenario.events:
        event_time = start + timedelta(minutes=event.offset_minutes)
        result = compute_aki_score(
            patient_id=scenario.patient_id,
            event_time=event_time,
            inputs=AkiInput(
                creatinine_mg_dl=event.creatinine_mg_dl,
                baseline_creatinine_mg_dl=event.baseline_creatinine_mg_dl,
                evidence_ids=[event.evidence_id],
                baseline_evidence_ids=(
                    [event.baseline_evidence_id] if event.baseline_evidence_id else []
                ),
            ),
        )
        tier = tier_for_aki_score(result.total_score, naive_threshold=threshold)
        if result.total_score is None or tier == AcuityTier.NONE:
            continue
        alert = {
            "alert_id": f"{scenario.scenario_id}-{event.offset_minutes}",
            "patient_id": scenario.patient_id,
            "indicator": "aki",
            "event_time": event_time.isoformat(),
            "score": result.total_score,
            "tier": tier.value,
            "completeness": result.completeness.value,
            "evidence_ids": result.evidence_ids,
            "governance_path": "naive",
            "rule_bundle_id": result.rule_bundle_id,
            "rule_version": result.rule_version,
        }
        naive_alerts.append(alert)
        decision = evaluate(alert, gov_state, config)
        if decision.emit:
            governed_alerts.append(decision.alert)

    return {
        "scenario_id": scenario.scenario_id,
        "expected_label": scenario.expected_label,
        "indicator": "aki",
        "naive_alert_count": len(naive_alerts),
        "governed_alert_count": len(governed_alerts),
        "alert_reduction_ratio": alert_reduction_ratio(
            len(naive_alerts), len(governed_alerts)
        ),
        "naive_alerts": naive_alerts,
        "governed_alerts": governed_alerts,
    }


def run_all_aki() -> dict:
    rows = [replay_aki_scenario(s) for s in built_in_aki_scenarios()]
    naive = sum(r["naive_alert_count"] for r in rows)
    governed = sum(r["governed_alert_count"] for r in rows)
    return {
        "indicator": "aki",
        "rule_bundle": load_rule_bundle("aki-kdigo"),
        "scenarios": rows,
        "totals": {
            "naive_alert_count": naive,
            "governed_alert_count": governed,
            "alert_reduction_ratio": alert_reduction_ratio(naive, governed),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay AKI T2 scenarios")
    parser.add_argument("--json-out", type=str, default=None)
    args = parser.parse_args(argv)
    report = run_all_aki()
    print(json.dumps(report["totals"], indent=2))
    for row in report["scenarios"]:
        print(
            f"  {row['scenario_id']}: naive={row['naive_alert_count']} "
            f"governed={row['governed_alert_count']} "
            f"ratio={row['alert_reduction_ratio']:.2f}"
        )
    if args.json_out:
        path = __import__("pathlib").Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Don't dump full rule bundle binary-loudly; keep summary
        slim = {
            "indicator": report["indicator"],
            "bundle_id": report["rule_bundle"]["bundle_id"],
            "version": report["rule_bundle"]["version"],
            "scenarios": report["scenarios"],
            "totals": report["totals"],
        }
        path.write_text(json.dumps(slim, indent=2))
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
