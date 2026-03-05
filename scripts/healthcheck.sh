#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

CONFIG="${1:-config.kraken_spot.live_profit.yaml}"
python3 -m cli.health --config "${CONFIG}"
