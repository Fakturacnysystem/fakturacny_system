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
SUP_LOG="${RUN_DIR}/harmony24h_supervisor.log"
BOT_LOG="${RUN_DIR}/harmony24h_bot.out"
: > "${SUP_LOG}"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

log() {
  printf "%s %s\n" "$(ts)" "$*" | tee -a "${SUP_LOG}" >/dev/null
}

trap 'log "status=signal signal=INT_TERM"' INT TERM
trap 'rc=$?; log "status=exit code=${rc}"' EXIT

bot_pids() {
  pgrep -f "cli.run --config ${CONFIG_PATH}" || true
}

bot_count() {
  local n
  n="$(bot_pids | sed '/^\s*$/d' | wc -l | tr -d ' ')"
  echo "${n:-0}"
}

stop_bot() {
  log "action=stop_bot"
  pkill -f "cli.run --config ${CONFIG_PATH}" || true
  pkill -f "run_kraken_spot_live.sh" || true
  sleep 2
  if [[ "$(bot_count)" -gt 0 ]]; then
    log "action=stop_bot_force_kill"
    pkill -9 -f "cli.run --config ${CONFIG_PATH}" || true
    pkill -9 -f "run_kraken_spot_live.sh" || true
    sleep 1
  fi
  for _ in $(seq 1 10); do
    if [[ "$(bot_count)" -eq 0 ]]; then
      break
    fi
    sleep 1
  done
}

start_bot() {
  local force="${1:-0}"
  local count
  count="$(bot_count)"
  if [[ "${count}" -gt 0 ]]; then
    if [[ "${force}" == "1" ]]; then
      log "action=start_bot_force_stop count=${count}"
      stop_bot
      count="$(bot_count)"
    fi
  fi
  if [[ "${count}" -gt 0 ]]; then
    log "action=start_bot_skip reason=already_running count=${count}"
    return 0
  fi
  rm -f "${RUN_DIR}/health.json" "${RUN_DIR}/watchdog_state.json"
  log "action=start_bot"
  (
    TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
    nohup bash ./scripts/run_kraken_spot_live.sh >> "${BOT_LOG}" 2>&1 &
    echo $! > "${RUN_DIR}/harmony24h_supervisor.pid"
  )
  sleep 6
}

json_get_ok() {
  local payload="$1"
  python3 - "${payload}" <<'PY'
import json
import math
import sys

raw = sys.argv[1].strip()
if not raw:
    print("0")
    raise SystemExit(0)
try:
    data = json.loads(raw)
except Exception:
    print("0")
    raise SystemExit(0)
ok = bool(data.get("ok"))
running = bool(data.get("running", True))
age = data.get("heartbeat_age_s")
if isinstance(age, (int, float)) and (math.isinf(age) or age > 120):
    ok = False
if age in {"Infinity", "inf"}:
    ok = False
print("1" if (ok and running) else "0")
PY
}

health_ok() {
  local raw
  raw="$(TESTNET_VALIDATED=true ./.venv/bin/python -m cli.health --config "${CONFIG_PATH}" 2>/dev/null || true)"
  json_get_ok "${raw}"
}

audit_ok() {
  local raw
  raw="$(TESTNET_VALIDATED=true ./.venv/bin/python -m cli.audit110 --config "${CONFIG_PATH}" --once 2>/dev/null || true)"
  python3 - "${raw}" <<'PY'
import json
import sys

raw = sys.argv[1]
start = raw.find("{")
end = raw.rfind("}")
if start < 0 or end < start:
    print("0")
    raise SystemExit(0)
try:
    data = json.loads(raw[start : end + 1])
except Exception:
    print("0")
    raise SystemExit(0)
print("1" if bool(data.get("ok")) else "0")
PY
}

ensure_single_instance() {
  local count
  count="$(bot_count)"
  if [[ "${count}" -le 2 ]]; then
    return 0
  fi
  log "action=restart reason=duplicate_processes count=${count}"
  stop_bot
  start_bot 1
}

restart_on_failure() {
  local reason="$1"
  log "action=restart reason=${reason}"
  stop_bot
  start_bot 1
}

start_ts="$(date +%s)"
end_ts="$((start_ts + DURATION_HOURS * 3600))"

log "status=begin config=${CONFIG_PATH} run_dir=${RUN_DIR} check_interval_s=${CHECK_INTERVAL_S} duration_h=${DURATION_HOURS}"
start_bot

while true; do
  now_ts="$(date +%s)"
  if [[ "${now_ts}" -ge "${end_ts}" ]]; then
    log "status=complete duration_h=${DURATION_HOURS}"
    break
  fi

  ensure_single_instance

  health_state="$(health_ok || echo 0)"
  audit_state="$(audit_ok || echo 0)"

  if [[ "${health_state}" != "1" ]]; then
    restart_on_failure "health_failed"
  elif [[ "${audit_state}" != "1" ]]; then
    restart_on_failure "audit110_failed"
  else
    log "status=ok health=1 audit110=1 pids=$(bot_pids | tr '\n' ',' | sed 's/,$//')"
  fi

  sleep "${CHECK_INTERVAL_S}"
done
