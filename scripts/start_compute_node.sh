#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-${ROOT_DIR}/deploy/compute-node.env}"

"${ROOT_DIR}/scripts/deploy_compute_node.sh" "${ENV_FILE}"

echo "[start_compute_node] Compute node started."
echo "[start_compute_node] Follow logs:"
echo "  docker compose -f ${ROOT_DIR}/docker-compose.compute.yml --env-file ${ENV_FILE} logs -f compute-node"
