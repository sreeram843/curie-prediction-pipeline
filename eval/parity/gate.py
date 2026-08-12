"""CURIE-007 cross-runtime parity gate.

Runs Python reference checks against shared fixtures. CI also runs the matching
Java Surefire tests; ``make parity`` / ``publish_rules.sh`` require this gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from eval.aki.scoring import AkiInput, compute_aki_score
from eval.fixtures.test_golden_sofa import GOLDEN as SOFA_GOLDEN
from eval.indicators.registry import governance_config_from_bundle, load_rule_bundle
from eval.replay_harness.governance import GovernanceConfig, PatientGovState, evaluate
from eval.sofa.scoring import (
    SofaComponentInput,
    SofaComponentName,
    compute_sofa_score,
    tier_for_score,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "eval" / "fixtures" / "golden"
PARITY = FIXTURES / "cross_runtime_parity.v1.json"
GOV_PARITY = FIXTURES / "governance_parity.v1.json"


def _load_parity() -> dict:
    return json.loads(PARITY.read_text())


def count_fixtures(data: dict | None = None) -> dict[str, int]:
    data = data or _load_parity()
    sofa = json.loads(SOFA_GOLDEN.read_text())
    gov_cfg = json.loads(GOV_PARITY.read_text())
    return {
        "sofa_cases": len(sofa.get("cases") or []),
        "aki_cases": len(data.get("aki_cases") or []),
        "governance_decisions": len(data.get("governance_decisions") or []),
        "governance_config_fields": len(gov_cfg.get("expect") or {}),
    }


def _gov_config(raw: dict) -> GovernanceConfig:
    base = GovernanceConfig()
    for key, value in raw.items():
        if key in ("suppression_flags", "interruptive_tiers", "passive_tiers"):
            setattr(base, key, set(value))
        else:
            setattr(base, key, value)
    return base


def check_sofa() -> list[str]:
    mismatches: list[str] = []
    data = json.loads(SOFA_GOLDEN.read_text())
    bundle = load_rule_bundle(data["rule_bundle_id"], data["rule_version"])
    from datetime import UTC, datetime

    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    for case in data["cases"]:
        inputs = []
        for name in SofaComponentName:
            if name.value not in case["inputs"]:
                continue
            inputs.append(
                SofaComponentInput.model_validate(
                    {"name": name.value, **case["inputs"][name.value]}
                )
            )
        result = compute_sofa_score(
            patient_id=f"Patient/golden-{case['id']}",
            event_time=t0,
            inputs=inputs,
            rule_bundle_id=bundle["bundle_id"],
            rule_version=bundle["version"],
            rule_bundle=bundle,
        )
        expect = case["expect"]
        if result.total_score != expect.get("total_score"):
            mismatches.append(
                f"sofa/{case['id']}: score {result.total_score} != {expect.get('total_score')}"
            )
        if result.completeness.value != expect.get("completeness"):
            mismatches.append(f"sofa/{case['id']}: completeness mismatch")
        tier = tier_for_score(result.total_score)
        if tier.value != expect.get("tier"):
            mismatches.append(f"sofa/{case['id']}: tier {tier.value} != {expect.get('tier')}")
    return mismatches


def check_aki(data: dict) -> list[str]:
    from datetime import UTC, datetime

    mismatches: list[str] = []
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    for case in data["aki_cases"]:
        raw = case["inputs"]
        result = compute_aki_score(
            patient_id=f"Patient/parity-{case['id']}",
            event_time=t0,
            inputs=AkiInput(
                creatinine_mg_dl=raw.get("creatinine_mg_dl"),
                baseline_creatinine_mg_dl=raw.get("baseline_creatinine_mg_dl"),
                urine_ml_kg_h=raw.get("urine_ml_kg_h"),
                urine_duration_hours=raw.get("urine_duration_hours"),
            ),
            rule_bundle_id="aki-kdigo",
            rule_version="0.3.0",
        )
        expect = case["expect"]
        if result.stage != expect.get("stage"):
            mismatches.append(f"aki/{case['id']}: stage mismatch")
        if result.total_score != expect.get("total_score"):
            mismatches.append(f"aki/{case['id']}: score mismatch")
        if result.completeness.value != expect.get("completeness"):
            mismatches.append(f"aki/{case['id']}: completeness mismatch")
        if "missing_components" in expect:
            missing = set(result.missing_components)
            if missing != set(expect["missing_components"]):
                mismatches.append(f"aki/{case['id']}: missing_components {missing}")
        if "creatinine_stage" in expect and result.creatinine_stage != expect["creatinine_stage"]:
            mismatches.append(f"aki/{case['id']}: creatinine_stage mismatch")
        if "urine_stage" in expect and result.urine_stage != expect["urine_stage"]:
            mismatches.append(f"aki/{case['id']}: urine_stage mismatch")
    return mismatches


def check_governance(data: dict) -> list[str]:
    mismatches: list[str] = []
    for case in data["governance_decisions"]:
        state = PatientGovState()
        config = _gov_config(case["config"])
        for alert, expect in zip(case["alerts"], case["expect"], strict=True):
            d = evaluate(dict(alert), state, config)
            if d.emit != expect["emit"]:
                mismatches.append(f"gov/{case['id']}: emit {d.emit} != {expect['emit']}")
            if d.reason != expect["reason"]:
                mismatches.append(
                    f"gov/{case['id']}: reason {d.reason!r} != {expect['reason']!r}"
                )
            if d.routing != expect["routing"]:
                mismatches.append(
                    f"gov/{case['id']}: routing {d.routing!r} != {expect['routing']!r}"
                )
    return mismatches


def check_governance_config_parity() -> list[str]:
    data = json.loads(GOV_PARITY.read_text())
    knobs = governance_config_from_bundle(data["bundle"])
    mismatches: list[str] = []
    for key, value in data["expect"].items():
        got = knobs[key]
        if isinstance(value, list):
            if set(got) != set(value):
                mismatches.append(f"gov-config/{key}: {got} != {value}")
        elif got != value:
            mismatches.append(f"gov-config/{key}: {got} != {value}")
    return mismatches


def run_parity_gate() -> dict:
    data = _load_parity()
    counts = count_fixtures(data)
    mismatches = (
        check_sofa()
        + check_aki(data)
        + check_governance(data)
        + check_governance_config_parity()
    )
    total = sum(counts.values())
    ok = len(mismatches) == 0 and total > 0
    return {
        "ok": ok,
        "fixture_counts": counts,
        "fixture_total": total,
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
    }


def main(argv: list[str] | None = None) -> int:
    report = run_parity_gate()
    print(
        f"PARITY_OK={str(report['ok']).lower()} "
        f"fixtures={report['fixture_total']} "
        f"mismatches={report['mismatch_count']}"
    )
    print(json.dumps(report["fixture_counts"], indent=2))
    for m in report["mismatches"]:
        print(f"MISMATCH: {m}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
