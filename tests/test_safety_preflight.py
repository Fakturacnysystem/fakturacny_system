from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_safety_preflight_paper_passes() -> None:
    cmd = [
        "python3",
        "scripts/safety_preflight.py",
        "--config",
        "config.paper.yaml",
        "--target-mode",
        "paper",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert bool(payload.get("ok")) is True
    checks = {str(row.get("name")): row for row in payload.get("checks", [])}
    assert checks["settings_validation"]["ok"] is True
    rollback = payload.get("rollback_dry_run", {})
    assert bool(rollback.get("validated")) is True
    assert str(rollback.get("artifact_id", ""))


def test_safety_preflight_live_requires_manual_gate(tmp_path: Path) -> None:
    cfg = {
        "mode": "live",
        "enable_live_trading": True,
        "ack_i_understand_risks": True,
        "canary_mode": True,
        "provider_whitelist": ["binance_um_perps"],
        "execution": {"mode": "live_testnet"},
        "safety": {
            "live_unlock": {
                "enable_live_trading": True,
                "ack_i_understand_risks": True,
                "require_testnet_passed": False,
                "canary_required_before_full": False,
                "require_operator_confirmation_artifact": True,
            }
        },
        "risk": {
            "max_daily_loss_pct": 5.0,
            "max_drawdown_pct": 10.0,
            "max_position_notional": 1000.0,
            "max_exposure_notional": 2000.0,
            "max_orders_per_min": 10,
            "leverage": 0,
            "max_spread_bps": 20.0,
            "min_depth_notional": 100.0,
            "stale_data_seconds": 60.0,
            "min_margin_buffer": 2.0,
            "max_funding_cost_per_day": 1.0,
            "max_oi_spike_pct": 3.0,
            "max_liquidation_spike": 100000.0,
            "divergence_threshold_bps": 30.0,
            "crowding_score_kill": 25.0,
        },
        "tco": {"max_total_cost_bps": 10.0, "max_impact_bps": 10.0},
    }
    cfg_path = tmp_path / "live_cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    env = dict(os.environ)
    env["EXCHANGE_API_KEY"] = "k"
    env["EXCHANGE_API_SECRET"] = "s"
    env.pop("AUTONOMOUS_LIVE_GO", None)
    env.pop("AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE", None)

    cmd = [
        "python3",
        "scripts/safety_preflight.py",
        "--config",
        str(cfg_path),
        "--target-mode",
        "live",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, check=False, capture_output=True, text=True)
    assert proc.returncode == 2, proc.stdout
    payload = json.loads(proc.stdout)
    checks = {str(row.get("name")): row for row in payload.get("checks", [])}
    assert checks["manual_live_gate"]["ok"] is False
    assert checks["manual_live_gate"]["reason"] == "manual_live_gate_not_satisfied"
    assert checks["manual_live_dual_control"]["ok"] is False
    assert checks["manual_live_dual_control"]["reason"] == "manual_live_dual_control_not_satisfied"
    rollback = payload.get("rollback_dry_run", {})
    assert bool(rollback.get("validated")) is False
    reasons = [str(item) for item in rollback.get("reason_codes", [])]
    assert "target_mode_not_paper_dry_run" in reasons
