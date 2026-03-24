#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_common_env.sh"
run_robot run --config config.kraken_spot.paper_full_analysis.yaml
