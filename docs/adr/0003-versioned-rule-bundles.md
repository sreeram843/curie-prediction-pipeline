# ADR-0003: Versioned JSON rule bundles with semver resolution

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

Score thresholds, governance knobs, and missing-data policy must be reproducible and auditable. Resolving
the "active" bundle by lexicographic filename sort (or an implicit "latest") is a known source of silent,
hard-to-debug drift.

## Decision

Rules are versioned JSON bundles at `streaming/rule-registry/bundles/<id>.v<semver>.json`; the active
version per bundle is `streaming/rule-registry/activation.json`. Resolution is **semver**, never filename
sort. Production sets `CURIE_REQUIRE_EXPLICIT_RULE_VERSION=1` to forbid implicit "latest".

## Consequences

- Every alert carries `rule_bundle_id`, `rule_version`, and a SHA-256 `content_hash` (sorted-key canonical
  JSON, injected by `publish_rules.sh`).
- Unsupported `score.type` fails at activation, not during patient processing.
- Frozen study artifacts are hash-gated and never edited in place (see AGENTS.md directory boundaries).

## Related

- [`../contracts/indicator-plugin-sdk.md`](../contracts/indicator-plugin-sdk.md)
- [`../runbooks/rule-publish-failure.md`](../runbooks/rule-publish-failure.md)
