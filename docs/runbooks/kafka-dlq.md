# Runbook: DLQ filling / late events

## Symptom

`GET /ops/status` (or `GET /ops/lag`) shows a rising DLQ depth, or you see `late_beyond_lateness` /
`late_out_of_order` dispositions in alerts/dlq.

## Diagnose

```bash
docker exec curie-kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --describe --topic dlq
```

Check the disposition field on DLQ records: `late_beyond_lateness` (event-time policy) vs
`late_out_of_order` (governance layer) vs poison/invalid input.

## Meaning & fix

- **`late_beyond_lateness`** — events arrived >5m past their event time (allowed lateness,
  [`../adr/0005-event-time-ordering.md`](../adr/0005-event-time-ordering.md)). This is by design: they never
  mutate feature/governance state. Investigate the producer for clock skew or stalled sources; the buffer
  flushes on end-of-input, so a stuck consumer can look like late data.
- **`late_out_of_order`** — an event older than the last processed event hit governance. Also dropped
  without mutating state. Same producer investigation applies.
- **Poison / invalid input** — schema, unit, or status validation failed. Fix the source or the adapter;
  do not relax validation to silence the DLQ (fail-closed posture).

Do not "replay DLQ into the main stream" as a fix — late events are deliberately excluded from scoring
state.
