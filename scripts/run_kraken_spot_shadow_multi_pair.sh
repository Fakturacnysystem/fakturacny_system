#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_common_env.sh"

export AUTONOMOUS_PAIR_UNIVERSE="${AUTONOMOUS_PAIR_UNIVERSE:-SOL/EUR,BTC/EUR,ETH/EUR}"
export AUTONOMOUS_MAX_ACTIVE_PAIRS="${AUTONOMOUS_MAX_ACTIVE_PAIRS:-3}"
export AUTONOMOUS_PAIR_CLUSTERING_ENABLED="${AUTONOMOUS_PAIR_CLUSTERING_ENABLED:-1}"

run_robot live-readonly --config config.kraken_spot.readonly_analysis.yaml
