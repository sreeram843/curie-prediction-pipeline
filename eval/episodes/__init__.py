"""Episode aggregation package (CURIE-012)."""

from eval.episodes.arbiter import (
    ArbiterResult,
    EpisodeArbiter,
    EpisodeConfig,
    select_dominant,
    signal_ref_from_alert,
)
from eval.episodes.models import (
    EPISODE_SCHEMA_VERSION,
    Episode,
    EpisodeAction,
    EpisodeStatus,
    SignalRef,
)

__all__ = [
    "EPISODE_SCHEMA_VERSION",
    "ArbiterResult",
    "Episode",
    "EpisodeAction",
    "EpisodeArbiter",
    "EpisodeConfig",
    "EpisodeStatus",
    "SignalRef",
    "select_dominant",
    "signal_ref_from_alert",
]
