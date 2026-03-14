from __future__ import annotations

from autonomous_investment_robot.services.autonomous_decision.engine import (
    AutonomousMarketPredictionAndDecisionEngine,
    DecisionContext,
)
from autonomous_investment_robot.services.reliability.runtime_cache import SignalCache


def _context() -> DecisionContext:
    return DecisionContext(
        symbol="XBTUSD",
        now_ts=1_700_000_000.0,
        bid=100.0,
        ask=100.2,
        mid=100.1,
        spread_bps=20.0,
        depth_notional=1500.0,
        features={
            "ret_1": 0.003,
            "ret_3": 0.008,
            "realized_vol": 0.0035,
            "spread_proxy": 0.0007,
            "depth_notional": 1500.0,
            "orderbook_imbalance": 0.25,
            "flow_imbalance": 0.2,
        },
        market_watch={
            "trend_30s_bps": 8.0,
            "trend_2m_bps": 42.0,
            "trend_10m_bps": 86.0,
            "realized_vol_2m": 0.003,
            "realized_vol_10m": 0.004,
            "confidence": 0.7,
        },
        forecast_mu=10.0,
        forecast_sigma=6.0,
        forecast_confidence=0.75,
        position_notional_quote=0.0,
        signed_exposure_notional_quote=0.0,
        avg_entry_price=0.0,
        position_age_s=0.0,
        current_profit_bps=0.0,
        drawdown_pct=0.3,
        quote_free=300.0,
        max_exposure_notional=2000.0,
        order_cadence_s=5.0,
        last_submission_ts=1_699_999_000.0,
        fee_bps=25.0,
        slippage_bps=1.5,
        latency_ms=45.0,
        guards_mode="strict",
        modeled_cost_floor_bps=120.0,
        sell_min_profit_bps=120.0,
        sell_target_profit_bps=200.0,
    )


def test_signal_cache_basic_set_get() -> None:
    cache = SignalCache(ttl_s=1.0, max_items=8)
    cache.set("k1", {"action": "hold", "confidence": 0.5})
    got = cache.get("k1")
    assert got is not None
    assert str(got.get("action")) == "hold"
    stats = cache.stats().to_dict()
    assert int(stats["hits"]) >= 1


def test_decision_engine_exposes_cache_diagnostics() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.45,
        uncertainty_threshold_bps=140.0,
        feature_cache_ttl_s=3.0,
        signal_cache_ttl_s=3.0,
    )
    out = engine.run_decision_algorithm(_context())
    assert "feature_cache_hit" in out.diagnostics
    assert "signal_cache_hit" in out.diagnostics
    assert "feature_cache_stats" in out.diagnostics
    assert "signal_cache_stats" in out.diagnostics
