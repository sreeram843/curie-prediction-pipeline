# Contributing

Thanks for contributing to Curie Prediction Pipeline. This file covers the **human workflow**:
branching, pull requests, and review. For the exact build/test commands and agent-facing conventions,
see [`AGENTS.md`](AGENTS.md).

> **Prototype only.** Synthetic data, no real PHI, not clinically validated, not FDA-cleared.
> Contributions must not change that posture. See [`docs/research/clinical-validation.md`](docs/research/clinical-validation.md).

## Local dev setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # + [api] for the dashboard, [kafka] for live Kafka consumers
cp .env.example .env             # gitignored; edit as needed
make up                          # Kafka + Flink + Kafka UI (Docker)
```

Prereqs: Docker, Python 3.11+, and Java 17 + Maven (or use `make flink-test`, which runs Maven in a
Docker image). Full command reference: [`AGENTS.md`](AGENTS.md).

## Workflow

1. Pick or create a `CURIE-xxx` task in [`docs/implementation-backlog.md`](docs/implementation-backlog.md).
2. Create a branch named `curie-xxx-short-description` (include the task ID).
3. Make the change. Update docs **in the same PR** as the behavior they describe — not as a follow-up.
4. Open a pull request.

## Branch naming

- `curie-###-kebab-case` — e.g. `curie-032-component-delta-paging`.
- Task ID comes first so CI and review can map the branch to the backlog.

## Pull requests

- One task per PR where practical.
- Describe what changed, why, and how it was verified (paste the command output).
- Mark a backlog task complete **only** after its acceptance criteria pass; update its checkboxes.

## Review expectations

A reviewer should confirm the change is safe to merge when:

- [ ] Behavior is covered by positive, negative, boundary, missing-data, and replay tests.
- [ ] Python and Java behavior match when both runtimes implement the feature.
- [ ] Rule/config versions and output provenance are explicit.
- [ ] `pytest -q`, `ruff check .`, `git diff --check`, and relevant Maven tests pass.
- [ ] Docs and benchmark claims are updated without overstating clinical validity.

## Hard rules

- **LLM is never on the alert path.** GRP (`reasoning/`) only adds narrative on top of an alert that
  already fired. It cannot create, suppress, or change a score.
- **Adding an indicator = authoring a rule bundle + plugin**, not rebuilding infrastructure.
- **Never tune thresholds on Challenge 2019 `training_setB`** (already inspected).
- **Never replace a frozen study artifact in place** — create a new version and keep its hash. See
  [`docs/adr/`](docs/adr/).

When you change a scorer, add/update fixtures in `eval/fixtures/golden/` and the matching Java test,
and run `make parity`.
