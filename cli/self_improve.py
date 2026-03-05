from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import _load_yaml_like  # noqa: E402
from autonomous_investment_robot.services.research import OpenAISelfImprovementAdvisor  # noqa: E402


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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.kraken_spot.live_profit.yaml")
    p.add_argument("--run-dir", default="")
    p.add_argument("--last", type=float, default=24.0, help="Analyze last N hours.")
    args = p.parse_args()

    run_dir = args.run_dir.strip() if isinstance(args.run_dir, str) else ""
    if not run_dir:
        run_dir = _resolve_run_dir(args.config)

    advisor = OpenAISelfImprovementAdvisor(run_dir=run_dir)
    out = advisor.run(last_hours=max(1.0, float(args.last)))
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
