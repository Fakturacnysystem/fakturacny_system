#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--allow-readonly", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    operator = _read(run_dir / "kraken_spot_operator_summary.json")
    readiness = _read(run_dir / "readiness_summary.json") or _read(run_dir / "tiny_live_readiness_report.json")
    live_safety = _read(run_dir / "live_safety_summary.json")
    health = _read(run_dir / "health_summary.json")
    preflight_ok = (operator.get("preflight") or {}).get("ok")
    if preflight_ok is None:
        preflight_ok = health.get("preflight_ok")
    ordering_allowed = operator.get("ordering_allowed")
    if ordering_allowed is None:
        ordering_allowed = health.get("ordering_allowed")
    payload: dict[str, Any] = {
        "run_dir": str(run_dir),
        "operator_summary_present": bool(operator),
        "readiness_present": bool(readiness),
        "live_safety_present": bool(live_safety),
        "preflight_ok": preflight_ok,
        "ordering_allowed": ordering_allowed,
        "readiness_ready": readiness.get("readiness_ready", readiness.get("ready")),
        "safety_ready": live_safety.get("safety_ready"),
    }
    mode = operator.get("mode")
    if args.allow_readonly and mode == "live_readonly":
        ok = bool(payload["operator_summary_present"] and payload["preflight_ok"])
    else:
        ok = bool(payload["operator_summary_present"] and payload["preflight_ok"] and payload["ordering_allowed"] and payload["safety_ready"])
    payload["status"] = "ok" if ok else "blocked"
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
