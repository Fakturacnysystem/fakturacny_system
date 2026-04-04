from datetime import datetime, timezone

from autonomous_investment_robot.core.contracts import ExecutionQualityForecast, ProbabilityField, RegimeAssessment, ScenarioBranch, ScenarioTree, SignalInterferenceReport
from autonomous_investment_robot.services.alpha_service.service import AlphaService
from autonomous_investment_robot.services.calibration_service.service import CalibrationService
from autonomous_investment_robot.services.models.service import Forecast
from autonomous_investment_robot.services.quantum_state_service.collapse_policy import collapse_decision
from autonomous_investment_robot.services.quantum_state_service.state_transition_engine import scenario_drift_score
from autonomous_investment_robot.services.quantum_state_service.service import QuantumStateService


def _forecast(mu: float = 0.0003, confidence: float = 0.8) -> Forecast:
    return Forecast(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        mu=mu,
        sigma=0.001,
        confidence=confidence,
        model_version="test",
        regime="TREND",
        liquidity_regime="GOOD",
    )


def test_quantum_state_service_normalizes_branch_probabilities():
    fc = _forecast()
    features = {"ret_1": 0.0004, "ret_3": 0.0012, "realized_vol": 0.001, "flow_imbalance": 0.4, "spread_proxy": 0.0002, "liquidations": 1000.0}
    regime = RegimeAssessment(fc.symbol, fc.ts, "trend", 0.8, 0.7, 0.2, None, {"ret_3": 0.0012})
    eq = ExecutionQualityForecast(fc.symbol, fc.ts, 0.9, 120, 1.2, 0.1, True, {})
    alpha = AlphaService().evaluate(fc.symbol, fc.ts, features, fc, regime, eq)

    state = QuantumStateService().evaluate(
        symbol=fc.symbol,
        ts=fc.ts,
        features=features,
        forecast=fc,
        regime_assessment=regime,
        alpha_signals=alpha,
        execution_quality=eq,
    )

    total = sum(branch.probability for branch in state.scenario_tree.branches)
    assert round(total, 8) == 1.0
    assert state.collapse_context.no_trade_probability >= 0.0
    assert set(state.scenario_tree.probability_field.confidence_decomposition) == {
        "signal",
        "regime",
        "execution",
        "market_quality",
        "portfolio",
    }
    assert "ultra_short" in state.scenario_tree.probability_field.horizons
    assert "short" in state.scenario_tree.probability_field.horizons
    assert "tactical" in state.scenario_tree.probability_field.horizons
    assert state.collapse_context.top_states


def test_quantum_state_service_degrades_to_no_trade_under_high_fragility_and_conflict():
    fc = _forecast(mu=0.0, confidence=0.45)
    features = {"ret_1": 0.0, "ret_3": 0.0, "realized_vol": 0.003, "flow_imbalance": 0.0, "spread_proxy": 0.003, "liquidations": 200000.0}
    regime = RegimeAssessment(fc.symbol, fc.ts, "news_chaos", 0.4, 0.3, 0.8, "panic_mode", {"ret_3": 0.0})
    eq = ExecutionQualityForecast(fc.symbol, fc.ts, 0.1, 2500, 18.0, 0.95, False, {})
    alpha = AlphaService().evaluate(fc.symbol, fc.ts, features, fc, regime, eq)

    state = QuantumStateService().evaluate(
        symbol=fc.symbol,
        ts=fc.ts,
        features=features,
        forecast=fc,
        regime_assessment=regime,
        alpha_signals=alpha,
        execution_quality=eq,
    )

    assert state.collapse_decision.recommended_action == "no_trade"
    assert state.collapse_decision.no_trade_probability >= 0.55
    assert state.collapse_decision.branch_disagreement_score >= 0.0


def test_quantum_state_service_applies_calibration_bias():
    calibration = CalibrationService()
    calibration.update_from_episodes(
        [
            type("Episode", (), {"realized_pnl": -5.0, "failure_mode": "truth"}),
            type("Episode", (), {"realized_pnl": -2.0, "failure_mode": "execution"}),
        ]
    )
    fc = _forecast(mu=0.0001, confidence=0.55)
    features = {"ret_1": 0.0001, "ret_3": 0.0002, "realized_vol": 0.002, "flow_imbalance": 0.1, "spread_proxy": 0.001, "liquidations": 50000.0}
    regime = RegimeAssessment(fc.symbol, fc.ts, "range", 0.55, 0.5, 0.5, None, {})
    eq = ExecutionQualityForecast(fc.symbol, fc.ts, 0.4, 900, 6.0, 0.5, True, {})
    alpha = AlphaService().evaluate(fc.symbol, fc.ts, features, fc, regime, eq)

    state = QuantumStateService(calibration_service=calibration).evaluate(
        symbol=fc.symbol,
        ts=fc.ts,
        features=features,
        forecast=fc,
        regime_assessment=regime,
        alpha_signals=alpha,
        execution_quality=eq,
    )

    assert state.collapse_decision.metadata["calibrated"] is True
    assert state.collapse_decision.no_trade_probability >= 0.0


def test_scenario_drift_aligns_range_and_dead_market_with_mean_reversion_family():
    fc = _forecast()
    features = {"ret_1": 0.0004, "ret_3": 0.0012, "realized_vol": 0.001, "flow_imbalance": 0.4, "spread_proxy": 0.0002, "liquidations": 1000.0}
    regime = RegimeAssessment(fc.symbol, fc.ts, "mean_reversion", 0.8, 0.7, 0.2, None, {"ret_3": 0.0012})
    eq = ExecutionQualityForecast(fc.symbol, fc.ts, 0.9, 120, 1.2, 0.1, True, {})
    alpha = AlphaService().evaluate(fc.symbol, fc.ts, features, fc, regime, eq)
    state = QuantumStateService().evaluate(
        symbol=fc.symbol,
        ts=fc.ts,
        features=features,
        forecast=fc,
        regime_assessment=regime,
        alpha_signals=alpha,
        execution_quality=eq,
    )

    drift_range = scenario_drift_score(regime_label="range", branches=state.scenario_tree.branches)
    drift_dead = scenario_drift_score(regime_label="dead_market", branches=state.scenario_tree.branches)

    assert drift_range < 1.0
    assert drift_dead < 1.0


def test_quantum_state_service_does_not_promote_panic_flush_from_forecast_sign_alone_in_mean_reversion_regime():
    fc = _forecast(mu=-0.1460335228218255, confidence=0.825)
    features = {
        "ret_1": -0.0003117342841968407,
        "ret_3": 0.0,
        "realized_vol": 0.00015589144045172922,
        "flow_imbalance": 0.15,
        "spread_proxy": 0.00003694685933222246,
        "liquidations": 0.0,
        "history_points": 3.0,
    }
    regime = RegimeAssessment(fc.symbol, fc.ts, "mean_reversion", 0.65, 0.39, 0.05, "insufficient_history_for_dead_market_label", {"ret_3": 0.0})
    eq = ExecutionQualityForecast(fc.symbol, fc.ts, 0.98, 250, 0.1847, 0.0074, True, {})
    alpha = AlphaService().evaluate(fc.symbol, fc.ts, features, fc, regime, eq)

    state = QuantumStateService().evaluate(
        symbol=fc.symbol,
        ts=fc.ts,
        features=features,
        forecast=fc,
        regime_assessment=regime,
        alpha_signals=alpha,
        execution_quality=eq,
    )

    assert state.scenario_tree.dominant_state != "panic_flush"
    assert state.collapse_decision.scenario_drift_score < 0.8


def test_collapse_policy_keeps_ambiguity_bounded_without_double_counting_into_no_trade():
    ts = datetime.now(timezone.utc)
    tree = ScenarioTree(
        symbol="BTCUSDT",
        ts=ts,
        branches=[
            ScenarioBranch("short", "bullish_continuation", 0.45, 14.0, 5.0, 10.0, 0.18),
            ScenarioBranch("short", "mean_reversion_bounce", 0.35, 8.0, 7.0, 7.0, 0.16),
            ScenarioBranch("short", "low_vol_range", 0.20, 2.0, 8.0, 3.0, 0.22),
        ],
        transitions=[],
        probability_field=ProbabilityField(
            symbol="BTCUSDT",
            ts=ts,
            horizons={"short": {"bullish_continuation": 0.45, "mean_reversion_bounce": 0.35, "low_vol_range": 0.20}},
            entropy=1.45,
            no_trade_probability=0.23,
            execution_fragility_score=0.18,
            confidence_decomposition={"signal": 0.72, "regime": 0.66, "execution": 0.78, "market_quality": 0.71, "portfolio": 0.74},
            branch_disagreement_score=0.58,
            scenario_drift_score=0.52,
        ),
        dominant_state="bullish_continuation",
        metadata={"top_states": {"primary": "bullish_continuation"}},
    )
    interference = SignalInterferenceReport(
        symbol="BTCUSDT",
        ts=ts,
        reinforcement_score=0.62,
        conflict_score=0.28,
        net_score=0.34,
        uncertainty_penalty=0.32,
    )

    ctx, decision = collapse_decision(symbol="BTCUSDT", ts=ts, scenario_tree=tree, interference=interference)

    assert decision.recommended_action != "no_trade"
    assert decision.uncertainty < 1.0
    assert decision.no_trade_probability < 0.40
    assert set(ctx.uncertainty_decomposition) >= {
        "epistemic_uncertainty",
        "policy_disagreement",
        "execution_fragility",
        "observability_uncertainty",
        "negative_evidence_mass",
    }
