#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_common_env.sh"

python3 -m pytest -q tests/test_kraken_provider.py tests/test_kraken_connector.py
run_robot live-readonly --config config.kraken_derivatives.live_readonly.yaml

echo
echo "Kraken signed trading adapter is implemented (REST v3 core endpoints) but must be validated on testnet first."
echo "Next step: ./scripts/run_kraken_testnet.sh"
