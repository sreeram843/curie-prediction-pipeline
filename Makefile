.PHONY: help up down logs topics test lint synthea

help:
	@echo "Targets:"
	@echo "  up       - start Kafka + Flink (Docker Compose)"
	@echo "  down     - stop local stack"
	@echo "  logs     - tail compose logs"
	@echo "  topics   - list Kafka topics"
	@echo "  test     - run Python tests"
	@echo "  lint     - run ruff"
	@echo "  synthea  - generate synthetic FHIR (default 10 patients)"

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
