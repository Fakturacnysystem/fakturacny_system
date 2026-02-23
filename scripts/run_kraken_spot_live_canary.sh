#!/usr/bin/env bash
set -euo pipefail
TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.live_canary.yaml
