# Event-time policy (CURIE-026 / CURIE-027)

**Policy version:** `event-time-v1-lateness-5m` (`EventTimeBuffer.POLICY_VERSION`)

SOFA (`SofaAlertFunction`) and AKI (`AkiAlertFunction`) share one reorder / lateness contract.

## Rules

| Topic | Behavior |
| --- | --- |
| Allowed lateness | 5 minutes (`DEFAULT_ALLOWED_LATENESS_MS`) |
| Order | Flush in `(eventTimeMs, idempotency_key)` ascending |
| Watermark (local) | `maxEventTime − lateness` after each offer; advanced by event-time timers |
| Timer flush | Register `eventTime + lateness`; `onTimer` calls `advanceWatermark` so a **single final event** still scores |
| Late beyond lateness | Disposition `late_beyond_lateness` → DLQ; **no** feature / governance mutation; no alert retraction |
| End-of-input | `EventTimeBuffer.close()` flushes all pending (bounded replay / tests) |
| Checkpoint | Pending buffer is Flink `ValueState`; restore via `restorePending` |
| Equal timestamps | Stable tie-break on idempotency key |

## Observability

Operators expose the same `POLICY_VERSION`. Pending / late counts belong on `/ops/status` when the ops surface is wired for per-key buffer metrics.

## Non-goals

Processing-time timers are not used for clinical ordering. Wall-clock idleness of a Kafka partition is handled by Flink watermark idleness on the source; the local buffer still relies on event-time timers for key-local completion.
