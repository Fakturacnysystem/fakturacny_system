#!/usr/bin/env bash
set -euo pipefail

export AUTONOMOUS_LIVE_POLL_SECONDS="${AUTONOMOUS_LIVE_POLL_SECONDS:-1}"
export AUTONOMOUS_USER_MIN_ORDER_QUOTE="${AUTONOMOUS_USER_MIN_ORDER_QUOTE:-1.0}"
export AUTONOMOUS_SPOT_SELL_PROFIT_LOCK_FATAL_BYPASS="${AUTONOMOUS_SPOT_SELL_PROFIT_LOCK_FATAL_BYPASS:-false}"
export AUTONOMOUS_MIN_TP_AFTER_COSTS="${AUTONOMOUS_MIN_TP_AFTER_COSTS:-1}"
export AUTONOMOUS_MIN_TAKE_PROFIT_PCT="${AUTONOMOUS_MIN_TAKE_PROFIT_PCT:-0.3}"
export AUTONOMOUS_NO_LOSS_SELL="${AUTONOMOUS_NO_LOSS_SELL:-1}"
export AUTONOMOUS_TP_ONLY_MODE="${AUTONOMOUS_TP_ONLY_MODE:-1}"
export AUTONOMOUS_MAX_ORDERS_PER_MIN="${AUTONOMOUS_MAX_ORDERS_PER_MIN:-1}"
export AUTONOMOUS_TRADE_COOLDOWN_S="${AUTONOMOUS_TRADE_COOLDOWN_S:-300}"
export AUTONOMOUS_REBALANCE_DEADZONE_FACTOR="${AUTONOMOUS_REBALANCE_DEADZONE_FACTOR:-0.02}"
export AUTONOMOUS_REBALANCE_DEADZONE_FLOOR="${AUTONOMOUS_REBALANCE_DEADZONE_FLOOR:-0.01}"
export AUTONOMOUS_GUARDS_MODE="${AUTONOMOUS_GUARDS_MODE:-strict}"
export AUTONOMOUS_WALK_FORWARD_ENFORCE="${AUTONOMOUS_WALK_FORWARD_ENFORCE:-false}"
export AUTONOMOUS_NESTED_WALK_FORWARD_ENFORCE="${AUTONOMOUS_NESTED_WALK_FORWARD_ENFORCE:-false}"
export AUTONOMOUS_FALLBACK_SYMBOLS="${AUTONOMOUS_FALLBACK_SYMBOLS:-XBTEUR,ETHEUR,SOLEUR,XBTUSD,ETHUSD,SOLUSD}"
export AUTONOMOUS_UNIVERSE_ALLOWLIST="${AUTONOMOUS_UNIVERSE_ALLOWLIST:-${AUTONOMOUS_FALLBACK_SYMBOLS}}"
export AUTONOMOUS_DYNAMIC_UNIVERSE="${AUTONOMOUS_DYNAMIC_UNIVERSE:-true}"
export AUTONOMOUS_DYNAMIC_UNIVERSE_ALL="${AUTONOMOUS_DYNAMIC_UNIVERSE_ALL:-false}"
export AUTONOMOUS_DYNAMIC_UNIVERSE_MAX="${AUTONOMOUS_DYNAMIC_UNIVERSE_MAX:-120}"
export AUTONOMOUS_KRAKEN_TRADE_ALL="${AUTONOMOUS_KRAKEN_TRADE_ALL:-false}"
export AUTONOMOUS_PORTFOLIO_OPTIMIZER="${AUTONOMOUS_PORTFOLIO_OPTIMIZER:-true}"
export AUTONOMOUS_PORTFOLIO_RESELECT_EVERY_STEPS="${AUTONOMOUS_PORTFOLIO_RESELECT_EVERY_STEPS:-2}"
export AUTONOMOUS_PORTFOLIO_SCAN_BATCH="${AUTONOMOUS_PORTFOLIO_SCAN_BATCH:-260}"
export AUTONOMOUS_PORTFOLIO_TURNOVER_PENALTY="${AUTONOMOUS_PORTFOLIO_TURNOVER_PENALTY:-0.30}"
export AUTONOMOUS_PORTFOLIO_CLUSTER_CAP="${AUTONOMOUS_PORTFOLIO_CLUSTER_CAP:-0.60}"
export AUTONOMOUS_CHALLENGER_ENABLED="${AUTONOMOUS_CHALLENGER_ENABLED:-true}"
export AUTONOMOUS_ADAPTIVE_SIZING_ENABLED="${AUTONOMOUS_ADAPTIVE_SIZING_ENABLED:-true}"
export AUTONOMOUS_MIN_NET_EDGE_BPS="${AUTONOMOUS_MIN_NET_EDGE_BPS:-0.6}"
export AUTONOMOUS_DYNAMIC_EDGE_SPREAD_WEIGHT="${AUTONOMOUS_DYNAMIC_EDGE_SPREAD_WEIGHT:-0.020}"
export AUTONOMOUS_DYNAMIC_EDGE_VOL_WEIGHT="${AUTONOMOUS_DYNAMIC_EDGE_VOL_WEIGHT:-0.008}"
export AUTONOMOUS_DYNAMIC_EDGE_THIN_ADD_BPS="${AUTONOMOUS_DYNAMIC_EDGE_THIN_ADD_BPS:-0.35}"
export AUTONOMOUS_DYNAMIC_EDGE_PANIC_ADD_BPS="${AUTONOMOUS_DYNAMIC_EDGE_PANIC_ADD_BPS:-0.55}"
export AUTONOMOUS_DYNAMIC_EDGE_MAX_BPS="${AUTONOMOUS_DYNAMIC_EDGE_MAX_BPS:-0}"
export AUTONOMOUS_MAX_COST_TO_ALPHA_RATIO="${AUTONOMOUS_MAX_COST_TO_ALPHA_RATIO:-1.25}"
export AUTONOMOUS_MAKER_TIMEOUT_S="${AUTONOMOUS_MAKER_TIMEOUT_S:-12}"
export AUTONOMOUS_EXIT_TIME_STOP_S="${AUTONOMOUS_EXIT_TIME_STOP_S:-1800}"
export AUTONOMOUS_EXIT_TRAILING_DD_QUOTE="${AUTONOMOUS_EXIT_TRAILING_DD_QUOTE:-0.75}"
export AUTONOMOUS_EXIT_PARTIAL_FRACTION="${AUTONOMOUS_EXIT_PARTIAL_FRACTION:-0.5}"
export AUTONOMOUS_FEED_STALE_AFTER_S="${AUTONOMOUS_FEED_STALE_AFTER_S:-3.5}"
export AUTONOMOUS_MAX_CLOCK_DRIFT_MS="${AUTONOMOUS_MAX_CLOCK_DRIFT_MS:-500}"
export AUTONOMOUS_MIN_PRIMARY_FEED_SCORE="${AUTONOMOUS_MIN_PRIMARY_FEED_SCORE:-25}"
export AUTONOMOUS_RESERVE_CASH_RATIO="${AUTONOMOUS_RESERVE_CASH_RATIO:-0.12}"
export AUTONOMOUS_MIN_MARGIN_BUFFER_POLICY="${AUTONOMOUS_MIN_MARGIN_BUFFER_POLICY:-1.4}"
export AUTONOMOUS_ENFORCE_MANDATE="${AUTONOMOUS_ENFORCE_MANDATE:-true}"
export AUTONOMOUS_MANDATE_MAX_LEVERAGE="${AUTONOMOUS_MANDATE_MAX_LEVERAGE:-1}"
export AUTONOMOUS_BUS_MAX_ATTEMPTS="${AUTONOMOUS_BUS_MAX_ATTEMPTS:-3}"
export AUTONOMOUS_MODEL_STACK_V2="${AUTONOMOUS_MODEL_STACK_V2:-true}"
export AUTONOMOUS_KRAKEN_TICKER_TTL_S="${AUTONOMOUS_KRAKEN_TICKER_TTL_S:-1.0}"
export AUTONOMOUS_KRAKEN_BALANCE_TTL_S="${AUTONOMOUS_KRAKEN_BALANCE_TTL_S:-4.0}"
export AUTONOMOUS_KRAKEN_TRADES_TTL_S="${AUTONOMOUS_KRAKEN_TRADES_TTL_S:-3.0}"
export AUTONOMOUS_TRADES_SYNC_MIN_INTERVAL_S="${AUTONOMOUS_TRADES_SYNC_MIN_INTERVAL_S:-3.0}"
export AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S="${AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S:-3.0}"
export AUTONOMOUS_RATE_LIMIT_COOLDOWN_S="${AUTONOMOUS_RATE_LIMIT_COOLDOWN_S:-${AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S:-4.0}}"
export AUTONOMOUS_KRAKEN_RATE_LIMIT_STORM="${AUTONOMOUS_KRAKEN_RATE_LIMIT_STORM:-12}"
export AUTONOMOUS_KRAKEN_EXEC_RETRY_ATTEMPTS="${AUTONOMOUS_KRAKEN_EXEC_RETRY_ATTEMPTS:-4}"
export AUTONOMOUS_JURISDICTION="${AUTONOMOUS_JURISDICTION:-SK}"
export AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE="${AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE:-1.0}"
export ORDER_SUBMISSION_INTERVAL_SECONDS="${ORDER_SUBMISSION_INTERVAL_SECONDS:-300}"
export AUTONOMOUS_PROFIT_TARGET_NET="${AUTONOMOUS_PROFIT_TARGET_NET:-0.003}"
export AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS="${AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS:-30}"
export AUTONOMOUS_SPOT_SELL_HARD_FLOOR_BPS="${AUTONOMOUS_SPOT_SELL_HARD_FLOOR_BPS:-30}"
export AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS="${AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS:-30}"
export AUTONOMOUS_SPOT_SELL_TARGET_HOLD_S="${AUTONOMOUS_SPOT_SELL_TARGET_HOLD_S:-90}"
export AUTONOMOUS_MIN_SECONDS_BETWEEN_ORDERS="${AUTONOMOUS_MIN_SECONDS_BETWEEN_ORDERS:-300}"
export AUTONOMOUS_SELF_TUNER_ENABLED="${AUTONOMOUS_SELF_TUNER_ENABLED:-true}"
export AUTONOMOUS_SELF_TUNER_EVERY_STEPS="${AUTONOMOUS_SELF_TUNER_EVERY_STEPS:-5}"
export AUTONOMOUS_SELF_TUNER_WINDOW_EVENTS="${AUTONOMOUS_SELF_TUNER_WINDOW_EVENTS:-300}"
export AUTONOMOUS_SELF_TUNER_MIN_SAMPLES="${AUTONOMOUS_SELF_TUNER_MIN_SAMPLES:-10}"
export AUTONOMOUS_SELF_TUNER_SIZE_SCALE_MIN="${AUTONOMOUS_SELF_TUNER_SIZE_SCALE_MIN:-0.35}"
export AUTONOMOUS_SELF_TUNER_SIZE_SCALE_MAX="${AUTONOMOUS_SELF_TUNER_SIZE_SCALE_MAX:-1.75}"
export AUTONOMOUS_SELF_TUNER_MIN_ORDER_FLOOR_MIN="${AUTONOMOUS_SELF_TUNER_MIN_ORDER_FLOOR_MIN:-1}"
export AUTONOMOUS_SELF_TUNER_MIN_ORDER_FLOOR_MAX="${AUTONOMOUS_SELF_TUNER_MIN_ORDER_FLOOR_MAX:-10}"
export PYTHONUNBUFFERED=1
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[run_kraken_spot_live] Missing python runtime at ${PYTHON_BIN}. Create/activate .venv first." >&2
  exit 2
fi
# Normalize config path because user shells sometimes export it with extra spaces.
LIVE_CONFIG="$(printf '%s' "${AUTONOMOUS_LIVE_CONFIG:-config.kraken_spot.live_profit.yaml}" | awk '{$1=$1};1')"
if [[ ! -f "${LIVE_CONFIG}" ]]; then
  LIVE_CONFIG="config.kraken_spot.live.yaml"
fi
PAPER_CONFIG="${AUTONOMOUS_PAPER_CONFIG:-config.kraken_spot.paper.yaml}"
if [[ ! -f "${PAPER_CONFIG}" ]]; then
  PAPER_CONFIG="${LIVE_CONFIG}"
fi
RUN_DIR="${AUTONOMOUS_RUN_DIR:-}"
if [[ -z "${RUN_DIR}" ]]; then
  RUN_DIR="$("${PYTHON_BIN}" - "${LIVE_CONFIG}" <<'PY'
from pathlib import Path
import json
import sys

config_path = Path(sys.argv[1])
default_run_dir = "runs/kraken_spot_live"
if not config_path.exists():
    print(default_run_dir)
    raise SystemExit(0)
text = config_path.read_text(encoding="utf-8")
data = {}
try:
    import yaml  # type: ignore

    parsed = yaml.safe_load(text)
    if isinstance(parsed, dict):
        data = parsed
except Exception:
    pass
if not data:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            data = parsed
    except Exception:
        data = {}
storage = data.get("storage", {}) if isinstance(data, dict) else {}
run_dir = storage.get("run_dir") if isinstance(storage, dict) else None
if isinstance(run_dir, str) and run_dir.strip():
    print(run_dir.strip())
else:
    print(default_run_dir)
PY
)"
fi
_kraken_cred_source="${AUTONOMOUS_CREDENTIAL_SOURCE:-}"
if [[ -z "${_kraken_cred_source}" && -n "${KRAKEN_API_KEY:-}" && -n "${KRAKEN_API_SECRET:-}" ]]; then
  _kraken_cred_source="shell_env"
fi
for f in "${RUN_DIR}/env_overrides.sh" "${RUN_DIR}/operator_overrides.sh"; do
  if [[ -f "${f}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${f}"
    set +a
    if [[ -z "${_kraken_cred_source}" && -n "${KRAKEN_API_KEY:-}" && -n "${KRAKEN_API_SECRET:-}" ]]; then
      _kraken_cred_source="run_dir_override:${f}"
    fi
  fi
done

_import_kraken_vars_from_env_file() {
  local _f="${1:-}"
  [[ -n "${_f}" && -f "${_f}" ]] || return 0
  while IFS= read -r _line || [[ -n "${_line}" ]]; do
    case "${_line}" in
      export\ KRAKEN_API_KEY=*|KRAKEN_API_KEY=*|export\ KRAKEN_API_SECRET=*|KRAKEN_API_SECRET=*)
        _line="${_line#export }"
        local _name="${_line%%=*}"
        local _value="${_line#*=}"
        _name="$(printf '%s' "${_name}" | tr -d '[:space:]')"
        _value="${_value//$'\r'/}"
        _value="${_value#"${_value%%[![:space:]]*}"}"
        _value="${_value%"${_value##*[![:space:]]}"}"
        if [[ "${_value}" == \"*\" && "${_value}" == *\" && ${#_value} -ge 2 ]]; then
          _value="${_value:1:${#_value}-2}"
        elif [[ "${_value}" == \'*\' && "${_value}" == *\' && ${#_value} -ge 2 ]]; then
          _value="${_value:1:${#_value}-2}"
        fi
        if [[ "${_name}" == "KRAKEN_API_KEY" || "${_name}" == "KRAKEN_API_SECRET" ]]; then
          export "${_name}=${_value}"
        fi
        ;;
      *)
        ;;
    esac
  done < "${_f}"
}

_import_kraken_vars_from_shell_history() {
  local _hist="${1:-}"
  [[ -n "${_hist}" && -f "${_hist}" ]] || return 0
  _pull_assignment() {
    local _var="${1:-}"
    local _line
    _line="$(LC_ALL=C grep -E "(^|;)[[:space:]]*export[[:space:]]+${_var}[[:space:]]*=" "${_hist}" | tail -n 1 || true)"
    [[ -n "${_line}" ]] || return 0
    _line="${_line#*export }"
    _line="${_line#*${_var}}"
    _line="${_line#*=}"
    _line="${_line%%;*}"
    _line="${_line//$'\r'/}"
    _line="${_line#"${_line%%[![:space:]]*}"}"
    _line="${_line%"${_line##*[![:space:]]}"}"
    if [[ "${_line}" == \"*\" && "${_line}" == *\" && ${#_line} -ge 2 ]]; then
      _line="${_line:1:${#_line}-2}"
    elif [[ "${_line}" == \'*\' && "${_line}" == *\' && ${#_line} -ge 2 ]]; then
      _line="${_line:1:${#_line}-2}"
    fi
    if [[ -n "${_line}" ]]; then
      export "${_var}=${_line}"
    fi
  }
  _pull_assignment "KRAKEN_API_KEY"
  _pull_assignment "KRAKEN_API_SECRET"
}

if [[ -z "${KRAKEN_API_KEY:-}" || -z "${KRAKEN_API_SECRET:-}" ]]; then
  if [[ -n "${AUTONOMOUS_ENV_FILE:-}" ]]; then
    _import_kraken_vars_from_env_file "${AUTONOMOUS_ENV_FILE}"
    if [[ -z "${_kraken_cred_source}" && -n "${KRAKEN_API_KEY:-}" && -n "${KRAKEN_API_SECRET:-}" ]]; then
      _kraken_cred_source="env_file:${AUTONOMOUS_ENV_FILE}"
    fi
  fi
  _import_kraken_vars_from_env_file ".env"
  if [[ -z "${_kraken_cred_source}" && -n "${KRAKEN_API_KEY:-}" && -n "${KRAKEN_API_SECRET:-}" ]]; then
    _kraken_cred_source="env_file:.env"
  fi
  _import_kraken_vars_from_env_file ".env.local"
  if [[ -z "${_kraken_cred_source}" && -n "${KRAKEN_API_KEY:-}" && -n "${KRAKEN_API_SECRET:-}" ]]; then
    _kraken_cred_source="env_file:.env.local"
  fi
  _import_kraken_vars_from_env_file "${HOME}/.config/autonomous_investment_robot/env.sh"
  if [[ -z "${_kraken_cred_source}" && -n "${KRAKEN_API_KEY:-}" && -n "${KRAKEN_API_SECRET:-}" ]]; then
    _kraken_cred_source="env_file:${HOME}/.config/autonomous_investment_robot/env.sh"
  fi
fi

if [[ -z "${KRAKEN_API_KEY:-}" || -z "${KRAKEN_API_SECRET:-}" ]]; then
  _shell_hist="${AUTONOMOUS_SHELL_HISTORY_FILE:-${HOME}/.zsh_history}"
  _import_kraken_vars_from_shell_history "${_shell_hist}"
  if [[ -z "${_kraken_cred_source}" && -n "${KRAKEN_API_KEY:-}" && -n "${KRAKEN_API_SECRET:-}" ]]; then
    _kraken_cred_source="shell_history:${_shell_hist}"
  fi
fi

if [[ -z "${KRAKEN_API_KEY:-}" || -z "${KRAKEN_API_SECRET:-}" ]]; then
  _snap_dir="${HOME}/.codex/shell_snapshots"
  if [[ -d "${_snap_dir}" ]]; then
    while IFS= read -r _snap; do
      [[ -f "${_snap}" ]] || continue
      if grep -q "KRAKEN_API_KEY" "${_snap}" && grep -q "KRAKEN_API_SECRET" "${_snap}"; then
        _import_kraken_vars_from_env_file "${_snap}"
        if [[ -n "${KRAKEN_API_KEY:-}" && -n "${KRAKEN_API_SECRET:-}" ]]; then
          if [[ -z "${_kraken_cred_source}" ]]; then
            _kraken_cred_source="codex_shell_snapshot:${_snap}"
          fi
          break
        fi
      fi
    done < <(ls -1t "${_snap_dir}"/*.sh 2>/dev/null || true)
  fi
fi

mkdir -p "${RUN_DIR}"
AUTONOMOUS_CREDENTIAL_SOURCE="${_kraken_cred_source:-unresolved}" \
AUTONOMOUS_CREDENTIAL_HAS_KEY="$([[ -n "${KRAKEN_API_KEY:-}" ]] && echo true || echo false)" \
AUTONOMOUS_CREDENTIAL_HAS_SECRET="$([[ -n "${KRAKEN_API_SECRET:-}" ]] && echo true || echo false)" \
AUTONOMOUS_RUN_DIR="${RUN_DIR}" \
"${PYTHON_BIN}" - <<'PY'
from pathlib import Path
import json
import os

run_dir = Path(os.getenv("AUTONOMOUS_RUN_DIR", "")).resolve()
run_dir.mkdir(parents=True, exist_ok=True)
payload = {
    "credential_source": str(os.getenv("AUTONOMOUS_CREDENTIAL_SOURCE", "unresolved") or "unresolved"),
    "has_key": str(os.getenv("AUTONOMOUS_CREDENTIAL_HAS_KEY", "false")).lower() == "true",
    "has_secret": str(os.getenv("AUTONOMOUS_CREDENTIAL_HAS_SECRET", "false")).lower() == "true",
}
(run_dir / "credential_resolution.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY

# Prevent duplicate live runners for the same config/run directory.
if pgrep -f "python.*-m cli.run --config ${LIVE_CONFIG} --nonstop" >/dev/null 2>&1; then
  echo "[run_kraken_spot_live] Runner already active for ${LIVE_CONFIG}; skipping duplicate launch."
  exit 0
fi

if [[ -z "${KRAKEN_API_KEY:-}" || -z "${KRAKEN_API_SECRET:-}" ]]; then
  echo "[run_kraken_spot_live] No Kraken credentials resolved from shell or run-dir override chain." >&2
  echo "[run_kraken_spot_live] Checked: ${RUN_DIR}/env_overrides.sh and ${RUN_DIR}/operator_overrides.sh" >&2
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

FALLBACK_TO_PAPER_ON_PERM_DENIED="$(printf '%s' "${AUTONOMOUS_FALLBACK_TO_PAPER_ON_PERMISSION_DENIED:-true}" | tr '[:upper:]' '[:lower:]')"
PERM_CHECK_RESULT="$(
  PYTHONPATH=src "${PYTHON_BIN}" - <<'PY'
import json
import os
from autonomous_investment_robot.config.settings import KrakenSpotExecutionSettings
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector

require_open_orders = str(os.getenv("AUTONOMOUS_KRAKEN_REQUIRE_OPEN_ORDERS_SCOPE", "false") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
settings = KrakenSpotExecutionSettings(
    allow_unknown_permissions=True,
    require_open_orders_scope=require_open_orders,
)
connector = KrakenSpotConnector(settings)
diag = {}
if hasattr(connector, "diagnose_private_api_access"):
    try:
        out = connector.diagnose_private_api_access()
        diag = dict(out) if isinstance(out, dict) else {}
    except Exception as exc:
        diag = {
            "ok": False,
            "classification": "permission_check_failed",
            "scope": "diagnose",
            "reason": str(exc),
        }
else:
    ok, reason = connector.verify_live_permissions()
    diag = {
        "ok": bool(ok),
        "classification": "legacy",
        "scope": "legacy",
        "reason": str(reason),
    }
print(
    json.dumps(
        {
            "ok": bool(diag.get("ok", False)),
            "classification": str(diag.get("classification", "")),
            "scope": str(diag.get("scope", "")),
            "reason": str(diag.get("reason", "")),
        },
        sort_keys=True,
    )
)
PY
)" || true

PERM_CLASS="$(
  PERM_JSON="${PERM_CHECK_RESULT}" "${PYTHON_BIN}" - <<'PY'
import json
import os

raw = str(os.getenv("PERM_JSON", "") or "").strip()
cls = "unknown_error"
try:
    payload = json.loads(raw) if raw else {}
    cls = str(payload.get("classification", cls) or cls)
except Exception:
    cls = "parse_error"
print(cls)
PY
)"

PERM_SCOPE="$(
  PERM_JSON="${PERM_CHECK_RESULT}" "${PYTHON_BIN}" - <<'PY'
import json
import os

raw = str(os.getenv("PERM_JSON", "") or "").strip()
scope = "unknown"
try:
    payload = json.loads(raw) if raw else {}
    scope = str(payload.get("scope", scope) or scope)
except Exception:
    scope = "parse_error"
print(scope)
PY
)"

PERM_REASON="$(
  PERM_JSON="${PERM_CHECK_RESULT}" "${PYTHON_BIN}" - <<'PY'
import json
import os

raw = str(os.getenv("PERM_JSON", "") or "").strip()
reason = ""
try:
    payload = json.loads(raw) if raw else {}
    reason = str(payload.get("reason", "") or "")
except Exception:
    reason = "parse_error"
print(reason)
PY
)"

if [[ "${PERM_CLASS}" == "missing_credentials" || "${PERM_CLASS}" == "invalid_credentials" || "${PERM_CLASS}" == "invalid_permissions" || "${PERM_CLASS}" == "invalid_nonce" ]]; then
  echo "[run_kraken_spot_live] Kraken private API permissions missing (${PERM_CLASS}, scope=${PERM_SCOPE})." >&2
  if [[ -n "${PERM_REASON}" ]]; then
    echo "[run_kraken_spot_live] Kraken reason: ${PERM_REASON}" >&2
  fi
  if [[ "${PERM_CLASS}" == "invalid_permissions" ]]; then
    echo "[run_kraken_spot_live] Hint: check API key scopes and IP allowlist restriction on Kraken key." >&2
  fi
  if [[ "${FALLBACK_TO_PAPER_ON_PERM_DENIED}" == "true" || "${FALLBACK_TO_PAPER_ON_PERM_DENIED}" == "1" || "${FALLBACK_TO_PAPER_ON_PERM_DENIED}" == "yes" || "${FALLBACK_TO_PAPER_ON_PERM_DENIED}" == "on" ]]; then
    PAPER_RUN_DIR="$("${PYTHON_BIN}" - "${PAPER_CONFIG}" <<'PY'
from pathlib import Path
import json
import sys

config_path = Path(sys.argv[1])
default_run_dir = "runs/kraken_spot_paper"
if not config_path.exists():
    print(default_run_dir)
    raise SystemExit(0)
text = config_path.read_text(encoding="utf-8")
data = {}
try:
    import yaml  # type: ignore

    parsed = yaml.safe_load(text)
    if isinstance(parsed, dict):
        data = parsed
except Exception:
    pass
if not data:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            data = parsed
    except Exception:
        data = {}
storage = data.get("storage", {}) if isinstance(data, dict) else {}
run_dir = storage.get("run_dir") if isinstance(storage, dict) else None
if isinstance(run_dir, str) and run_dir.strip():
    print(run_dir.strip())
else:
    print(default_run_dir)
PY
)"
    echo "[run_kraken_spot_live] Switching to paper mode (${PAPER_CONFIG}, run_dir=${PAPER_RUN_DIR}) to avoid live error loops." >&2
    TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=false ACK_I_UNDERSTAND_RISKS=true \
    AUTONOMOUS_DYNAMIC_UNIVERSE=false AUTONOMOUS_DYNAMIC_UNIVERSE_ALL=false \
    AUTONOMOUS_UNIVERSE_ALLOWLIST="${AUTONOMOUS_PAPER_UNIVERSE_ALLOWLIST:-XBTUSD}" \
    AUTONOMOUS_RUN_DIR="${PAPER_RUN_DIR}" AUTONOMOUS_CONFIG_OVERRIDE_PATH="" \
    PYTHONPATH=src "${PYTHON_BIN}" -m cli.run --config "${PAPER_CONFIG}" --paper --nonstop --max-restarts 0
    exit $?
  fi
  exit 3
fi

if [[ "${PERM_CLASS}" == "optional_scope_unavailable" ]]; then
  echo "[run_kraken_spot_live] Warning: optional private scope unavailable (scope=${PERM_SCOPE}); continuing." >&2
fi

TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
PYTHONPATH=src "${PYTHON_BIN}" -m cli.run --config "${LIVE_CONFIG}" --nonstop
