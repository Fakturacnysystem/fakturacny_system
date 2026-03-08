#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _load_config(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}


def _tail_audit(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _pgrep(cmd_pattern: str) -> tuple[bool, list[str]]:
    proc = subprocess.run(
        ["pgrep", "-af", cmd_pattern],
        text=True,
        capture_output=True,
        check=False,
    )
    rows = [r.strip() for r in (proc.stdout or "").splitlines() if r.strip()]
    return proc.returncode == 0 and bool(rows), rows


def _safe_restart(repo_root: Path, run_script: str) -> dict[str, Any]:
    proc = subprocess.run(
        ["/bin/zsh", "-lc", f"cd {repo_root} && {run_script}"],
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    out = (proc.stdout or "").strip().splitlines()[-8:]
    err = (proc.stderr or "").strip().splitlines()[-8:]
    return {
        "attempted": True,
        "return_code": proc.returncode,
        "stdout_tail": out,
        "stderr_tail": err,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.kraken_spot.live_profit.yaml")
    parser.add_argument("--event-limit", type=int, default=800)
    parser.add_argument(
        "--run-script",
        default="./scripts/run_kraken_spot_profit_full_throttle.sh",
        help="Repo-local command used for safe restart attempts.",
    )
    parser.add_argument("--reject-rate-threshold", type=float, default=0.75)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    cfg_path = (repo_root / args.config).resolve()
    cfg = _load_config(cfg_path)
    run_dir = str(((cfg.get("storage", {}) if isinstance(cfg.get("storage", {}), dict) else {}).get("run_dir")) or "runs/kraken_spot_live_profit09")
    run_path = (repo_root / run_dir).resolve()
    run_path.mkdir(parents=True, exist_ok=True)

    health = _load_json(run_path / "health.json")
    harmony = _load_json(run_path / "harmony_report.json")
    mastermind = _load_json(run_path / "mastermind_status.json")
    dashboard = _load_json(run_path / "dashboard_snapshot.json")
    events = _tail_audit(run_path / "audit.log", limit=max(100, int(args.event_limit)))

    process_pattern = f"python.*-m cli.run --config {args.config} --nonstop"
    process_ok, process_rows = _pgrep(process_pattern)

    status = str(health.get("status", "")).lower()
    health_ok = status in {"running", "ok"}
    harmony_ok = all(
        key in harmony
        for key in (
            "guards_mode",
            "order_cadence_s",
            "effective_min_order_quote",
            "sell_min_profit_bps",
        )
    )
    mastermind_ok = bool(mastermind) and bool(mastermind.get("health"))

    reject_rate = float(((dashboard.get("execution", {}) if isinstance(dashboard.get("execution"), dict) else {}).get("reject_rate", 0.0)) or 0.0)
    auth_lockout = 0
    auth_invalid = 0
    dns_errors = 0
    profit_lock_violations = 0
    for ev in events:
        payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
        reason = str(ev.get("reason") or payload.get("reason") or "").lower()
        et = str(ev.get("event_type") or "").lower()
        if "temporary lockout" in reason:
            auth_lockout += 1
        if "invalid key" in reason or "invalid signature" in reason or "permission denied" in reason:
            auth_invalid += 1
        if "nodename nor servname provided" in reason:
            dns_errors += 1
        if "profit_lock_sell_below_entry" in reason or "profit_lock_sell_below_min_profit" in reason:
            profit_lock_violations += 1
        if et == "fill_sync_error":
            msg = str(payload.get("error", "")).lower()
            if "temporary lockout" in msg:
                auth_lockout += 1
            if "invalid key" in msg or "invalid signature" in msg or "permission denied" in msg:
                auth_invalid += 1
            if "nodename nor servname provided" in msg:
                dns_errors += 1

    stale_runtime_files = []
    for pattern in ("**/*.pid", "**/*.lock", "**/KILL"):
        for p in run_path.glob(pattern):
            if p.is_file():
                stale_runtime_files.append(str(p))

    checks = {
        "process_ok": process_ok,
        "health_ok": health_ok,
        "harmony_ok": harmony_ok,
        "mastermind_ok": mastermind_ok,
        "reject_rate_ok": reject_rate <= float(args.reject_rate_threshold),
        "profit_lock_violations_ok": profit_lock_violations == 0,
    }
    critical_failure = (not checks["process_ok"]) or (not checks["health_ok"]) or (not checks["harmony_ok"]) or (not checks["mastermind_ok"]) or (profit_lock_violations > 0)

    restart = {"attempted": False}
    if critical_failure:
        restart = _safe_restart(repo_root=repo_root, run_script=args.run_script)

    report = {
        "ts": time.time(),
        "config": str(cfg_path),
        "run_dir": str(run_path),
        "checks": checks,
        "metrics": {
            "reject_rate": reject_rate,
            "auth_lockout_events": auth_lockout,
            "auth_invalid_events": auth_invalid,
            "dns_error_events": dns_errors,
            "profit_lock_violations": profit_lock_violations,
            "stale_runtime_files": stale_runtime_files,
        },
        "process_matches": process_rows,
        "restart": restart,
        "result": "ok" if not critical_failure else "warn",
    }

    report_path = run_path / "deep_health_check.json"
    log_path = run_path / "deep_health_check.log"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report, sort_keys=True) + "\n")
    print(json.dumps({"status": report["result"], "report": str(report_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
