import pytest

from autonomous_investment_robot.config.settings import ExecutionSettings, LiveUnlockSettings, RiskLimits, RobotSettings, SafetySettings, TCOSettings


def _complete_limits() -> RiskLimits:
    return RiskLimits(
        max_daily_loss_pct=5.0,
        max_drawdown_pct=10.0,
        max_position_notional=1000.0,
        max_exposure_notional=2000.0,
        max_orders_per_min=10,
        leverage=0,
        target_portfolio_vol=0.2,
        cvar_limit_pct=4.0,
        max_spread_bps=20.0,
        min_depth_notional=100.0,
        stale_data_seconds=60.0,
        min_margin_buffer=2.0,
        max_funding_cost_per_day=1.0,
        max_oi_spike_pct=3.0,
        max_liquidation_spike=100000.0,
        divergence_threshold_bps=30.0,
        crowding_score_kill=25.0,
    )


def test_live_mode_rejected_without_double_unlock():
    with pytest.raises(ValueError):
        RobotSettings(
            execution=ExecutionSettings(mode="live_testnet"),
            provider_whitelist=["binance_um_perps"],
            safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=False, require_testnet_passed=False)),
            risk=_complete_limits(),
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        )


def test_live_mode_rejected_without_limits_even_if_unlocked():
    with pytest.raises(ValueError):
        RobotSettings(
            execution=ExecutionSettings(mode="live_testnet"),
            provider_whitelist=["binance_um_perps"],
            safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        )


def test_live_mode_rejected_without_canary():
    with pytest.raises(ValueError):
        RobotSettings(
            execution=ExecutionSettings(mode="live"),
            provider_whitelist=["binance_um_perps"],
            safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False, canary_required_before_full=True)),
            canary_mode=False,
            risk=_complete_limits(),
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        )


def test_live_mode_can_initialize_only_with_limits_and_double_unlock(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    s = RobotSettings(
        execution=ExecutionSettings(mode="live_testnet"),
        provider_whitelist=["binance_um_perps"],
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        canary_mode=True,
        risk=_complete_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    assert s.execution.mode == "live_testnet"
