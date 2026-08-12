# Alert stewardship feedback classification (CURIE-024)

**Status:** Offline stewardship copilot — never mutates active rules  
**Code:** `eval/stewardship/`  
**Commands:** `make stewardship` / `python -m eval.stewardship.runner run --write`

## Taxonomy

`already_recognized`, `already_treated`, `chronic_baseline`, `incorrect_input`,
`appropriate_non_actionable`, `wrong_recipient`, `repeated_episode`, `true_escalation`,
`other` (+ classifier `abstain`).

## Acceptance posture

1. **Dual-reviewed fixtures** — `fixtures/dual_reviewed.v1.json`; metrics report reviewer
   agreement and classifier-vs-consensus accuracy.
2. **Frozen replay binding** — every proposal references
   `frozen/replay_manifest.v1.json` (MIMIC study + Challenge OP artifacts). Evaluation is
   offline only; no tune on test/setB.
3. **Human approval required** — `approve` records `human_approved` and queues evaluation;
   `mutates_active_rules` remains `false`.

## API

| Path | Role |
|---|---|
| `GET /stewardship/taxonomy` | Category list |
| `POST /stewardship/classify` | Classify free-text feedback |
| `GET /stewardship/report` | Dual-review metrics + proposals |
| `POST /stewardship/proposals/{id}/approve` | Ops human approval (no activation) |

```bash
make stewardship
curl -s -X POST localhost:8000/stewardship/classify \
  -H 'content-type: application/json' \
  -d '{"text":"Duplicate page for the same episode — already paged."}'
```
