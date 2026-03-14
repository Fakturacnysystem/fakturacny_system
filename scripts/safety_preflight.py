#!/usr/bin/env python3
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import RobotSettings, _load_yaml_like  # noqa: E402


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def _load_runtime_settings(config_path: Path, target_mode: str) -> tuple[bool, str]:
    if target_mode == "live":
        try:
            RobotSettings.from_file(str(config_path))
            return True, "ok"
        except Exception as exc:
            return False, str(exc)

    try:
        cfg = _load_yaml_like(str(config_path))
    except Exception as exc:
        return False, f"config_parse_failed:{exc}"
    if not isinstance(cfg, dict):
        return False, "config_root_not_mapping"
    cfg = dict(cfg)
    cfg["mode"] = "paper"
    execution = cfg.get("execution", {})
    if not isinstance(execution, dict):
        execution = {}
    execution["mode"] = "paper"
    cfg["execution"] = execution

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(cfg, tmp)
        tmp_path = Path(tmp.name)
    try:
        RobotSettings.from_file(str(tmp_path))
        return True, "ok"
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Safety preflight checker for paper/live startup.")
    parser.add_argument("--config", required=True, help="Path to robot config file.")
    parser.add_argument(
        "--target-mode",
        choices=("paper", "live"),
        default="paper",
        help="Validation target mode. Default is paper.",
    )
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    args = parser.parse_args()

    config_path = (ROOT / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config).resolve()
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "name": "config_exists",
            "ok": config_path.exists(),
            "reason": "ok" if config_path.exists() else "missing_config",
            "details": {"config": str(config_path)},
        }
    )

    required_docs = [
        ROOT / "SYSTEM_ARCHITECTURE.md",
        ROOT / "OPERATOR_RUNBOOK.md",
        ROOT / "CONFIG_REFERENCE.md",
        ROOT / "LIVE_READINESS_CHECKLIST.md",
    ]
    missing_docs = [str(p.relative_to(ROOT)) for p in required_docs if not p.exists()]
    checks.append(
        {
            "name": "required_docs",
            "ok": not missing_docs,
            "reason": "ok" if not missing_docs else "missing_docs",
            "details": {"missing": missing_docs},
        }
    )

    required_artifacts = [
        ROOT / "docker-compose.live.yml",
        ROOT / "docker-compose.compute.yml",
        ROOT / "docker-compose.full.yml",
        ROOT / "deploy/live-node.env.example",
        ROOT / "deploy/compute-node.env.example",
        ROOT / "scripts/start_live_node.sh",
        ROOT / "scripts/start_compute_node.sh",
        ROOT / "scripts/start_ultra_profit_cluster.sh",
    ]
    missing_artifacts = [str(p.relative_to(ROOT)) for p in required_artifacts if not p.exists()]
    checks.append(
        {
            "name": "cloud_artifacts",
            "ok": not missing_artifacts,
            "reason": "ok" if not missing_artifacts else "missing_artifacts",
            "details": {"missing": missing_artifacts},
        }
    )

    if config_path.exists():
        ok, reason = _load_runtime_settings(config_path, args.target_mode)
        checks.append(
            {
                "name": "settings_validation",
                "ok": ok,
                "reason": reason,
                "details": {"target_mode": args.target_mode},
            }
        )

    if args.target_mode == "live":
        live_go = _truthy(os.getenv("AUTONOMOUS_LIVE_GO"))
        confirmation_file = str(
            os.getenv("AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE", "ops/live_operator_confirmation.txt")
            or "ops/live_operator_confirmation.txt"
        ).strip()
        confirmation_path = (
            (ROOT / confirmation_file).resolve()
            if not Path(confirmation_file).is_absolute()
            else Path(confirmation_file).resolve()
        )
        checks.append(
            {
                "name": "manual_live_gate",
                "ok": bool(live_go and confirmation_path.exists()),
                "reason": "ok" if bool(live_go and confirmation_path.exists()) else "manual_live_gate_not_satisfied",
                "details": {
                    "live_go": bool(live_go),
                    "confirmation_file_exists": confirmation_path.exists(),
                    "confirmation_file": str(confirmation_path),
                },
            }
        )
        approval_file = str(
            os.getenv("AUTONOMOUS_LIVE_OPERATOR_APPROVAL_ARTIFACT_FILE", "ops/live_governance_approval.json")
            or "ops/live_governance_approval.json"
        ).strip()
        approval_path = (
            (ROOT / approval_file).resolve()
            if not Path(approval_file).is_absolute()
            else Path(approval_file).resolve()
        )
        approval_artifact_ok = False
        approval_reason = "approval_artifact_missing"
        if approval_path.exists():
            try:
                approval_payload = json.loads(approval_path.read_text(encoding="utf-8"))
                approval_artifact_ok = bool(
                    isinstance(approval_payload, dict)
                    and str(approval_payload.get("artifact_id", "")).strip()
                    and bool(approval_payload.get("approved", False))
                    and str(approval_payload.get("approver", "")).strip()
                    and str(approval_payload.get("stage", "")).strip()
                )
                approval_reason = "ok" if approval_artifact_ok else "approval_artifact_invalid"
            except Exception as exc:
                approval_reason = f"approval_artifact_parse_failed:{exc}"
        checks.append(
            {
                "name": "manual_live_dual_control",
                "ok": bool(live_go and confirmation_path.exists() and approval_artifact_ok),
                "reason": "ok" if bool(live_go and confirmation_path.exists() and approval_artifact_ok) else "manual_live_dual_control_not_satisfied",
                "details": {
                    "live_go": bool(live_go),
                    "confirmation_file_exists": confirmation_path.exists(),
                    "approval_file_exists": approval_path.exists(),
                    "approval_artifact_ok": approval_artifact_ok,
                    "approval_reason": approval_reason,
                    "approval_file": str(approval_path),
                },
            }
        )

    ok = all(bool(item.get("ok")) for item in checks)
    failed_checks = [str(item.get("name", "")) for item in checks if not bool(item.get("ok"))]
    rollback_reason_codes: list[str] = []
    if args.target_mode != "paper":
        rollback_reason_codes.append("target_mode_not_paper_dry_run")
    if failed_checks:
        rollback_reason_codes.extend(f"check_failed:{name}" for name in failed_checks if name)
    rollback_validated = bool(args.target_mode == "paper" and ok)
    rollback_artifact_id = _stable_hash(
        {
            "type": "rollback_dry_run_preflight",
            "target_mode": args.target_mode,
            "config": str(config_path),
            "checks": [
                {
                    "name": str(item.get("name", "")),
                    "ok": bool(item.get("ok")),
                    "reason": str(item.get("reason", "")),
                }
                for item in checks
            ],
        }
    )
    payload = {
        "ok": ok,
        "target_mode": args.target_mode,
        "config": str(config_path),
        "checks": checks,
        "rollback_dry_run": {
            "validated": rollback_validated,
            "artifact_id": rollback_artifact_id,
            "reason_codes": rollback_reason_codes,
        },
    }
    text = json.dumps(payload, indent=2)
    print(text)
    if args.output:
        out_path = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
