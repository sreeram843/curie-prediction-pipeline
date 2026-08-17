# ADR-0002: The LLM is never on the alert-firing path

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

An LLM could plausibly compute, modify, or gate a clinical alert. That would make interruptive delivery
depend on a non-deterministic, latency-variable, potentially-hallucinating model — unacceptable for a
clinical safety boundary.

## Decision

The deterministic Flink alert (score, severity, evidence IDs, rule bundle id + version + hash) is complete
by itself. The Guarded Reasoning Pipeline ("GRP", `reasoning/`) only adds narrative on top of an alert that
already fired. It cannot create, suppress, or change a score. Phase-2 flags (`CURIE_ENABLE_GRP`,
`CURIE_ENABLE_EXTRACTION`) default to off.

## Consequences

- Every GRP result records model/prompt version, source provenance, confidence/abstention, and validation
  status; ungrounded output is quarantined.
- Model failure, timeout, or malformed output cannot delay or alter alert delivery.
- Release gates for any LLM workflow must demonstrate the deterministic path works with the model
  unavailable. See [`../llm-workflows.md`](../llm-workflows.md).

## Related

- [`../architecture.md`](../architecture.md)
- [`../governance/episode-narratives.md`](../governance/episode-narratives.md)
