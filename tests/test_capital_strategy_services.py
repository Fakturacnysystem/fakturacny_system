from datetime import datetime, timezone
from types import SimpleNamespace

from autonomous_investment_robot.services.adaptive_exit_allocator.service import AdaptiveExitAllocator
from autonomous_investment_robot.services.capital_sovereignty_service.service import CapitalSovereigntyService
from autonomous_investment_robot.services.position_morphing_service.service import PositionMorphingEngine
from autonomous_investment_robot.services.synthetic_affect_service.service import SyntheticAffectEngine


def test_capital_sovereignty_releases_stale_inventory_under_reserve_breach():
    decision = CapitalSovereigntyService().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        reserve_state=SimpleNamespace(free_quote_reserve_pct=0.1, reserve_breached=True),
        inventory_state=SimpleNamespace(stale_inventory_score=0.7, gross_open_notional=200.0),
        portfolio_allocation=SimpleNamespace(opportunity_cost_score=0.5),
        round_trip={"action": "trade_now", "net_edge_bps": 16.0},
        event_intelligence=SimpleNamespace(overall_risk_score=0.2, recommended_action="continue"),
        synthetic_affect=SimpleNamespace(stress=0.4, fear=0.3, aggression_clamp=0.7),
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(uncertainty=0.3)),
        edge_immunity_decision=SimpleNamespace(report=SimpleNamespace(fragility_index=0.2)),
    )

    assert decision.action == "release"
    assert decision.release_notional > 0.0
    assert "reserve_breach" in decision.reasons


def test_position_morphing_allows_runner_in_bullish_continuation():
    plan = PositionMorphingEngine().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        current_exposure=100.0,
        capital_sovereignty=SimpleNamespace(action="continue", keep_core_ratio=0.7, satellite_ratio=0.3),
        synthetic_affect=SimpleNamespace(stress=0.1, conviction=0.8, fear=0.1),
        quantum_state=SimpleNamespace(scenario_tree=SimpleNamespace(dominant_state="bullish_continuation")),
        edge_immunity_decision=SimpleNamespace(report=SimpleNamespace(fragility_index=0.2)),
    )

    assert plan.allow_runner is True
    assert plan.runner_fraction > 0.0
    assert "runner_allowed" in plan.reasons


def test_adaptive_exit_allocator_prioritizes_risk_exit_when_event_turns_hostile():
    allocation = AdaptiveExitAllocator().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        current_exposure=120.0,
        capital_release_decision=SimpleNamespace(allowed=False, recommended_notional=0.0, reason=""),
        position_morph_plan=SimpleNamespace(reduce_notional=10.0, runner_fraction=0.1),
        synthetic_affect=SimpleNamespace(stress=0.2, fear=0.2),
        event_intelligence=SimpleNamespace(recommended_action="no_trade", overall_risk_score=0.9),
    )

    assert allocation.action == "risk_exit"
    assert allocation.total_exit_notional > 0.0
    assert allocation.execution_style == "marketable_limit"


def test_adaptive_exit_allocator_preserves_runner_bias_for_reacceleration_hold():
    allocation = AdaptiveExitAllocator().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        current_exposure=120.0,
        capital_release_decision=SimpleNamespace(
            allowed=True,
            recommended_notional=24.0,
            reason="profit_lock_partial_exit",
            metadata={"exit_path_comparison": {"selected_family": "reacceleration_hold"}},
        ),
        position_morph_plan=SimpleNamespace(reduce_notional=10.0, runner_fraction=0.2),
        synthetic_affect=SimpleNamespace(stress=0.1, fear=0.1),
        event_intelligence=SimpleNamespace(recommended_action="continue", overall_risk_score=0.1),
    )

    assert allocation.action in {"hold", "partial_exit"}
    assert allocation.execution_style == "passive_limit"
    assert allocation.metadata["selected_exit_family"] == "reacceleration_hold"


def test_synthetic_affect_shifts_to_no_trade_under_stress():
    affect = SyntheticAffectEngine().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        forecast=SimpleNamespace(confidence=0.3),
        regime_assessment=SimpleNamespace(confidence=0.2),
        execution_quality=SimpleNamespace(fill_probability=0.1, adverse_selection_risk=0.8),
        inventory_state=SimpleNamespace(stale_inventory_score=0.9),
        reserve_state=SimpleNamespace(reserve_breached=True),
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(uncertainty=0.8)),
        edge_immunity_decision=SimpleNamespace(report=SimpleNamespace(fragility_index=0.9)),
        event_intelligence=SimpleNamespace(overall_risk_score=0.9),
    )

    assert affect.recommended_action == "no_trade"
    assert affect.aggression_clamp == 0.0
    assert affect.stress >= 0.8 or affect.fear >= 0.8
