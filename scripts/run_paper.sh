#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

CONFIG="${1:-config.kraken_spot.paper.yaml}"
export LIVE_TRADING="${LIVE_TRADING:-false}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" && -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi
if [[ -z "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

echo "[run_paper] config=${CONFIG}"
echo "[run_paper] LIVE_TRADING=${LIVE_TRADING} (forced-safe default)"

PYTHONPATH=src "${PYTHON_BIN}" -m cli.run --config "${CONFIG}" --once
