from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import _load_yaml_like  # noqa: E402
from autonomous_investment_robot.services.reliability import WatchdogConfig, WatchdogSupervisor  # noqa: E402


def _resolve_run_dir(config_path: str, explicit: str) -> str:
    if explicit:
        return explicit
    try:
        cfg = _load_yaml_like(config_path)
        storage = cfg.get("storage", {}) if isinstance(cfg, dict) else {}
        run_dir = storage.get("run_dir")
        if isinstance(run_dir, str) and run_dir.strip():
            return run_dir
    except Exception:
        pass
    return "runs/kraken_spot_live"


def _watchdog_config(config_path: str) -> WatchdogConfig:
    try:
        cfg = _load_yaml_like(config_path)
        wd = cfg.get("watchdog", {}) if isinstance(cfg, dict) else {}
    except Exception:
        wd = {}
    if not isinstance(wd, dict):
        wd = {}
    return WatchdogConfig(
        enabled=bool(wd.get("enabled", True)),
        poll_interval_s=max(0.25, float(wd.get("poll_interval_s", 2.0) or 2.0)),
        stall_timeout_s=max(1.0, float(wd.get("stall_timeout_s", 45.0) or 45.0)),
        restart_backoff_s=max(0.0, float(wd.get("restart_backoff_s", 5.0) or 5.0)),
        max_restarts=max(0, int(wd.get("max_restarts", 0) or 0)),
        heartbeat_filename=str(wd.get("heartbeat_file", "health.json") or "health.json"),
        state_filename=str(wd.get("state_file", "watchdog_state.json") or "watchdog_state.json"),
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.kraken_spot.live_profit.yaml")
    p.add_argument("--run-dir", default="")
    p.add_argument("--max-lag-s", type=float, default=0.0)
    args = p.parse_args()

    run_dir = _resolve_run_dir(args.config, args.run_dir)
    wd_cfg = _watchdog_config(args.config)
    if args.max_lag_s and args.max_lag_s > 0:
        wd_cfg.stall_timeout_s = max(1.0, float(args.max_lag_s))
    sup = WatchdogSupervisor(run_dir=run_dir, config=wd_cfg)
    out = sup.health(now_ts=time.time())
    print(json.dumps(out, indent=2, default=str))
    return 0 if bool(out.get("ok", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
