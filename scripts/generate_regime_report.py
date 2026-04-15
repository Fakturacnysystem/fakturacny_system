#!/usr/bin/env python3
from __future__ import annotations

from _runtime_report_common import emit, load_artifact, parse_args, resolve_run_dir


def main() -> int:
    args = parse_args("Emit regime diagnostics for a run.")
    run_dir = resolve_run_dir(args)
    emit(
        {
            "regime_snapshot": load_artifact(run_dir, "regime_snapshot"),
            "regime_transition_log": load_artifact(run_dir, "regime_transition_log"),
            "regime_pair_matrix": load_artifact(run_dir, "regime_pair_matrix"),
            "regime_hysteresis_report": load_artifact(run_dir, "regime_hysteresis_report"),
            "regime_exit_family_report": load_artifact(run_dir, "regime_exit_family_report"),
        },
        pretty=args.pretty,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
