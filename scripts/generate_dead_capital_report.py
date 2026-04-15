#!/usr/bin/env python3
from __future__ import annotations

from _runtime_report_common import emit, load_artifact, parse_args, resolve_run_dir


def main() -> int:
    args = parse_args("Emit dead-capital and utilization diagnostics for a run.")
    run_dir = resolve_run_dir(args)
    emit(
        {
            "capital_envelope_summary": load_artifact(run_dir, "capital_envelope_summary"),
            "capital_utilization_diagnostics": load_artifact(run_dir, "capital_utilization_diagnostics"),
            "capital_utilization_report": load_artifact(run_dir, "capital_utilization_report"),
            "deployment_efficiency_report": load_artifact(run_dir, "deployment_efficiency_report"),
            "dead_capital_pressure_report": load_artifact(run_dir, "dead_capital_pressure_report"),
            "opportunity_miss_journal": load_artifact(run_dir, "opportunity_miss_journal"),
        },
        pretty=args.pretty,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
