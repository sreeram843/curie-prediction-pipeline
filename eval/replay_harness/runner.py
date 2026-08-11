"""T2 scenario library + offline replay for alert-reduction metrics."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eval.replay_harness.governance import (
    GovernanceConfig,
    PatientGovState,
    alert_reduction_ratio,
    evaluate,
)
from eval.sofa.scoring import (
    AcuityTier,
    SofaComponentInput,
    SofaComponentName,
    compute_sofa_score,
    tier_for_score,
)

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenario_library"


@dataclass
class ScenarioEvent:
    offset_minutes: int
    inputs: list[SofaComponentInput]


@dataclass
class Scenario:
    scenario_id: str
    patient_id: str
    description: str
    events: list[ScenarioEvent]
    expected_label: str  # positive | negative | borderline


def _inp(name: SofaComponentName, **kwargs: object) -> SofaComponentInput:
    evidence = kwargs.pop("evidence_ids", None)
    data = {"name": name, **kwargs}
    if evidence is not None:
        data["evidence_ids"] = evidence
    return SofaComponentInput.model_validate(data)


def built_in_scenarios() -> list[Scenario]:
    """Deterministic T2 scenarios (no Synthea dependency)."""
    base_evidence = lambda n: [f"Observation/{n}"]  # noqa: E731
    return [
        Scenario(
            scenario_id="t2-abrupt-deterioration",
            patient_id="Patient/t2-pos-001",
            description="Rising multi-organ scores sustained over 40 minutes",
            expected_label="positive",
            events=[
                ScenarioEvent(
                    0,
                    [
                        _inp(
                            SofaComponentName.COAGULATION,
                            platelets_10e9_l=140,
                            evidence_ids=base_evidence("plt-a0"),
                        ),
                        _inp(
                            SofaComponentName.LIVER,
                            bilirubin_mg_dl=1.0,
                            evidence_ids=base_evidence("bili-a0"),
                        ),
                        _inp(
                            SofaComponentName.RENAL,
                            creatinine_mg_dl=1.0,
                            evidence_ids=base_evidence("cr-a0"),
                        ),
                    ],
                ),
                ScenarioEvent(
                    15,
                    [
                        _inp(
                            SofaComponentName.COAGULATION,
                            platelets_10e9_l=40,
                            evidence_ids=base_evidence("plt-a1"),
                        ),
                        _inp(
                            SofaComponentName.LIVER,
                            bilirubin_mg_dl=2.5,
                            evidence_ids=base_evidence("bili-a1"),
                        ),
                        _inp(
                            SofaComponentName.RENAL,
                            creatinine_mg_dl=2.1,
                            evidence_ids=base_evidence("cr-a1"),
                        ),
                    ],
                ),
                ScenarioEvent(
                    35,
                    [
                        _inp(
                            SofaComponentName.COAGULATION,
                            platelets_10e9_l=35,
                            evidence_ids=base_evidence("plt-a2"),
                        ),
                        _inp(
                            SofaComponentName.LIVER,
                            bilirubin_mg_dl=2.8,
                            evidence_ids=base_evidence("bili-a2"),
                        ),
                        _inp(
                            SofaComponentName.RENAL,
                            creatinine_mg_dl=2.4,
                            evidence_ids=base_evidence("cr-a2"),
                        ),
                        _inp(
                            SofaComponentName.CNS,
                            gcs=12,
                            evidence_ids=base_evidence("gcs-a2"),
                        ),
                    ],
                ),
                ScenarioEvent(
                    45,
                    [
                        _inp(
                            SofaComponentName.COAGULATION,
                            platelets_10e9_l=30,
                            evidence_ids=base_evidence("plt-a3"),
                        ),
                        _inp(
                            SofaComponentName.CARDIOVASCULAR,
                            map_mmhg=65,
                            evidence_ids=base_evidence("map-a3"),
                        ),
                    ],
                ),
            ],
        ),
        Scenario(
            scenario_id="t2-stable-negative",
            patient_id="Patient/t2-neg-001",
            description="Mild abnormal labs that never sustain an alertable trajectory",
            expected_label="negative",
            events=[
                ScenarioEvent(
                    0,
                    [
                        _inp(
                            SofaComponentName.RENAL,
                            creatinine_mg_dl=1.3,
                            evidence_ids=base_evidence("cr-n0"),
                        ),
                        _inp(
                            SofaComponentName.LIVER,
                            bilirubin_mg_dl=1.3,
                            evidence_ids=base_evidence("bili-n0"),
                        ),
                        _inp(
                            SofaComponentName.COAGULATION,
                            platelets_10e9_l=160,
                            evidence_ids=base_evidence("plt-n0"),
                        ),
                    ],
                ),
                ScenarioEvent(
                    20,
                    [
                        _inp(
                            SofaComponentName.RENAL,
                            creatinine_mg_dl=1.25,
                            evidence_ids=base_evidence("cr-n1"),
                        ),
                    ],
                ),
            ],
        ),
        Scenario(
            scenario_id="t2-noisy-flicker",
            patient_id="Patient/t2-bord-001",
            description="Single-tick spike then recovery — governance should suppress",
            expected_label="borderline",
            events=[
                ScenarioEvent(
                    0,
                    [
                        _inp(
                            SofaComponentName.COAGULATION,
                            platelets_10e9_l=180,
                            evidence_ids=base_evidence("plt-b0"),
                        ),
                        _inp(
                            SofaComponentName.LIVER,
                            bilirubin_mg_dl=0.9,
                            evidence_ids=base_evidence("bili-b0"),
                        ),
                        _inp(
                            SofaComponentName.RENAL,
                            creatinine_mg_dl=0.9,
                            evidence_ids=base_evidence("cr-b0"),
                        ),
                    ],
                ),
                ScenarioEvent(
                    5,
                    [
                        _inp(
                            SofaComponentName.COAGULATION,
                            platelets_10e9_l=45,
                            evidence_ids=base_evidence("plt-b1"),
                        ),
                        _inp(
                            SofaComponentName.LIVER,
                            bilirubin_mg_dl=2.2,
                            evidence_ids=base_evidence("bili-b1"),
                        ),
                        _inp(
                            SofaComponentName.RENAL,
                            creatinine_mg_dl=2.0,
                            evidence_ids=base_evidence("cr-b1"),
                        ),
                    ],
                ),
                ScenarioEvent(
                    10,
                    [
                        _inp(
                            SofaComponentName.COAGULATION,
                            platelets_10e9_l=170,
                            evidence_ids=base_evidence("plt-b2"),
                        ),
                        _inp(
                            SofaComponentName.LIVER,
                            bilirubin_mg_dl=1.0,
                            evidence_ids=base_evidence("bili-b2"),
                        ),
                        _inp(
                            SofaComponentName.RENAL,
                            creatinine_mg_dl=1.0,
                            evidence_ids=base_evidence("cr-b2"),
                        ),
                    ],
                ),
            ],
        ),
    ]


def replay_scenario(scenario: Scenario, config: GovernanceConfig | None = None) -> dict:
    config = config or GovernanceConfig(baseline_enabled=False)
    start = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    latest: dict[SofaComponentName, SofaComponentInput] = {}
    naive_alerts: list[dict] = []
    governed_alerts: list[dict] = []
    gov_state = PatientGovState()

    for event in scenario.events:
        for upd in event.inputs:
            latest[upd.name] = upd
        inputs = [latest.get(n) or SofaComponentInput(name=n) for n in SofaComponentName]
        event_time = start + timedelta(minutes=event.offset_minutes)
        result = compute_sofa_score(
            patient_id=scenario.patient_id,
            event_time=event_time,
            inputs=inputs,
            rule_bundle_id="sepsis-sofa",
            rule_version="0.1.0",
        )
        tier = tier_for_score(result.total_score)
        if result.total_score is None or tier == AcuityTier.NONE:
            continue
        alert = {
            "alert_id": f"{scenario.scenario_id}-{event.offset_minutes}",
            "patient_id": scenario.patient_id,
            "event_time": event_time.isoformat(),
            "score": result.total_score,
            "tier": tier.value,
            "completeness": result.completeness.value,
            "evidence_ids": result.evidence_ids,
            "governance_path": "naive",
        }
        naive_alerts.append(alert)
        decision = evaluate(alert, gov_state, config)
        if decision.emit:
            governed_alerts.append(decision.alert)

    return {
        "scenario_id": scenario.scenario_id,
        "expected_label": scenario.expected_label,
        "naive_alert_count": len(naive_alerts),
        "governed_alert_count": len(governed_alerts),
        "alert_reduction_ratio": alert_reduction_ratio(
            len(naive_alerts), len(governed_alerts)
        ),
        "naive_alerts": naive_alerts,
        "governed_alerts": governed_alerts,
    }


def run_all() -> dict:
    rows = [replay_scenario(s) for s in built_in_scenarios()]
    naive = sum(r["naive_alert_count"] for r in rows)
    governed = sum(r["governed_alert_count"] for r in rows)
    return {
        "scenarios": rows,
        "totals": {
            "naive_alert_count": naive,
            "governed_alert_count": governed,
            "alert_reduction_ratio": alert_reduction_ratio(naive, governed),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay T2 scenarios / alert-reduction metric")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)
    report = run_all()
    print(json.dumps(report["totals"], indent=2))
    for row in report["scenarios"]:
        print(
            f"  {row['scenario_id']}: naive={row['naive_alert_count']} "
            f"governed={row['governed_alert_count']} "
            f"ratio={row['alert_reduction_ratio']:.2f}"
        )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2))
        print(f"Wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
