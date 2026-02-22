from dataclasses import replace
from datetime import datetime, timezone

from autonomous_investment_robot.config.settings import AllocatorSettings, PolicySettings, RegimeSettings, TCOSettings
from autonomous_investment_robot.services.models.service import Forecast
from autonomous_investment_robot.services.policy.regime import detect_regime_state
from autonomous_investment_robot.services.policy.service import PolicyService
from autonomous_investment_robot.services.policy.strategy_plugins import StrategySignal


def _forecast() -> Forecast:
    return Forecast(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        mu=0.0002,
        sigma=0.001,
        confidence=0.8,
        model_version="t",
        regime="RANGE",
        liquidity_regime="GOOD",
    )


def _policy(tco: TCOSettings) -> PolicyService:
    svc = PolicyService(PolicySettings(confidence_threshold=0.5, base_risk_budget=100.0), AllocatorSettings(), tco)
    svc.evaluate_strategies = lambda features, forecast: [  # type: ignore[method-assign]
        StrategySignal(
            name="unit",
            target_notional=50.0,
            confidence=0.9,
            estimated_cost_bps=1.0,
            expected_edge_bps=12.0,
            why={"source": "test"},
        )
    ]
    return svc


def test_regime_thresholds_are_config_driven_and_deterministic():
    features = {
        "realized_vol": 0.01,
        "ret_3": 0.003,
        "spread_proxy": 0.005,
        "funding_rate": 0.0001,
        "liquidations": 1000.0,
    }
    base = detect_regime_state(features, RegimeSettings())
    tighter = detect_regime_state(features, RegimeSettings(trend_ret3_abs=0.002))
    assert base.market == "RANGE"
    assert tighter.market == "TREND"
    assert tighter == detect_regime_state(features, RegimeSettings(trend_ret3_abs=0.002))


def test_tco_impact_cap_veto_counts():
    policy = _policy(TCOSettings(max_total_cost_bps=100.0, max_impact_bps=1.0))
    features = {"depth_notional": 1000.0, "funding_rate": 0.0, "spread_proxy": 0.0001}
    intent = policy.make_intent(_forecast(), features, fee_bps=1.0, slippage_bps=1.0)
    assert intent is None
    assert policy.last_veto_counts.get("impact_cap") == 1


def test_policy_uses_strategy_edge_and_emits_why_fields():
    policy = _policy(TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0))
    fc = _forecast()
    fc = replace(fc, mu=0.0001)
    features = {"depth_notional": 10_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0}
    intent = policy.make_intent(fc, features, fee_bps=1.0, slippage_bps=0.1)
    assert intent is not None
    comp = intent.why["components"][0]
    assert comp["strategy_edge_bps_used"] == 12.0
    assert comp["fc_mu_used"] > 0.0
    assert comp["final_edge_bps"] >= comp["strategy_edge_bps_used"] * 0.5

