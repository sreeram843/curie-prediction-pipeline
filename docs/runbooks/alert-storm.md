# Runbook: too many alerts (alert storm)

## Symptom

Alert volume far above the expected governed baseline (see the replay/reduction metrics), or interruptive
pages firing on every component update.

## Diagnose

```bash
GET /ops/status          # alert rate, active bundle(s), governance knobs in effect
GET /alerts              # inspect routing / page_deferred_reason / positive_components
```

## Check, in order

1. **Active bundle is wrong.** Verify the resolved bundle in `/ops/status` matches intent. Refractory /
   dedup / page-gate knobs are bundle-driven — a missing or older bundle reverts to looser defaults.
   Re-publish with `make rules` if needed.
2. **Page gate off / quality gate off.** New knobs default **off** so historical artifacts stay
   reproducible. If the bundle doesn't set them, pages are downgraded less aggressively. See
   [`../governance/page-gates.md`](../governance/page-gates.md).
3. **Episode arbitration not engaged.** Multiple correlated signals should fold into one episode with a
   page refractory window. See [`../governance/episode-arbitration.md`](../governance/episode-arbitration.md).

## Emergency lever

`POST /ops/kill-switches` can disable the interruptive lane (or per-indicator gates) without redeploying.
This does not stop scoring — it changes delivery. Use it while you fix the root cause.

Do **not** "fix" an alert storm by raising thresholds on holdout data (Challenge `training_setB` is
already inspected and off-limits for tuning).
