#!/usr/bin/env python3
from __future__ import annotations

from _runtime_report_common import emit, load_artifact, parse_args, resolve_run_dir


def main() -> int:
    args = parse_args("Emit expectancy diagnostics bundle for a run.")
    run_dir = resolve_run_dir(args)
    emit(
        {
            "expectancy_engine_report": load_artifact(run_dir, "expectancy_engine_report"),
            "expectancy_segment_matrix": load_artifact(run_dir, "expectancy_segment_matrix"),
            "playbook_promotion_readiness": load_artifact(run_dir, "playbook_promotion_readiness"),
            "pair_regime_expectancy_grid": load_artifact(run_dir, "pair_regime_expectancy_grid"),
            "promotion_score_report": load_artifact(run_dir, "promotion_score_report"),
            "intraday_session_model_report": load_artifact(run_dir, "intraday_session_model_report"),
            "meta_router_report": load_artifact(run_dir, "meta_router_report"),
            "confidence_calibration_report": load_artifact(run_dir, "confidence_calibration_report"),
        },
        pretty=args.pretty,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
