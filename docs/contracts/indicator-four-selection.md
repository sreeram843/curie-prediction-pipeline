# Indicator four selection rubric (CURIE-036)

**Selected:** hemodynamic shock / hyperlactatemia surveillance (`hemo-shock` / `hemo_shock`)  
**Access date for rubric lock:** 2026-08-12

## Rubric (weights)

| Criterion | Weight | Hemo/shock | Hypotension-only | Hepatic | Delirium |
| --- | ---: | ---: | ---: | ---: | ---: |
| Actionability (time-sensitive intervention) | 25 | 5 | 4 | 2 | 2 |
| Data availability in current FHIR ingest | 20 | 4 | 5 | 3 | 1 |
| Label / phenotype quality for eval | 15 | 3 | 3 | 2 | 2 |
| Overlap with existing connectors | 15 | 4 | 5 | 3 | 1 |
| Clinical risk of overclaim | 15 | 3 | 3 | 2 | 2 |
| Validation cost | 10 | 3 | 4 | 2 | 1 |
| **Weighted** | 100 | **3.85** | **4.05** | **2.35** | **1.50** |

Hypotension-only scored slightly higher on data availability, but **hemo/shock** was selected as the default candidate in the backlog because it:

1. Combines lactate + MAP + vasopressor into one bounded surveillance signal.
2. Avoids rebranding the existing `hypotension-demo` fixture as a product indicator.
3. Reuses shared governance, episode, shadow, API, and dashboard paths.

## Rejected alternatives

| Candidate | Reason rejected |
| --- | --- |
| Hypotension-only (MAP) | Too narrow vs backlog default; demo signal already exists without a full plugin |
| Hepatic injury | Weaker actionability and higher missing-lab risk for streaming prototype |
| Delirium / CAM | Poor structured-data availability; high NLP dependence (Connect edge, not Signal core) |

## Non-claims

Outputs are **surveillance indicators / phenotypes**, not confirmed diagnoses of shock,
septic shock, or tissue hypoperfusion. Clinical validity remains `not_claimed` until
evaluated on an appropriate labeled dataset.
