#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "Applying Postgres schema..."
docker compose -f infra/docker-compose.yml exec -T postgres psql -U robot -d robot < sql/postgres.sql

echo "Applying ClickHouse schema..."
docker compose -f infra/docker-compose.yml exec -T clickhouse clickhouse-client --multiquery < sql/clickhouse.sql

echo "DB init complete"
