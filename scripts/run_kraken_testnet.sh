#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_common_env.sh"
require_env KRAKEN_API_KEY
require_env KRAKEN_API_SECRET
export ENABLE_LIVE_TRADING="${ENABLE_LIVE_TRADING:-true}"
export ACK_I_UNDERSTAND_RISKS="${ACK_I_UNDERSTAND_RISKS:-true}"
run_robot live --config config.kraken_derivatives.testnet.yaml
