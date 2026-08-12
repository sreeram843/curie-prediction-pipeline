# Page-quality and component-delta gates (CURIE-032 / CURIE-033)

**Policy note:** Frozen Challenge studies continue to use the pre-existing page-gate
fields only. New knobs default **off** so historical artifacts remain reproducible.

## Component-delta paging (CURIE-032)

Bundle path: `governance.page_gate`

| Knob | Default | Effect |
| --- | --- | --- |
| `min_newly_worsened_components` | `0` (off) | Require N components with positive delta vs prior vector |
| `min_component_delta` | `0` (off) | Require max per-component delta ≥ N |
| `high_actionability_components` | `[]` | Require at least one newly worsened name in this set |

Alerts carry `newly_worsened_components`, `component_deltas`, and optional
`newly_worsened_evidence`.

## Quality gates (CURIE-033)

Bundle path: `governance.quality_gate`

Deterministic only — never reads LLM outputs. Failures downgrade interruptive →
passive with `page_deferred_reason` (`quality_stale`, `quality_invalid`, …).

## Ablation reporting

Replay harness configs can enable each gate independently. Report sensitivity,
page burden, NNA, lead time, and miss reasons per ablation when running Challenge
or MIMIC studies — without retuning on `training_setB`.
