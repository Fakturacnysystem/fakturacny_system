#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.full.yml"
LIVE_ENV="${ROOT_DIR}/deploy/live-node.env"
COMPUTE_ENV="${ROOT_DIR}/deploy/compute-node.env"
FALLBACK_LIVE="${ROOT_DIR}/deploy/live-node.env.example"
FALLBACK_COMPUTE="${ROOT_DIR}/deploy/compute-node.env.example"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "[start_ultra_profit_cluster] Missing compose file: ${COMPOSE_FILE}" >&2
  exit 2
fi

if [[ ! -f "${LIVE_ENV}" ]]; then
  LIVE_ENV="${FALLBACK_LIVE}"
fi
if [[ ! -f "${COMPUTE_ENV}" ]]; then
  COMPUTE_ENV="${FALLBACK_COMPUTE}"
fi

set -a
source "${LIVE_ENV}"
source "${COMPUTE_ENV}"
set +a

docker compose -f "${COMPOSE_FILE}" up -d --build
docker compose -f "${COMPOSE_FILE}" ps

echo "[start_ultra_profit_cluster] Cluster started (live + compute + infra)."
echo "[start_ultra_profit_cluster] Follow logs:"
echo "  docker compose -f ${COMPOSE_FILE} logs -f live-node compute-node"
