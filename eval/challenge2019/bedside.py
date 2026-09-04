"""Hourly SIRS / NEWS2 / qSOFA from Challenge 2019 columns.

These are *threshold-only* comparators for the methods paper — not Curie's
alert path, not complete clinical scores, and not a superiority claim.

Challenge 2019 has no AVPU/GCS. NEWS2 consciousness is omitted (scored 0).
qSOFA uses only RR and SBP (partial; max 2).
"""

from __future__ import annotations

from typing import Any

# Columns used for bedside comparators (forward-filled independently of SOFA).
BEDSIDE_COLS = ("Temp", "HR", "Resp", "WBC", "SBP", "O2Sat", "FiO2")

NEWS2_ALERT_THRESHOLD = 5  # RCP medium-trigger; ≥7 is a secondary cut
SIRS_ALERT_THRESHOLD = 2
QSOFA_ALERT_THRESHOLD = 2


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() == "NAN":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_fio2(raw: float | None) -> float | None:
    if raw is None:
        return None
    frac = raw / 100.0 if raw > 1.0 else raw
    if frac <= 0 or frac > 1.0:
        return None
    return frac


def update_vitals(state: dict[str, float | None], raw: dict[str, Any]) -> dict[str, float | None]:
    """Forward-fill bedside columns from one Challenge hour row."""
    out = dict(state)
    for col in BEDSIDE_COLS:
        parsed = parse_float(raw.get(col))
        if parsed is not None:
            out[col] = parsed
    return out


def sirs_criteria(vitals: dict[str, float | None]) -> tuple[int, dict[str, bool]]:
    """Bone 1992 SIRS: count of met criteria (0–4). Missing vital → that limb False."""
    temp = vitals.get("Temp")
    hr = vitals.get("HR")
    rr = vitals.get("Resp")
    wbc = vitals.get("WBC")
    flags = {
        "temp": temp is not None and (temp > 38.0 or temp < 36.0),
        "hr": hr is not None and hr > 90.0,
        "rr": rr is not None and rr > 20.0,
        "wbc": wbc is not None and (wbc > 12.0 or wbc < 4.0),
    }
    return sum(flags.values()), flags


def news2_rr(rr: float | None) -> int | None:
    if rr is None:
        return None
    if rr <= 8:
        return 3
    if rr <= 11:
        return 1
    if rr <= 20:
        return 0
    if rr <= 24:
        return 2
    return 3


def news2_spo2_scale1(spo2: float | None) -> int | None:
    if spo2 is None:
        return None
    if spo2 <= 91:
        return 3
    if spo2 <= 93:
        return 2
    if spo2 <= 95:
        return 1
    return 0


def news2_air_or_oxygen(fio2: float | None) -> int:
    """2 if supplemental O2 (FiO2 > 0.21); 0 if air or FiO2 unknown (assume air)."""
    frac = normalize_fio2(fio2)
    if frac is not None and frac > 0.21:
        return 2
    return 0


def news2_temp(temp: float | None) -> int | None:
    if temp is None:
        return None
    if temp <= 35.0:
        return 3
    if temp <= 36.0:
        return 1
    if temp <= 38.0:
        return 0
    if temp <= 39.0:
        return 1
    return 2


def news2_sbp(sbp: float | None) -> int | None:
    if sbp is None:
        return None
    if sbp <= 90:
        return 3
    if sbp <= 100:
        return 2
    if sbp <= 110:
        return 1
    if sbp <= 219:
        return 0
    return 3


def news2_hr(hr: float | None) -> int | None:
    if hr is None:
        return None
    if hr <= 40:
        return 3
    if hr <= 50:
        return 1
    if hr <= 90:
        return 0
    if hr <= 110:
        return 1
    if hr <= 130:
        return 2
    return 3


def news2_score(vitals: dict[str, float | None]) -> tuple[int | None, dict[str, int | None]]:
    """Incomplete NEWS2: consciousness omitted (0). None if no scoreable limb."""
    parts: dict[str, int | None] = {
        "rr": news2_rr(vitals.get("Resp")),
        "spo2": news2_spo2_scale1(vitals.get("O2Sat")),
        "air_oxygen": news2_air_or_oxygen(vitals.get("FiO2")),
        "temp": news2_temp(vitals.get("Temp")),
        "sbp": news2_sbp(vitals.get("SBP")),
        "hr": news2_hr(vitals.get("HR")),
        "consciousness": 0,  # GCS/AVPU absent in Challenge 2019
    }
    scored = [v for k, v in parts.items() if k != "consciousness" and v is not None]
    if not scored:
        return None, parts
    total = sum(scored) + int(parts["consciousness"] or 0)
    return total, parts


def qsofa_score(vitals: dict[str, float | None]) -> tuple[int, dict[str, bool]]:
    """Partial qSOFA: RR ≥ 22 and SBP ≤ 100 only (GCS omitted). Max 2."""
    rr = vitals.get("Resp")
    sbp = vitals.get("SBP")
    flags = {
        "rr": rr is not None and rr >= 22.0,
        "sbp": sbp is not None and sbp <= 100.0,
        "mentation": False,  # GCS absent
    }
    return sum(1 for k in ("rr", "sbp") if flags[k]), flags


def hour_alerts(vitals: dict[str, float | None]) -> dict[str, Any]:
    """Alert flags for one forward-filled hour."""
    sirs_n, sirs_flags = sirs_criteria(vitals)
    news2_n, news2_parts = news2_score(vitals)
    qsofa_n, qsofa_flags = qsofa_score(vitals)
    return {
        "sirs": sirs_n,
        "sirs_flags": sirs_flags,
        "sirs_alert": sirs_n >= SIRS_ALERT_THRESHOLD,
        "news2": news2_n,
        "news2_parts": news2_parts,
        "news2_alert": news2_n is not None and news2_n >= NEWS2_ALERT_THRESHOLD,
        "news2_high_alert": news2_n is not None and news2_n >= 7,
        "qsofa": qsofa_n,
        "qsofa_flags": qsofa_flags,
        "qsofa_alert": qsofa_n >= QSOFA_ALERT_THRESHOLD,
    }
