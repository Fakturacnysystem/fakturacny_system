from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.universe_gateway.simulation_worker import run_worker_forever


if __name__ == "__main__":
    raise SystemExit(run_worker_forever())
