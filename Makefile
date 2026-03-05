.PHONY: up down init env paper paper-perps test replay

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

init:
	./scripts/init_db.sh

env:
	./scripts/create_env.sh

paper:
	PYTHONPATH=src python scripts/run_paper.py --config config.paper.yaml

paper-perps:
	PYTHONPATH=src python scripts/run_paper.py --config config.perps_intraday.paper.yaml

replay:
	PYTHONPATH=src python -m autonomous_investment_robot replay --config config.perps_intraday.paper.yaml --source fixtures

test:
	pytest -q
