#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"
source "${ROOT_DIR}/scripts/_common_env.sh"

PYTHON_BIN="$(resolve_python_bin)"

PYTHONPATH=src "${PYTHON_BIN}" -m autonomous_investment_robot replay --config config.kraken_spot.live_readonly.yaml --source recordings
