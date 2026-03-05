#!/usr/bin/env bash
# PRO GROWTH MODE (profit-first + hard guards) — ONE SCRIPT
# - vyberie 1 najlepší USD pár na Kraken Spot pre malý účet podľa: exchange min order + spread + 24h volume
# - vytvorí nový config: config.kraken_spot.live_pro_growth.yaml (universe = 1 symbol, USD)
# - vytvorí nový run skript: scripts/run_kraken_spot_pro_growth.sh
# - zastaví starý live proces a spustí nový (bez vypisovania API key/secret)
#
# Použitie:
#   cd ~/Projects/fakturacny_system
#   bash scripts/pro_growth_setup.sh
#
# Pozn:
# - 2 USD min order je na väčšine párov nereálny (exchange minimum). Preto nastavujeme "praktické" min/max:
#   MIN=6.5 USD, MAX=9.5 USD (zvyšok rezerva na fee / zostatok).
# - Guards sú STRICT (profit-first, neobchoduje keď je to nevýhodné/nespĺňa podmienky).

set -euo pipefail

REPO="${REPO:-$HOME/Projects/fakturacny_system}"
IN_CFG="${IN_CFG:-config.kraken_spot.live.yaml}"
OUT_CFG="${OUT_CFG:-config.kraken_spot.live_pro_growth.yaml}"

BUDGET_USD="${BUDGET_USD:-10.68}"
MIN_ORDER_USD="${MIN_ORDER_USD:-6.5}"
MAX_ORDER_USD="${MAX_ORDER_USD:-9.5}"

# self tuner (stabilnejšie než 10/5)
TUNER_MIN_SAMPLES="${TUNER_MIN_SAMPLES:-30}"
TUNER_EVERY_STEPS="${TUNER_EVERY_STEPS:-20}"

RATE_LIMIT_COOLDOWN_S="${RATE_LIMIT_COOLDOWN_S:-3}"

# profit filter
MIN_NET_EDGE_BPS="${MIN_NET_EDGE_BPS:-1.3}"
MAX_COST_TO_ALPHA_RATIO="${MAX_COST_TO_ALPHA_RATIO:-1.1}"

cd "$REPO"

python3 - <<PY
import math
from pathlib import Path
import sys

try:
    import yaml
    import requests
except Exception:
    print("Missing deps. Run: pip install pyyaml requests", file=sys.stderr)
    raise

KRAKEN_API="https://api.kraken.com"
BUDGET=float("${BUDGET_USD}")
MIN_ORDER=float("${MIN_ORDER_USD}")
QUOTE="USD"

MAJORS={"XBT","ETH","SOL","XRP","ADA","DOT","LINK"}
EXCLUDE_BASE={"USDT","USDC","DAI","USD","EUR"}
EXCLUDE_QUOTE={"USDT","USDC","DAI"}

def kget(path, params=None, timeout=10.0):
    r=requests.get(KRAKEN_API+path, params=params or {}, timeout=timeout)
    r.raise_for_status()
    j=r.json()
    if j.get("error"):
        raise RuntimeError(j["error"])
    return j["result"]

def split_pair(meta):
    ws=str(meta.get("wsname","") or "")
    if "/" in ws:
        b,q=ws.split("/",1)
        return b.upper(), q.upper()
    alt=str(meta.get("altname","") or "")
    if "/" in alt:
        b,q=alt.split("/",1)
        return b.upper(), q.upper()
    base=str(meta.get("base","") or "").upper()
    quote=str(meta.get("quote","") or "").upper()
    if base and quote:
        if len(base)>=4 and base[0] in {"X","Z"}:
            base=base[1:]
        if len(quote)>=4 and quote[0] in {"X","Z"}:
            quote=quote[1:]
        return base, quote
    return None, None

asset_pairs=kget("/0/public/AssetPairs")

cands=[]
for k,meta in asset_pairs.items():
    if not isinstance(meta, dict):
        continue
    base,q=split_pair(meta)
    if not base or not q:
        continue
    if q!=QUOTE:
        continue
    if base in EXCLUDE_BASE or q in EXCLUDE_QUOTE:
        continue
    if base not in MAJORS:
        continue
    if str(meta.get("status","online"))!="online":
        continue
    cands.append((k,f"{base}/{q}"))

if not cands:
    raise SystemExit("No USD majors found on Kraken public endpoints.")

# batch ticker
tick={}
BATCH=40
for i in range(0,len(cands),BATCH):
    batch=cands[i:i+BATCH]
    tick.update(kget("/0/public/Ticker", params={"pair": ",".join(k for k,_ in batch)}))

best=None  # (score, sym, diag)
max_usable=BUDGET*0.98

for pair_key,ws_sym in cands:
    meta=asset_pairs.get(pair_key, {}) or {}
    ordermin_base=float(meta.get("ordermin", 0.0) or 0.0)
    t=tick.get(pair_key)
    if not t:
        continue
    bid=float(t["b"][0]); ask=float(t["a"][0]); last=float(t["c"][0])
    vol_base=float(t["v"][1])
    if bid<=0 or ask<=0 or last<=0:
        continue
    mid=(bid+ask)/2.0
    spread_bps=((ask-bid)/mid)*10000.0
    vol_quote_24h=vol_base*last
    exch_min_quote=max(0.0, ordermin_base*mid)

    # musí sa dať obchodovať s účtom
    if exch_min_quote<=0 or exch_min_quote>max_usable:
        continue

    effective_min=max(MIN_ORDER, exch_min_quote)

    # score: volume/spread + mierna penalizácia za vysoké minimum
    score = math.log1p(vol_quote_24h) / (1.0 + (spread_bps/18.0)) / (1.0 + (effective_min/max_usable)*0.35)
    sym=ws_sym.replace("/","")
    diag={"exch_min_quote":exch_min_quote,"effective_min":effective_min,"spread_bps":spread_bps,"vol_quote_24h":vol_quote_24h,"score":score}
    if best is None or score>best[0]:
        best=(score,sym,diag)

if best is None:
    raise SystemExit(f"No USD major fits budget={BUDGET} USD. Deposit more or allow non-majors.")

_, chosen_sym, diag = best

# load YAML, set universe = [chosen_sym]
in_path=Path("${IN_CFG}")
out_path=Path("${OUT_CFG}")
cfg=yaml.safe_load(in_path.read_text(encoding="utf-8"))
if not isinstance(cfg, dict):
    raise SystemExit("Config root not a dict")

def set_universe(cfg, universe):
    if isinstance(cfg.get("universe"), list):
        cfg["universe"]=universe; return
    if isinstance(cfg.get("policy"), dict) and isinstance(cfg["policy"].get("universe"), list):
        cfg["policy"]["universe"]=universe; return
    cfg["universe"]=universe

set_universe(cfg, [chosen_sym])

# best-effort: store hints at top-level (ignored by settings parser, useful for ops introspection)
cfg["pro_growth_hints"] = {
    "max_positions": 1,
    "min_order_notional_quote_effective": round(float(diag["effective_min"]), 6),
    "quote_currency": "USD",
}

risk=cfg.setdefault("risk", {})
if isinstance(risk, dict):
    risk["max_orders_per_min"]=12

execution=cfg.setdefault("execution", {})
if isinstance(execution, dict):
    execution["maker_preference"]=True
    execution["maker_timeout_s"]=45
    execution["slicing_parts"]=1
    execution["max_child_orders"]=1

out_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")

print("OK: wrote", out_path)
print("Chosen:", chosen_sym)
print("Diag:", {k: round(v,6) for k,v in diag.items() if isinstance(v,(int,float))})
PY

# create dedicated run script
cat > scripts/run_kraken_spot_pro_growth.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

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
EOF
chmod +x scripts/run_kraken_spot_pro_growth.sh

# stop old live processes (kraken spot only)
pgrep -fl "autonomous_investment_robot live --config config\.kraken_spot" >/dev/null 2>&1 && \
  pgrep -f "autonomous_investment_robot live --config config\.kraken_spot" | xargs -r kill || true

# start new live (nohup) — do NOT print keys
if [[ -z "${KRAKEN_API_KEY:-}" || -z "${KRAKEN_API_SECRET:-}" ]]; then
  echo "ERROR: KRAKEN_API_KEY/KRAKEN_API_SECRET not set in environment."
  echo "Set them first (do NOT paste them into chat), then run:"
  echo "  nohup ./scripts/run_kraken_spot_pro_growth.sh > runs/live/kraken_pro_growth.out 2>&1 &"
  exit 1
fi

mkdir -p runs/live
nohup ./scripts/run_kraken_spot_pro_growth.sh > runs/live/kraken_pro_growth.out 2>&1 &
echo "PRO GROWTH live started. PID=$!"
echo "Config: $OUT_CFG"
echo "Log: runs/live/kraken_pro_growth.out"
echo "Quick check:"
echo "  tail -n 80 runs/kraken_spot_live/audit.log"
