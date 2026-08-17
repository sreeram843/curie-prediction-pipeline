# Runbooks

Operational playbooks: symptom → action. These get read at 2am; keep them concrete and executable.

| Symptom | Runbook |
|---|---|
| `make rules` refuses to publish | [`rule-publish-failure.md`](rule-publish-failure.md) |
| Parity gate / CI failing on fixtures | [`parity-drift.md`](parity-drift.md) |
| DLQ filling up / late events | [`kafka-dlq.md`](kafka-dlq.md) |
| Too many alerts firing | [`alert-storm.md`](alert-storm.md) |
| Production API posture / auth / kill switches | [`api-security.md`](api-security.md) |
