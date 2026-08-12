"""Site calibration profiles and production drift monitoring (CURIE-035)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class SiteProfile:
    site_id: str
    parent_bundle_id: str
    version: str
    approver: str
    evidence_window_start: str
    evidence_window_end: str
    rollback_target_version: str
    # Locked test period — must not be used for tuning.
    locked_test_start: str | None = None
    locked_test_end: str | None = None
    thresholds: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "parent_bundle_id": self.parent_bundle_id,
            "version": self.version,
            "approver": self.approver,
            "evidence_window_start": self.evidence_window_start,
            "evidence_window_end": self.evidence_window_end,
            "rollback_target_version": self.rollback_target_version,
            "locked_test_start": self.locked_test_start,
            "locked_test_end": self.locked_test_end,
            "thresholds": dict(self.thresholds),
        }


@dataclass
class DriftBaseline:
    version: str
    missingness_rate: float
    page_rate: float
    mean_score: float
    unit_error_rate: float = 0.0
    arrival_delay_p95_s: float = 0.0


@dataclass
class DriftAlarm:
    level: str  # warning | critical
    metric: str
    observed: float
    baseline: float
    message: str
    mutates_rules: bool = False


def assert_not_tuning_on_locked_test(
    profile: SiteProfile, *, as_of: str | None = None
) -> None:
    """Fail closed if a site profile is tuned against its locked test period."""
    if not profile.locked_test_start or not profile.locked_test_end:
        return
    when = as_of or datetime.now(UTC).date().isoformat()
    if profile.locked_test_start <= when <= profile.locked_test_end:
        raise ValueError(
            f"site profile {profile.site_id!r} cannot be selected/tuned during "
            f"locked test period {profile.locked_test_start}..{profile.locked_test_end}"
        )


def evaluate_drift(
    *,
    baseline: DriftBaseline,
    observed: dict[str, float],
    warning_factor: float = 1.5,
    critical_factor: float = 2.5,
) -> list[DriftAlarm]:
    """Compare observed site metrics to a versioned baseline. Never mutates rules."""
    alarms: list[DriftAlarm] = []
    checks = {
        "missingness_rate": baseline.missingness_rate,
        "page_rate": baseline.page_rate,
        "mean_score": baseline.mean_score,
        "unit_error_rate": baseline.unit_error_rate,
        "arrival_delay_p95_s": baseline.arrival_delay_p95_s,
    }
    for metric, base in checks.items():
        obs = float(observed.get(metric, 0.0))
        if base <= 0:
            if obs > 0 and metric in {"unit_error_rate", "missingness_rate"}:
                alarms.append(
                    DriftAlarm(
                        level="warning",
                        metric=metric,
                        observed=obs,
                        baseline=base,
                        message=f"{metric} rose above zero baseline",
                    )
                )
            continue
        ratio = obs / base if base else 0.0
        if ratio >= critical_factor:
            alarms.append(
                DriftAlarm(
                    level="critical",
                    metric=metric,
                    observed=obs,
                    baseline=base,
                    message=f"{metric} {obs:.4g} is {ratio:.2f}× baseline {base:.4g}",
                )
            )
        elif ratio >= warning_factor:
            alarms.append(
                DriftAlarm(
                    level="warning",
                    metric=metric,
                    observed=obs,
                    baseline=base,
                    message=f"{metric} {obs:.4g} is {ratio:.2f}× baseline {base:.4g}",
                )
            )
    return alarms


def drift_report(
    *,
    site_id: str,
    baseline: DriftBaseline,
    alarms: list[DriftAlarm],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "site_id": site_id,
        "baseline_version": baseline.version,
        "generated_at": datetime.now(UTC).isoformat(),
        "alarms": [
            {
                "level": a.level,
                "metric": a.metric,
                "observed": a.observed,
                "baseline": a.baseline,
                "message": a.message,
                "mutates_rules": a.mutates_rules,
            }
            for a in alarms
        ],
        "notes": [
            "Drift alarms are observational — they do not automatically mutate clinical rules.",
            "Operating-point selection is separate from probability calibration terminology.",
        ],
    }
