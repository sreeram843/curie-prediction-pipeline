# Grounded patient-episode narratives (CURIE-023)

**Status:** Additive GRP over immutable episode snapshots  
**Code:** `reasoning/episode_context.py`, `episode_narrative.py`, `pipeline.explain_episode`  
**API:** `POST /episodes/{episode_id}/explain`

## Hard rules

1. Narrative runs **after** deterministic episode arbitration — never on the alert-firing path.
2. Failure (quarantine / abstain / timeout / malformed / prompt-injection) **cannot** change
   episode status, page counts, dominant signal, scores, or routing.
3. Every claim must cite evidence IDs present on the frozen episode snapshot.
4. Outputs record `prompt_version` (`episode-narrative.v1`) and `snapshot_hash`.

## What the narrative includes

- What signals support the episode (sentence-level, evidence-cited)
- Missing-data disclosure (not imputed)
- Routing rationale (interruptive vs passive)
- Model name + prompt version + snapshot hash

## Reproduce

```bash
pytest reasoning/test_episode_narrative.py -q
# with API:
curl -s -X POST localhost:8000/episodes/$ID/explain -H 'content-type: application/json' \
  -d '{"force":true}'
```
