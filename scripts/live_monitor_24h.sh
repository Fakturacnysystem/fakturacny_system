#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

CONFIG_PATH="${CONFIG_PATH:-config.kraken_spot.live_profit.yaml}"
CHECK_INTERVAL_S="${CHECK_INTERVAL_S:-600}"
DURATION_HOURS="${DURATION_HOURS:-24}"

if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "Missing config: ${CONFIG_PATH}" >&2
  exit 2
fi

RUN_DIR="$(
  python3 - "${CONFIG_PATH}" <<'PY'
from pathlib import Path
import json
import sys

cfg = Path(sys.argv[1])
default = "runs/kraken_spot_live_harmonic24h"
text = cfg.read_text(encoding="utf-8")
data = {}
try:
    import yaml  # type: ignore
    parsed = yaml.safe_load(text)
    if isinstance(parsed, dict):
        data = parsed
except Exception:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            data = parsed
    except Exception:
        data = {}
storage = data.get("storage", {}) if isinstance(data, dict) else {}
run_dir = storage.get("run_dir") if isinstance(storage, dict) else None
print(run_dir if isinstance(run_dir, str) and run_dir.strip() else default)
PY
)"

mkdir -p "${RUN_DIR}" runs/live
MON_LOG="${RUN_DIR}/monitor_24h.log"
BOT_LOG="runs/live/kraken_profit_full_throttle_25usd.out"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { printf "%s %s\n" "$(ts)" "$*" | tee -a "${MON_LOG}" >/dev/null; }

bot_pids() {
  pgrep -f "cli.run --config ${CONFIG_PATH} --nonstop" || true
}

bot_count() {
  local n
  n="$(bot_pids | sed '/^\s*$/d' | wc -l | tr -d ' ')"
  echo "${n:-0}"
}

stop_bot() {
  log "action=stop_bot"
  pkill -f "cli.run --config ${CONFIG_PATH} --nonstop" || true
  pkill -f "run_kraken_spot_live.sh" || true
  sleep 2
}

start_bot() {
  local count
  count="$(bot_count)"
  if [[ "${count}" -gt 0 ]]; then
    log "action=start_bot_skip reason=already_running count=${count}"
    return 0
  fi
  log "action=start_bot"
  TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
    nohup bash ./scripts/run_kraken_spot_live.sh >> "${BOT_LOG}" 2>&1 < /dev/null &
  sleep 5
}

health_ok() {
  TESTNET_VALIDATED=true ./.venv/bin/python -m cli.health --config "${CONFIG_PATH}" 2>/dev/null \
    | python3 - <<'PY'
import json
import sys
raw = sys.stdin.read().strip()
if not raw:
    print("0")
    raise SystemExit(0)
try:
    data = json.loads(raw)
except Exception:
    print("0")
    raise SystemExit(0)
print("1" if bool(data.get("ok")) and bool(data.get("running", True)) else "0")
PY
}

audit_ok() {
  TESTNET_VALIDATED=true ./.venv/bin/python -m cli.audit110 --config "${CONFIG_PATH}" --once 2>/dev/null \
    | python3 - <<'PY'
import json
import sys
raw = sys.stdin.read()
start = raw.find("{")
end = raw.rfind("}")
if start < 0 or end < start:
    print("0")
    raise SystemExit(0)
try:
    data = json.loads(raw[start:end+1])
except Exception:
    print("0")
    raise SystemExit(0)
print("1" if bool(data.get("ok")) else "0")
PY
}

start_ts="$(date +%s)"
end_ts="$((start_ts + DURATION_HOURS * 3600))"

log "status=begin config=${CONFIG_PATH} run_dir=${RUN_DIR} check_interval_s=${CHECK_INTERVAL_S} duration_h=${DURATION_HOURS}"
start_bot

while true; do
  now_ts="$(date +%s)"
  if [[ "${now_ts}" -ge "${end_ts}" ]]; then
    log "status=complete duration_h=${DURATION_HOURS}"
    exit 0
  fi

  count="$(bot_count)"
  if [[ "${count}" -gt 1 ]]; then
    log "action=restart reason=duplicate_processes count=${count}"
    stop_bot
    start_bot
  elif [[ "${count}" -eq 0 ]]; then
    log "action=restart reason=bot_not_running"
    start_bot
  fi

  h="$(health_ok || echo 0)"
  a="$(audit_ok || echo 0)"
  if [[ "${h}" != "1" || "${a}" != "1" ]]; then
    log "action=restart reason=health_or_audit_failed health=${h} audit=${a}"
    stop_bot
    start_bot
  else
    log "status=ok health=1 audit110=1 pids=$(bot_pids | tr '\n' ',' | sed 's/,$//')"
  fi

  sleep "${CHECK_INTERVAL_S}"
done

