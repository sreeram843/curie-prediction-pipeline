"""Deterministic event-time buffering (CURIE-006).

Policy
------
- Buffer arrivals until the event-time watermark advances (``max_event_time - allowed_lateness``)
  or ``close()`` is called.
- Flush in order of ``(event_time, tie_breaker)`` so Kafka arrival order cannot change results
  within the lateness window.
- Events with ``event_time < watermark`` (beyond allowed lateness) are **not** applied to
  feature or governance state; they are returned with disposition ``late_beyond_lateness``.
- Late corrections do **not** retract prior alerts (future-state only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, order=True)
class _SortKey:
    event_time_ms: int
    tie_breaker: str


@dataclass
class BufferedEvent(Generic[T]):
    event_time_ms: int
    tie_breaker: str
    payload: T


@dataclass
class FlushResult(Generic[T]):
    """Events ready for state mutation, plus late drops for audit/DLQ."""

    ready: list[BufferedEvent[T]] = field(default_factory=list)
    late: list[BufferedEvent[T]] = field(default_factory=list)
    disposition_late: str = "late_beyond_lateness"


class EventTimeBuffer(Generic[T]):
    """Per-key event-time reorder buffer."""

    def __init__(self, *, allowed_lateness_ms: int = 5 * 60 * 1000) -> None:
        if allowed_lateness_ms < 0:
            raise ValueError("allowed_lateness_ms must be >= 0")
        self.allowed_lateness_ms = allowed_lateness_ms
        self._pending: list[BufferedEvent[T]] = []
        self.max_event_time_ms: int | None = None
        self.watermark_ms: int = 0

    def offer(
        self,
        event_time_ms: int,
        payload: T,
        *,
        tie_breaker: str = "",
    ) -> FlushResult[T]:
        """Admit an event; may flush previously buffered events as the watermark advances."""
        if self.max_event_time_ms is None or event_time_ms > self.max_event_time_ms:
            self.max_event_time_ms = event_time_ms
            self.watermark_ms = max(0, event_time_ms - self.allowed_lateness_ms)

        if event_time_ms < self.watermark_ms:
            return FlushResult(late=[BufferedEvent(event_time_ms, tie_breaker, payload)])

        self._pending.append(BufferedEvent(event_time_ms, tie_breaker, payload))
        return self._flush_ready()

    def close(self) -> FlushResult[T]:
        """End-of-stream: release everything remaining in order."""
        self.watermark_ms = (
            self.max_event_time_ms + 1 if self.max_event_time_ms is not None else 0
        )
        return self._flush_ready()

    def snapshot_pending(self) -> list[BufferedEvent[T]]:
        """Restart-friendly copy of buffered (not yet flushed) events."""
        return list(self._pending)

    def restore_pending(self, events: list[BufferedEvent[T]]) -> None:
        self._pending = list(events)
        if events:
            self.max_event_time_ms = max(e.event_time_ms for e in events)
            self.watermark_ms = max(0, self.max_event_time_ms - self.allowed_lateness_ms)

    def _flush_ready(self) -> FlushResult[T]:
        ready: list[BufferedEvent[T]] = []
        stay: list[BufferedEvent[T]] = []
        for ev in self._pending:
            if ev.event_time_ms <= self.watermark_ms:
                ready.append(ev)
            else:
                stay.append(ev)
        self._pending = stay
        ready.sort(key=lambda e: _SortKey(e.event_time_ms, e.tie_breaker))
        return FlushResult(ready=ready)
