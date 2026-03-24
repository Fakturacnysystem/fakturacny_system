#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_common_env.sh"

require_env KRAKEN_API_KEY
require_env KRAKEN_API_SECRET
require_env TESTNET_VALIDATED
require_true_env ENABLE_LIVE_TRADING
require_true_env ACK_I_UNDERSTAND_RISKS

run_robot live --config config.kraken_derivatives.live.yaml
