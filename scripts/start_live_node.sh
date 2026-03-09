#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-${ROOT_DIR}/deploy/live-node.env}"

"${ROOT_DIR}/scripts/deploy_live_node.sh" "${ENV_FILE}"

echo "[start_live_node] Live node started."
echo "[start_live_node] Follow logs:"
echo "  docker compose -f ${ROOT_DIR}/docker-compose.live.yml --env-file ${ENV_FILE} logs -f live-node"
