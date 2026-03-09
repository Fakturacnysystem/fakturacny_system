from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.services.distributed import (  # noqa: E402
    ComputeWorkerConfig,
    RedisComputeWorker,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run distributed compute worker for autonomous robot.")
    parser.add_argument("--run-dir", default=str(os.getenv("AUTONOMOUS_RUN_DIR", "runs/compute_node")))
    parser.add_argument("--once", action="store_true", help="Process one poll cycle and exit.")
    args = parser.parse_args()

    cfg = ComputeWorkerConfig.from_env()
    worker = RedisComputeWorker(cfg)
    conn = worker.connect()
    if not bool(conn.get("ok", False)):
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "compute_worker_connect_failed",
                    "detail": str(conn.get("reason", "")),
                },
                indent=2,
            )
        )
        return 2

    if args.once:
        out = worker.poll_once()
        print(json.dumps({"status": "ok", "health": worker.health(), "tick": out}, indent=2, default=str))
        return 0

    worker.run_forever(run_dir=str(args.run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
