import pytest

from autonomous_investment_robot.config.settings import RiskLimits, RobotSettings


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
    )


def test_live_mode_rejected_without_double_unlock():
    with pytest.raises(ValueError):
        RobotSettings(trading_mode="live", explicit_live_enable=True, ack_live_risks=False, canary_mode=True, risk=_complete_limits())


def test_live_mode_rejected_without_limits_even_if_unlocked():
    with pytest.raises(ValueError):
        RobotSettings(trading_mode="live", explicit_live_enable=True, ack_live_risks=True, canary_mode=True)


def test_live_mode_rejected_without_canary():
    with pytest.raises(ValueError):
        RobotSettings(trading_mode="live", explicit_live_enable=True, ack_live_risks=True, canary_mode=False, risk=_complete_limits())


def test_live_mode_can_initialize_only_with_limits_and_double_unlock():
    s = RobotSettings(trading_mode="live", explicit_live_enable=True, ack_live_risks=True, canary_mode=True, risk=_complete_limits())
    assert s.trading_mode.value == "live"
