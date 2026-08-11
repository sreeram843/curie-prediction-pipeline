# Architecture notes

Kafka topics (created by `kafka-init`):

| Topic | Purpose |
|---|---|
| `observations` | FHIR Observation events |
| `conditions` | FHIR Condition events |
| `medications` | Medication* events |
| `alerts` | Deterministic alert events (post-governance) |
| `rules` | Rule-bundle broadcast / updates |
| `dlq` | Dead-letter / poison messages |

Partition key: `patient_id` (ordering per patient).

Host producers use `localhost:9092`. Containers (Flink) should use `kafka:29092`.
