#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "runs"
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from autonomous_investment_robot.config.settings import RobotSettings


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _discover_run_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    candidates = [RUNS / "kraken_spot_tiny_live", RUNS / "kraken_spot_readonly_analysis"]
    existing = [path for path in candidates if path.exists()]
    if existing:
        return max(existing, key=lambda path: path.stat().st_mtime)
    return RUNS / "missing"


def _value_from_env_or_secret(name: str, secrets_dir: Path) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    secret_path = secrets_dir / name
    if secret_path.exists():
        try:
            return secret_path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
    return ""


@contextmanager
def _temporary_config_parse_env() -> Any:
    names = (
        "KRAKEN_SPOT_API_KEY",
        "KRAKEN_SPOT_API_SECRET",
        "ENABLE_LIVE_TRADING",
        "ACK_I_UNDERSTAND_RISKS",
    )
    original = {name: os.environ.get(name) for name in names}
    os.environ.setdefault("KRAKEN_SPOT_API_KEY", "__promotion_dummy__")
    os.environ.setdefault("KRAKEN_SPOT_API_SECRET", "__promotion_dummy__")
    os.environ.setdefault("ENABLE_LIVE_TRADING", "true")
    os.environ.setdefault("ACK_I_UNDERSTAND_RISKS", "true")
    try:
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--secrets-dir", default=os.getenv("SECRETS_DIR", str(REPO / "secrets")))
    parser.add_argument("--config", default="config.kraken_spot.tiny_live.yaml")
    args = parser.parse_args()

    run_dir = _discover_run_dir(args.run_dir or None)
    secrets_dir = Path(args.secrets_dir)
    operator = _read(run_dir / "kraken_spot_operator_summary.json")
    readiness = _read(run_dir / "readiness_summary.json") or _read(run_dir / "tiny_live_readiness_report.json")
    safety = _read(run_dir / "live_safety_summary.json")
    rollback = _read(run_dir / "rollback_preflight_liveprofit_paper.json")
    config_truth = _read(run_dir / "config_truth_report.json")
    with _temporary_config_parse_env():
        settings = RobotSettings.from_file(str(REPO / args.config))
    envelope = settings.rollout_profile()

    api_key = _value_from_env_or_secret("KRAKEN_SPOT_API_KEY", secrets_dir)
    api_secret = _value_from_env_or_secret("KRAKEN_SPOT_API_SECRET", secrets_dir)
    enable_live = _value_from_env_or_secret("ENABLE_LIVE_TRADING", secrets_dir)
    ack_risk = _value_from_env_or_secret("ACK_I_UNDERSTAND_RISKS", secrets_dir)

    current_stage = operator.get("rollout_stage") or readiness.get("rollout_stage") or readiness.get("stage")
    checks = {
        "run_dir_exists": run_dir.exists(),
        "operator_summary_present": bool(operator),
        "readiness_present": bool(readiness),
        "live_safety_present": bool(safety),
        "rollback_preflight_present": bool(rollback),
        "config_truth_present": bool(config_truth),
        "tiny_live_config_present": (REPO / args.config).exists(),
        "current_mode_is_readonly_or_tiny": operator.get("mode") in {"live_readonly", "live"},
        "current_stage_is_shadow_or_tiny": current_stage in {"shadow", "tiny_live"},
        "kraken_spot_api_key_present": bool(api_key),
        "kraken_spot_api_secret_present": bool(api_secret),
        "enable_live_trading_true": enable_live == "true",
        "ack_i_understand_risks_true": ack_risk == "true",
        "readonly_preflight_ok": (operator.get("preflight") or {}).get("ok") is True or readiness.get("preflight_ok") is True,
        "readonly_ordering_blocked": operator.get("ordering_allowed") is False or safety.get("ordering_allowed") is False,
        "rollback_ready": rollback.get("rollback_ready") is True,
    }
    missing_live_prerequisites = [
        name
        for name in (
            "kraken_spot_api_key_present",
            "kraken_spot_api_secret_present",
            "enable_live_trading_true",
            "ack_i_understand_risks_true",
        )
        if not checks[name]
    ]
    ready = all(checks.values())
    payload = {
        "status": "ready" if ready else "blocked",
        "target_stage": "tiny_live",
        "run_dir": str(run_dir),
        "current_mode": operator.get("mode"),
        "current_rollout_stage": current_stage,
        "checks": checks,
        "missing_live_prerequisites": missing_live_prerequisites,
        "tiny_live_envelope": envelope,
        "config_hash": config_truth.get("config_hash"),
        "promotion_commands": [
            "printf '%s\\n' '<REAL_KRAKEN_SPOT_API_KEY>' > /opt/trading-bot/secrets/KRAKEN_SPOT_API_KEY",
            "printf '%s\\n' '<REAL_KRAKEN_SPOT_API_SECRET>' > /opt/trading-bot/secrets/KRAKEN_SPOT_API_SECRET",
            "cat > /opt/trading-bot/secrets/trading-engine.env <<'EOF'\nENABLE_LIVE_TRADING=true\nACK_I_UNDERSTAND_RISKS=true\nEOF",
            "cd /opt/trading-bot && docker compose up -d --no-deps --force-recreate trading-engine",
            "python3 /opt/trading-bot/core/scripts/tiny_live_promotion_readiness.py --run-dir /opt/trading-bot/core/runs/kraken_spot_tiny_live --secrets-dir /opt/trading-bot/secrets",
            "python3 /opt/trading-bot/core/scripts/runtime_healthcheck.py --run-dir /opt/trading-bot/core/runs/kraken_spot_tiny_live",
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
