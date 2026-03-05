#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

CONFIG="${1:-config.kraken_spot.live_profit.yaml}"
LIVE_FLAG="$(printf '%s' "${LIVE_TRADING:-false}" | tr '[:upper:]' '[:lower:]')"

if [[ "${LIVE_FLAG}" != "true" ]]; then
  echo "[run_live] LIVE_TRADING is not true. Refusing to start live mode."
  echo "[run_live] Set LIVE_TRADING=true explicitly to proceed."
  exit 2
fi

if [[ -z "${KRAKEN_API_KEY:-}" || -z "${KRAKEN_API_SECRET:-}" ]]; then
  echo "[run_live] Missing KRAKEN_API_KEY or KRAKEN_API_SECRET."
  exit 2
fi

echo "============================================================"
echo "LIVE MODE WARNING"
echo "- This can place real exchange orders."
echo "- Profit is NOT guaranteed."
echo "- Sell/close invariant remains enforced by ProfitGate >= +2% net."
echo "============================================================"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" && -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi
if [[ -z "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

"${PYTHON_BIN}" -m cli.run --config "${CONFIG}" --nonstop
