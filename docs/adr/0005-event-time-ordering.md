# ADR-0005: Deterministic event-time ordering with allowed lateness

- **Status:** Accepted
- **Date:** 2026-08-12

## Context

Kafka arrival order is not clinical order. If scores and governance depended on arrival order, the same
event set could produce different alerts — breaking replay determinism (a hard bar of 100%) and audit.

## Decision

SOFA and AKI share one reorder/lateness contract: buffer per-patient events, flush in
`(event_time, idempotency_key)` ascending order, with an allowed lateness of 5 minutes. Events beyond
lateness are routed to `dlq` with disposition `late_beyond_lateness` and never mutate feature or governance
state. End-of-input flushes pending events; the buffer is checkpointed as Flink `ValueState`.

## Consequences

- Output is a deterministic function of the input event set, not arrival order.
- Replay/restart produce identical output and DLQ records.
- Wall-clock idleness is handled by Flink watermark idleness, not by processing-time timers for clinical
  ordering.

## Related

- [`../governance/event-time-policy.md`](../governance/event-time-policy.md)
- [`../runbooks/kafka-dlq.md`](../runbooks/kafka-dlq.md)
