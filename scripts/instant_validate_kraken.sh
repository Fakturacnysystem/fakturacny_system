#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_common_env.sh"

PYTEST_BIN="${PYTEST_BIN:-pytest}"
if ! command -v "$PYTEST_BIN" >/dev/null 2>&1; then
  echo "Missing pytest executable: ${PYTEST_BIN}" >&2
  exit 1
fi

"$PYTEST_BIN" -q tests/test_kraken_provider.py tests/test_kraken_connector.py
run_robot live-readonly --config config.kraken_derivatives.live_readonly.yaml

echo
echo "Kraken signed trading adapter is implemented (REST v3 core endpoints) but must be validated on testnet first."
echo "Next step: ./scripts/run_kraken_testnet.sh"
