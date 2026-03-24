#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_common_env.sh"
run_robot replay-report --config config.kraken_spot.replay_full_analysis.yaml
