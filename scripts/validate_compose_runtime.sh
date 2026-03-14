#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" && -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
fi
if [[ -z "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[validate_compose_runtime] BLOCKED: docker is not installed on this host." >&2
  exit 2
fi

echo "[validate_compose_runtime] Validating compose syntax..."
docker compose -f "${ROOT_DIR}/docker-compose.live.yml" config >/dev/null
docker compose -f "${ROOT_DIR}/docker-compose.compute.yml" config >/dev/null
docker compose -f "${ROOT_DIR}/docker-compose.full.yml" config >/dev/null

echo "[validate_compose_runtime] Validating deployment manifests..."
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/validate_deployment_manifests.py" >/dev/null

echo "[validate_compose_runtime] OK"
