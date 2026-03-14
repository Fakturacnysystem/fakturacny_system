from __future__ import annotations

import argparse
import json
import time
import traceback
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.cli_runtime_config import apply_runtime_override  # noqa: E402
from autonomous_investment_robot.config.settings import _load_yaml_like  # noqa: E402
from autonomous_investment_robot.main import run_with_config  # noqa: E402


def _blocked_exception(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "blocked" in text or "live trading blocked" in text


def _resolve_run_dir(config_path: str) -> Path:
    try:
        cfg = _load_yaml_like(config_path)
        if isinstance(cfg, dict):
            storage = cfg.get("storage", {})
            if isinstance(storage, dict):
                run_dir = storage.get("run_dir")
                if isinstance(run_dir, str) and run_dir.strip():
                    return Path(run_dir.strip())
    except Exception:
        pass
    return Path("runs/kraken_spot_live")


def _write_worker_error(config_path: str, payload: dict) -> None:
    try:
        run_dir = _resolve_run_dir(config_path)
        run_dir.mkdir(parents=True, exist_ok=True)
        stamped = {"ts": float(time.time()), **payload}
        (run_dir / "worker_last_error.json").write_text(
            json.dumps(stamped, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        with (run_dir / "worker_error.log").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(stamped, sort_keys=True, default=str) + "\n")
    except Exception:
        return


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    args = p.parse_args()
    effective_config = apply_runtime_override(args.config)
    try:
        out = run_with_config(effective_config)
    except Exception as exc:
        blocked = _blocked_exception(exc)
        out = {
            "status": "blocked" if blocked else "error",
            "reason": str(exc),
            "config": effective_config,
        }
        _write_worker_error(
            effective_config,
            {
                "status": out["status"],
                "reason": out["reason"],
                "config": out["config"],
                "traceback": traceback.format_exc(),
            },
        )
        print(json.dumps(out, indent=2, default=str))
        return 2 if blocked else 1
    print(json.dumps(out, indent=2, default=str))
    status = str(out.get("status", "") or "").lower()
    if status == "blocked":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
