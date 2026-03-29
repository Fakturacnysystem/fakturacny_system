#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "runs"


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _discover_run_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    matches = sorted(RUNS.glob("**/kraken_spot_operator_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        return RUNS / "missing"
    return matches[0].parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", default="")
    args = parser.parse_args()
    run_dir = _discover_run_dir(args.run_dir or None)
    operator = _read(run_dir / "kraken_spot_operator_summary.json")
    readiness = _read(run_dir / "readiness_summary.json") or _read(run_dir / "tiny_live_readiness_report.json")
    health = _read(run_dir / "health_summary.json")
    config_truth = _read(run_dir / "config_truth_report.json")
    release_manifest = _read(run_dir / "release_manifest.json")
    payload = {
        "run_dir": str(run_dir),
        "exists": run_dir.exists(),
        "provider_id": operator.get("provider_id"),
        "mode": operator.get("mode"),
        "rollout_stage": operator.get("rollout_stage") or readiness.get("stage") or readiness.get("rollout_stage"),
        "ordering_allowed": operator.get("ordering_allowed"),
        "preflight_ok": (operator.get("preflight") or {}).get("ok"),
        "preflight_reason": (operator.get("preflight") or {}).get("reason"),
        "readiness_ready": readiness.get("readiness_ready", readiness.get("ready")),
        "config_hash": (operator.get("harmony") or {}).get("config_hash") or config_truth.get("config_hash"),
        "release_fingerprint": release_manifest.get("release_fingerprint"),
        "health": health,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if run_dir.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
