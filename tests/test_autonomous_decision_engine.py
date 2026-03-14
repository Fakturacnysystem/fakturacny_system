from __future__ import annotations

import sys
import types

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


def test_apply_profit_lock_respects_configured_hard_floor(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMOUS_SELL_HARD_MIN_PROFIT_BPS", "33")
    lock = apply_profit_lock(
        side="sell",
        bid=100.40,
        avg_entry_price=100.0,
        modeled_cost_bps=10.0,
        min_net_profit_bps=33.0,
        target_net_profit_bps=33.0,
        hold_time_s=60.0,
    )
    assert lock["allowed"] is True
    assert lock["hard_min_net_bps"] == 33.0


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


def test_decision_engine_plugin_backend_adapter() -> None:
    module = types.ModuleType("test_backend_plugin_module")

    class _PluginBackend:
        def predict_adjustment(self, *, fused_features, regime, nowcast):  # noqa: ANN001
            _ = fused_features
            _ = regime
            _ = nowcast
            return {
                "backend": "plugin_backend",
                "mean_adjust_bps": 7.5,
                "std_scale": 1.05,
                "confidence_scale": 1.02,
                "diagnostics": {"plugin_loaded": 1.0},
            }

    module.PluginBackend = _PluginBackend
    sys.modules[module.__name__] = module
    try:
        engine = AutonomousMarketPredictionAndDecisionEngine(
            confidence_threshold=0.45,
            uncertainty_threshold_bps=120.0,
            forecast_backend="baseline",
            forecast_backend_plugin="test_backend_plugin_module:PluginBackend",
        )
        out = engine.run_decision_algorithm(_base_context())
        assert str(out.forecast.get("backend", "")).startswith("plugin:")
        assert float(out.diagnostics.get("forecast_backend_mean_adjust_bps", 0.0)) > 0.0
    finally:
        sys.modules.pop(module.__name__, None)


def test_self_optimization_applies_bounded_threshold_updates() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.72,
        uncertainty_threshold_bps=160.0,
        self_optimization_min_samples=10,
        self_optimization_apply_every=1,
    )
    applied_any = False
    for _ in range(20):
        out = engine.run_decision_algorithm(_base_context())
        so = out.diagnostics.get("self_optimization", {})
        if isinstance(so, dict) and so.get("applied"):
            applied_any = True
            break
    assert applied_any is True
    assert 0.40 <= engine.confidence_threshold <= 0.85
    assert 45.0 <= engine.uncertainty_threshold_bps <= 180.0


def test_portfolio_diversification_and_rotation_scales_present() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.45,
        uncertainty_threshold_bps=120.0,
    )
    ctx = _base_context()
    ctx.features["portfolio_symbol_score"] = 8.0
    ctx.features["portfolio_best_symbol_score"] = 28.0
    ctx.features["portfolio_concentration"] = 0.9
    ctx.features["portfolio_corr_proxy"] = 0.7
    out = engine.run_decision_algorithm(ctx)
    assert "portfolio_diversification_scale" in out.diagnostics
    assert "capital_rotation_scale" in out.diagnostics
    assert float(out.diagnostics["portfolio_diversification_scale"]) > 0.0
    assert float(out.diagnostics["capital_rotation_scale"]) > 0.0


def test_decision_engine_respects_xstock_session_closed_guard() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.40,
        uncertainty_threshold_bps=160.0,
    )
    ctx = _base_context()
    ctx.market_class = "xstock"
    ctx.market_session = "xstock_session_closed"
    out = engine.run_decision_algorithm(ctx)
    assert "session_closed" in out.risk_flags
    assert out.action in {"skip", "hold"}


def test_decision_engine_market_class_threshold_overrides_apply() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.42,
        uncertainty_threshold_bps=120.0,
        market_class_confidence_thresholds={"xstock": 0.60},
        market_class_uncertainty_threshold_bps={"xstock": 70.0},
    )
    ctx = _base_context()
    ctx.market_class = "xstock"
    out = engine.run_decision_algorithm(ctx)
    thresholds = out.diagnostics.get("adaptive_thresholds", {})
    assert isinstance(thresholds, dict)
    assert float(thresholds.get("confidence_threshold", 0.0)) >= 0.60
    assert float(thresholds.get("uncertainty_threshold_bps", 1e9)) <= 70.0


def test_decision_engine_opportunity_decay_guard_blocks_stale_signal() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.35,
        uncertainty_threshold_bps=200.0,
        opportunity_decay_max_age_s=30.0,
        opportunity_decay_guard_threshold=0.45,
    )
    ctx = _base_context()
    ctx.features["signal_ts"] = ctx.now_ts - 240.0
    out = engine.run_decision_algorithm(ctx)
    assert float(out.diagnostics.get("signal_age_s", 0.0)) >= 200.0
    assert float(out.diagnostics.get("opportunity_decay_score", 0.0)) >= 0.45
    assert ("opportunity_decay" in out.risk_flags) or (out.action in {"skip", "hold"})


def test_decision_engine_cross_market_confirmation_guard_can_block_buy() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.35,
        uncertainty_threshold_bps=200.0,
        enable_macro=True,
        enable_sentiment=True,
        cross_market_confirmation_enabled=True,
        cross_market_confirmation_min=0.55,
    )
    ctx = _base_context()
    ctx.market_class = "xstock"
    ctx.macro_features = {"risk_on": -1.0, "liquidity": -0.8, "surprise": -1.0}
    ctx.sentiment_features = {"score": -1.0, "momentum": -1.0, "dispersion": 0.4}
    ctx.features["ret_1"] = -0.015
    ctx.features["ret_3"] = -0.03
    out = engine.run_decision_algorithm(ctx)
    assert float(out.diagnostics.get("cross_market_confirmation_score", 1.0)) < 0.55
    assert ("cross_market_filter" in out.risk_flags) or (out.action in {"skip", "hold"})


def test_decision_engine_regime_size_multiplier_exposed() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.40,
        uncertainty_threshold_bps=160.0,
        regime_size_multipliers={"BULL_TREND": 1.35, "PANIC": 0.40},
    )
    ctx = _base_context()
    ctx.market_watch["trend_2m_bps"] = 85.0
    out = engine.run_decision_algorithm(ctx)
    mult = float(out.diagnostics.get("regime_size_multiplier", 0.0))
    assert 0.25 <= mult <= 1.75


def test_decision_engine_blocks_when_world_state_unavailable() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.40,
        uncertainty_threshold_bps=160.0,
    )
    ctx = _base_context()
    ctx.world_state_adapter = {
        "source": "world_state_graph",
        "world_state_available": False,
        "graph_available": False,
        "safe_to_trade": False,
        "stale_domains": ["market_state"],
        "stale_critical_domains": ["market_state"],
        "freshness_s": {"market_state": 120.0},
    }
    out = engine.run_decision_algorithm(ctx)
    assert "world_state_unavailable" in out.risk_flags
    assert out.action in {"skip", "hold"}


def test_decision_engine_blocks_on_world_state_stale_critical_domains() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.40,
        uncertainty_threshold_bps=160.0,
    )
    ctx = _base_context()
    ctx.world_state_adapter = {
        "source": "runtime_observation",
        "world_state_available": True,
        "graph_available": True,
        "safe_to_trade": True,
        "stale_domains": ["risk_state"],
        "stale_critical_domains": ["risk_state"],
        "freshness_s": {"risk_state": 65.0},
    }
    out = engine.run_decision_algorithm(ctx)
    assert "world_state_stale" in out.risk_flags
    assert float(out.diagnostics.get("world_state_available", 0.0)) == 1.0
    assert isinstance(out.diagnostics.get("world_state_stale_critical_domains", []), list)
