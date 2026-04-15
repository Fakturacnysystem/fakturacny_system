#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
compose_file=""
service=""
dry_run="false"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --compose-file)
      compose_file="$2"
      shift 2
      ;;
    --service)
      service="$2"
      shift 2
      ;;
    --dry-run)
      dry_run="true"
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ -z "$compose_file" ] || [ -z "$service" ]; then
  echo '{"status":"blocked","reason":"compose_file_and_service_required"}'
  exit 1
fi

python3 "$repo_root/scripts/deployment_preflight.py" >/dev/null

python3 - "$compose_file" "$service" <<'PY'
from __future__ import annotations
import json
import sys
from pathlib import Path
import yaml
compose = Path(sys.argv[1])
service = sys.argv[2]
if not compose.exists():
    print(json.dumps({"status": "blocked", "reason": f"compose_missing:{compose}"}))
    raise SystemExit(1)
payload = yaml.safe_load(compose.read_text(encoding="utf-8")) or {}
runtime_class = ((payload or {}).get("x-runtime-classification") or {}) if isinstance(payload, dict) else {}
if runtime_class.get("status") == "legacy_blocked":
    print(json.dumps({"status": "blocked", "reason": "legacy_blocked_compose_manifest"}))
    raise SystemExit(1)
services = ((payload or {}).get("services") or {}) if isinstance(payload, dict) else {}
if service not in services:
    print(json.dumps({"status": "blocked", "reason": f"service_missing:{service}"}))
    raise SystemExit(1)
print(json.dumps({"status": "validated", "compose_file": str(compose), "service": service}))
PY

if [ "$dry_run" = "true" ]; then
  echo "{\"status\":\"dry_run_ok\",\"compose_file\":\"$compose_file\",\"service\":\"$service\"}"
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo '{"status":"blocked","reason":"docker_cli_missing"}'
  exit 1
fi

docker compose -f "$compose_file" config -q >/dev/null
if ! docker compose -f "$compose_file" config --services | grep -qx "$service"; then
  echo "{\"status\":\"blocked\",\"reason\":\"service_not_in_compose:$service\"}"
  exit 1
fi

docker compose -f "$compose_file" up -d --no-deps --force-recreate "$service"
echo "{\"status\":\"ok\",\"compose_file\":\"$compose_file\",\"service\":\"$service\"}"
