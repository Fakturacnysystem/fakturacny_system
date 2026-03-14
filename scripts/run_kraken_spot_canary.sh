#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source "./scripts/_common_env.sh"
PYTHON_BIN="$(resolve_python_bin)"

: "${KRAKEN_API_KEY:?Set KRAKEN_API_KEY}"
: "${KRAKEN_API_SECRET:?Set KRAKEN_API_SECRET}"

LIVE_CONFIG="${AUTONOMOUS_LIVE_CONFIG:-config.kraken_spot.live_profit.yaml}"
if [[ ! -f "${LIVE_CONFIG}" ]]; then
  LIVE_CONFIG="config.kraken_spot.live.yaml"
fi

RUN_DIR="${AUTONOMOUS_RUN_DIR:-}"
if [[ -z "${RUN_DIR}" ]]; then
  RUN_DIR="$("${PYTHON_BIN}" - "${LIVE_CONFIG}" <<'PY'
from pathlib import Path
import json
import sys
default_run_dir = "runs/kraken_spot_live"
p = Path(sys.argv[1])
if not p.exists():
    print(default_run_dir)
    raise SystemExit(0)
text = p.read_text(encoding="utf-8")
data = {}
try:
    import yaml  # type: ignore
    x = yaml.safe_load(text)
    if isinstance(x, dict):
        data = x
except Exception:
    pass
if not data:
    try:
        x = json.loads(text)
        if isinstance(x, dict):
            data = x
    except Exception:
        pass
storage = data.get("storage", {}) if isinstance(data, dict) else {}
run_dir = storage.get("run_dir") if isinstance(storage, dict) else ""
print(run_dir if isinstance(run_dir, str) and run_dir.strip() else default_run_dir)
PY
)"
fi

for f in "${RUN_DIR}/env_overrides.sh" "${RUN_DIR}/operator_overrides.sh"; do
  if [[ -f "${f}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${f}"
    set +a
  fi
done

export AUTONOMOUS_MODE_LABEL="${AUTONOMOUS_MODE_LABEL:-canary}"
export AUTONOMOUS_GROWTH_MAX_FRACTION="${AUTONOMOUS_GROWTH_MAX_FRACTION:-0.20}"
export AUTONOMOUS_CANARY_AUTOPILOT="${AUTONOMOUS_CANARY_AUTOPILOT:-true}"
export AUTONOMOUS_LIVE_LOOP_MAX_STEPS="${AUTONOMOUS_LIVE_LOOP_MAX_STEPS:-1200}"
export PYTHONUNBUFFERED=1

TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
PYTHONPATH=src "${PYTHON_BIN}" -m autonomous_investment_robot live --config "${LIVE_CONFIG}"
