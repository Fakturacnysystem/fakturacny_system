#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.full.yml"

"${ROOT_DIR}/scripts/validate_compose_runtime.sh" || {
  rc=$?
  if [[ "${rc}" -eq 2 ]]; then
    echo "[smoke_test_distributed_cluster] BLOCKED by host infrastructure (docker unavailable)." >&2
    exit 2
  fi
  exit "${rc}"
}

echo "[smoke_test_distributed_cluster] Starting cluster..."
docker compose -f "${COMPOSE_FILE}" up -d --build
docker compose -f "${COMPOSE_FILE}" ps

echo "[smoke_test_distributed_cluster] Verifying in-repo distributed e2e contract..."
pytest -q "${ROOT_DIR}/tests/test_distributed_e2e.py"

if [[ "${AUTONOMOUS_SMOKE_KEEP_UP:-0}" != "1" ]]; then
  echo "[smoke_test_distributed_cluster] Stopping cluster..."
  docker compose -f "${COMPOSE_FILE}" down
fi

echo "[smoke_test_distributed_cluster] OK"
