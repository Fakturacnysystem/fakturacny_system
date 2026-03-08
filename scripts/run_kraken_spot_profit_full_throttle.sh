#!/usr/bin/env bash
set -euo pipefail

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

export AUTONOMOUS_GUARDS_MODE="${AUTONOMOUS_GUARDS_MODE:-fatal_only}"
export AUTONOMOUS_ORDER_CADENCE_S="${AUTONOMOUS_ORDER_CADENCE_S:-5}"
export AUTONOMOUS_MAX_ORDERS_PER_MIN="${AUTONOMOUS_MAX_ORDERS_PER_MIN:-10}"
export AUTONOMOUS_USER_MIN_ORDER_QUOTE="${AUTONOMOUS_USER_MIN_ORDER_QUOTE:-2.0}"
export AUTONOMOUS_TP_ONLY_MODE="${AUTONOMOUS_TP_ONLY_MODE:-1}"
export AUTONOMOUS_MIN_TP_AFTER_COSTS="${AUTONOMOUS_MIN_TP_AFTER_COSTS:-1}"
export AUTONOMOUS_SELL_MIN_NET_PROFIT_BPS="${AUTONOMOUS_SELL_MIN_NET_PROFIT_BPS:-120}"
export AUTONOMOUS_SPOT_SELL_PROFIT_LOCK_FATAL_BYPASS="${AUTONOMOUS_SPOT_SELL_PROFIT_LOCK_FATAL_BYPASS:-false}"
export AUTONOMOUS_MARKET_WATCH_EVERY_S="${AUTONOMOUS_MARKET_WATCH_EVERY_S:-30}"

_cadence_raw="${AUTONOMOUS_ORDER_CADENCE_S:-5}"
_cadence_safe="$(awk -v c="${_cadence_raw}" 'BEGIN { x=(c+0); if (x < 5.0) x = 5.0; if (x > 60.0) x = 60.0; printf "%.6g", x }')"
export AUTONOMOUS_ORDER_CADENCE_S="${_cadence_safe}"

export AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS="${AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS:-120}"
export AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS="${AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS:-200}"
export AUTONOMOUS_SPOT_SELL_HARD_FLOOR_BPS="${AUTONOMOUS_SPOT_SELL_HARD_FLOOR_BPS:-120}"
export AUTONOMOUS_MIN_TAKE_PROFIT_PCT="${AUTONOMOUS_MIN_TAKE_PROFIT_PCT:-1.2}"

# Operator alias compatibility:
# AUTONOMOUS_MAX_PARALLEL_TRADES controls live open-order concurrency if provided.
if [[ -n "${AUTONOMOUS_MAX_PARALLEL_TRADES:-}" && -z "${AUTONOMOUS_MAX_OPEN_ORDERS_GLOBAL:-}" ]]; then
  export AUTONOMOUS_MAX_OPEN_ORDERS_GLOBAL="${AUTONOMOUS_MAX_PARALLEL_TRADES}"
fi
# AUTONOMOUS_RISK_PER_TRADE maps to initial self-tuner sizing in bounded safe range.
if [[ -n "${AUTONOMOUS_RISK_PER_TRADE:-}" && -z "${AUTONOMOUS_SELF_TUNER_SIZE_SCALE_INIT:-}" ]]; then
  SCALE="$(awk -v risk_per_trade="${AUTONOMOUS_RISK_PER_TRADE}" 'BEGIN { s = risk_per_trade / 0.01; if (s < 0.10) s = 0.10; if (s > 2.00) s = 2.00; printf "%.4f", s }')"
  export AUTONOMOUS_SELF_TUNER_SIZE_SCALE_INIT="${SCALE}"
fi

export AUTONOMOUS_LIVE_POLL_SECONDS="${AUTONOMOUS_LIVE_POLL_SECONDS:-1}"
unset AUTONOMOUS_TRADE_COOLDOWN_S || true
unset AUTONOMOUS_MIN_SECONDS_BETWEEN_ORDERS || true
unset ORDER_SUBMISSION_INTERVAL_SECONDS || true

export AUTONOMOUS_SPOT_SELL_PROFIT_LOCK="${AUTONOMOUS_SPOT_SELL_PROFIT_LOCK:-true}"
export AUTONOMOUS_SPOT_SELL_REQUIRE_COST_BASIS="${AUTONOMOUS_SPOT_SELL_REQUIRE_COST_BASIS:-true}"

export AUTONOMOUS_BLACKOUT_ENABLED="${AUTONOMOUS_BLACKOUT_ENABLED:-true}"
export AUTONOMOUS_BLACKOUT_WINDOWS="${AUTONOMOUS_BLACKOUT_WINDOWS:-}"
export AUTONOMOUS_SPREAD_SPIKE_ENABLED="${AUTONOMOUS_SPREAD_SPIKE_ENABLED:-true}"
export AUTONOMOUS_SPREAD_SPIKE_MULT="${AUTONOMOUS_SPREAD_SPIKE_MULT:-2.5}"
export AUTONOMOUS_SPREAD_SPIKE_MIN_BPS="${AUTONOMOUS_SPREAD_SPIKE_MIN_BPS:-8.0}"
export AUTONOMOUS_SPREAD_SPIKE_HOLD_S="${AUTONOMOUS_SPREAD_SPIKE_HOLD_S:-45}"
export AUTONOMOUS_LIQUIDITY_MAP_ENABLED="${AUTONOMOUS_LIQUIDITY_MAP_ENABLED:-true}"
export AUTONOMOUS_LIQUIDITY_NIGHT_START_HOUR_UTC="${AUTONOMOUS_LIQUIDITY_NIGHT_START_HOUR_UTC:-20}"
export AUTONOMOUS_LIQUIDITY_NIGHT_END_HOUR_UTC="${AUTONOMOUS_LIQUIDITY_NIGHT_END_HOUR_UTC:-6}"

export AUTONOMOUS_WALK_FORWARD_ENFORCE="${AUTONOMOUS_WALK_FORWARD_ENFORCE:-false}"
export AUTONOMOUS_NESTED_WALK_FORWARD_ENFORCE="${AUTONOMOUS_NESTED_WALK_FORWARD_ENFORCE:-false}"

export AUTONOMOUS_FALLBACK_SYMBOLS="${AUTONOMOUS_FALLBACK_SYMBOLS:-ADAXBT,ALGOXBT,DOTXBT,SOLXBT,XXRPXXBT,XXLMXXBT,LINKXBT,XETHXXBT}"
export AUTONOMOUS_UNIVERSE_ALLOWLIST="${AUTONOMOUS_UNIVERSE_ALLOWLIST:-${AUTONOMOUS_FALLBACK_SYMBOLS}}"

export AUTONOMOUS_PROFIT_TARGET_NET="${AUTONOMOUS_PROFIT_TARGET_NET:-0.012}"
export AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S="${AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S:-3.0}"
export AUTONOMOUS_RATE_LIMIT_COOLDOWN_S="${AUTONOMOUS_RATE_LIMIT_COOLDOWN_S:-${AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S}}"
export AUTONOMOUS_KRAKEN_TEMP_LOCKOUT_COOLDOWN_S="${AUTONOMOUS_KRAKEN_TEMP_LOCKOUT_COOLDOWN_S:-45.0}"
export AUTONOMOUS_KRAKEN_RATE_LIMIT_STORM="${AUTONOMOUS_KRAKEN_RATE_LIMIT_STORM:-8}"
export AUTONOMOUS_MAX_CONSEC_REJECTS="${AUTONOMOUS_MAX_CONSEC_REJECTS:-5}"
export AUTONOMOUS_REJECT_COOLDOWN_S="${AUTONOMOUS_REJECT_COOLDOWN_S:-120}"
export AUTONOMOUS_TRADES_SYNC_MIN_INTERVAL_S="${AUTONOMOUS_TRADES_SYNC_MIN_INTERVAL_S:-10.0}"
export AUTONOMOUS_KRAKEN_BALANCE_TTL_S="${AUTONOMOUS_KRAKEN_BALANCE_TTL_S:-8.0}"
export AUTONOMOUS_KRAKEN_TRADES_TTL_S="${AUTONOMOUS_KRAKEN_TRADES_TTL_S:-8.0}"

export AUTONOMOUS_EXIT_TIME_STOP_S="${AUTONOMOUS_EXIT_TIME_STOP_S:-3600}"
export AUTONOMOUS_EXIT_TRAILING_DD_QUOTE="${AUTONOMOUS_EXIT_TRAILING_DD_QUOTE:-1.0}"
export AUTONOMOUS_EXIT_PARTIAL_FRACTION="${AUTONOMOUS_EXIT_PARTIAL_FRACTION:-0.5}"

export AUTONOMOUS_PORTFOLIO_OPTIMIZER="${AUTONOMOUS_PORTFOLIO_OPTIMIZER:-true}"
export AUTONOMOUS_PORTFOLIO_RESELECT_EVERY_STEPS="${AUTONOMOUS_PORTFOLIO_RESELECT_EVERY_STEPS:-2}"
export AUTONOMOUS_PORTFOLIO_SCAN_BATCH="${AUTONOMOUS_PORTFOLIO_SCAN_BATCH:-80}"

export AUTONOMOUS_RESERVE_CASH_RATIO="${AUTONOMOUS_RESERVE_CASH_RATIO:-0.15}"
export AUTONOMOUS_MIN_MARGIN_BUFFER_POLICY="${AUTONOMOUS_MIN_MARGIN_BUFFER_POLICY:-1.4}"

export AUTONOMOUS_CONFORMAL_ALPHA="${AUTONOMOUS_CONFORMAL_ALPHA:-0.1}"
export AUTONOMOUS_UNCERTAINTY_THRESHOLD_BPS="${AUTONOMOUS_UNCERTAINTY_THRESHOLD_BPS:-85.0}"
export AUTONOMOUS_DRIFT_THRESHOLD="${AUTONOMOUS_DRIFT_THRESHOLD:-0.2}"
export AUTONOMOUS_LATENCY_RISK_THRESHOLD="${AUTONOMOUS_LATENCY_RISK_THRESHOLD:-0.65}"
export AUTONOMOUS_MAX_SLIPPAGE_GUARD_BPS="${AUTONOMOUS_MAX_SLIPPAGE_GUARD_BPS:-8.0}"
export AUTONOMOUS_ONLINE_LEARNING_ENABLED="${AUTONOMOUS_ONLINE_LEARNING_ENABLED:-true}"
export AUTONOMOUS_ENABLE_NEWS_FEATURES="${AUTONOMOUS_ENABLE_NEWS_FEATURES:-false}"
export AUTONOMOUS_ENABLE_MACRO_FEATURES="${AUTONOMOUS_ENABLE_MACRO_FEATURES:-false}"
export AUTONOMOUS_ENABLE_FUNDAMENTAL_FEATURES="${AUTONOMOUS_ENABLE_FUNDAMENTAL_FEATURES:-false}"
export AUTONOMOUS_ENABLE_SENTIMENT_FEATURES="${AUTONOMOUS_ENABLE_SENTIMENT_FEATURES:-false}"
export AUTONOMOUS_FORECAST_BACKEND_PLUGIN="${AUTONOMOUS_FORECAST_BACKEND_PLUGIN:-}"
export AUTONOMOUS_SELF_OPTIMIZATION_WINDOW="${AUTONOMOUS_SELF_OPTIMIZATION_WINDOW:-120}"
export AUTONOMOUS_SELF_OPTIMIZATION_MIN_SAMPLES="${AUTONOMOUS_SELF_OPTIMIZATION_MIN_SAMPLES:-24}"
export AUTONOMOUS_SELF_OPTIMIZATION_APPLY_EVERY="${AUTONOMOUS_SELF_OPTIMIZATION_APPLY_EVERY:-12}"

export PYTHONUNBUFFERED=1

LIVE_CONFIG="config.kraken_spot.live_profit.yaml"

RUN_DIR="${AUTONOMOUS_RUN_DIR:-}"
if [[ -z "${RUN_DIR}" ]]; then
  RUN_DIR="runs/kraken_spot_live_profit_full_throttle"
fi
export AUTONOMOUS_RUN_DIR="${RUN_DIR}"

for f in "${RUN_DIR}/env_overrides.sh" "${RUN_DIR}/operator_overrides.sh"; do
  if [[ -f "${f}" ]]; then
    set -a
    source "${f}" 2>/dev/null
    set +a
  fi
done

# Full-throttle sanity hardening:
# 1) prevent legacy micro-notional caps from silently disabling intent generation
# 2) avoid health-audit restart loops under temporary private-API lockouts
_ff_user_min="${AUTONOMOUS_USER_MIN_ORDER_QUOTE:-2.0}"
_ff_quote_floor="${AUTONOMOUS_QUOTE_NOTIONAL_FLOOR:-${_ff_user_min}}"
_ff_max_notional="${AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE:-0}"
_ff_floor_enforced="$(awk -v a="${_ff_user_min}" -v b="${_ff_quote_floor}" 'BEGIN { x=(a+0); y=(b+0); if (y>x) x=y; if (x<2.0) x=2.0; printf "%.8f", x }')"
_ff_max_enforced="$(awk -v m="${_ff_max_notional}" -v floor="${_ff_floor_enforced}" 'BEGIN { x=(m+0); f=(floor+0); if (x < f) x=25.0; if (x < 25.0) x=25.0; printf "%.8f", x }')"
export AUTONOMOUS_QUOTE_NOTIONAL_FLOOR="${_ff_floor_enforced}"
export AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE="${_ff_floor_enforced}"
export AUTONOMOUS_PROBE_NOTIONAL_QUOTE="${AUTONOMOUS_PROBE_NOTIONAL_QUOTE:-${_ff_floor_enforced}}"
export AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE="${_ff_max_enforced}"
export AUTONOMOUS_HEALTH_AUDIT110_ENABLED="${AUTONOMOUS_HEALTH_AUDIT110_ENABLED:-false}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" && -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi
if [[ -z "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

if pgrep -f "python.*-m cli.run --config ${LIVE_CONFIG} --nonstop" >/dev/null 2>&1; then
  echo "[run_kraken_spot_profit_full_throttle] Runner already active for ${LIVE_CONFIG}; skipping duplicate launch."
  exit 0
fi

PERM_CHECK_RESULT="$(
  PYTHONPATH=src "${PYTHON_BIN}" - <<'PY'
import json
from autonomous_investment_robot.config.settings import KrakenSpotExecutionSettings
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector

settings = KrakenSpotExecutionSettings(allow_unknown_permissions=True)
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

mkdir -p "${RUN_DIR}"
printf '%s\n' "${PERM_CHECK_RESULT}" > "${RUN_DIR}/live_preflight_script_diag.json"

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

case "${PERM_CLASS}" in
  missing_credentials|invalid_credentials|invalid_permissions|invalid_nonce|kraken_auth_error|kraken_permission_denied)
    echo "[run_kraken_spot_profit_full_throttle] Fatal private API preflight blocker: ${PERM_CLASS}." >&2
    echo "[run_kraken_spot_profit_full_throttle] Fix credentials/permissions/nonce path before live start." >&2
    exit 3
    ;;
  temporary_lockout|rate_limit|network_unreachable|temporary_lockout_override|rate_limit_override|network_unreachable_override)
    echo "[run_kraken_spot_profit_full_throttle] Non-fatal private API preflight blocker: ${PERM_CLASS}; continuing with runtime cooldown handling." >&2
    ;;
  *)
    ;;
esac

echo "[run_kraken_spot_profit_full_throttle] Starting live Kraken SPOT robot..."
echo "[run_kraken_spot_profit_full_throttle] Config: ${LIVE_CONFIG}"
echo "[run_kraken_spot_profit_full_throttle] Run directory: ${RUN_DIR}"
echo "[run_kraken_spot_profit_full_throttle] Guards mode: ${AUTONOMOUS_GUARDS_MODE}"
echo "[run_kraken_spot_profit_full_throttle] Sell min profit: ${AUTONOMOUS_SELL_MIN_NET_PROFIT_BPS} bps"

TESTNET_VALIDATED=true ENABLE_LIVE_TRADING=true ACK_I_UNDERSTAND_RISKS=true \
PYTHONPATH=src "${PYTHON_BIN}" -m cli.run --config "${LIVE_CONFIG}" --nonstop
