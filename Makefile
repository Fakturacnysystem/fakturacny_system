.PHONY: up down init paper test replay

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

init:
	./scripts/init_db.sh

paper:
	PYTHONPATH=src python scripts/run_paper.py --config config.paper.yaml

replay:
	PYTHONPATH=src python -m autonomous_investment_robot replay --config config.paper.yaml --source fixtures

test:
	pytest -q
