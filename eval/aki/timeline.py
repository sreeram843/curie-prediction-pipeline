"""Stateful KDIGO AKI timelines (CURIE-009).

Prototype only — not clinically validated.

Baseline selection (v1.0.0)
---------------------------
At evaluation time ``t`` with usable creatinine observations:

- **Current Cr** — latest observation with ``event_time <= t`` after
  applying corrections (same ``evidence_id`` replaced by later
  ``corrected`` / ``amended``).
- **48h reference** — minimum Cr in ``[t - 48h, t]``. Used for the
  absolute rise rule: ``current - ref_48h >= 0.3``.
- **7d baseline** — minimum Cr among observations in ``[t - 7d, t]``
  excluding the current sample when older values exist. Used for ratio
  rules (1.5× / 2.0× / 3.0×). Explicit ``as_baseline`` tags are retained
  in history like any other value.

Urine output
------------
- Preferred: raw volume (mL) over an interval plus patient weight (kg).
  Mean rate for a window of length W hours ending at ``t`` is
  ``sum(volume in window) / (weight_kg * W)``.
- Legacy: pre-normalized ``mL/kg/h`` segments with ``duration_hours``
  ending at the observation time.
- Missing weight with only volume inputs → UO path not staged (listed
  in ``missing_components``); creatinine path still evaluates.
- Anuria lasting ≥ 12h → stage 3.

Exclusions / RRT
----------------
- ``esrd`` without ``rrt_initiated`` → status ``excluded`` (never a
  reassuring stage 0 from chronic ESRD alone).
- ``rrt_initiated`` → stage 3 via criterion ``rrt``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from eval.aki.scoring import (
    AkiComponentScore,
    AkiInputName,
    AkiScoreResult,
)
from eval.sofa.scoring import ScoreCompleteness

TIMELINE_VERSION = "1.0.0"
WINDOW_48H = timedelta(hours=48)
WINDOW_7D = timedelta(days=7)
_STAGE_TO_SCORE = {0: 0, 1: 2, 2: 4, 3: 6}


@dataclass(frozen=True)
class CreatinineObs:
    event_time: datetime
    value_mg_dl: float
    evidence_id: str
    status: str = "final"
    as_baseline: bool = False


@dataclass(frozen=True)
class UrineObs:
    """Urine segment ending at ``end_time``."""

    end_time: datetime
    evidence_id: str
    volume_ml: float | None = None
    duration_hours: float | None = None
    ml_kg_h: float | None = None
    anuria: bool = False


@dataclass(frozen=True)
class WeightObs:
    event_time: datetime
    weight_kg: float
    evidence_id: str


@dataclass
class AkiTimelineState:
    """Mutable per-encounter AKI feature timeline."""

    patient_id: str = ""
    encounter_id: str | None = None
    creatinine: list[CreatinineObs] = field(default_factory=list)
    urine: list[UrineObs] = field(default_factory=list)
    weights: list[WeightObs] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)

    def reset_for_encounter(self, encounter_id: str) -> None:
        self.encounter_id = encounter_id
        self.creatinine.clear()
        self.urine.clear()
        self.weights.clear()
        self.flags.clear()

    def ingest_creatinine(self, obs: CreatinineObs) -> None:
        """Insert/replace creatinine; corrected results replace same evidence_id."""
        status = (obs.status or "final").lower()
        if status in {"entered-in-error", "cancelled", "unknown"}:
            return
        self.creatinine = [
            c for c in self.creatinine if c.evidence_id != obs.evidence_id
        ]
        self.creatinine.append(obs)
        self.creatinine.sort(key=lambda c: (c.event_time, c.evidence_id))

    def ingest_urine(self, obs: UrineObs) -> None:
        self.urine = [u for u in self.urine if u.evidence_id != obs.evidence_id]
        self.urine.append(obs)
        self.urine.sort(key=lambda u: (u.end_time, u.evidence_id))

    def ingest_weight(self, obs: WeightObs) -> None:
        if obs.weight_kg <= 0:
            return
        self.weights = [w for w in self.weights if w.evidence_id != obs.evidence_id]
        self.weights.append(obs)
        self.weights.sort(key=lambda w: (w.event_time, w.evidence_id))

    def set_flag(self, flag: str, present: bool = True) -> None:
        if present:
            self.flags.add(flag)
        else:
            self.flags.discard(flag)


@dataclass
class TimelineAkiResult:
    score: AkiScoreResult
    timeline_version: str = TIMELINE_VERSION
    criteria_met: list[str] = field(default_factory=list)
    baseline_7d_mg_dl: float | None = None
    reference_48h_mg_dl: float | None = None
    weight_kg: float | None = None
    onset_time: datetime | None = None
    status: Literal["scored", "insufficient_data", "excluded"] = "scored"


def _usable_creatinine(
    history: list[CreatinineObs], as_of: datetime
) -> list[CreatinineObs]:
    return [c for c in history if c.event_time <= as_of and c.value_mg_dl > 0]


def _min_in_closed_window(
    obs: list[CreatinineObs], start: datetime, end: datetime
) -> CreatinineObs | None:
    window = [c for c in obs if start <= c.event_time <= end]
    if not window:
        return None
    return min(window, key=lambda c: (c.value_mg_dl, c.event_time, c.evidence_id))


def _latest_weight(weights: list[WeightObs], as_of: datetime) -> WeightObs | None:
    eligible = [w for w in weights if w.event_time <= as_of and w.weight_kg > 0]
    if not eligible:
        return None
    return max(eligible, key=lambda w: (w.event_time, w.evidence_id))


def _mean_uo_rate_ml_kg_h(
    urine: list[UrineObs],
    *,
    as_of: datetime,
    window_hours: float,
    weight_kg: float | None,
) -> tuple[float | None, list[str], list[str]]:
    """Return (rate, evidence_ids, missing).

    A window is only evaluable when overlapping segment coverage is at least
    ``window_hours``. Unobserved gaps are **not** treated as zero urine.
    """
    missing: list[str] = []
    evidence: list[str] = []
    start = as_of - timedelta(hours=window_hours)
    segments = [u for u in urine if start < u.end_time <= as_of]
    if not segments:
        return None, evidence, missing

    legacy = [u for u in segments if u.ml_kg_h is not None and u.duration_hours]
    volume = [u for u in segments if u.volume_ml is not None]

    if legacy and not volume:
        total_h = 0.0
        weighted = 0.0
        for u in legacy:
            assert u.ml_kg_h is not None and u.duration_hours is not None
            seg_start = u.end_time - timedelta(hours=u.duration_hours)
            overlap_start = max(seg_start, start)
            overlap_h = (u.end_time - overlap_start).total_seconds() / 3600.0
            if overlap_h <= 0:
                continue
            weighted += u.ml_kg_h * overlap_h
            total_h += overlap_h
            evidence.append(u.evidence_id)
        if total_h + 1e-9 < window_hours:
            return None, list(dict.fromkeys(evidence)), missing
        return weighted / total_h, list(dict.fromkeys(evidence)), missing

    if volume:
        if weight_kg is None or weight_kg <= 0:
            missing.append("weight_kg")
            return None, evidence, missing
        total_ml = 0.0
        covered_h = 0.0
        for u in volume:
            assert u.volume_ml is not None
            if not u.duration_hours or u.duration_hours <= 0:
                continue
            seg_start = u.end_time - timedelta(hours=u.duration_hours)
            overlap_start = max(seg_start, start)
            if u.end_time <= overlap_start:
                continue
            overlap_h = (u.end_time - overlap_start).total_seconds() / 3600.0
            frac = overlap_h / u.duration_hours
            total_ml += u.volume_ml * max(0.0, min(1.0, frac))
            covered_h += overlap_h
            evidence.append(u.evidence_id)
        if covered_h + 1e-9 < window_hours:
            return None, list(dict.fromkeys(evidence)), missing
        rate = total_ml / (weight_kg * covered_h)
        return rate, list(dict.fromkeys(evidence)), missing

    if any(
        ((u.ml_kg_h is None) != (u.duration_hours is None))
        or ((u.volume_ml is not None) and u.duration_hours is None)
        for u in segments
    ):
        missing.append(AkiInputName.URINE_OUTPUT.value)
    return None, evidence, missing


def _anuria_hours(urine: list[UrineObs], as_of: datetime) -> tuple[float, list[str]]:
    evidence: list[str] = []
    hours = 0.0
    for u in urine:
        if not u.anuria or u.end_time > as_of:
            continue
        if u.end_time < as_of - timedelta(hours=48):
            continue
        hours += u.duration_hours or 0.0
        evidence.append(u.evidence_id)
    return hours, list(dict.fromkeys(evidence))


def _stage_from_uo_rates(
    *,
    rate_6: float | None,
    rate_12: float | None,
    rate_24: float | None,
    anuria_h: float,
) -> tuple[int | None, list[str]]:
    if anuria_h >= 12:
        return 3, ["anuria_ge_12h"]
    stage: int | None = None
    criteria: list[str] = []
    if rate_24 is not None and rate_24 < 0.3:
        stage = 3
        criteria.append("uo_lt_0_3_for_24h")
    elif rate_12 is not None and rate_12 < 0.5:
        stage = 2
        criteria.append("uo_lt_0_5_for_12h")
    elif rate_6 is not None and rate_6 < 0.5:
        stage = 1
        criteria.append("uo_lt_0_5_for_6h")
    elif rate_6 is not None or rate_12 is not None or rate_24 is not None:
        stage = 0
    return stage, criteria


def _creatinine_criteria(
    current: float,
    *,
    baseline_7d: float | None,
    ref_48h: float | None,
) -> tuple[int, list[str], list[str]]:
    missing: list[str] = []
    criteria: list[str] = []
    stage = 0

    if baseline_7d is None or baseline_7d <= 0:
        missing.append(AkiInputName.BASELINE_CREATININE.value)
        if current >= 4.0:
            return 3, ["cr_ge_4_0"], missing
        return 0, criteria, missing

    ratio = current / baseline_7d
    if current >= 4.0:
        stage = 3
        criteria.append("cr_ge_4_0")
    if ratio >= 3.0:
        stage = 3
        criteria.append("cr_ge_3_0x_baseline")
    elif ratio >= 2.0:
        stage = max(stage, 2)
        criteria.append("cr_ge_2_0x_baseline")
    elif ratio >= 1.5:
        stage = max(stage, 1)
        criteria.append("cr_ge_1_5x_baseline")

    if ref_48h is not None:
        delta = current - ref_48h
        if delta >= 0.3:
            stage = max(stage, 1)
            criteria.append("delta_cr_ge_0_3_within_48h")

    return stage, list(dict.fromkeys(criteria)), missing


def evaluate_aki_timeline(
    state: AkiTimelineState,
    *,
    as_of: datetime,
    rule_bundle_id: str = "aki-kdigo",
    rule_version: str = "0.4.0",
    compute_onset: bool = True,
) -> TimelineAkiResult:
    """Evaluate KDIGO stage from full histories at ``as_of``."""
    if "esrd" in state.flags and "rrt_initiated" not in state.flags:
        empty = AkiScoreResult(
            patient_id=state.patient_id,
            encounter_id=state.encounter_id,
            event_time=as_of,
            stage=None,
            creatinine_stage=None,
            urine_stage=None,
            total_score=None,
            completeness=ScoreCompleteness.INSUFFICIENT_DATA,
            components=[],
            missing_components=["esrd_exclusion"],
            evidence_ids=[],
            rule_bundle_id=rule_bundle_id,
            rule_version=rule_version,
        )
        return TimelineAkiResult(
            score=empty,
            status="excluded",
            criteria_met=["exclusion_esrd"],
        )

    cr_hist = _usable_creatinine(state.creatinine, as_of)
    current_obs = cr_hist[-1] if cr_hist else None
    current = current_obs.value_mg_dl if current_obs else None

    baseline_obs = (
        _min_in_closed_window(cr_hist, as_of - WINDOW_7D, as_of) if cr_hist else None
    )
    if current_obs and len(cr_hist) > 1:
        older = [c for c in cr_hist if c.evidence_id != current_obs.evidence_id]
        alt = _min_in_closed_window(older, as_of - WINDOW_7D, as_of)
        if alt is not None:
            baseline_obs = alt

    ref_48_obs = (
        _min_in_closed_window(cr_hist, as_of - WINDOW_48H, as_of) if cr_hist else None
    )

    baseline_7d = baseline_obs.value_mg_dl if baseline_obs else None
    ref_48h = ref_48_obs.value_mg_dl if ref_48_obs else None

    weight_obs = _latest_weight(state.weights, as_of)
    weight_kg = weight_obs.weight_kg if weight_obs else None

    rate_6, ev6, miss6 = _mean_uo_rate_ml_kg_h(
        state.urine, as_of=as_of, window_hours=6, weight_kg=weight_kg
    )
    rate_12, ev12, miss12 = _mean_uo_rate_ml_kg_h(
        state.urine, as_of=as_of, window_hours=12, weight_kg=weight_kg
    )
    rate_24, ev24, miss24 = _mean_uo_rate_ml_kg_h(
        state.urine, as_of=as_of, window_hours=24, weight_kg=weight_kg
    )
    anuria_h, anuria_ev = _anuria_hours(state.urine, as_of)
    uo_stage, uo_criteria = _stage_from_uo_rates(
        rate_6=rate_6, rate_12=rate_12, rate_24=rate_24, anuria_h=anuria_h
    )
    uo_missing = list(dict.fromkeys([*miss6, *miss12, *miss24]))

    if state.urine and uo_stage is None:
        if any(
            (u.ml_kg_h is None) != (u.duration_hours is None)
            for u in state.urine
            if u.end_time <= as_of and not u.anuria
        ):
            uo_missing.append(AkiInputName.URINE_OUTPUT.value)

    criteria: list[str] = []
    cr_stage: int | None = None
    cr_missing: list[str] = []
    evidence: list[str] = []

    if current is not None:
        cr_stage, cr_criteria, cr_missing = _creatinine_criteria(
            current, baseline_7d=baseline_7d, ref_48h=ref_48h
        )
        criteria.extend(cr_criteria)
        if current_obs:
            evidence.append(current_obs.evidence_id)
        if baseline_obs:
            evidence.append(baseline_obs.evidence_id)
        if ref_48_obs:
            evidence.append(ref_48_obs.evidence_id)

    criteria.extend(uo_criteria)
    evidence.extend([*ev6, *ev12, *ev24, *anuria_ev])
    if weight_obs and any(r is not None for r in (rate_6, rate_12, rate_24)):
        evidence.append(weight_obs.evidence_id)

    if "rrt_initiated" in state.flags:
        criteria.append("rrt")

    if current is None and uo_stage is None and "rrt_initiated" not in state.flags:
        missing = list(dict.fromkeys([AkiInputName.CREATININE.value, *uo_missing]))
        score = AkiScoreResult(
            patient_id=state.patient_id,
            encounter_id=state.encounter_id,
            event_time=as_of,
            stage=None,
            creatinine_stage=None,
            urine_stage=None,
            total_score=None,
            completeness=ScoreCompleteness.INSUFFICIENT_DATA,
            components=[
                AkiComponentScore(
                    name=AkiInputName.CREATININE.value, points=None, missing=True
                )
            ],
            missing_components=missing,
            evidence_ids=list(dict.fromkeys(evidence)),
            rule_bundle_id=rule_bundle_id,
            rule_version=rule_version,
        )
        return TimelineAkiResult(
            score=score,
            status="insufficient_data",
            weight_kg=weight_kg,
            baseline_7d_mg_dl=baseline_7d,
            reference_48h_mg_dl=ref_48h,
            criteria_met=list(dict.fromkeys(criteria)),
        )

    stages = [s for s in (cr_stage, uo_stage) if s is not None]
    if "rrt_initiated" in state.flags:
        stages.append(3)
    stage = max(stages) if stages else 0
    missing = list(dict.fromkeys([*cr_missing, *uo_missing]))
    completeness = (
        ScoreCompleteness.PARTIAL if missing else ScoreCompleteness.COMPLETE
    )

    components = [
        AkiComponentScore(
            name=AkiInputName.CREATININE.value,
            points=_STAGE_TO_SCORE[cr_stage] if cr_stage is not None else None,
            missing=current is None,
            evidence_ids=[current_obs.evidence_id] if current_obs else [],
        ),
        AkiComponentScore(
            name=AkiInputName.BASELINE_CREATININE.value,
            points=None if AkiInputName.BASELINE_CREATININE.value in missing else 0,
            missing=AkiInputName.BASELINE_CREATININE.value in missing,
            evidence_ids=[baseline_obs.evidence_id] if baseline_obs else [],
        ),
        AkiComponentScore(
            name=AkiInputName.URINE_OUTPUT.value,
            points=_STAGE_TO_SCORE[uo_stage] if uo_stage is not None else None,
            missing=AkiInputName.URINE_OUTPUT.value in missing
            or "weight_kg" in missing,
            evidence_ids=list(dict.fromkeys([*ev6, *ev12, *ev24, *anuria_ev])),
        ),
    ]

    score = AkiScoreResult(
        patient_id=state.patient_id,
        encounter_id=state.encounter_id,
        event_time=as_of,
        stage=stage,
        creatinine_stage=cr_stage,
        urine_stage=uo_stage,
        total_score=_STAGE_TO_SCORE[stage],
        completeness=completeness,
        components=components,
        missing_components=missing,
        evidence_ids=list(dict.fromkeys(evidence)),
        rule_bundle_id=rule_bundle_id,
        rule_version=rule_version,
    )

    onset = None
    if compute_onset and stage >= 1:
        onset = _find_onset(
            state,
            as_of,
            rule_bundle_id=rule_bundle_id,
            rule_version=rule_version,
        )

    return TimelineAkiResult(
        score=score,
        criteria_met=list(dict.fromkeys(criteria)),
        baseline_7d_mg_dl=baseline_7d,
        reference_48h_mg_dl=ref_48h,
        weight_kg=weight_kg,
        onset_time=onset,
        status="scored",
    )


def _find_onset(
    state: AkiTimelineState,
    as_of: datetime,
    *,
    rule_bundle_id: str,
    rule_version: str,
) -> datetime | None:
    times = sorted(
        {
            *[c.event_time for c in state.creatinine if c.event_time <= as_of],
            *[u.end_time for u in state.urine if u.end_time <= as_of],
        }
    )
    for t in times:
        result = evaluate_aki_timeline(
            state,
            as_of=t,
            rule_bundle_id=rule_bundle_id,
            rule_version=rule_version,
            compute_onset=False,
        )
        if result.score.stage is not None and result.score.stage >= 1:
            return t
    return None
