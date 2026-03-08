#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="${LABEL:-codex.autonomous.deephealth}"
CONFIG_PATH="${CONFIG_PATH:-config.kraken_spot.live_profit.yaml}"
RUN_SCRIPT="${RUN_SCRIPT:-./scripts/run_kraken_spot_profit_full_throttle.sh}"
START_INTERVAL="${START_INTERVAL:-600}"

RUN_DIR="$(
python3 - "$REPO_ROOT/$CONFIG_PATH" <<'PY'
from pathlib import Path
import json
import sys

cfg = Path(sys.argv[1])
default = "runs/kraken_spot_live_profit09"
if not cfg.exists():
    print(default)
    raise SystemExit(0)
txt = cfg.read_text(encoding="utf-8")
data = {}
try:
    import yaml  # type: ignore
    p = yaml.safe_load(txt)
    if isinstance(p, dict):
        data = p
except Exception:
    pass
if not data:
    try:
        p = json.loads(txt)
        if isinstance(p, dict):
            data = p
    except Exception:
        data = {}
storage = data.get("storage", {}) if isinstance(data, dict) else {}
v = storage.get("run_dir") if isinstance(storage, dict) else None
print(v if isinstance(v, str) and v.strip() else default)
PY
)"

mkdir -p "$REPO_ROOT/$RUN_DIR"
mkdir -p "$HOME/Library/LaunchAgents"

PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
OUT_LOG="$REPO_ROOT/$RUN_DIR/deep_health_launchd.out"
ERR_LOG="$REPO_ROOT/$RUN_DIR/deep_health_launchd.err"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd ${REPO_ROOT} &amp;&amp; PYTHONPATH=src .venv/bin/python scripts/deep_system_health_check.py --config ${CONFIG_PATH} --run-script '${RUN_SCRIPT}'</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>${START_INTERVAL}</integer>
  <key>StandardOutPath</key>
  <string>${OUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${ERR_LOG}</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl kickstart -k "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true

echo "installed_label=${LABEL}"
echo "plist=${PLIST_PATH}"
echo "run_dir=${RUN_DIR}"
echo "stdout=${OUT_LOG}"
echo "stderr=${ERR_LOG}"
