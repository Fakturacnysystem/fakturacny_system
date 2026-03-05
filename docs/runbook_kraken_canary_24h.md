# Kraken Spot Canary 24h Runbook

This runbook starts canary mode with hard safety invariants preserved and active trading enabled (not paper mode).

## 1) Start (24h canary manager)

```bash
cd /Users/martinholik/Projects/fakturacny_system

# Required secrets in shell env (do not put into files)
export KRAKEN_API_KEY="..."
export KRAKEN_API_SECRET="..."

# Live profile
export AUTONOMOUS_LIVE_CONFIG="config.kraken_spot.live_profit.yaml"
export AUTONOMOUS_MANAGER_MAX_RUNTIME_S=86400
export AUTONOMOUS_CANARY_AUTOPILOT=true
export AUTONOMOUS_CANARY_FRACTION=0.20
export AUTONOMOUS_PROMOTED_FRACTION=1.00

# Trading behavior (keeps safety guards)
export AUTONOMOUS_GUARDS_MODE=strict
export AUTONOMOUS_MIN_NET_EDGE_BPS=0.8
export AUTONOMOUS_MAX_ORDERS_PER_MIN=12
export AUTONOMOUS_RATE_LIMIT_COOLDOWN_S=5
export AUTONOMOUS_OPERATOR_PAUSE_ENTRIES=false

mkdir -p runs/live
nohup bash scripts/run_kraken_spot_growth_manager.sh > runs/live/growth_manager_24h.out 2>&1 &
echo "manager_pid=$!"
```

Expected:
- Manager log: `runs/live/kraken_growth_manager.log`
- Child live log: `runs/live/kraken_growth.out`
- Trading audit: `runs/kraken_spot_live/audit.log`

## 2) Monitor (every 5-15 min)

```bash
cd /Users/martinholik/Projects/fakturacny_system

tail -n 80 runs/live/kraken_growth_manager.log
tail -n 80 runs/live/kraken_growth.out
```

Execution health snapshot:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p=Path("runs/kraken_spot_live/dashboard_snapshot.json")
if not p.exists():
    print("dashboard_snapshot.json missing")
    raise SystemExit(0)
d=json.loads(p.read_text())
g=d.get("groups",{})
print("execution:", g.get("execution",{}))
print("efficiency:", g.get("efficiency",{}))
print("microstructure:", g.get("microstructure",{}))
PY
```

Top block reasons:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from collections import Counter
p=Path("runs/kraken_spot_live/audit.log")
c=Counter()
for line in p.read_text(encoding="utf-8",errors="ignore").splitlines()[-2000:]:
    if not line.strip(): continue
    try: row=json.loads(line)
    except Exception: continue
    pl=row.get("payload",{})
    if isinstance(pl,dict):
        r=pl.get("reason")
        if isinstance(r,str) and r.strip(): c[r.strip()]+=1
print(dict(c.most_common(20)))
PY
```

## 3) Promote (after enough canary evidence)

Use built-in KPI gate:

```bash
cd /Users/martinholik/Projects/fakturacny_system
python3 scripts/promote_canary.py --run-dir runs/kraken_spot_live
```

If promoted, switch to main process:

```bash
pkill -f "scripts/growth_manager.py" || true
nohup bash scripts/run_kraken_spot_main.sh > runs/live/kraken_main.out 2>&1 &
echo "main_pid=$!"
```

## 4) Rollback (if canary/main degrades)

Trigger conditions:
- rate-limit storm
- high reject regime with poor net pnl
- live/backtest divergence worsening

Rollback:

```bash
cd /Users/martinholik/Projects/fakturacny_system
python3 scripts/rollback_last_good.py --run-dir runs/kraken_spot_live
pkill -f "autonomous_investment_robot live --config" || true
nohup bash scripts/run_kraken_spot_main.sh > runs/live/kraken_main.out 2>&1 &
```

## 5) Stop

```bash
pkill -f "scripts/growth_manager.py" || true
pkill -f "autonomous_investment_robot live --config" || true
```

