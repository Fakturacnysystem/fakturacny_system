from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from autonomous_investment_robot.core.contracts import EdgeImmunityDecision, PortfolioAllocation, RegimeAssessment
from autonomous_investment_robot.services.calibration_service.service import CalibrationService
from autonomous_investment_robot.services.edge_immunity_service.service import EdgeImmunityService
from autonomous_investment_robot.services.edge_immunity_service.wait_dominance_engine import evaluate_wait_dominance
from autonomous_investment_robot.services.models.service import Forecast


def _forecast(mu: float = 0.0003) -> Forecast:
    return Forecast(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        mu=mu,
        sigma=0.001,
        confidence=0.8,
        model_version="test",
        regime="TREND",
        liquidity_regime="GOOD",
    )


def test_edge_immunity_service_returns_trade_smaller_for_fragile_edge():
    fc = _forecast(mu=0.0002)
    decision = EdgeImmunityService().evaluate(
        symbol=fc.symbol,
        ts=fc.ts,
        features={"spread_proxy": 0.0008, "depth_notional": 20000.0},
        forecast=fc,
        regime_assessment=RegimeAssessment(fc.symbol, fc.ts, "trend", 0.8, 0.7, 0.2, None, {}),
        execution_quality=SimpleNamespace(fill_probability=0.45),
        portfolio_allocation=PortfolioAllocation(fc.symbol, fc.ts, 500.0, 0.1, 0.1, 0.9, 0.5, 1.0, 1.0, 0.9, 0.9, {}),
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(expected_move_bps=8.0, execution_fragility_score=0.55)),
    )

    assert isinstance(decision, EdgeImmunityDecision)
    assert decision.action in {"trade_smaller", "wait", "no_trade"}
    assert decision.report.fragility_index >= 0.0
    assert decision.report.metadata["worlds"]


def test_edge_immunity_service_can_recommend_wait_when_wait_value_dominates():
    fc = _forecast(mu=0.0001)
    decision = EdgeImmunityService().evaluate(
        symbol=fc.symbol,
        ts=fc.ts,
        features={"spread_proxy": 0.0015, "depth_notional": 15000.0},
        forecast=fc,
        regime_assessment=RegimeAssessment(fc.symbol, fc.ts, "liquidity_vacuum", 0.6, 0.4, 0.6, "panic", {}),
        execution_quality=SimpleNamespace(fill_probability=0.3),
        portfolio_allocation=PortfolioAllocation(fc.symbol, fc.ts, 800.0, 0.1, 0.1, 0.8, 0.4, 1.0, 0.7, 0.7, 0.7, {}),
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(expected_move_bps=5.0, execution_fragility_score=0.7)),
    )

    assert decision.action in {"wait", "no_trade"}
    assert decision.report.recommended_execution_style == "passive_limit"
    assert any(world["name"] == "wait_improves_entry" for world in decision.report.metadata["worlds"])


def test_edge_immunity_service_applies_calibration_bias():
    calibration = CalibrationService()
    calibration.update_from_episodes(
        [
            type("Episode", (), {"realized_pnl": -3.0, "failure_mode": "execution"}),
            type("Episode", (), {"realized_pnl": -4.0, "failure_mode": "execution_truth"}),
        ]
    )
    fc = _forecast(mu=0.00025)
    decision = EdgeImmunityService(calibration_service=calibration).evaluate(
        symbol=fc.symbol,
        ts=fc.ts,
        features={"spread_proxy": 0.001, "depth_notional": 9000.0},
        forecast=fc,
        regime_assessment=RegimeAssessment(fc.symbol, fc.ts, "trend", 0.7, 0.6, 0.3, None, {}),
        execution_quality=SimpleNamespace(fill_probability=0.5),
        portfolio_allocation=PortfolioAllocation(fc.symbol, fc.ts, 700.0, 0.1, 0.1, 0.9, 0.6, 1.0, 0.8, 0.8, 0.8, {}),
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(expected_move_bps=7.0, execution_fragility_score=0.4, reasons=[])),
    )

    assert decision.report.metadata["calibrated"] is True
    assert decision.report.recommended_size_multiplier <= 1.0


def test_wait_dominance_reports_incremental_advantage_without_relabeling_full_wait_score():
    report = evaluate_wait_dominance(
        base_edge_bps=1377.6780060189583,
        stressed_edge_bps=1227.7610086858338,
        wait_bonus_bps=0.1,
        fragility_index=0.16380359855140555,
    )

    assert report.wait_dominant is True
    assert report.wait_value_score == pytest.approx(0.1)
    assert report.trade_now_score == pytest.approx(1002.0923936548035)
    assert float(report.metadata["wait_score_bps"]) == pytest.approx(1227.8610086858337)
    assert float(report.metadata["incremental_advantage_bps"]) == pytest.approx(225.76861503103017)


def test_edge_immunity_service_keeps_wait_value_incremental_for_high_edge_benign_trade():
    fc = _forecast(mu=0.13776780060189583)
    decision = EdgeImmunityService().evaluate(
        symbol=fc.symbol,
        ts=fc.ts,
        features={"spread_proxy": 0.0000014791881918073513, "depth_notional": 625295.2810000002},
        forecast=fc,
        regime_assessment=RegimeAssessment(fc.symbol, fc.ts, "dead_market", 0.65, 0.49, 0.05, None, {}),
        execution_quality=SimpleNamespace(fill_probability=0.98),
        portfolio_allocation=PortfolioAllocation(fc.symbol, fc.ts, 4.401247288979623, 0.0, 0.0875, 1.0, 0.825, 1.0, 1.0, 0.3233, 1.0, {}),
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(expected_move_bps=1293.6837000537507, execution_fragility_score=0.16380359855140555, reasons=[])),
    )

    assert decision.action == "trade_now"
    assert decision.report.wait_value_score == pytest.approx(0.1)
    wait_meta = decision.report.metadata["wait_dominance"]["metadata"]
    assert float(wait_meta["incremental_advantage_bps"]) > 200.0
