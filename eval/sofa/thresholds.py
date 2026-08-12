"""Load SOFA component thresholds from a rule bundle (source of truth)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CoagBand:
    points: int
    max_exclusive: float | None = None
    min_inclusive: float | None = None


@dataclass(frozen=True)
class LiverBand:
    points: int
    min_inclusive: float | None = None
    max_exclusive: float | None = None


@dataclass(frozen=True)
class CnsBand:
    points: int
    gcs_lt: int | None = None
    gcs_le: int | None = None
    gcs_eq: int | None = None


@dataclass(frozen=True)
class RenalCrBand:
    points: int
    min_inclusive: float | None = None
    max_exclusive: float | None = None


@dataclass(frozen=True)
class RenalUoBand:
    points: int
    max_exclusive: float | None = None
    min_inclusive: float | None = None


@dataclass(frozen=True)
class SofaThresholds:
    """Numeric SOFA cutoffs interpreted from rule-bundle JSON."""

    resp_p4_lt: float = 100.0
    resp_p3_lt: float = 200.0
    resp_p2_lt: float = 300.0
    resp_p1_lt: float = 400.0
    map_lt: float = 70.0
    map_points: int = 1
    dopamine_p2_max: float = 5.0
    dopamine_p3_max: float = 15.0
    epi_norepi_p3_max: float = 0.1
    unknown_pressor_points: int = 3
    coag: tuple[CoagBand, ...] = field(default_factory=tuple)
    liver: tuple[LiverBand, ...] = field(default_factory=tuple)
    cns: tuple[CnsBand, ...] = field(default_factory=tuple)
    renal_cr: tuple[RenalCrBand, ...] = field(default_factory=tuple)
    renal_uo: tuple[RenalUoBand, ...] = field(default_factory=tuple)

    @classmethod
    def from_bundle(cls, bundle: dict[str, Any] | None) -> SofaThresholds:
        if not bundle:
            return cls.defaults()
        ct = (bundle.get("score") or {}).get("component_thresholds") or {}
        if not ct:
            return cls.defaults()
        resp = ct.get("respiration") or {}
        params = resp.get("params") or {}
        cv = ct.get("cardiovascular") or {}
        cv_params = cv.get("params") or {}
        coag = tuple(
            CoagBand(
                points=int(b["points"]),
                max_exclusive=b.get("max_exclusive"),
                min_inclusive=b.get("min_inclusive"),
            )
            for b in (ct.get("coagulation") or {}).get("bands") or []
        )
        liver = tuple(
            LiverBand(
                points=int(b["points"]),
                min_inclusive=b.get("min_inclusive"),
                max_exclusive=b.get("max_exclusive"),
            )
            for b in (ct.get("liver") or {}).get("bands") or []
        )
        cns = tuple(
            CnsBand(
                points=int(b["points"]),
                gcs_lt=b.get("gcs_lt"),
                gcs_le=b.get("gcs_le"),
                gcs_eq=b.get("gcs_eq"),
            )
            for b in (ct.get("cns") or {}).get("bands") or []
        )
        renal = ct.get("renal") or {}
        renal_cr = tuple(
            RenalCrBand(
                points=int(b["points"]),
                min_inclusive=b.get("min_inclusive"),
                max_exclusive=b.get("max_exclusive"),
            )
            for b in renal.get("creatinine_mg_dl") or []
        )
        renal_uo = tuple(
            RenalUoBand(
                points=int(b["points"]),
                max_exclusive=b.get("max_exclusive"),
                min_inclusive=b.get("min_inclusive"),
            )
            for b in renal.get("urine_output_ml_day") or []
        )
        base = cls.defaults()
        return cls(
            resp_p4_lt=float(params.get("p4_ratio_lt", 100)),
            resp_p3_lt=float(params.get("p3_ratio_lt", 200)),
            resp_p2_lt=float(params.get("p2_ratio_lt", 300)),
            resp_p1_lt=float(params.get("p1_ratio_lt", 400)),
            map_lt=float(cv.get("map_mmhg_lt", cv_params.get("map_mmhg_lt", 70))),
            map_points=int(cv.get("map_mmhg_lt_70_points", 1)),
            dopamine_p2_max=float(cv_params.get("dopamine_p2_max_inclusive", 5)),
            dopamine_p3_max=float(cv_params.get("dopamine_p3_max_inclusive", 15)),
            epi_norepi_p3_max=float(cv_params.get("epi_norepi_p3_max_inclusive", 0.1)),
            unknown_pressor_points=int(cv_params.get("unknown_dose_points", 3)),
            coag=coag or base.coag,
            liver=liver or base.liver,
            cns=cns or base.cns,
            renal_cr=renal_cr or base.renal_cr,
            renal_uo=renal_uo or base.renal_uo,
        )

    @classmethod
    def defaults(cls) -> SofaThresholds:
        return cls(
            coag=(
                CoagBand(4, max_exclusive=20),
                CoagBand(3, max_exclusive=50),
                CoagBand(2, max_exclusive=100),
                CoagBand(1, max_exclusive=150),
                CoagBand(0, min_inclusive=150),
            ),
            liver=(
                LiverBand(4, min_inclusive=12.0),
                LiverBand(3, min_inclusive=6.0),
                LiverBand(2, min_inclusive=2.0),
                LiverBand(1, min_inclusive=1.2),
                LiverBand(0, max_exclusive=1.2),
            ),
            cns=(
                CnsBand(4, gcs_lt=6),
                CnsBand(3, gcs_le=9),
                CnsBand(2, gcs_le=12),
                CnsBand(1, gcs_le=14),
                CnsBand(0, gcs_eq=15),
            ),
            renal_cr=(
                RenalCrBand(4, min_inclusive=5.0),
                RenalCrBand(3, min_inclusive=3.5),
                RenalCrBand(2, min_inclusive=2.0),
                RenalCrBand(1, min_inclusive=1.2),
                RenalCrBand(0, max_exclusive=1.2),
            ),
            renal_uo=(
                RenalUoBand(4, max_exclusive=200),
                RenalUoBand(3, max_exclusive=500),
                RenalUoBand(0, min_inclusive=500),
            ),
        )
