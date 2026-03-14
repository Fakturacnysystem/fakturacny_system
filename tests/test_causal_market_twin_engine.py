from __future__ import annotations

from autonomous_investment_robot.services.autonomous_decision.causal_market_twin import (
    CausalMarketTwinEngine,
    build_market_twin_state,
    choose_best_counterfactual_action,
    estimate_causal_drivers,
    generate_counterfactual_scenarios,
    persist_market_twin_snapshot,
)
from autonomous_investment_robot.services.autonomous_decision.engine import (
    AutonomousMarketPredictionAndDecisionEngine,
    DecisionContext,
)


def _base_state() -> dict[str, float | str]:
    return {
        "regime": "BULL_TREND",
        "state": "risk_on",
        "trend_bps": 48.0,
        "vol": 0.006,
        "spread_bps": 12.0,
        "liquidity_state": "deep",
    }


def _base_context() -> DecisionContext:
    return DecisionContext(
        symbol="XBTUSD",
        now_ts=1_700_000_000.0,
        bid=100.0,
        ask=100.2,
        mid=100.1,
        spread_bps=20.0,
        depth_notional=3000.0,
        features={
            "ret_1": 0.004,
            "ret_3": 0.010,
            "realized_vol": 0.004,
            "spread_proxy": 0.0008,
            "depth_notional": 3000.0,
            "orderbook_imbalance": 0.30,
            "flow_imbalance": 0.35,
            "portfolio_corr_proxy": 0.25,
        },
        market_watch={
            "trend_2m_bps": 55.0,
            "confidence": 0.8,
        },
        forecast_mu=12.0,
        forecast_sigma=8.0,
        forecast_confidence=0.80,
        position_notional_quote=0.0,
        signed_exposure_notional_quote=0.0,
        avg_entry_price=0.0,
        position_age_s=0.0,
        current_profit_bps=0.0,
        drawdown_pct=0.5,
        quote_free=250.0,
        max_exposure_notional=2500.0,
        order_cadence_s=9.0,
        last_submission_ts=1_699_999_000.0,
        fee_bps=25.0,
        slippage_bps=1.5,
        latency_ms=40.0,
        market_class="crypto_spot",
        market_session="always_open_24_7",
        guards_mode="strict",
        modeled_cost_floor_bps=120.0,
        sell_min_profit_bps=120.0,
        sell_target_profit_bps=200.0,
    )


def test_market_twin_state_and_causal_drivers() -> None:
    state = build_market_twin_state(
        symbol="XBTUSD",
        market_class="crypto_spot",
        regime="BULL_TREND",
        market_state=_base_state(),
        nowcast={"order_flow_pressure": 0.4, "execution_urgency": 0.6, "market_state_confidence": 0.7},
        fused_features={"ret_1": 0.002, "ret_3": 0.004, "multimodal_score": 0.3, "multimodal_quality": 0.7},
        confidence=0.66,
        uncertainty_bps=72.0,
        liquidity_pressure=0.35,
    )
    drivers = estimate_causal_drivers(state)
    assert state["market_class"] == "crypto_spot"
    assert len(drivers) >= 3
    assert "driver" in drivers[0]
    assert "score" in drivers[0]


def test_counterfactual_generation_contains_required_entry_choices() -> None:
    scenarios = generate_counterfactual_scenarios(
        market_state={
            **_base_state(),
            "order_flow_pressure": 0.3,
            "liquidity_pressure": 0.2,
            "uncertainty_bps": 80.0,
        },
        projected_edge_bps=15.0,
        fee_bps=25.0,
        slippage_bps=1.5,
        spread_bps=12.0,
        depth_notional=2500.0,
        liquidity_pressure=0.2,
        latency_risk=0.2,
        signal_age_s=8.0,
        cadence_s=9.0,
        market_class="crypto_spot",
        has_position=False,
        current_profit_bps=0.0,
        include_advanced=True,
    )
    scenario_ids = {scenario.scenario_id for scenario in scenarios}
    assert "entry_now_market" in scenario_ids
    assert "entry_now_limit" in scenario_ids
    assert "wait_one_cadence" in scenario_ids
    assert "skip" in scenario_ids


def test_counterfactual_action_prefers_skip_when_edge_too_low() -> None:
    scenarios = generate_counterfactual_scenarios(
        market_state={
            **_base_state(),
            "order_flow_pressure": -0.1,
            "liquidity_pressure": -0.4,
            "uncertainty_bps": 140.0,
        },
        projected_edge_bps=0.5,
        fee_bps=25.0,
        slippage_bps=2.0,
        spread_bps=35.0,
        depth_notional=350.0,
        liquidity_pressure=-0.4,
        latency_risk=0.4,
        signal_age_s=60.0,
        cadence_s=9.0,
        market_class="xstock",
        has_position=False,
        current_profit_bps=0.0,
        include_advanced=True,
    )
    best = choose_best_counterfactual_action(scenarios=scenarios, min_counterfactual_edge_bps=2.0)
    assert best.action in {"skip", "wait_one_cadence"}


def test_market_twin_snapshot_persistence_is_bounded() -> None:
    engine = CausalMarketTwinEngine(max_snapshots=5)
    model_state: dict[str, object] = {}
    for idx in range(9):
        snapshot = engine.evaluate(
            timestamp=1_700_000_000.0 + idx,
            symbol="XBTUSD",
            market_class="crypto_spot",
            regime="BULL_TREND",
            market_state=_base_state(),
            nowcast={"order_flow_pressure": 0.2, "execution_urgency": 0.4, "market_state_confidence": 0.7},
            fused_features={"ret_1": 0.001, "ret_3": 0.004, "multimodal_score": 0.2, "multimodal_quality": 0.6},
            confidence=0.62,
            uncertainty_bps=78.0,
            liquidity_pressure=0.2,
            projected_edge_bps=14.0,
            fee_bps=25.0,
            slippage_bps=1.4,
            spread_bps=12.0,
            depth_notional=2200.0,
            latency_risk=0.2,
            signal_age_s=4.0,
            cadence_s=9.0,
            has_position=False,
            current_profit_bps=0.0,
        )
        model_state = persist_market_twin_snapshot(model_state=model_state, snapshot=snapshot, max_snapshots=5)
    history = model_state.get("market_twin_snapshots", [])
    assert isinstance(history, list)
    assert len(history) == 5


def test_decision_engine_integration_has_market_twin_diagnostics() -> None:
    engine = AutonomousMarketPredictionAndDecisionEngine(
        confidence_threshold=0.45,
        uncertainty_threshold_bps=120.0,
        counterfactual_min_edge_bps=1.0,
    )
    out = engine.run_decision_algorithm(_base_context())
    market_twin = out.diagnostics.get("market_twin", {})
    assert isinstance(market_twin, dict)
    assert "best_action" in market_twin
    assert int(market_twin.get("scenario_count", 0)) >= 4
