from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import _load_yaml_like  # noqa: E402
from autonomous_investment_robot.monitoring.dashboard import create_dashboard_app  # noqa: E402


def _resolve_run_dir(config_path: str) -> str:
    try:
        cfg = _load_yaml_like(config_path)
        storage = cfg.get("storage", {}) if isinstance(cfg, dict) else {}
        run_dir = storage.get("run_dir")
        if isinstance(run_dir, str) and run_dir.strip():
            return run_dir.strip()
    except Exception:
        pass
    return "runs/kraken_spot_live"


def _is_live(config_path: str) -> bool:
    env_live = str(os.getenv("LIVE_TRADING", "")).strip().lower() in {"1", "true", "yes", "on"}
    if env_live:
        return True
    try:
        cfg = _load_yaml_like(config_path)
        exec_cfg = cfg.get("execution", {}) if isinstance(cfg, dict) else {}
        mode = str(exec_cfg.get("mode", cfg.get("mode", "paper"))).strip().lower()
        return mode in {"live", "live_testnet", "live_readonly"}
    except Exception:
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.getenv("AUTONOMOUS_DASHBOARD_PORT", "8080") or "8080"))
    p.add_argument("--override-path", default="")
    args = p.parse_args()

    run_dir = _resolve_run_dir(args.config)
    app = create_dashboard_app(
        run_dir=run_dir,
        config_path=args.config,
        live_mode=_is_live(args.config),
        override_path=args.override_path.strip() or None,
    )
    app.run(host=args.host, port=max(1, int(args.port)), debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
