# Uncertainty-band contextual reasoning (CURIE-025)

**Status:** Retrospective / passive decision support only  
**Code:** `eval/uncertainty/`  
**Commands:** `make uncertainty-band` / `python -m eval.uncertainty.runner run`

## Frozen eligibility policy

`frozen/eligibility_policy.v1.json` selects borderline/conflicting cases:

- near-threshold scores
- partial completeness / missing components
- positive + missing conflict
- multi-signal severity spread
- watch tier with rising score

Ineligible cases are skipped — the assistant is **not** invoked for every patient.

## Hard safety rules

- Assistant **cannot** suppress or escalate deterministic alerts
- **Cannot** change routing (`routing_before == routing_after`)
- Interruptive delivery **never** depends on the LLM (`interruptive_depends_on_llm=false`)
- Ungrounded / malformed mimic claims are quarantined

## Study metrics (fixture retrospective)

Reported in `frozen/study_report.v1.json`:

| Metric | Source |
|---|---|
| Sensitivity / PPV / alert burden | Deterministic labels on fixtures |
| Unsupported claim rate | Quarantined ungrounded claims |
| Abstention rate | Eligible cases with no evidence |
| Subgroups | eligible / ineligible / partial / interruptive |

Detection metrics are identical before vs after assist by construction.

```bash
make uncertainty-band
pytest eval/uncertainty -q
```
