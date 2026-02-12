import pytest

from autonomous_investment_robot.config.settings import RobotSettings


def test_live_mode_rejected_without_limits():
    with pytest.raises(ValueError):
        RobotSettings(trading_mode="live", explicit_live_enable=True)
