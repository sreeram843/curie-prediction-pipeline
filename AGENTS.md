# AGENTS.md

Operating manual for agents. Streaming FHIR clinical-deterioration prototype: Kafka → Flink computes
deterministic risk scores (SOFA, AKI, respiratory, hemodynamic shock), a shared alert-governance layer
gates them, and an LLM ("GRP", `reasoning/`) only adds narrative on top of already-fired alerts.

## Hard rules

- **Prototype only.** Synthetic data, no real PHI, not clinically validated, not FDA-cleared. Never
  describe it as validated or production-ready; see `docs/research/clinical-validation.md`.
- **LLM is never on the alert path.** The Flink alert (score, severity, evidence, rule version) is
  complete by itself. GRP cannot create, suppress, or change a score. Phase-2 flags
  (`CURIE_ENABLE_GRP`, `CURIE_ENABLE_EXTRACTION`) default to off.
- **Adding an indicator = authoring a rule bundle + plugin, not rebuilding infrastructure.** Do not
  rewrite the governance or streaming layers to add an indicator.

## Commands (exact)

```bash
pip install -e ".[dev]"          # + [api] for the dashboard, [kafka] for live Kafka consumers
make test                         # pytest -q  (testpaths: eval, ingestion, action, reasoning)
make lint                         # ruff check . (line-length 100; E,F,I,UP)
make parity                       # Python parity gate + Maven tests (needs Docker)
make flink-test                   # Maven tests via maven:3.9.9-eclipse-temurin-17 image (Java 17)
make up / up-full / down          # Docker Compose (Kafka :9092, Flink UI :8081, Kafka UI :8080)
make rules                        # publish active rule bundles to Kafka (runs parity gate first)
make replay / replay-aki          # T2 replay harness → alert-reduction metric
make api                          # uvicorn on :8000 (host dev; use up-full for container)
```

- Single test: `pytest -q eval/sofa/test_scoring.py::TestX::test_y` (any pytest path/selector works).
- Skip the integration suite: `pytest -q -m "not integration"`. The `integration` marker needs
  `data/mimic-iv-demo/` (PhysioNet open demo, not committed).
- CI = `ruff check .` + `pytest -q` + `python -m eval.parity.gate` + Maven `mvn -B -q test`
  (CI Python is 3.12; local `requires-python >=3.11`).

## Directory boundaries

**Generated / gitignored — do not edit, do not read as source of truth:**
`data/`, `.tools/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `*.egg-info/`,
`streaming/flink-jobs/**/target/`, `eval/manuscript/generated/`.

**Frozen study artifacts — never edit in place.** Create a new version and keep its hash:
`eval/challenge2019/frozen/`, `eval/mimic_study/frozen/`, `eval/investor_demo/frozen/`,
`eval/manuscript/frozen/`, `eval/fixtures/golden/` (golden fixtures change only alongside a scorer change).

**Rule registry:** `streaming/rule-registry/bundles/<id>.v<semver>.json` + `activation.json`.

## Two runtimes, must stay in parity (CURIE-007)

Every indicator has a **Python reference scorer** and a **Java/Flink implementation** that must produce
identical results:

- Python: `eval/sofa/scoring.py`, `eval/aki/scoring.py` (+ `eval/aki/timeline.py`),
  `eval/respiratory/scoring.py`, `eval/hemodynamic/scoring.py`
- Java: `streaming/flink-jobs/sofa/src/main/java/com/curie/sofa/{scoring,aki,resp,hemo}/`
- Shared governance mirror: Python `eval/replay_harness/governance.py` ↔ Java
  `streaming/flink-jobs/governance/`

`make parity` (or `python -m eval.parity.gate`) verifies the Python side against `eval/fixtures/golden/`;
the Java side is Maven surefire tests. **`make rules` refuses to publish unless this gate passes** (and
`validate_activation()` passes). CI requires `PARITY_OK=true` with `fixtures>=1`. When you change a scorer,
add/update fixtures in `eval/fixtures/golden/` and the matching Java test.

## Rule bundles & adding an indicator

- Versioned JSON bundles live in `streaming/rule-registry/bundles/<id>.v<semver>.json`; the active version
  per bundle is in `streaming/rule-registry/activation.json`.
- Resolution is **semver**, never lexicographic filename sort. `load_rule_bundle(id, version=None)`
  resolves via `activation.json`; production sets `CURIE_REQUIRE_EXPLICIT_RULE_VERSION=1` to forbid
  implicit "latest".
- A bundle's `score.type` must map to a registered `IndicatorPlugin` (`eval/indicators/plugin.py`,
  CURIE-011) or the activation is invalid. To add an indicator you must wire all of: new bundle file +
  activation entry + `IndicatorPlugin` registration + Python scorer + Java runtime impl (`runtime_impl`
  dict) + parity fixtures. See `docs/contracts/indicator-plugin-sdk.md`.
- `publish_rules.sh` injects a SHA-256 `content_hash` (sorted-key canonical JSON) into each bundle before
  publishing.

## Naming & error-handling conventions

- Work is tracked as `CURIE-xxx` tasks; use the task ID in branch/PR names
  (`curie-xxx-short-description`).
- Indicators are **open-string** `signal_type`s, never a closed enum. New conditions project onto the
  shared signal contract (`docs/contracts/signal-contract.md`) with condition-specific fields in
  `extensions`.
- Missing data is **never silently imputed** to a reassuring value: emit `partial` /
  `insufficient_data` with an explicit `missing_components` / `missing_inputs` list.
- Fail closed, not silent: invalid/poison input → DLQ; unsupported `score.type` fails at activation;
  ungrounded LLM output is quarantined, and a deterministic alert still ships.

## Validate before calling a change done

- [ ] `pytest -q`, `ruff check .`, `git diff --check`, and `mvn -B -q test` (via `make flink-test`) pass.
- [ ] Positive, negative, boundary, missing-data, and replay cases are covered.
- [ ] Python and Java behavior match when both runtimes implement the feature.
- [ ] Any scorer change updates `eval/fixtures/golden/` + the matching Java test, and `make parity` passes.
- [ ] Docs updated in the same change (README/AGENTS/`docs/` links still resolve; no stale paths).

## Never

- Never tune thresholds on Challenge 2019 `training_setB` (already inspected).
- Never replace a frozen study artifact in place — create a new version and keep its hash.
- Every clinical-rule change needs Python tests, Java tests (when the runtime implements it), and a
  replay result.

## Config & data

- Settings load via pydantic-settings with `env_prefix="CURIE_"` and `env_file=".env"`; `.env` is
  gitignored, copy from `.env.example`.
- `data/` and `.tools/` are gitignored local artifacts. Optional evals need externally placed data:
  MIMIC-IV demo at `data/mimic-iv-demo/` (`make mimic-demo`), Challenge 2019 at `data/archive/`
  (`make challenge-2019`), overridable via `CURIE_MIMIC_DEMO_DIR` / `CURIE_CHALLENGE2019_DIR`.
