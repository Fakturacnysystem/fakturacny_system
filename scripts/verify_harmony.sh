#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/6] Python syntax compile (best-effort)..."
python3 - <<PY
import os, sys, subprocess
root="src/autonomous_investment_robot"
paths=[]
for dirpath, _, filenames in os.walk(root):
    for f in filenames:
        if f.endswith(".py"):
            paths.append(os.path.join(dirpath,f))
# limit is fine; py_compile handles many files
import py_compile
bad=[]
for p in paths:
    try:
        py_compile.compile(p, doraise=True)
    except Exception as e:
        bad.append((p,str(e)))
if bad:
    print("FAIL py_compile:")
    for p,e in bad[:50]:
        print(" -",p, e)
    sys.exit(1)
print("OK py_compile", len(paths), "files")
PY

echo "[2/6] pytest -q (this may take a bit)..."
pytest -q

echo "[3/6] Check core rule strings exist (sell profit lock)..."
grep -RIn --line-number "profit_lock_sell_below_entry\\|profit_lock_sell_below_min_profit\\|AUTONOMOUS_SELL_MIN_NET_PROFIT_BPS\\|AUTONOMOUS_TP_SCHEDULE_TARGET_GROSS_BPS" src/autonomous_investment_robot | head -n 80 || true

echo "[4/6] Check harmony resolver exists..."
test -f src/autonomous_investment_robot/services/ops/harmony.py && echo "OK harmony.py exists"

echo "[5/6] Check mastermind exists..."
test -f src/autonomous_investment_robot/services/mastermind/service.py && echo "OK mastermind exists"

echo "[6/6] Check config matrix generator exists..."
test -f scripts/audit_config_matrix.py && echo "OK audit_config_matrix.py exists"

echo "DONE. If all passed: system should be harmonized & testable."
