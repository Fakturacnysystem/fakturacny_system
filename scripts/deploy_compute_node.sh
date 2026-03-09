#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.compute.yml"
DEFAULT_ENV="${ROOT_DIR}/deploy/compute-node.env"
FALLBACK_ENV="${ROOT_DIR}/deploy/compute-node.env.example"
ENV_FILE="${1:-${DEFAULT_ENV}}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "[deploy_compute_node] Missing compose file: ${COMPOSE_FILE}" >&2
  exit 2
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  if [[ -f "${FALLBACK_ENV}" ]]; then
    ENV_FILE="${FALLBACK_ENV}"
  else
    echo "[deploy_compute_node] Missing env file: ${ENV_FILE}" >&2
    exit 2
  fi
fi

echo "[deploy_compute_node] compose=${COMPOSE_FILE}"
echo "[deploy_compute_node] env=${ENV_FILE}"

docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d --build
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" ps
