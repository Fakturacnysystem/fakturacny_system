from autonomous_investment_robot.config.settings import RiskLimits
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


def test_reconciliation_mismatch_triggers_integrity_kill():
    risk = RiskEngineService(
        limits=RiskLimits(
            max_daily_loss_pct=5.0,
            max_drawdown_pct=10.0,
            max_position_notional=1000.0,
            max_exposure_notional=2000.0,
            max_orders_per_min=10,
            leverage=0,
        ),
        safe_mode=False,
    )
    decision = risk.evaluate(
        intent=OrderIntent(symbol="BTCUSDT", side="buy", target_notional=100.0, why={}),
        current_exposure=0.0,
        drawdown_pct=0.0,
        daily_loss_pct=0.0,
        data_stale=False,
        reconciliation_ok=False,
    )
    assert decision.allowed is False
    assert risk.state.kill_switch is True
