# Indicator plugin SDK (CURIE-011)

Prototype only — not clinically validated.

Adding an indicator is a **plugin task**: declare an `IndicatorPlugin`, ship a
rule bundle whose `score.type` matches, and provide Python + Java runtimes.
A JSON bundle alone cannot activate without an installed scorer.

**Code:** `eval/indicators/plugin.py`, `eval/indicators/registry.py`

## Plugin contract

| Field | Purpose |
|---|---|
| `plugin_id` / `score_type` / `indicator` | Identity |
| `signal_kind` | `risk` \| `phenotype` (CURIE-010) |
| `clinical_concepts`, `codes`, `units`, `windows` | Required clinical surface |
| `eligibility`, `exclusions` | Cohort gates |
| `missing_data_policy`, `resolution_rule` | Completeness / resolve behavior |
| `scorer_module` / `scorer_attr` | Importable reference scorer (proof) |
| `tier_module` / `tier_attr` | Acuity mapping |
| `runtime_impl` | Explicit python / java / flink mapping |
| `fixture_paths` | Golden / parity fixtures |

## Built-ins

| score.type | indicator | Python | Java |
|---|---|---|---|
| `sofa` | `sofa-deterioration` | `eval.sofa.scoring.compute_sofa_score` | `SofaScorer` / `SofaAlertFunction` |
| `aki_kdigo` | `aki` | `eval.aki.timeline` (+ legacy `compute_aki_score`) | `AkiTimeline` / `AkiAlertFunction` |
| `resp_hypoxemia` | `respiratory-deterioration` | `eval.respiratory.scoring.compute_resp_score` | `RespScorer` (mapped; shared alert path) |

## Activation

```python
from eval.indicators.registry import validate_activation, load_rule_bundle

validate_activation()  # fails if any active bundle lacks a plugin
load_rule_bundle("sepsis-sofa")  # require_scorer=True by default
```

`scripts/publish_rules.sh` runs `validate_activation()` before Kafka publish.

## API

- `GET /indicators` — bundles with `scorer_installed=True` (+ `plugin_id`, `runtime_impl`)
- `GET /plugins` — full plugin catalog

## Dispatch

```python
from eval.indicators.plugin import dispatch_score

score_fn = dispatch_score("aki_kdigo")  # shared interface
```
