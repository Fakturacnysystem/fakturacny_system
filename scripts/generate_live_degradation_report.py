#!/usr/bin/env python3
from __future__ import annotations

from _runtime_report_common import emit, load_artifact, parse_args, resolve_run_dir


def main() -> int:
    args = parse_args("Emit execution degradation diagnostics for a run.")
    run_dir = resolve_run_dir(args)
    emit(
        {
            "private_stream_health": load_artifact(run_dir, "private_stream_health"),
            "execution_lifecycle_report": load_artifact(run_dir, "execution_lifecycle_report"),
            "live_degradation_delta_report": load_artifact(run_dir, "live_degradation_delta_report"),
            "live_degradation_detector_report": load_artifact(run_dir, "live_degradation_detector_report"),
            "self_throttling_state_report": load_artifact(run_dir, "self_throttling_state_report"),
            "adaptive_cadence_report": load_artifact(run_dir, "adaptive_cadence_report"),
        },
        pretty=args.pretty,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
