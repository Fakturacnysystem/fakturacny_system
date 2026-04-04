#!/usr/bin/env python3
from __future__ import annotations

from _runtime_report_common import emit, load_artifact, parse_args, resolve_run_dir


def main() -> int:
    args = parse_args("Emit performance target translation gap report for a run.")
    emit(load_artifact(resolve_run_dir(args), "performance_gap_report"), pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
