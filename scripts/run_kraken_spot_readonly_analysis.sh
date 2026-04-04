#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_common_env.sh"
run_robot live-readonly --config config.kraken_spot.readonly_analysis.yaml
"$(dirname "$0")/generate_performance_gap_report.py" --run-id latest >/dev/null 2>&1 || true
"$(dirname "$0")/generate_pair_ranking_report.py" --run-id latest >/dev/null 2>&1 || true
"$(dirname "$0")/generate_regime_report.py" --run-id latest >/dev/null 2>&1 || true
