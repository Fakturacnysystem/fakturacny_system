#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"
source "${ROOT_DIR}/scripts/_common_env.sh"

CONFIG="${1:-config.kraken_spot.paper.yaml}"
export LIVE_TRADING="${LIVE_TRADING:-false}"
PYTHON_BIN="$(resolve_python_bin)"

echo "[run_paper] config=${CONFIG}"
echo "[run_paper] LIVE_TRADING=${LIVE_TRADING} (forced-safe default)"

PYTHONPATH=src "${PYTHON_BIN}" -m cli.run --config "${CONFIG}" --once
