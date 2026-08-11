.PHONY: help up down logs topics test lint synthea rules flink-test api replay

help:
	@echo "Targets:"
	@echo "  up          - start Kafka + Flink (Docker Compose)"
	@echo "  down        - stop local stack"
	@echo "  logs        - tail compose logs"
	@echo "  topics      - list Kafka topics"
	@echo "  test        - run Python tests"
	@echo "  lint        - run ruff"
	@echo "  synthea     - generate synthetic FHIR (default 10 patients)"
	@echo "  rules       - publish sepsis-sofa rule bundle to Kafka"
	@echo "  flink-test  - compile/test Flink modules via Maven Docker image"
	@echo "  api         - run alert API + dashboard on :8000"
	@echo "  replay      - run T2 replay harness (alert-reduction metric)"

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f

topics:
	docker exec curie-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

test:
	pytest -q

lint:
	ruff check .

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
