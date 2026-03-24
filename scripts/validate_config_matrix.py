#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import RobotSettings


def main() -> int:
    configs = sorted(REPO.glob("config*.yaml"))
    failures: list[dict[str, str]] = []
    loaded: list[dict[str, str]] = []
    blocked_expected: list[dict[str, str]] = []
    for cfg in configs:
        try:
            settings = RobotSettings.from_file(str(cfg))
        except Exception as exc:  # pragma: no cover - failure path exercised by script run
            message = str(exc)
            if message.startswith("Live trading blocked until configured:") or message.startswith("Live trading blocked: unsupported_doctrine_target_use_kraken_spot"):
                blocked_expected.append({"config": cfg.name, "reason": message})
                continue
            failures.append({"config": cfg.name, "error": message})
            continue
        loaded.append(
            {
                "config": cfg.name,
                "mode": settings.execution_mode_enum().value,
                "provider": settings.execution.provider_id,
                "stage": settings.rollout_stage().value,
                "rollout_profile": settings.rollout_profile(),
                "doctrine_launch_safe": bool(settings.live_gate_status().get("doctrine_launch_safe", False)),
            }
        )
    print(json.dumps({"loaded": loaded, "blocked_expected": blocked_expected, "failures": failures}, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
