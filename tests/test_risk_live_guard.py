import pytest

from autonomous_investment_robot.config.settings import RiskLimits, RobotSettings


def test_live_mode_rejected_without_double_unlock():
    with pytest.raises(ValueError):
        RobotSettings(trading_mode="live", explicit_live_enable=True, ack_live_risks=False)


def test_live_mode_rejected_without_limits_even_if_unlocked():
    with pytest.raises(ValueError):
        RobotSettings(trading_mode="live", explicit_live_enable=True, ack_live_risks=True)


def test_live_mode_can_initialize_only_with_limits_and_double_unlock():
    s = RobotSettings(
        trading_mode="live",
        explicit_live_enable=True,
        ack_live_risks=True,
        risk=RiskLimits(
            max_daily_loss_pct=5.0,
            max_drawdown_pct=10.0,
            max_position_notional=1000.0,
            max_exposure_notional=2000.0,
            max_orders_per_min=10,
            leverage=0,
        ),
    )
    assert s.trading_mode.value == "live"
