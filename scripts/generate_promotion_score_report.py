#!/usr/bin/env python3
from __future__ import annotations

from _runtime_report_common import emit, load_artifact, parse_args, resolve_run_dir


def main() -> int:
    args = parse_args("Emit promotion and rollback evidence for a run.")
    run_dir = resolve_run_dir(args)
    emit(
        {
            "promotion_score_report": load_artifact(run_dir, "promotion_score_report"),
            "promotion_gate_report": load_artifact(run_dir, "promotion_gate_report"),
            "rollback_trigger_report": load_artifact(run_dir, "rollback_trigger_report"),
            "rollout_readiness_report": load_artifact(run_dir, "rollout_readiness_report"),
        },
        pretty=args.pretty,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
