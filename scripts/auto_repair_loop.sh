#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  echo "[ERR] .venv neexistuje"
  exit 1
fi

source .venv/bin/activate

export PYTHONPATH=src

echo "=== AUTO REPAIR LOOP START ==="
python scripts/agent_repair_runner.py --maxfail 1 || true

LATEST="$(ls -1dt runs/auto_repair/auto_repair_* 2>/dev/null | head -n1 || true)"
if [ -z "${LATEST}" ]; then
  echo "[ERR] Nenašiel sa run report"
  exit 1
fi

echo
echo "=== LATEST REPORT ==="
echo "$LATEST"

if [ -f "$LATEST/repair_hints.txt" ]; then
  echo
  cat "$LATEST/repair_hints.txt"
fi

echo
echo "=== DONE ==="
echo "Pozri:"
echo "  $LATEST/report.json"
echo "  $LATEST/pytest.stdout.log"
echo "  $LATEST/pytest.stderr.log"
