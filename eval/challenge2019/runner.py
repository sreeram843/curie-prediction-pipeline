"""Offline sepsis alert evaluation on PhysioNet Challenge 2019 archive.

Replays each stay hour-by-hour through Curie SOFA + shared governance and scores
against ``SepsisLabel`` onset (not the challenge utility function).
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eval.challenge2019.bootstrap import bootstrap_metric_cis, summarize_stay_metrics
from eval.indicators.registry import load_rule_bundle
from eval.replay_harness.gov_profiles import PROFILES, apply_gov_knobs, apply_gov_profile
from eval.replay_harness.governance import (
    GovernanceConfig,
    PatientGovState,
    evaluate,
    note_below_threshold,
)
from eval.sofa.scoring import (
    AcuityTier,
    SofaComponentInput,
    SofaComponentName,
    compute_sofa_score,
    tier_for_score,
)
from ingestion.adapters.challenge2019.loader import (
    ChallengeHour,
    iter_psv_paths,
    load_stay_hours,
    require_challenge2019_dir,
    sepsis_onset_iculos,
)


def _replay_stay(
    hours: list[ChallengeHour],
    *,
    bundle: dict,
    gov_config: GovernanceConfig,
    min_components_required: int,
) -> dict:
    stay_id = hours[0].stay_id if hours else "unknown"
    onset = sepsis_onset_iculos(hours)
    threshold = int(bundle["alert"]["naive_threshold"])
    bands = bundle["alert"].get("severity_bands")
    latest: dict[SofaComponentName, SofaComponentInput] = {}
    gov_state = PatientGovState()
    was_qualifying = False
    naive_hours: list[int] = []
    governed_hours: list[int] = []
    watch_hours: list[int] = []
    interruptive_hours: list[int] = []
    t0 = datetime(2020, 1, 1, tzinfo=UTC)

    for h in hours:
        for upd in h.inputs:
            latest[upd.name] = upd
        inputs = [latest.get(n) or SofaComponentInput(name=n) for n in SofaComponentName]
        event_time = t0 + timedelta(hours=h.iculos)
        result = compute_sofa_score(
            patient_id=f"Patient/{stay_id}",
            encounter_id=f"Encounter/{stay_id}",
            event_time=event_time,
            inputs=inputs,
            rule_bundle_id=bundle["bundle_id"],
            rule_version=bundle["version"],
            rule_bundle=bundle,
            min_components_required=min_components_required,
        )
        tier = tier_for_score(
            result.total_score, naive_threshold=threshold, severity_bands=bands
        )
        positive_components = sum(
            1 for c in result.components if not c.missing and (c.points or 0) > 0
        )
        qualifying = result.total_score is not None and tier != AcuityTier.NONE
        if was_qualifying and not qualifying:
            note_below_threshold(gov_state)
        was_qualifying = qualifying
        if not qualifying:
            evaluate(
                {
                    "score": result.total_score,
                    "tier": "none",
                    "event_time": event_time.isoformat(),
                    "patient_id": stay_id,
                    "encounter_id": f"Encounter/{stay_id}",
                    "positive_components": positive_components,
                },
                gov_state,
                gov_config,
            )
            continue
        naive_hours.append(h.iculos)
        decision = evaluate(
            {
                "score": result.total_score,
                "tier": tier.value,
                "event_time": event_time.isoformat(),
                "patient_id": stay_id,
                "encounter_id": f"Encounter/{stay_id}",
                "positive_components": positive_components,
            },
            gov_state,
            gov_config,
        )
        if decision.emit:
            governed_hours.append(h.iculos)
            if decision.routing == "interruptive":
                interruptive_hours.append(h.iculos)
            elif decision.routing == "passive":
                watch_hours.append(h.iculos)

    return {
        "stay_id": stay_id,
        "hours": len(hours),
        "sepsis": onset is not None,
        "onset_iculos": onset,
        "naive_alert_count": len(naive_hours),
        "governed_alert_count": len(governed_hours),
        "watch_alert_count": len(watch_hours),
        "interruptive_alert_count": len(interruptive_hours),
        "naive_alert_hours": naive_hours,
        "governed_alert_hours": governed_hours,
        "watch_alert_hours": watch_hours,
        "interruptive_alert_hours": interruptive_hours,
        "first_naive_iculos": naive_hours[0] if naive_hours else None,
        "first_governed_iculos": governed_hours[0] if governed_hours else None,
        "first_watch_iculos": watch_hours[0] if watch_hours else None,
        "first_interruptive_iculos": (
            interruptive_hours[0] if interruptive_hours else None
        ),
    }


def run_challenge2019_eval(
    *,
    root: Path | None = None,
    limit: int | None = 200,
    set_name: str | None = None,
    detection_grace_hours: int = 6,
    gov_profile: str = "accuracy",
    gov_knobs: dict | None = None,
    gov_config_path: Path | None = None,
    bootstrap_samples: int = 1000,
    bootstrap_seed: int = 42,
    bootstrap_alpha: float = 0.05,
    cached_stays: list[list] | None = None,
) -> dict:
    base = require_challenge2019_dir(root)
    bundle_in = load_rule_bundle("sepsis-sofa")

    frozen_meta: dict | None = None
    if gov_config_path is not None:
        frozen_meta = json.loads(Path(gov_config_path).read_text())
        knobs = frozen_meta.get("knobs") or frozen_meta
        bundle, gov_config, profile_meta = apply_gov_knobs(bundle_in, knobs)
        profile_label = frozen_meta.get("name") or frozen_meta.get("candidate_id") or "frozen"
    elif gov_knobs is not None:
        bundle, gov_config, profile_meta = apply_gov_knobs(bundle_in, gov_knobs)
        profile_label = str(
            gov_knobs.get("candidate_id") or gov_knobs.get("description") or "custom"
        )
    else:
        bundle, gov_config, profile_meta = apply_gov_profile(bundle_in, gov_profile)
        profile_label = gov_profile

    min_components = int(
        (bundle.get("score") or {}).get("min_components_required") or 3
    )

    if cached_stays is not None:
        stay_hours = cached_stays
    else:
        paths = list(iter_psv_paths(base, set_name=set_name))
        if limit is not None:
            paths = paths[:limit]
        stay_hours = []
        for path in paths:
            hours = load_stay_hours(path)
            if hours:
                stay_hours.append(hours)

    rows: list[dict] = []
    for hours in stay_hours:
        rows.append(
            _replay_stay(
                hours,
                bundle=bundle,
                gov_config=gov_config,
                min_components_required=min_components,
            )
        )

    grace = detection_grace_hours
    metrics = summarize_stay_metrics(rows, grace)
    bootstrap = bootstrap_metric_cis(
        rows,
        grace,
        n_boot=bootstrap_samples,
        seed=bootstrap_seed,
        alpha=bootstrap_alpha,
    )

    notes = [
        "Partial SOFA only (no GCS/UO/pressors in Challenge 2019).",
        "SepsisLabel onset is the challenge label, not Sepsis-3 chart review.",
        "Lead time > 0 means alert before onset.",
        "Detection sensitivity uses any governed emit (watch ∪ interruptive); "
        "interruptive_* metrics count urgent/critical pages only.",
        f"Governance profile={profile_label}: {profile_meta.get('description')}",
    ]
    if gov_config_path is not None:
        notes.append(f"Frozen gov config from {gov_config_path}.")
    if bootstrap_samples > 0:
        notes.append(
            f"Bootstrap CIs: stay-level percentile, n_boot={bootstrap_samples}, "
            f"seed={bootstrap_seed}, alpha={bootstrap_alpha}."
        )

    return {
        "dataset": "physionet-challenge-2019",
        "source": str(base),
        "stays_scored": len(rows),
        "detection_grace_hours": grace,
        "gov_profile": profile_label,
        "gov_config_path": str(gov_config_path) if gov_config_path else None,
        "gov_profile_meta": {
            "description": profile_meta.get("description"),
            "trajectory_persistence_minutes": gov_config.trajectory_persistence_minutes,
            "min_crossings": gov_config.min_crossings,
            "baseline_enabled": gov_config.baseline_enabled,
            "refractory_minutes": gov_config.refractory_minutes,
            "min_components_required": min_components,
            "naive_threshold": int(bundle["alert"]["naive_threshold"]),
            "interruptive_tiers": sorted(gov_config.interruptive_tiers),
            "passive_tiers": sorted(gov_config.passive_tiers),
            "page_gate_enabled": gov_config.page_gate_enabled,
            "page_min_crossings": gov_config.page_min_crossings,
            "page_trajectory_persistence_minutes": (
                gov_config.page_trajectory_persistence_minutes
            ),
            "page_min_score_delta": gov_config.page_min_score_delta,
            "page_min_positive_components": gov_config.page_min_positive_components,
        },
        "rule_bundle": {"id": bundle["bundle_id"], "version": bundle["version"]},
        "cohort": metrics["cohort"],
        "alerts": metrics["alerts"],
        "detection": metrics["detection"],
        "bootstrap": bootstrap,
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Curie sepsis alerts on Challenge 2019 archive"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Archive root (default: data/archive or CURIE_CHALLENGE2019_DIR)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max stays (default 200; use 0 for all)",
    )
    parser.add_argument(
        "--set",
        dest="set_name",
        default=None,
        help="Only training_setA or training_setB",
    )
    parser.add_argument(
        "--grace-hours",
        type=int,
        default=6,
        help="Count detection if first alert <= onset + grace",
    )
    parser.add_argument(
        "--gov-profile",
        default="accuracy",
        choices=sorted(PROFILES),
        help="Governance tradeoff profile (default: accuracy = best detection)",
    )
    parser.add_argument(
        "--gov-config",
        type=Path,
        default=None,
        help="Frozen governance JSON sidecar (overrides --gov-profile)",
    )
    parser.add_argument(
        "--bootstrap",
        type=int,
        default=1000,
        help="Stay-level bootstrap replicates for CIs (0 disables; default 1000)",
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=42,
        help="RNG seed for bootstrap resampling",
    )
    parser.add_argument(
        "--bootstrap-alpha",
        type=float,
        default=0.05,
        help="Two-sided CI alpha (default 0.05 → 95%% CI)",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)
    limit = None if args.limit == 0 else args.limit
    report = run_challenge2019_eval(
        root=args.root,
        limit=limit,
        set_name=args.set_name,
        detection_grace_hours=args.grace_hours,
        gov_profile=args.gov_profile,
        gov_config_path=args.gov_config,
        bootstrap_samples=args.bootstrap,
        bootstrap_seed=args.bootstrap_seed,
        bootstrap_alpha=args.bootstrap_alpha,
    )
    summary = {k: v for k, v in report.items() if k != "notes"}
    print(json.dumps({**summary, "notes": report["notes"]}, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2))
        print(f"Wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
