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


def test_market_neutral_plugins_present_and_directional_is_small_budget():
    policy = _policy(TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0))
    names = [s.name for s in policy.strategies]
    assert "delta_neutral_carry" in names
    assert "basis" in names
    assert "pairs_stat_arb" in names
    trend = next(s for s in policy.strategies if s.name == "trend")
    sig = trend.signal({"ret_3": 0.01}, regime="RANGE", liq_regime="GOOD")
    assert sig.why.get("directional_throttled") is True


def test_policy_weights_by_net_after_costs_per_regime():
    policy = _policy(TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0))
    policy.evaluate_strategies = lambda features, forecast: [  # type: ignore[method-assign]
        StrategySignal("delta_neutral_carry", 100.0, 0.9, 1.0, 20.0, {"market_neutral": True}),
        StrategySignal("trend", 100.0, 0.9, 1.0, 12.0, {"market_neutral": False}),
    ]
    intent = policy.make_intent(_forecast(), {"depth_notional": 10_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0}, fee_bps=1.0, slippage_bps=0.1)
    assert intent is not None
    by_name = {c["strategy"]: c for c in intent.why["components"]}
    assert by_name["delta_neutral_carry"]["weight"] > by_name["trend"]["weight"]
    assert "weights_net_after_costs" in intent.why


def test_strategy_regime_cooldown_after_repeated_veto():
    policy = _policy(TCOSettings(max_total_cost_bps=1.0, max_impact_bps=100.0))
    policy.evaluate_strategies = lambda features, forecast: [  # type: ignore[method-assign]
        StrategySignal("pairs_stat_arb", 100.0, 0.9, 1.0, 50.0, {"market_neutral": True}),
    ]
    features = {"depth_notional": 10_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.01}
    fc = _forecast()
    for _ in range(3):
        out = policy.make_intent(fc, features, fee_bps=1.0, slippage_bps=1.0)
        assert out is None
    assert policy.strategy_regime_cooldowns.get(("pairs_stat_arb", fc.regime), 0) > 0


def test_meta_gating_blocks_mean_reversion_in_trend():
    class _Stub:
        def __init__(self, name: str):
            self.name = name

        def signal(self, features, regime, liq_regime):  # noqa: ARG002
            return StrategySignal(self.name, 50.0, 0.9, 1.0, 12.0, {"source": "stub"})

    policy = PolicyService(PolicySettings(confidence_threshold=0.5, base_risk_budget=100.0), AllocatorSettings(), TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0))
    policy.strategies = [_Stub("mean_reversion"), _Stub("trend")]
    fc = _forecast()
    fc = replace(fc, regime="TREND", liquidity_regime="GOOD")
    intent = policy.make_intent(fc, {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0}, fee_bps=1.0, slippage_bps=0.1)
    assert intent is not None
    names = [c["strategy"] for c in intent.why["components"]]
    assert names == ["trend"]
    assert any(g["strategy"] == "mean_reversion" and g["reason"] == "meta_gate_regime" for g in intent.why["meta_gates"])


def test_meta_gating_blocks_directional_strategies_in_thin_liquidity():
    class _Stub:
        name = "trend"

        def signal(self, features, regime, liq_regime):  # noqa: ARG002
            return StrategySignal(self.name, 50.0, 0.9, 1.0, 12.0, {"source": "stub"})

    policy = PolicyService(PolicySettings(confidence_threshold=0.5, base_risk_budget=100.0), AllocatorSettings(), TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0))
    policy.strategies = [_Stub()]
    fc = _forecast()
    fc = replace(fc, regime="TREND", liquidity_regime="THIN")
    intent = policy.make_intent(fc, {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0}, fee_bps=1.0, slippage_bps=0.1)
    assert intent is None
    assert policy.last_veto_counts.get("meta_gate_liquidity") == 1


def test_strategy_auto_disable_on_degradation():
    class _Stub:
        name = "pairs_stat_arb"

        def signal(self, features, regime, liq_regime):  # noqa: ARG002
            return StrategySignal(self.name, 50.0, 0.9, 1.0, 12.0, {"source": "stub"})

    policy = PolicyService(
        PolicySettings(confidence_threshold=0.5, base_risk_budget=100.0),
        AllocatorSettings(),
        TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0),
    )
    policy.strategies = [_Stub()]
    for _ in range(15):
        policy.update_allocator({"pairs_stat_arb": -3.5})
    fc = _forecast()
    intent = policy.make_intent(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        fee_bps=1.0,
        slippage_bps=0.1,
    )
    assert intent is None
    assert policy.last_veto_counts.get("meta_gate_degraded", 0) >= 1


def test_dynamic_edge_floor_blocks_weak_net_edge(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_MIN_NET_EDGE_BPS", "8.0")
    policy = _policy(TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0))
    policy.evaluate_strategies = lambda features, forecast: [  # type: ignore[method-assign]
        StrategySignal(
            name="unit",
            target_notional=50.0,
            confidence=0.9,
            estimated_cost_bps=1.0,
            expected_edge_bps=6.0,
            why={"source": "test"},
        )
    ]
    fc = _forecast()
    intent = policy.make_intent(fc, {"depth_notional": 10_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0002, "realized_vol": 0.0003}, fee_bps=1.0, slippage_bps=0.1)
    assert intent is None
    assert policy.last_veto_counts.get("dynamic_edge_floor", 0) >= 1


def test_max_order_notional_quote_caps_target(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE", "7.5")
    monkeypatch.setenv("AUTONOMOUS_STRATEGY_PROPOSAL_ADAPTER_ENABLED", "1")
    policy = _policy(TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0))
    fc = _forecast()
    intent = policy.make_intent(fc, {"depth_notional": 10_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0}, fee_bps=1.0, slippage_bps=0.1)
    assert intent is not None
    assert intent.target_notional == 7.5
    assert intent.why.get("max_order_notional_quote_cap") == 7.5
    proposals = intent.why.get("strategy_proposals", [])
    assert isinstance(proposals, list)
    assert proposals
    assert proposals[0]["target_notional_quote"] <= 7.5
    assert proposals[0]["source"] == "legacy_policy_adapter"


def test_policy_strategy_proposal_serialization_is_deterministic(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_STRATEGY_PROPOSAL_ADAPTER_ENABLED", "1")
    policy = _policy(TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0))
    fc = _forecast()
    features = {"depth_notional": 10_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0}
    intent_a = policy.make_intent(fc, features, fee_bps=1.0, slippage_bps=0.1)
    intent_b = policy.make_intent(fc, features, fee_bps=1.0, slippage_bps=0.1)
    assert intent_a is not None
    assert intent_b is not None
    proposals_a = intent_a.why.get("strategy_proposals", [])
    proposals_b = intent_b.why.get("strategy_proposals", [])
    assert proposals_a == proposals_b
    assert intent_a.why.get("strategy_proposals_contract_version") == "v1"
    assert proposals_a[0]["strategy"] == "unit"
    assert sum(float(row["target_notional_quote"]) for row in proposals_a) <= intent_a.target_notional + 1e-9


def test_policy_strategy_proposal_adapter_is_default_off_for_replay_stability():
    policy = _policy(TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0))
    fc = _forecast()
    intent = policy.make_intent(fc, {"depth_notional": 10_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0}, fee_bps=1.0, slippage_bps=0.1)
    assert intent is not None
    assert "strategy_proposals" not in intent.why


def test_max_order_cap_below_min_floor_skips_intent(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE", "5.0")
    monkeypatch.setenv("AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE", "6.0")
    policy = _policy(TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0))
    fc = _forecast()
    intent = policy.make_intent(fc, {"depth_notional": 10_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0}, fee_bps=1.0, slippage_bps=0.1)
    assert intent is None
    assert policy.last_no_intent_debug.get("reason") == "min_order_floor_skip"
    assert policy.last_no_intent_debug.get("max_order_cap") == 5.0
