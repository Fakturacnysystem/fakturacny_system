#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path

DEFAULT_FILES = [
    "kraken_spot_operator_summary.json",
    "safety_preflight_live_target.json",
    "rollback_preflight_liveprofit_paper.json",
    "tiny_live_readiness_report.json",
    "readiness_summary.json",
    "live_safety_summary.json",
    "config_truth_report.json",
    "release_manifest.json",
    "deployment_stamp.json",
    "runtime_fingerprint.json",
    "health_summary.json",
    "throughput_diagnostics.json",
    "failure_taxonomy.json",
    "decision_explainability.json",
    "live_artifact_index.json",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    out_dir = run_dir / "diagnostics" if not args.output else Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    tar_path = out_dir / f"{run_dir.name}_diagnostics.tar.gz"
    manifest_path = out_dir / f"{run_dir.name}_diagnostics_manifest.json"
    present = []
    missing = []
    with tarfile.open(tar_path, "w:gz") as tar:
        for rel in DEFAULT_FILES:
            path = run_dir / rel
            if path.exists():
                tar.add(path, arcname=path.name)
                present.append(path.name)
            else:
                missing.append(path.name)
    manifest = {
        "run_dir": str(run_dir),
        "bundle": str(tar_path),
        "present_files": present,
        "missing_files": missing,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
