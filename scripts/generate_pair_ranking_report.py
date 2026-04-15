#!/usr/bin/env python3
from __future__ import annotations

from _runtime_report_common import emit, load_artifact, parse_args, resolve_run_dir


def main() -> int:
    args = parse_args("Emit multi-pair ranking diagnostics for a run.")
    run_dir = resolve_run_dir(args)
    emit(
        {
            "pair_universe_snapshot": load_artifact(run_dir, "pair_universe_snapshot"),
            "pair_ranking_report": load_artifact(run_dir, "pair_ranking_report"),
            "pair_rotation_decisions": load_artifact(run_dir, "pair_rotation_decisions"),
            "pair_cluster_report": load_artifact(run_dir, "pair_cluster_report"),
            "pair_admission_expulsion_report": load_artifact(run_dir, "pair_admission_expulsion_report"),
            "venue_behavior_profile_report": load_artifact(run_dir, "venue_behavior_profile_report"),
        },
        pretty=args.pretty,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
