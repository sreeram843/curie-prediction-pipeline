.PHONY: help up up-full down logs topics test lint synthea rules flink-test api replay replay-aki mimic mimic-demo syn-icu mimic-study-protocol mimic-harness mimic-study manuscript manuscript-phi paper-tables investor-demo trusted-fact-bridge stewardship uncertainty-band challenge-2019 challenge-2019-sweep challenge-2019-robustness challenge-2019-paper-analyses open-eval parity

help:
	@echo "Targets:"
	@echo "  up          - start Kafka + Flink + Kafka UI (Docker Compose)"
	@echo "  up-full     - Kafka + Flink + Kafka UI + API + publish rules + submit Sofa/AKI jobs"
	@echo "  down        - stop local stack"
	@echo "  logs        - tail compose logs"
	@echo "  topics      - list Kafka topics"
	@echo "  test        - run Python tests"
	@echo "  lint        - run ruff"
	@echo "  parity      - CURIE-007 cross-runtime parity gate (Python + Java fixtures)"
	@echo "  synthea     - generate synthetic FHIR (default 10 patients)"
	@echo "  rules       - publish active rule bundles (requires parity gate)"
	@echo "  flink-test  - compile/test Flink modules via Maven Docker image"
	@echo "  api         - run alert API + dashboard on :8000 (host; use up-full for container)"
	@echo "  replay      - run sepsis T2 replay harness (alert-reduction metric)"
	@echo "  replay-aki  - run AKI T2 replay harness (alert-reduction metric)"
	@echo "  mimic       - score SOFA/AKI on credentialed MIMIC-IV 3.1 (CURIE_MIMIC_DIR; LIMIT=5)"
	@echo "  mimic-demo  - score SOFA/AKI on local MIMIC-IV demo (data/mimic-iv-demo)"
	@echo "  syn-icu     - score SOFA/AKI on SYN-ICU synthetic ICU (data/syn-icu, [syn-icu] extra)"
	@echo "  mimic-study-protocol - show frozen MIMIC-IV study protocol (CURIE-014)"
	@echo "  mimic-harness - leakage-safe demo-schema timeline harness (CURIE-015)"
	@echo "  mimic-study - locked MIMIC ablation/robustness study (CURIE-016)"
	@echo "  manuscript - research manuscript package + paper/tables from frozen sidecars"
	@echo "  manuscript-phi - scan manuscript artifacts for PHI-like leakage"
	@echo "  paper-tables - regenerate paper/tables/*.tex from frozen Challenge JSON"
	@echo "  investor-demo - investor timeline demo + claims matrix (CURIE-021)"
	@echo "  trusted-fact-bridge - validate shared trusted-fact fixtures (CURIE-022)"
	@echo "  stewardship - feedback classification + offline proposals (CURIE-024)"
	@echo "  uncertainty-band - passive uncertainty-band study (CURIE-025)"
	@echo "  challenge-2019 - sepsis alert eval on PhysioNet Challenge 2019 (data/archive)"
	@echo "  challenge-2019-sweep - setA tune → freeze → setB holdout"
	@echo "  challenge-2019-robustness - detection-window robustness on setB"
	@echo "  challenge-2019-paper-analyses - setB comparators/ablation/miss/CIs (never retune)"
	@echo "  open-eval  - run every local open/synthetic dataset (LIMIT=50 unlabeled, 200 Challenge)"

up:
	docker compose -f infra/docker-compose.yml up -d

up-full:
	docker compose -f infra/docker-compose.yml --profile full up -d --build

down:
	docker compose -f infra/docker-compose.yml --profile full down

logs:
	docker compose -f infra/docker-compose.yml --profile full logs -f

topics:
	docker exec curie-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

test:
	pytest -q

lint:
	ruff check .

parity:
	python -m eval.parity.gate
	$(MAKE) flink-test

synthea:
	./scripts/generate_synthea.sh $${N:-10}

rules:
	./scripts/publish_rules.sh

flink-test:
	docker run --rm \
		-v "$(CURDIR)/streaming/flink-jobs:/w" \
		-w /w \
		maven:3.9.9-eclipse-temurin-17 \
		mvn -B -q test

api:
	CURIE_ALERT_DB=data/curie_alerts.sqlite \
	uvicorn action.api.app.main:app --reload --host 127.0.0.1 --port 8000

replay:
	python -m eval.replay_harness.runner

replay-aki:
	python -m eval.replay_harness.aki_runner

mimic:
	python -m eval.mimic_demo.runner --full $(if $(LIMIT),--limit $(LIMIT),)

mimic-demo:
	python -m eval.mimic_demo.runner $(if $(LIMIT),--limit $(LIMIT),)

syn-icu:
	python -m eval.syn_icu.runner $(if $(LIMIT),--limit $(LIMIT),)

mimic-study-protocol:
	python -m eval.mimic_study.sweep show

mimic-harness:
	python -m eval.mimic_harness.runner

mimic-study:
	python -m eval.mimic_study.study run

manuscript:
	python -m eval.manuscript.package build

manuscript-phi:
	python -m eval.manuscript.package phi-scan

paper-tables:
	python -m eval.manuscript.generate_paper_tables

investor-demo:
	python -m eval.investor_demo.runner run

trusted-fact-bridge:
	python -m ingestion.bridge.validate_fixtures

stewardship:
	python -m eval.stewardship.runner run --write

uncertainty-band:
	python -m eval.uncertainty.runner run

# PhysioNet Challenge 2019 archive under data/archive (LIMIT=0 = all stays)
# PROFILE=accuracy|sensitive|balanced|strict|dual (default accuracy = best detection)
# dual = accuracy watch lane + harder interruptive page gate
challenge-2019:
	python -m eval.challenge2019.runner $(if $(LIMIT),--limit $(LIMIT),--limit 200) \
		--gov-profile $${PROFILE:-accuracy} \
		$(if $(SET),--set $(SET),) $(if $(JSON_OUT),--json-out $(JSON_OUT),) \
		$(if $(BOOTSTRAP),--bootstrap $(BOOTSTRAP),) \
		$(if $(GOV_CONFIG),--gov-config $(GOV_CONFIG),)

# Tune on training_setA, freeze winner, score training_setB (LIMIT=0 = all)
# JOBS=N parallel candidate workers (default: cpu_count-1)
challenge-2019-sweep:
	python -m eval.challenge2019.sweep $(if $(LIMIT),--limit $(LIMIT),--limit 0) \
		$(if $(JOBS),--jobs $(JOBS),) \
		$(if $(SWEEP_JSON),--sweep-json-out $(SWEEP_JSON),) \
		$(if $(HOLDOUT_JSON),--holdout-json-out $(HOLDOUT_JSON),) \
		$(if $(BOOTSTRAP),--bootstrap $(BOOTSTRAP),)

# Detection definitions on setB (grace 0/6/12, early-only, ±12h window)
challenge-2019-robustness:
	python -m eval.challenge2019.robustness $(if $(LIMIT),--limit $(LIMIT),--limit 0) \
		$(if $(JOBS),--jobs $(JOBS),) \
		$(if $(JSON_OUT),--json-out $(JSON_OUT),) \
		$(if $(SET),--set $(SET),)

# Comparators + setB ablation + miss table + primary-window bootstrap (no setB retune)
challenge-2019-paper-analyses:
	python -m eval.challenge2019.paper_analyses \
		$(if $(LIMIT),--limit $(LIMIT),--limit 0) \
		$(if $(BOOTSTRAP),--bootstrap $(BOOTSTRAP),) \
		$(if $(SKIP_PARETO),--skip-pareto,) \
		$(if $(SKIP_ABLATION),--skip-ablation,) \
		$(if $(JSON_OUT),--json-out $(JSON_OUT),) \
		--write-frozen

# Local open + synthetic evals. LIMIT applies to unlabeled ICU sets (0 = all).
# CHALLENGE_LIMIT defaults to 200 (0 = all). Only labeled detection is Challenge 2019.
open-eval:
	python -m eval.open_suite.runner \
		$(if $(LIMIT),--limit $(LIMIT),--limit 50) \
		$(if $(CHALLENGE_LIMIT),--challenge-limit $(CHALLENGE_LIMIT),) \
		$(if $(ONLY),--only $(ONLY),) \
		$(if $(JSON_OUT),--json-out $(JSON_OUT),--json-out data/open_suite/report.json)
