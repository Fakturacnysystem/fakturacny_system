#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

CONFIG="${1:-config.kraken_spot.paper.yaml}"
export LIVE_TRADING="${LIVE_TRADING:-false}"

echo "[run_paper] config=${CONFIG}"
echo "[run_paper] LIVE_TRADING=${LIVE_TRADING} (forced-safe default)"

python3 -m cli.run --config "${CONFIG}" --once
