from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.services.ml.pipeline import train_model_from_csv  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--target", default="edge_bps")
    p.add_argument("--model", default="random_forest")
    args = p.parse_args()

    res = train_model_from_csv(args.input, args.output, target_col=args.target, model_type=args.model)
    print(json.dumps(res.__dict__, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
