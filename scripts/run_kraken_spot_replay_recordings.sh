#!/usr/bin/env bash
set -euo pipefail
PYTHONPATH=src python3 -m autonomous_investment_robot replay --config config.kraken_spot.live_readonly.yaml --source recordings
