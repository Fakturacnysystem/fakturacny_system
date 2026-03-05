#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -z "${KRAKEN_API_KEY:-}" || -z "${KRAKEN_API_SECRET:-}" ]]; then
  echo "Missing Kraken Spot credentials in env: set KRAKEN_API_KEY and KRAKEN_API_SECRET" >&2
  exit 2
fi
if [[ "${KRAKEN_API_KEY}" == " "* || "${KRAKEN_API_KEY}" == *" " ]]; then
  echo "KRAKEN_API_KEY has leading/trailing space" >&2
  exit 2
fi
if [[ "${KRAKEN_API_SECRET}" == " "* || "${KRAKEN_API_SECRET}" == *" " ]]; then
  echo "KRAKEN_API_SECRET has leading/trailing space" >&2
  exit 2
fi

# ---- PRO GROWTH MODE (profit-first + hard guards) ----
export AUTONOMOUS_GUARDS_MODE="${AUTONOMOUS_GUARDS_MODE:-strict}"
export AUTONOMOUS_WALK_FORWARD_ENFORCE="${AUTONOMOUS_WALK_FORWARD_ENFORCE:-false}"
export AUTONOMOUS_NESTED_WALK_FORWARD_ENFORCE="${AUTONOMOUS_NESTED_WALK_FORWARD_ENFORCE:-false}"

# stable self tuner (less twitchy than 10/5)
export AUTONOMOUS_SELF_TUNER_MIN_SAMPLES="${AUTONOMOUS_SELF_TUNER_MIN_SAMPLES:-30}"
export AUTONOMOUS_SELF_TUNER_EVERY_STEPS="${AUTONOMOUS_SELF_TUNER_EVERY_STEPS:-20}"

# small-balance sizing
export AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE="${AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE:-6.5}"
export AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE="${AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE:-9.5}"

# exchange API physics (prevents rate_limit_storm)
export AUTONOMOUS_RATE_LIMIT_COOLDOWN_S="${AUTONOMOUS_RATE_LIMIT_COOLDOWN_S:-3}"

# profit filters (net edge after costs)
export AUTONOMOUS_MIN_NET_EDGE_BPS="${AUTONOMOUS_MIN_NET_EDGE_BPS:-1.3}"
export AUTONOMOUS_MAX_COST_TO_ALPHA_RATIO="${AUTONOMOUS_MAX_COST_TO_ALPHA_RATIO:-1.1}"

# IMPORTANT: do NOT hardcode secrets here.
# Expect KRAKEN_API_KEY / KRAKEN_API_SECRET already in environment.

TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
PYTHONPATH=src python3 -m autonomous_investment_robot live --config config.kraken_spot.live_pro_growth.yaml
