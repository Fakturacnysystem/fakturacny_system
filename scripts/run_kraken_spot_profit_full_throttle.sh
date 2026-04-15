#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_common_env.sh"
load_runtime_env_from_supported_sources

require_env KRAKEN_SPOT_API_KEY
require_env KRAKEN_SPOT_API_SECRET
require_true_env ENABLE_LIVE_TRADING
require_true_env ACK_I_UNDERSTAND_RISKS

run_robot live --config config.kraken_spot.live.yaml
