from autonomous_investment_robot.config.settings import RiskLimits
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


def _risk() -> RiskEngineService:
    return RiskEngineService(
        limits=RiskLimits(
            max_daily_loss_pct=5.0,
            max_drawdown_pct=10.0,
            max_position_notional=1000.0,
            max_exposure_notional=5000.0,
            max_orders_per_min=1,
            leverage=0,
            max_spread_bps=20.0,
            min_depth_notional=100.0,
            stale_data_seconds=60.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=3.0,
            max_liquidation_spike=100000.0,
            divergence_threshold_bps=30.0,
            crowding_score_kill=25.0,
        ),
        safe_mode=False,
    )


def test_stale_data_kill_switch_and_flatten():
    r = _risk()
    d = r.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}), 0.0, 0.0, 0.0,
        data_lag_seconds=120.0, spread_bps=1.0, depth_notional=1000.0,
        reconciliation_ok=True, funding_paid_pct=0.0, oi_spike_pct=0.0,
        liquidation_spike=0.0, divergence_bps=0.0, margin_buffer=3.0,
    )
    assert d.allowed is False
    assert d.flatten is True
    assert r.state.kill_switch is True


def test_max_orders_per_min_enforced():
    r = _risk()
    d1 = r.evaluate(OrderIntent("BTCUSDT", "buy", 100.0, {}), 0.0, 0.0, 0.0, 0, 1.0, 1000.0, True, 0.0, 0.0, 0.0, 0.0, 3.0)
    d2 = r.evaluate(OrderIntent("BTCUSDT", "buy", 100.0, {}), 0.0, 0.0, 0.0, 0, 1.0, 1000.0, True, 0.0, 0.0, 0.0, 0.0, 3.0)
    assert d1.allowed is True
    assert d2.allowed is False
