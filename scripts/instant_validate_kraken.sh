#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_common_env.sh"

python3 -m pytest -q tests/test_kraken_provider.py
run_robot live-readonly --config config.kraken_derivatives.live_readonly.yaml

echo
echo "Kraken live trading path is intentionally fail-closed until signed order adapter is implemented."
echo "Try testnet preflight (expected blocked): ./scripts/run_kraken_testnet.sh"
