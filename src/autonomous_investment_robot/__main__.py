from __future__ import annotations

import argparse
import json

from autonomous_investment_robot.main import emergency_flatten, request_kill, run_record, run_replay, run_with_config


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    p_run = sub.add_parser("run")
    p_run.add_argument("--config", default="config.paper.yaml")
    p_run.add_argument("--kill", action="store_true")

    p_rep = sub.add_parser("replay")
    p_rep.add_argument("--config", default="config.paper.yaml")
    p_rep.add_argument("--source", default="fixtures")
    p_rep.add_argument("--run-id", default=None)

    p_ro = sub.add_parser("live-readonly")
    p_ro.add_argument("--config", default="config.perps_intraday.live_readonly.yaml")

    p_live = sub.add_parser("live")
    p_live.add_argument("--config", default="config.perps_intraday.live.yaml")
    p_live.add_argument("--kill", action="store_true")

    p_record = sub.add_parser("record")
    p_record.add_argument("--config", default="config.perps_intraday.live_readonly.yaml")
    p_record.add_argument("--run-id", default="latest")
    p_record.add_argument("--duration-seconds", type=int, default=0)
    p_record.add_argument("--poll-interval-seconds", type=float, default=1.0)

    p_flatten = sub.add_parser("flatten")
    p_flatten.add_argument("--config", default="config.perps_intraday.live.yaml")

    args = parser.parse_args()
    if getattr(args, "kill", False):
        cfg = getattr(args, "config", "config.paper.yaml")
        print(json.dumps(request_kill(cfg), indent=2))
        return

    if args.cmd == "replay":
        out = run_replay(args.config, source=args.source, run_id=args.run_id)
    elif args.cmd == "live-readonly":
        out = run_with_config(args.config)
    elif args.cmd == "live":
        out = run_with_config(args.config)
    elif args.cmd == "record":
        out = run_record(
            args.config,
            run_id=args.run_id,
            duration_seconds=args.duration_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    elif args.cmd == "flatten":
        out = emergency_flatten(args.config)
    else:
        out = run_with_config(args.config)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
