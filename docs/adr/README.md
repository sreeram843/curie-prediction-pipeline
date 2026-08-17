# Architecture Decision Records

One file per significant decision, sequentially numbered. Status is one of `Proposed`, `Accepted`,
`Deprecated`, `Superseded`. Numbering is sequential and never reused; a superseded ADR keeps its number and
gets marked `Superseded` (with a pointer to its replacement) rather than deleted.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-shared-alert-governance.md) | Shared alert governance is the product, not the score | Accepted |
| [0002](0002-llm-off-alert-path.md) | The LLM is never on the alert-firing path | Accepted |
| [0003](0003-versioned-rule-bundles.md) | Versioned JSON rule bundles with semver resolution | Accepted |
| [0004](0004-dual-runtime-parity.md) | Dual-runtime parity (Python reference + Java/Flink) | Accepted |
| [0005](0005-event-time-ordering.md) | Deterministic event-time ordering with allowed lateness | Accepted |
| [0006](0006-sofa-vs-sepsis.md) | Separate SOFA deterioration from sepsis identification | Accepted |
| [0007](0007-indicator-plugin-sdk.md) | Indicators are plugins, not new infrastructure | Accepted |

## Template

```markdown
# ADR-NNNN: <title>

- **Status:** Proposed | Accepted | Deprecated | Superseded by ADR-NNNN
- **Date:** YYYY-MM-DD

## Context
## Decision
## Consequences
## Related
```
