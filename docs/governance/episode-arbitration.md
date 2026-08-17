# Patient episode arbitration (CURIE-012)

Prototype only — not clinically validated.

Correlated clinical signals for one patient/encounter are folded into a single
**episode** with a dominant problem and supporting differential. Interruptive
pages fire on new actionability or severity escalation — not on every component
update.

**Code:** `eval/episodes/`

## Config (`EpisodeConfig`)

| Knob | Default | Meaning |
|---|---|---|
| `window_minutes` | 120 | Join signals into the active episode if within this gap |
| `page_refractory_minutes` | 60 | Min gap between interruptive pages for one episode |
| `reopen_after_resolve_minutes` | 30 | Re-deterioration within this gap reopens the episode |

## Lifecycle

`open` → `updated` / `escalated` → `acknowledged` → `resolved` → (`reopened`)

## Dominance

1. Highest severity (`critical` > `urgent` > `watch`)
2. Then configured `signal_priority` (default: sepsis-3, sofa-deterioration, aki, hypotension, …)

## Page vs passive

- **Page** once when an actionable (urgent/critical or interruptive routing) signal opens an episode, or severity escalates outside refractory.
- **Passive** for additional signals / updates inside the page refractory — still visible on the episode and alert list.

## API / demo

- `GET /episodes`, `GET /episodes/{id}`
- Demo patient `Patient/p-ep-901` (Elena Vargas): SOFA + AKI + hypotension → one episode, one page

## Fixtures

`eval/fixtures/golden/episode_cases.v1.json`
