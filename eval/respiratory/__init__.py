"""Respiratory deterioration indicator (CURIE-013).

Prototype only — not clinically validated.
"""

from eval.respiratory.scoring import (
    RespInput,
    RespScoreResult,
    compute_resp_score,
    tier_for_resp_score,
)

__all__ = [
    "RespInput",
    "RespScoreResult",
    "compute_resp_score",
    "tier_for_resp_score",
]
