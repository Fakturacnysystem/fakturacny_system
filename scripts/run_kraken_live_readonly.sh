#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_common_env.sh"
run_robot live-readonly --config config.kraken_derivatives.live_readonly.yaml
