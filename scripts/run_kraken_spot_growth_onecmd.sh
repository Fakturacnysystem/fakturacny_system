#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# ===== SETTINGS (can override via env) =====
export AUTONOMOUS_QUOTE_BUDGET="${AUTONOMOUS_QUOTE_BUDGET:-10.68}"
export AUTONOMOUS_USER_MIN_ORDER_USD="${AUTONOMOUS_USER_MIN_ORDER_USD:-2.0}"
export AUTONOMOUS_GROWTH_MAX_FRACTION="${AUTONOMOUS_GROWTH_MAX_FRACTION:-0.75}"

export AUTONOMOUS_GUARDS_MODE="${AUTONOMOUS_GUARDS_MODE:-strict}"
export AUTONOMOUS_RATE_LIMIT_COOLDOWN_S="${AUTONOMOUS_RATE_LIMIT_COOLDOWN_S:-5}"
export AUTONOMOUS_MAX_ORDERS_PER_MIN="${AUTONOMOUS_MAX_ORDERS_PER_MIN:-14}"
export AUTONOMOUS_LIVE_POLL_SECONDS="${AUTONOMOUS_LIVE_POLL_SECONDS:-2}"

export AUTONOMOUS_MIN_NET_EDGE_BPS="${AUTONOMOUS_MIN_NET_EDGE_BPS:-0.7}"
export AUTONOMOUS_MAX_COST_TO_ALPHA_RATIO="${AUTONOMOUS_MAX_COST_TO_ALPHA_RATIO:-1.15}"
export AUTONOMOUS_QUOTE_RESERVE_RATIO="${AUTONOMOUS_QUOTE_RESERVE_RATIO:-0.95}"
export AUTONOMOUS_CVAR_MIN_SAMPLES="${AUTONOMOUS_CVAR_MIN_SAMPLES:-60}"
export AUTONOMOUS_SAFE_MODE_RELEASE_STEPS="${AUTONOMOUS_SAFE_MODE_RELEASE_STEPS:-6}"

export AUTONOMOUS_SELF_TUNER_MIN_SAMPLES="${AUTONOMOUS_SELF_TUNER_MIN_SAMPLES:-30}"
export AUTONOMOUS_SELF_TUNER_EVERY_STEPS="${AUTONOMOUS_SELF_TUNER_EVERY_STEPS:-15}"
export AUTONOMOUS_REBALANCE_DEADZONE_FACTOR="${AUTONOMOUS_REBALANCE_DEADZONE_FACTOR:-0.02}"
export AUTONOMOUS_REBALANCE_DEADZONE_FLOOR="${AUTONOMOUS_REBALANCE_DEADZONE_FLOOR:-0.02}"

export AUTONOMOUS_FALLBACK_CONSECUTIVE_REJECTS="${AUTONOMOUS_FALLBACK_CONSECUTIVE_REJECTS:-3}"
export AUTONOMOUS_HEALTHCHECK_INTERVAL_S="${AUTONOMOUS_HEALTHCHECK_INTERVAL_S:-10}"
export AUTONOMOUS_FALLBACK_COOLDOWN_S="${AUTONOMOUS_FALLBACK_COOLDOWN_S:-90}"
export AUTONOMOUS_MANAGER_MAX_RUNTIME_S="${AUTONOMOUS_MANAGER_MAX_RUNTIME_S:-86400}"

# hard stop risk limits for 24h unattended run
export AUTONOMOUS_MAX_DAILY_LOSS_PCT="${AUTONOMOUS_MAX_DAILY_LOSS_PCT:-3.0}"
export AUTONOMOUS_MAX_DRAWDOWN_PCT="${AUTONOMOUS_MAX_DRAWDOWN_PCT:-8.0}"

# quality gate tuning
export AUTONOMOUS_QUALITY_WINDOW_S="${AUTONOMOUS_QUALITY_WINDOW_S:-600}"
export AUTONOMOUS_QUALITY_REJECT_RATIO_TRIGGER="${AUTONOMOUS_QUALITY_REJECT_RATIO_TRIGGER:-0.8}"
export AUTONOMOUS_QUALITY_MIN_ATTEMPTS="${AUTONOMOUS_QUALITY_MIN_ATTEMPTS:-8}"
export AUTONOMOUS_QUALITY_EDGE_STEP_BPS="${AUTONOMOUS_QUALITY_EDGE_STEP_BPS:-0.2}"
export AUTONOMOUS_QUALITY_ORDERS_STEP="${AUTONOMOUS_QUALITY_ORDERS_STEP:-2}"

# no-fill gate: intents but no fills over 2h => switch or pause
export AUTONOMOUS_NO_FILL_WINDOW_S="${AUTONOMOUS_NO_FILL_WINDOW_S:-7200}"
export AUTONOMOUS_NO_FILL_PAUSE_S="${AUTONOMOUS_NO_FILL_PAUSE_S:-1800}"

# dynamic rate-limit storm control
export AUTONOMOUS_RATE_LIMIT_WINDOW_S="${AUTONOMOUS_RATE_LIMIT_WINDOW_S:-600}"
export AUTONOMOUS_RATE_LIMIT_STORM_THRESHOLD="${AUTONOMOUS_RATE_LIMIT_STORM_THRESHOLD:-12}"
export AUTONOMOUS_RATE_LIMIT_COOLDOWN_STORM_S="${AUTONOMOUS_RATE_LIMIT_COOLDOWN_STORM_S:-9}"

# snapshot cadence for post-mortem
export AUTONOMOUS_SNAPSHOT_INTERVAL_S="${AUTONOMOUS_SNAPSHOT_INTERVAL_S:-300}"

IN_CFG="${AUTONOMOUS_GROWTH_IN_CONFIG:-config.kraken_spot.live.yaml}"
OUT_CFG="${AUTONOMOUS_GROWTH_OUT_CONFIG:-config.kraken_spot.live_growth.yaml}"
MANAGER_OUT="${AUTONOMOUS_GROWTH_MANAGER_LOG:-runs/live/kraken_growth_manager.out}"
PICK_OUT="${AUTONOMOUS_GROWTH_PICK_OUT:-/tmp/kraken_growth_pick.out}"

# ===== Credentials required in shell env (do not hardcode secrets) =====
: "${KRAKEN_API_KEY:?Set KRAKEN_API_KEY in your shell env}"
: "${KRAKEN_API_SECRET:?Set KRAKEN_API_SECRET in your shell env}"

if ! python3 - <<'PY' >/dev/null 2>&1
import requests  # noqa: F401
import yaml  # noqa: F401
PY
then
  python3 -m pip -q install --user pyyaml requests >/dev/null || \
    python3 -m pip -q install --break-system-packages pyyaml requests >/dev/null
fi

python3 - <<'PY' | tee "$PICK_OUT" >/dev/null
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import requests
import yaml

KRAKEN = "https://api.kraken.com"
BUDGET = float(os.getenv("AUTONOMOUS_QUOTE_BUDGET", "10.68"))
USER_MIN = float(os.getenv("AUTONOMOUS_USER_MIN_ORDER_USD", "2.0"))
MAX_FRAC = max(0.1, min(0.98, float(os.getenv("AUTONOMOUS_GROWTH_MAX_FRACTION", "0.75"))))
MAX_ORDERS_PER_MIN = max(1, int(os.getenv("AUTONOMOUS_MAX_ORDERS_PER_MIN", "8")))

IN_CFG = Path(os.getenv("AUTONOMOUS_GROWTH_IN_CONFIG", "config.kraken_spot.live.yaml"))
OUT_CFG = Path(os.getenv("AUTONOMOUS_GROWTH_OUT_CONFIG", "config.kraken_spot.live_growth.yaml"))
CANDIDATES = [s.strip().upper() for s in os.getenv("AUTONOMOUS_GROWTH_CANDIDATES", "XBT/USD,ETH/USD,SOL/USD").split(",") if s.strip()]

if BUDGET <= 0:
    raise SystemExit("AUTONOMOUS_QUOTE_BUDGET must be > 0.")
if USER_MIN <= 0:
    raise SystemExit("AUTONOMOUS_USER_MIN_ORDER_USD must be > 0.")

def kget(path: str, params: dict[str, Any] | None = None, timeout: float = 10.0) -> dict[str, Any]:
    r = requests.get(KRAKEN + path, params=params or {}, timeout=timeout)
    r.raise_for_status()
    out = r.json()
    if out.get("error"):
        raise RuntimeError(f"Kraken error: {out['error']}")
    return out["result"]

def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)

def split_pair(meta: dict[str, Any]) -> tuple[str, str]:
    ws = str(meta.get("wsname", "") or "")
    if "/" in ws:
        b, q = ws.split("/", 1)
        return b.upper(), q.upper()
    alt = str(meta.get("altname", "") or "")
    if "/" in alt:
        b, q = alt.split("/", 1)
        return b.upper(), q.upper()
    return "", ""

asset_pairs = kget("/0/public/AssetPairs")

alt_to_key: dict[str, str] = {}
for pair_key, meta in asset_pairs.items():
    if not isinstance(meta, dict):
        continue
    base, quote = split_pair(meta)
    if not base or not quote:
        continue
    alt_to_key[f"{base}/{quote}"] = pair_key

rows: list[tuple[float, str, str, float, float, float, float]] = []
max_usable = BUDGET * 0.98

for alt in CANDIDATES:
    key = alt_to_key.get(alt)
    if not key:
        continue
    meta = asset_pairs.get(key, {}) or {}
    if str(meta.get("status", "online")) != "online":
        continue
    ordermin_base = float(meta.get("ordermin", 0.0) or 0.0)
    t = kget("/0/public/Ticker", {"pair": key})
    tt = t.get(key) or next(iter(t.values()))
    bid = float(tt["b"][0]); ask = float(tt["a"][0]); last = float(tt["c"][0]); vol_base = float(tt["v"][1])
    if min(bid, ask, last) <= 0:
        continue
    mid = (bid + ask) / 2.0
    spread_bps = ((ask - bid) / max(mid, 1e-9)) * 10000.0
    vol_quote = vol_base * last
    exch_min_quote = ordermin_base * mid
    if exch_min_quote <= 0 or exch_min_quote > max_usable:
        continue
    effective_min = max(USER_MIN, exch_min_quote)
    score = math.log1p(vol_quote) / (1.0 + spread_bps / 18.0) / (1.0 + (effective_min / max_usable) * 0.35)
    symbol = alt.replace("/", "")
    rows.append((score, symbol, key, exch_min_quote, effective_min, spread_bps, vol_quote))

if not rows:
    raise SystemExit(f"No feasible USD candidate for budget={BUDGET}. Increase budget or widen candidates.")

rows.sort(reverse=True, key=lambda x: x[0])
top = rows[:3]
chosen = top[0]
_, chosen_symbol, chosen_pair_key, chosen_exch_min, chosen_effective_min, chosen_spread_bps, chosen_vol_quote = chosen

max_order = max(chosen_effective_min, BUDGET * MAX_FRAC)
max_order = min(max_order, max_usable)

cfg = yaml.safe_load(IN_CFG.read_text(encoding="utf-8"))
if not isinstance(cfg, dict):
    raise SystemExit("Input config root must be a dict.")

cfg["mode"] = "live"
cfg["enable_live_trading"] = True
cfg["ack_i_understand_risks"] = True
cfg["canary_mode"] = True
cfg["provider_whitelist"] = ["kraken_spot"]
cfg["universe"] = [chosen_symbol]

policy = cfg.get("policy", {})
if not isinstance(policy, dict):
    policy = {}
allowed_policy = {"confidence_threshold", "estimated_cost_bps", "safety_buffer_bps", "base_risk_budget"}
policy = {k: v for k, v in policy.items() if k in allowed_policy}
policy.setdefault("confidence_threshold", 0.0)
policy.setdefault("safety_buffer_bps", -40.0)
policy["base_risk_budget"] = round(float(max_order), 6)
cfg["policy"] = policy

risk = cfg.get("risk", {})
if not isinstance(risk, dict):
    risk = {}
risk["max_orders_per_min"] = int(MAX_ORDERS_PER_MIN)
daily_loss_cap = safe_float(os.getenv("AUTONOMOUS_MAX_DAILY_LOSS_PCT", "3.0"), 3.0)
drawdown_cap = safe_float(os.getenv("AUTONOMOUS_MAX_DRAWDOWN_PCT", "8.0"), 8.0)
risk["max_daily_loss_pct"] = min(daily_loss_cap, safe_float(risk.get("max_daily_loss_pct"), daily_loss_cap))
risk["max_drawdown_pct"] = min(drawdown_cap, safe_float(risk.get("max_drawdown_pct"), drawdown_cap))
risk["max_position_notional"] = round(float(max_order), 6)
risk["max_symbol_exposure_notional"] = round(float(max_order), 6)
risk["max_exposure_notional"] = round(float(max_usable), 6)
risk["max_cluster_exposure_notional"] = round(float(max_usable), 6)
cfg["risk"] = risk

execution = cfg.get("execution", {})
if not isinstance(execution, dict):
    execution = {}
execution["maker_preference"] = True
execution["maker_timeout_s"] = 45
execution["slicing_parts"] = 1
execution["max_child_orders"] = 1
cfg["execution"] = execution

ub = cfg.get("universe_builder", {})
if not isinstance(ub, dict):
    ub = {}
ub["trade_max_positions"] = 1
cfg["universe_builder"] = ub

cfg["growth_hints"] = {
    "quote_currency": "USD",
    "budget_quote": round(float(BUDGET), 6),
    "exchange_min_quote": round(float(chosen_exch_min), 6),
    "effective_min_order_quote": round(float(chosen_effective_min), 6),
    "max_order_quote": round(float(max_order), 6),
    "fallback_symbols": [row[1] for row in top],
}

OUT_CFG.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")

print(f"CHOSEN_SYMBOL={chosen_symbol}")
print(f"FALLBACK_SYMBOLS={','.join(row[1] for row in top)}")
print(f"EXPORT_AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE={chosen_effective_min}")
print(f"EXPORT_AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE={max_order}")
print(f"EXPORT_AUTONOMOUS_LIVE_CONFIG={OUT_CFG}")
print(
    "DEBUG "
    f"pair_key={chosen_pair_key} "
    f"exch_min_quote={round(chosen_exch_min,6)} "
    f"spread_bps={round(chosen_spread_bps,3)} "
    f"vol_quote_24h={round(chosen_vol_quote,2)}"
)
PY

export AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE="$(grep -o 'EXPORT_AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE=.*' "$PICK_OUT" | cut -d= -f2)"
export AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE="$(grep -o 'EXPORT_AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE=.*' "$PICK_OUT" | cut -d= -f2)"
export AUTONOMOUS_LIVE_CONFIG="$(grep -o 'EXPORT_AUTONOMOUS_LIVE_CONFIG=.*' "$PICK_OUT" | cut -d= -f2)"
export AUTONOMOUS_PRIMARY_SYMBOL="$(grep -o 'CHOSEN_SYMBOL=.*' "$PICK_OUT" | cut -d= -f2)"
export AUTONOMOUS_FALLBACK_SYMBOLS="$(grep -o 'FALLBACK_SYMBOLS=.*' "$PICK_OUT" | cut -d= -f2)"
export AUTONOMOUS_SELF_TUNER_MIN_ORDER_FLOOR_MIN="${AUTONOMOUS_SELF_TUNER_MIN_ORDER_FLOOR_MIN:-$AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE}"
export AUTONOMOUS_SELF_TUNER_MIN_ORDER_FLOOR_MAX="${AUTONOMOUS_SELF_TUNER_MIN_ORDER_FLOOR_MAX:-$AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE}"

mkdir -p runs/live

echo "Chosen: $AUTONOMOUS_PRIMARY_SYMBOL"
echo "Fallbacks: $AUTONOMOUS_FALLBACK_SYMBOLS"
echo "min_order_quote=$AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE max_order_quote=$AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE"
echo "guards_mode=$AUTONOMOUS_GUARDS_MODE tuner=${AUTONOMOUS_SELF_TUNER_MIN_SAMPLES}/${AUTONOMOUS_SELF_TUNER_EVERY_STEPS}"
echo "loss_limits daily=${AUTONOMOUS_MAX_DAILY_LOSS_PCT}% drawdown=${AUTONOMOUS_MAX_DRAWDOWN_PCT}% runtime=${AUTONOMOUS_MANAGER_MAX_RUNTIME_S}s"
echo "live_config=$AUTONOMOUS_LIVE_CONFIG"

# stop existing manager and old kraken live processes
pkill -f "scripts/run_kraken_spot_growth_manager.sh" >/dev/null 2>&1 || true
pkill -f "scripts/growth_manager.py" >/dev/null 2>&1 || true
pgrep -f "autonomous_investment_robot live --config .*config\\.kraken_spot\\.live_growth\\.yaml" >/dev/null 2>&1 && \
  pgrep -f "autonomous_investment_robot live --config .*config\\.kraken_spot\\.live_growth\\.yaml" | xargs -r kill || true

nohup ./scripts/run_kraken_spot_growth_manager.sh > "$MANAGER_OUT" 2>&1 &
echo "Started growth manager. PID=$!"
echo "Manager log: $MANAGER_OUT"
echo "Live log: runs/live/kraken_growth.out"
echo "Audit: runs/kraken_spot_live/audit.log"
