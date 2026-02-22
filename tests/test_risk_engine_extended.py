from autonomous_investment_robot.config.settings import RiskLimits
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


def _risk() -> RiskEngineService:
    return RiskEngineService(
        limits=RiskLimits(
            max_daily_loss_pct=5.0,
            max_weekly_loss_pct=10.0,
            max_drawdown_pct=10.0,
            max_position_notional=1000.0,
            max_exposure_notional=5000.0,
            max_symbol_exposure_notional=2000.0,
            max_cluster_exposure_notional=3000.0,
            max_orders_per_min=1,
            leverage=0,
            stress_loss_limit_pct=5.0,
            max_spread_bps=20.0,
            min_depth_notional=100.0,
            stale_data_seconds=60.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=3.0,
            max_liquidation_spike=100000.0,
            divergence_threshold_bps=30.0,
            crowding_score_kill=25.0,
            crowding_score_medium=8.0,
            crowding_score_high=14.0,
            crowding_score_extreme=16.0,
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


def test_weekly_loss_triggers_stop_and_safe_mode():
    r = _risk()
    d = r.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}),
        0.0,
        0.0,
        0.0,
        data_lag_seconds=0.0,
        spread_bps=1.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.0,
        oi_spike_pct=0.0,
        liquidation_spike=0.0,
        divergence_bps=0.0,
        margin_buffer=3.0,
        weekly_loss_pct=-12.0,
    )
    assert d.allowed is False
    assert d.reason == "weekly_loss_stop"
    assert d.flatten is True
    assert r.state.weekly_stop is True
    assert r.state.safe_mode is True


def test_regime_thin_blocks_opens_but_reduce_only_can_pass():
    r = _risk()
    d_block = r.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}),
        0.0,
        0.0,
        0.0,
        data_lag_seconds=0.0,
        spread_bps=1.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.0,
        oi_spike_pct=0.0,
        liquidation_spike=0.0,
        divergence_bps=0.0,
        margin_buffer=3.0,
        market_regime="RANGE",
        liquidity_regime="THIN",
        is_reduce_only=False,
    )
    assert d_block.allowed is False
    assert d_block.reason == "regime_open_block_reduce_only"

    r.reset_periodic_limits()
    d_ro = r.evaluate(
        OrderIntent("BTCUSDT", "sell", 100.0, {}),
        0.0,
        0.0,
        0.0,
        data_lag_seconds=0.0,
        spread_bps=1.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.0,
        oi_spike_pct=0.0,
        liquidation_spike=0.0,
        divergence_bps=0.0,
        margin_buffer=3.0,
        market_regime="RANGE",
        liquidity_regime="THIN",
        is_reduce_only=True,
    )
    assert d_ro.allowed is True


def test_symbol_and_cluster_exposure_caps_enforced():
    r = _risk()
    d = r.evaluate(
        OrderIntent("BTCUSDT", "buy", 500.0, {}),
        500.0,
        0.0,
        0.0,
        data_lag_seconds=0.0,
        spread_bps=1.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.0,
        oi_spike_pct=0.0,
        liquidation_spike=0.0,
        divergence_bps=0.0,
        margin_buffer=3.0,
        symbol_exposure=1800.0,
        cluster_exposure=2800.0,
    )
    assert d.allowed is False
    assert d.reason in {"symbol_exposure_notional_exceeded", "cluster_exposure_notional_exceeded"}


def test_stress_guard_blocks_before_order():
    r = _risk()
    d = r.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}),
        4500.0,
        0.0,
        0.0,
        data_lag_seconds=0.0,
        spread_bps=40.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.0,
        oi_spike_pct=20.0,
        liquidation_spike=0.0,
        divergence_bps=0.0,
        margin_buffer=3.0,
    )
    assert d.allowed is False
    assert d.reason == "spread_explosion_kill" or d.reason == "stress_guard"


def test_drawdown_safe_mode_recovers_after_cooldown_and_stability():
    r = _risk()
    r.limits.drawdown_cooldown_steps = 2
    r.limits.drawdown_recovery_stable_steps = 2
    d = r.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}),
        0.0,
        -11.0,
        0.0,
        data_lag_seconds=0.0,
        spread_bps=1.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.0,
        oi_spike_pct=0.0,
        liquidation_spike=0.0,
        divergence_bps=0.0,
        margin_buffer=3.0,
    )
    assert d.allowed is False
    assert d.reason == "drawdown_safe_mode"
    assert r.state.safe_mode is True
    assert r.state.kill_switch is False

    r.record_return(0.1)
    r.record_return(0.1)
    b1 = r.evaluate(OrderIntent("BTCUSDT", "buy", 100.0, {}), 0.0, -1.0, 0.0, 0.0, 1.0, 1000.0, True, 0.0, 0.0, 0.0, 0.0, 3.0)
    b2 = r.evaluate(OrderIntent("BTCUSDT", "buy", 100.0, {}), 0.0, -1.0, 0.0, 0.0, 1.0, 1000.0, True, 0.0, 0.0, 0.0, 0.0, 3.0)
    b3 = r.evaluate(OrderIntent("BTCUSDT", "buy", 100.0, {}), 0.0, -1.0, 0.0, 0.0, 1.0, 1000.0, True, 0.0, 0.0, 0.0, 0.0, 3.0)
    assert b1.allowed is False
    assert b2.allowed is False
    assert b3.allowed is True


def test_crowding_medium_throttles_size_and_emits_details():
    r = _risk()
    d = r.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}),
        0.0,
        0.0,
        0.0,
        data_lag_seconds=0.0,
        spread_bps=15.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.2,
        oi_spike_pct=2.0,
        liquidation_spike=20000.0,
        divergence_bps=5.0,
        margin_buffer=3.0,
        funding_rate_abs=0.012,
    )
    assert d.allowed is True
    assert d.adjusted_notional < 100.0
    assert d.details["crowding_level"] in {"medium", "high"}
    assert d.details["crowding_score"] > 0.0
    assert "crowding_components" in d.details


def test_crowding_high_blocks_opens_reduce_only():
    r = _risk()
    d = r.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}),
        0.0,
        0.0,
        0.0,
        data_lag_seconds=0.0,
        spread_bps=18.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.2,
        oi_spike_pct=3.0,
        liquidation_spike=90000.0,
        divergence_bps=20.0,
        margin_buffer=3.0,
        funding_rate_abs=0.02,
    )
    assert d.allowed is False
    assert d.reason in {"crowding_high_block_open_reduce_only", "crowding_radar_kill"}


def test_crowding_extreme_kills_and_flattens():
    r = _risk()
    d = r.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}),
        0.0,
        0.0,
        0.0,
        data_lag_seconds=0.0,
        spread_bps=20.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.5,
        oi_spike_pct=3.0,
        liquidation_spike=100000.0,
        divergence_bps=30.0,
        margin_buffer=3.0,
        funding_rate_abs=0.02,
    )
    assert d.allowed is False
    assert d.reason == "crowding_radar_kill"
    assert d.flatten is True
    assert r.state.kill_switch is True
    assert r.state.safe_mode is True


def test_funding_budget_thresholds_throttle_then_block():
    r = _risk()
    d1 = r.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}),
        0.0,
        0.0,
        0.0,
        data_lag_seconds=0.0,
        spread_bps=1.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.7,
        oi_spike_pct=0.0,
        liquidation_spike=0.0,
        divergence_bps=0.0,
        margin_buffer=3.0,
    )
    assert d1.allowed is True
    assert d1.adjusted_notional < 100.0
    assert d1.details["funding_budget_utilization"] >= 0.6

    r.reset_periodic_limits()
    d2 = r.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}),
        0.0,
        0.0,
        0.0,
        data_lag_seconds=0.0,
        spread_bps=1.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.9,
        oi_spike_pct=0.0,
        liquidation_spike=0.0,
        divergence_bps=0.0,
        margin_buffer=3.0,
    )
    assert d2.allowed is False
    assert d2.reason == "funding_budget_throttle_block_open"
