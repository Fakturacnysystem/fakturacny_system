#!/usr/bin/env bash
set -euo pipefail
PYTHONPATH=src python3 -m autonomous_investment_robot live-readonly --config config.kraken_spot.live_readonly.yaml
