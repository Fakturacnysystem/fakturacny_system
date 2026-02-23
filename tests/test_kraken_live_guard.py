import json

import pytest

from autonomous_investment_robot.config.settings import RobotSettings


def test_live_guard_fail_closed_missing_creds(tmp_path, monkeypatch):
    monkeypatch.delenv("KRAKEN_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_API_SECRET", raising=False)
    cfg = {
        "mode": "live",
        "enable_live_trading": True,
        "ack_i_understand_risks": True,
        "provider_whitelist": ["kraken_spot"],
        "canary_mode": True,
        "execution": {"mode": "live", "kraken_spot": {"allow_unknown_permissions": True}},
        "risk": {
            "max_daily_loss_pct": 1.0, "max_drawdown_pct": 2.0, "max_position_notional": 1.0, "max_exposure_notional": 1.0,
            "max_orders_per_min": 1, "leverage": 0, "max_spread_bps": 1.0, "min_depth_notional": 0.0, "stale_data_seconds": 1.0,
            "min_margin_buffer": 1.0, "max_funding_cost_per_day": 0.0, "max_oi_spike_pct": 0.0, "max_liquidation_spike": 0.0,
            "divergence_threshold_bps": 1.0, "crowding_score_kill": 1.0
        },
        "tco": {"max_total_cost_bps": 1.0, "max_impact_bps": 1.0}
    }
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(ValueError) as e:
        RobotSettings.from_file(str(p))
    assert "kraken_spot_api_credentials" in str(e.value)
