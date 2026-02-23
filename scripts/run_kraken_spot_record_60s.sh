#!/usr/bin/env bash
set -euo pipefail
PYTHONPATH=src python3 -m autonomous_investment_robot record --config config.kraken_spot.live_readonly.yaml --duration-seconds 60
