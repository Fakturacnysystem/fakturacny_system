from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.cli_runtime_config import apply_runtime_override  # noqa: E402
from autonomous_investment_robot.main import run_with_config  # noqa: E402


def _blocked_exception(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "blocked" in text or "live trading blocked" in text


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
        print(json.dumps(out, indent=2, default=str))
        return 2 if blocked else 1
    print(json.dumps(out, indent=2, default=str))
    status = str(out.get("status", "") or "").lower()
    if status == "blocked":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
