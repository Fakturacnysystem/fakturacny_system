#!/usr/bin/env bash
set -euo pipefail
PYTHONPATH=src python3 -m autonomous_investment_robot run --config config.perps_intraday.paper.yaml
