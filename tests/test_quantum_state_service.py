from datetime import datetime, timezone

from autonomous_investment_robot.core.contracts import ExecutionQualityForecast, RegimeAssessment
from autonomous_investment_robot.services.alpha_service.service import AlphaService
from autonomous_investment_robot.services.calibration_service.service import CalibrationService
from autonomous_investment_robot.services.models.service import Forecast
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
