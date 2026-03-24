from datetime import datetime, timezone

from autonomous_investment_robot.config.settings import RegimeSettings
from autonomous_investment_robot.services.alpha_service.service import AlphaService
from autonomous_investment_robot.services.execution.service import Fill
from autonomous_investment_robot.services.models.service import Forecast
from autonomous_investment_robot.services.portfolio_service.service import PortfolioService
from autonomous_investment_robot.services.regime_service.service import RegimeService


def test_regime_service_detects_dead_market_and_trend():
    svc = RegimeService(RegimeSettings())
    ts = datetime.now(timezone.utc)
    dead = svc.assess("BTCUSDT", ts, {"realized_vol": 0.001, "ret_3": 0.0002, "spread_proxy": 0.001, "liquidations": 0.0})
    trend = svc.assess("BTCUSDT", ts, {"realized_vol": 0.01, "ret_3": 0.01, "spread_proxy": 0.001, "liquidations": 0.0})
    assert dead.label == "dead_market"
    assert trend.label in {"trend", "high_vol_expansion"}


def test_alpha_service_emits_required_experts():
    ts = datetime.now(timezone.utc)
    forecast = Forecast("BTCUSDT", ts, 0.0003, 0.001, 0.8, "test", "TREND", "GOOD")
    regime = RegimeService().assess("BTCUSDT", ts, {"realized_vol": 0.01, "ret_3": 0.01, "spread_proxy": 0.001, "flow_imbalance": 0.2, "depth_notional": 100000.0}, forecast)
    signals = AlphaService().evaluate(
        "BTCUSDT",
        ts,
        {"ret_1": 0.001, "ret_3": 0.01, "realized_vol": 0.01, "spread_proxy": 0.001, "flow_imbalance": 0.2, "depth_notional": 100000.0, "liquidations": 0.0},
        forecast,
        regime,
    )
    names = {signal.expert_name for signal in signals}
    assert "trend_expert" in names
    assert "execution_quality_forecaster" in names
    assert "failure_risk_forecaster" in names


def test_portfolio_service_records_ledger_and_snapshot():
    svc = PortfolioService()
    fill = Fill("paper", "ord-1", "fill-1", "BTCUSDT", "buy", 50.0, 0.5, 0.2, 100, "filled_maker")
    state = svc.record_fill(fill, realized_pnl=3.5)
    assert state.exposure_notional == 50.0
    assert state.realized_pnl == 3.5
    assert state.cumulative_fees == 0.5
    assert len(svc.ledger_rows()) == 1


def test_portfolio_allocator_derisks_under_drawdown_and_uncertainty():
    svc = PortfolioService()
    ts = datetime.now(timezone.utc)
    alloc = svc.recommend_allocation(
        symbol="BTCUSDT",
        ts=ts,
        base_budget=1000.0,
        expected_edge_bps=8.0,
        confidence=0.6,
        uncertainty=0.7,
        realized_vol=0.02,
        depth_notional=5000.0,
        current_exposure=900.0,
        drawdown_pct=-8.0,
        regime_fit=0.5,
    )
    assert alloc.recommended_notional < 1000.0
    assert alloc.opportunity_cost_score > 0.0
