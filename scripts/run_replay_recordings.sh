#!/usr/bin/env bash
set -euo pipefail
PYTHONPATH=src python3 -m autonomous_investment_robot replay \
  --config=config.perps_intraday.live_readonly.yaml \
  --source=recordings --run-id=latest
