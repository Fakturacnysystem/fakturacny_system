from __future__ import annotations

import argparse
import json

from autonomous_investment_robot.main import run_replay, run_with_config


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    p_run = sub.add_parser("run")
    p_run.add_argument("--config", default="config.paper.yaml")

    p_rep = sub.add_parser("replay")
    p_rep.add_argument("--config", default="config.paper.yaml")
    p_rep.add_argument("--source", default="fixtures")

    args = parser.parse_args()
    if args.cmd == "replay":
        out = run_replay(args.config, source=args.source)
    else:
        out = run_with_config(args.config)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
