.PHONY: help up up-full down logs topics test lint synthea rules flink-test api replay replay-aki mimic-demo mimic-study-protocol mimic-harness challenge-2019 challenge-2019-sweep challenge-2019-robustness parity

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
	@echo "  mimic-demo  - score SOFA/AKI on local MIMIC-IV demo (data/mimic-iv-demo)"
	@echo "  mimic-study-protocol - show frozen MIMIC-IV study protocol (CURIE-014)"
	@echo "  mimic-harness - leakage-safe demo-schema timeline harness (CURIE-015)"
	@echo "  challenge-2019 - sepsis alert eval on PhysioNet Challenge 2019 (data/archive)"
	@echo "  challenge-2019-sweep - setA tune → freeze → setB holdout"
	@echo "  challenge-2019-robustness - detection-window robustness on setB"

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
	uvicorn action.api.app.main:app --reload --host 127.0.0.1 --port 8000

replay:
	python -m eval.replay_harness.runner

replay-aki:
	python -m eval.replay_harness.aki_runner

mimic-demo:
	python -m eval.mimic_demo.runner $(if $(LIMIT),--limit $(LIMIT),)

mimic-study-protocol:
	python -m eval.mimic_study.sweep show

mimic-harness:
	python -m eval.mimic_harness.runner

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
