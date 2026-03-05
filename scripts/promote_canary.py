#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _parse_env_overrides(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or not line.startswith("export "):
            continue
        body = line[len("export ") :]
        if "=" not in body:
            continue
        k, v = body.split("=", 1)
        out[k.strip()] = v.strip().strip("'").strip('"')
    return out


def _load_dashboard(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        out = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return out if isinstance(out, dict) else {}


def _count_rate_limits(audit_path: Path, max_lines: int = 1000) -> int:
    if not audit_path.exists():
        return 0
    lines = audit_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-max_lines:]
    count = 0
    for line in lines:
        if "rate_limit" in line.lower():
            count += 1
    return count


def evaluate_canary(kpis: dict[str, Any], rate_limit_events: int, args: argparse.Namespace) -> tuple[bool, dict[str, float]]:
    groups = kpis.get("groups", {}) if isinstance(kpis.get("groups"), dict) else {}
    execution = groups.get("execution", {}) if isinstance(groups.get("execution"), dict) else {}
    efficiency = groups.get("efficiency", {}) if isinstance(groups.get("efficiency"), dict) else {}
    performance = groups.get("performance", {}) if isinstance(groups.get("performance"), dict) else {}
    net_pnl = _to_float(performance.get("net_pnl_after_fees"), 0.0)
    reject_rate = _to_float(execution.get("reject_rate"), 1.0)
    cost_to_alpha = _to_float(efficiency.get("cost_to_alpha_ratio_modeled"), 999.0)
    submitted = _to_float(execution.get("executions_submitted_total"), 0.0)
    details = {
        "net_pnl_after_fees": net_pnl,
        "reject_rate": reject_rate,
        "cost_to_alpha_ratio_modeled": cost_to_alpha,
        "executions_submitted_total": submitted,
        "rate_limit_events": float(rate_limit_events),
    }
    promote = (
        submitted >= args.min_submitted
        and net_pnl >= args.min_net_pnl_after_fees
        and reject_rate <= args.max_reject_rate
        and cost_to_alpha <= args.max_cost_to_alpha
        and rate_limit_events <= args.max_rate_limit_events
    )
    return promote, details


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Promote canary overrides to last-good snapshot.")
    p.add_argument("--run-dir", default="runs/kraken_spot_live")
    p.add_argument("--min-submitted", type=float, default=10.0)
    p.add_argument("--min-net-pnl-after-fees", type=float, default=0.0)
    p.add_argument("--max-reject-rate", type=float, default=0.6)
    p.add_argument("--max-cost-to-alpha", type=float, default=1.2)
    p.add_argument("--max-rate-limit-events", type=int, default=10)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = Path(args.run_dir).expanduser()
    run_dir.mkdir(parents=True, exist_ok=True)
    env_path = run_dir / "env_overrides.sh"
    dash_path = run_dir / "dashboard_snapshot.json"
    audit_path = run_dir / "audit.log"
    if not env_path.exists():
        print(json.dumps({"status": "blocked", "reason": "missing_env_overrides", "path": str(env_path)}))
        return 1

    kpis = _load_dashboard(dash_path)
    rate_limit_events = _count_rate_limits(audit_path)
    promote, details = evaluate_canary(kpis, rate_limit_events, args)
    if not promote:
        print(json.dumps({"status": "hold", "reason": "kpi_gate_not_met", "details": details}, indent=2))
        return 0

    overrides = _parse_env_overrides(env_path)
    payload = {
        "saved_ts": time.time(),
        "mode": "main",
        "source": "promote_canary",
        "overrides": overrides,
        "details": details,
    }
    (run_dir / "last_good_overrides.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "promote_main.marker").write_text(str(int(time.time())) + "\n", encoding="utf-8")
    print(json.dumps({"status": "promoted", "last_good": str(run_dir / "last_good_overrides.json"), "details": details}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
