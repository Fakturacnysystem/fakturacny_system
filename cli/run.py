from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import _load_yaml_like  # noqa: E402
from autonomous_investment_robot.cli_runtime_config import apply_runtime_override  # noqa: E402
from autonomous_investment_robot.main import run_with_config  # noqa: E402
from autonomous_investment_robot.services.reliability import WatchdogConfig, WatchdogSupervisor  # noqa: E402
from autonomous_investment_robot.services.research import MISSING_KEY_MESSAGE  # noqa: E402


def _blocked_exception(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "blocked" in text or "live trading blocked" in text


def _read_mode(config_path: str) -> str:
    try:
        cfg = _load_yaml_like(config_path)
        exec_cfg = cfg.get("execution", {}) if isinstance(cfg, dict) else {}
        mode = str(exec_cfg.get("mode", cfg.get("mode", "paper"))).strip().lower()
        return mode or "paper"
    except Exception:
        return "paper"


def _resolve_run_dir(config_path: str) -> str:
    env_override = str(os.getenv("AUTONOMOUS_RUN_DIR", "") or "").strip()
    if env_override:
        return env_override
    try:
        cfg = _load_yaml_like(config_path)
        storage = cfg.get("storage", {}) if isinstance(cfg, dict) else {}
        value = storage.get("run_dir")
        if isinstance(value, str) and value.strip():
            return value
    except Exception:
        pass
    return "runs/kraken_spot_live"


def _force_execution_mode(config_path: str, mode: str) -> str:
    try:
        cfg = _load_yaml_like(config_path)
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}
    cfg["mode"] = mode
    exec_cfg = cfg.get("execution", {})
    if not isinstance(exec_cfg, dict):
        exec_cfg = {}
    exec_cfg["mode"] = mode
    cfg["execution"] = exec_cfg
    out_path = Path(_resolve_run_dir(config_path)) / f"runtime_config.forced_{mode}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore

        out_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    except Exception:
        out_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return str(out_path)


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


def _run_once(config_path: str) -> int:
    try:
        out = run_with_config(config_path)
    except Exception as exc:
        blocked = _blocked_exception(exc)
        out = {
            "status": "blocked" if blocked else "error",
            "reason": str(exc),
            "config": config_path,
        }
        print(json.dumps(out, indent=2, default=str))
        return 2 if blocked else 1
    print(json.dumps(out, indent=2, default=str))
    return 2 if str(out.get("status", "")).lower() == "blocked" else 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--once", action="store_true", help="Run single cycle and exit.")
    p.add_argument("--nonstop", action="store_true", help="Force watchdog nonstop mode.")
    p.add_argument("--paper", action="store_true", help="Force paper-safe run semantics.")
    p.add_argument("--live", action="store_true", help="Force live semantics (requires explicit env arming).")
    p.add_argument("--dashboard", action="store_true", help="Start read-only monitoring dashboard sidecar.")
    p.add_argument("--max-restarts", type=int, default=None)
    p.add_argument("--stall-timeout-s", type=float, default=None)
    p.add_argument("--restart-backoff-s", type=float, default=None)
    p.add_argument("--poll-s", type=float, default=None)
    args = p.parse_args()

    if args.paper and args.live:
        print(json.dumps({"status": "error", "reason": "flags_conflict_paper_and_live"}, indent=2))
        return 1

    if not str(os.getenv("OPENAI_API_KEY", "")).strip():
        print(MISSING_KEY_MESSAGE)

    if args.paper:
        os.environ["LIVE_TRADING"] = "false"
        os.environ["ENABLE_LIVE_TRADING"] = "false"
        if not args.nonstop:
            args.once = True
    if args.live:
        os.environ["LIVE_TRADING"] = "true"

    effective_config = apply_runtime_override(args.config)
    if args.paper:
        effective_config = _force_execution_mode(effective_config, "paper")
    dash_enabled = bool(args.dashboard or str(os.getenv("AUTONOMOUS_DASHBOARD_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"})
    dash_proc: subprocess.Popen | None = None
    if dash_enabled:
        try:
            dash_proc = subprocess.Popen(
                [sys.executable, "-m", "cli.dashboard", "--config", args.config],
                cwd=str(ROOT),
            )
        except Exception:
            dash_proc = None

    if args.once:
        rc = _run_once(effective_config)
        if dash_proc is not None:
            try:
                dash_proc.terminate()
            except Exception:
                pass
        return rc

    mode = _read_mode(effective_config)
    auto_nonstop = mode in {"live", "live_testnet", "live_readonly"}
    nonstop = bool(args.nonstop or auto_nonstop)
    if not nonstop:
        rc = _run_once(effective_config)
        if dash_proc is not None:
            try:
                dash_proc.terminate()
            except Exception:
                pass
        return rc

    run_dir = _resolve_run_dir(effective_config)
    wd_cfg = _watchdog_config(effective_config)
    if args.max_restarts is not None:
        wd_cfg.max_restarts = max(0, int(args.max_restarts))
    if args.stall_timeout_s is not None:
        wd_cfg.stall_timeout_s = max(1.0, float(args.stall_timeout_s))
    if args.restart_backoff_s is not None:
        wd_cfg.restart_backoff_s = max(0.0, float(args.restart_backoff_s))
    if args.poll_s is not None:
        wd_cfg.poll_interval_s = max(0.25, float(args.poll_s))

    sup = WatchdogSupervisor(run_dir=run_dir, config=wd_cfg)
    loop_config_source = effective_config if args.paper else args.config
    while True:
        effective_config = apply_runtime_override(loop_config_source)
        if args.paper:
            effective_config = _force_execution_mode(effective_config, "paper")
        child = subprocess.Popen(
            [sys.executable, "-m", "cli.worker", "--config", effective_config],
            cwd=str(ROOT),
        )
        sup.mark_child_started(child.pid)
        restart_reason = "child_exit"

        while True:
            rc = child.poll()
            if rc is not None:
                restart_reason = f"child_exit_code_{rc}"
                break
            if sup.stalled(now_ts=time.time()):
                restart_reason = "heartbeat_stalled"
                try:
                    child.terminate()
                    child.wait(timeout=10.0)
                except Exception:
                    try:
                        child.kill()
                    except Exception:
                        pass
                break
            time.sleep(wd_cfg.poll_interval_s)

        sup.mark_child_stopped()
        final_rc = child.poll()
        if final_rc == 2:
            # Configuration/auth blocks are not recoverable via blind restarts.
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "reason": "child_reported_blocked",
                        "restart_reason": restart_reason,
                    },
                    indent=2,
                )
            )
            if dash_proc is not None:
                try:
                    dash_proc.terminate()
                except Exception:
                    pass
            return 2

        if not sup.can_restart():
            print(
                json.dumps(
                    {
                        "status": "error",
                        "reason": "watchdog_max_restarts_exceeded",
                        "restart_reason": restart_reason,
                        "restart_count": sup.state.restart_count,
                        "max_restarts": wd_cfg.max_restarts,
                    },
                    indent=2,
                )
            )
            if dash_proc is not None:
                try:
                    dash_proc.terminate()
                except Exception:
                    pass
            return 1

        sup.register_restart(restart_reason)
        if wd_cfg.restart_backoff_s > 0:
            time.sleep(wd_cfg.restart_backoff_s)


if __name__ == "__main__":
    raise SystemExit(main())
