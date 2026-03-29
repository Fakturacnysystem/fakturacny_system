#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parent.parent
DEFAULT_FILES = [
    "Dockerfile",
    "pyproject.toml",
    "ops/runtime_surface.json",
    "ops/docker-compose.server.yml",
    "config.kraken_spot.tiny_live.yaml",
    "config.kraken_spot.live.yaml",
    "config.kraken_spot.live_profit.yaml",
    "infra/docker-compose.yml",
    "scripts/_common_env.sh",
    "scripts/container_start_tiny_live.sh",
    "scripts/deployment_preflight.py",
    "scripts/run_kraken_spot_tiny_live.sh",
    "scripts/run_kraken_spot_readonly_analysis.sh",
    "scripts/run_kraken_spot_profit_full_throttle.sh",
    "scripts/run_kraken_ultra_profit_full_throttle.sh",
    "scripts/runtime_status.py",
    "scripts/runtime_healthcheck.py",
    "scripts/verify_server_parity.py",
    "src/autonomous_investment_robot/config/settings.py",
    "src/autonomous_investment_robot/core/orchestrator.py",
    "src/autonomous_investment_robot/services/execution/live_kraken_spot_service.py",
    "src/autonomous_investment_robot/services/runtime_metadata/service.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _local_snapshot(base: Path, files: Iterable[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for rel in files:
        path = base / rel
        out[rel] = _sha(path) if path.exists() else None
    return out


def _remote_snapshot(target: str, key_path: str, remote_base: str, files: Iterable[str]) -> tuple[bool, dict[str, str | None], str]:
    cmd = (
        "python3 - <<'PY'\n"
        "import hashlib, json\n"
        f"base = {remote_base!r}\n"
        f"files = {list(files)!r}\n"
        "out = {}\n"
        "from pathlib import Path\n"
        "for rel in files:\n"
        "    path = Path(base) / rel\n"
        "    out[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None\n"
        "print(json.dumps(out, sort_keys=True))\n"
        "PY"
    )
    proc = subprocess.run(["ssh", "-i", key_path, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", target, cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        return False, {}, proc.stderr.strip()
    return True, json.loads(proc.stdout), ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-path", default="")
    parser.add_argument("--ssh-target", default="")
    parser.add_argument("--ssh-key", default=str(Path.home() / ".ssh" / "hetzner_trading_vm_nopass"))
    parser.add_argument("--remote-base", default="/home/martin/trading-bot-repo")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    local = _local_snapshot(REPO, DEFAULT_FILES)
    missing_local = [rel for rel, digest in local.items() if digest is None]
    report = {
        "authoritative_source_path": str(REPO),
        "files": DEFAULT_FILES,
        "local": local,
        "required_local_files_present": not missing_local,
        "missing_local_files": missing_local,
        "status": "blocked" if missing_local else "ok",
    }
    if args.runtime_path:
        runtime = _local_snapshot(Path(args.runtime_path), DEFAULT_FILES)
        mismatches = [rel for rel in DEFAULT_FILES if local.get(rel) != runtime.get(rel)]
        report.update({"runtime_path": args.runtime_path, "runtime": runtime, "mismatches": mismatches})
        if not missing_local:
            report["status"] = "ok" if not mismatches else "drift"
    elif args.ssh_target:
        ok, remote, error = _remote_snapshot(args.ssh_target, args.ssh_key, args.remote_base, DEFAULT_FILES)
        if not ok:
            report.update({"status": "blocked", "error": error})
        else:
            mismatches = [rel for rel in DEFAULT_FILES if local.get(rel) != remote.get(rel)]
            report.update(
                {
                    "remote_target": args.ssh_target,
                    "remote_base": args.remote_base,
                    "remote": remote,
                    "mismatches": mismatches,
                }
            )
            if not missing_local:
                report["status"] = "ok" if not mismatches else "drift"
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
