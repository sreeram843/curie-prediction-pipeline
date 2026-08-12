# Runtime ↔ benchmark governance parity

Product `sepsis-sofa.v0.3.0` carries the frozen **governance/page-gate knobs** for runtime,
but is **not** the Challenge study artifact: product scoring still defaults to
`min_components_required=3`, while the immutable study bundle
`eval/challenge2019/frozen/sepsis-sofa.challenge2019-p1.v1.json` uses **2** (and is
hash-gated). Eval reports include `rule_bundle.content_hash`.

Alert JSON now carries `routing`, `page_deferred_reason`, and `positive_components`.
API/dashboard consume these; enable `CURIE_KAFKA_ALERTS_CONSUMER=true` for live Kafka→API.

Late arrivals (event_time older than last processed) are dropped with
`late_out_of_order` at the governance layer and do not mutate governance state.

**Event-time buffer (CURIE-006):** within allowed lateness, arrivals are buffered and
flushed in `(event_time, tie_breaker)` order (`eval/replay_harness/event_time_buffer.py`,
`EventTimeBuffer` in Java). Beyond lateness → disposition `late_beyond_lateness` (no
feature/governance mutation; prior alerts are not retracted).

Challenge eval reports early_only / ±12h window sensitivities, stay-level PPV,
lead-time percentiles, alerts per patient-day, and offline official utility
under `challenge_utility` (emit-hour positives).
