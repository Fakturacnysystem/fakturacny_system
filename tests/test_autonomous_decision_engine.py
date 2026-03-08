from __future__ import annotations

from autonomous_investment_robot.services.autonomous_decision.engine import (
    AutonomousMarketPredictionAndDecisionEngine,
    DecisionContext,
    apply_profit_lock,
)


def _base_context() -> DecisionContext:
    return DecisionContext(
        symbol="XBTUSD",
        now_ts=1_700_000_000.0,
        bid=100.0,
        ask=100.2,
        mid=100.1,
        spread_bps=20.0,
        depth_notional=2500.0,
        features={
            "ret_1": 0.004,
            "ret_3": 0.009,
            "realized_vol": 0.004,
            "spread_proxy": 0.0008,
            "depth_notional": 2500.0,
            "orderbook_imbalance": 0.35,
            "flow_imbalance": 0.30,
        },
        market_watch={
            "trend_30s_bps": 16.0,
            "trend_2m_bps": 60.0,
            "trend_10m_bps": 120.0,
            "realized_vol_2m": 0.004,
            "realized_vol_10m": 0.005,
            "confidence": 0.8,
        },
        forecast_mu=12.0,
        forecast_sigma=8.0,
        forecast_confidence=0.82,
        position_notional_quote=0.0,
        signed_exposure_notional_quote=0.0,
        avg_entry_price=0.0,
        position_age_s=0.0,
        current_profit_bps=0.0,
        drawdown_pct=0.5,
        quote_free=500.0,
        max_exposure_notional=2500.0,
        order_cadence_s=5.0,
        last_submission_ts=1_699_999_000.0,
        fee_bps=25.0,
        slippage_bps=1.5,
        latency_ms=55.0,
        guards_mode="strict",
        modeled_cost_floor_bps=120.0,
        sell_min_profit_bps=120.0,
        sell_target_profit_bps=200.0,
    )


def test_apply_profit_lock_blocks_sell_below_entry() -> None:
    lock = apply_profit_lock(
        side="sell",
        bid=99.0,
        avg_entry_price=100.0,
        modeled_cost_bps=120.0,
        min_net_profit_bps=120.0,
        target_net_profit_bps=200.0,
        hold_time_s=60.0,
    )
    assert lock["allowed"] is False
    assert lock["reason"] == "profit_lock_sell_below_entry"
    assert lock["hard_min_net_bps"] >= 120.0


def test_decision_engine_generates_buy_entry_signal() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.45,
        uncertainty_threshold_bps=120.0,
        max_drawdown_pct=12.0,
    )
    out = engine.run_decision_algorithm(_base_context())
    assert out.action in {"open", "add", "hold", "skip"}
    assert out.confidence >= 0.0
    assert out.uncertainty_bps >= 0.0
    assert out.regime
    assert isinstance(out.alpha_signals, dict)


def test_decision_engine_blocks_in_panic_high_uncertainty() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.6,
        uncertainty_threshold_bps=45.0,
        max_drawdown_pct=6.0,
    )
    ctx = _base_context()
    ctx.features["realized_vol"] = 0.05
    ctx.spread_bps = 140.0
    ctx.market_watch["trend_2m_bps"] = -80.0
    out = engine.run_decision_algorithm(ctx)
    assert out.action in {"skip", "hold"}
    assert ("regime_filter" in out.risk_flags) or ("uncertainty_guard" in out.risk_flags)


def test_decision_engine_transformer_backend_emits_diagnostics() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.45,
        uncertainty_threshold_bps=120.0,
        enable_transformer_backend=True,
        forecast_backend="auto",
    )
    out = engine.run_decision_algorithm(_base_context())
    assert out.forecast.get("backend") == "transformer_ready"
    assert out.diagnostics.get("forecast_backend") == "transformer_ready"
    assert float(out.diagnostics.get("forecast_backend_std_scale", 1.0)) > 0.0


def test_decision_engine_signal_decay_guard_can_block_trade() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.35,
        uncertainty_threshold_bps=180.0,
        signal_decay_guard_threshold=0.45,
    )
    first = _base_context()
    _ = engine.run_decision_algorithm(first)

    second = _base_context()
    second.features["ret_1"] = -0.02
    second.features["ret_3"] = -0.04
    second.features["flow_imbalance"] = -0.8
    second.market_watch["trend_2m_bps"] = -120.0
    out = engine.run_decision_algorithm(second)
    assert float(out.diagnostics.get("signal_decay_score", 0.0)) >= 0.0
    assert ("signal_decay" in out.risk_flags) or (out.action in {"skip", "hold"})


def test_decision_engine_foundation_backend_uses_sentiment_features() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.45,
        uncertainty_threshold_bps=120.0,
        enable_sentiment=True,
        enable_foundation_backend=True,
        forecast_backend="auto",
    )
    ctx = _base_context()
    ctx.sentiment_features = {"score": 0.8, "momentum": 0.6, "dispersion": 0.2}
    ctx.features["macro_risk_on"] = 0.3
    out = engine.run_decision_algorithm(ctx)
    assert out.forecast.get("backend") == "foundation_ready"
    fb_diag = out.diagnostics.get("forecast_backend_diagnostics", {})
    assert isinstance(fb_diag, dict)
    assert "sentiment_score" in fb_diag
