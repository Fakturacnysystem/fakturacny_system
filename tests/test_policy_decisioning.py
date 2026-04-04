from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from autonomous_investment_robot.config.settings import AllocatorSettings, PolicySettings, TCOSettings
from autonomous_investment_robot.core.contracts import ExecutionQualityForecast, PortfolioAllocation, RegimeAssessment
from autonomous_investment_robot.services.models.service import Forecast
from autonomous_investment_robot.services.policy.service import PolicyService
from autonomous_investment_robot.services.policy.strategy_plugins import StrategySignal


def _forecast(confidence: float = 0.8) -> Forecast:
    return Forecast(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        mu=0.0002,
        sigma=0.001,
        confidence=confidence,
        model_version="test",
        regime="RANGE",
        liquidity_regime="GOOD",
    )


def _policy() -> PolicyService:
    svc = PolicyService(
        PolicySettings(confidence_threshold=0.55, base_risk_budget=100.0),
        AllocatorSettings(),
        TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0),
    )
    svc.evaluate_strategies = lambda features, forecast: [  # type: ignore[method-assign]
        StrategySignal(
            name="unit",
            target_notional=50.0,
            confidence=0.9,
            estimated_cost_bps=1.0,
            expected_edge_bps=15.0,
            why={"source": "test"},
        )
    ]
    return svc


def _kraken_spot_policy() -> PolicyService:
    return PolicyService(
        PolicySettings(confidence_threshold=0.55, base_risk_budget=100.0),
        AllocatorSettings(),
        TCOSettings(max_total_cost_bps=100.0, max_impact_bps=100.0),
        long_only=True,
        target_provider="kraken_spot",
        product_target="spot",
    )


def test_evaluate_decision_emits_no_trade_reason_for_low_confidence():
    svc = _policy()
    fc = _forecast(confidence=0.4)
    decision = svc.evaluate_decision(fc, {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0}, 1.0, 0.1)
    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason == "confidence_guard"
    assert "confidence_guard" in decision.no_trade.reasons


def test_kraken_spot_doctrine_filter_removes_market_neutral_strategies() -> None:
    svc = _kraken_spot_policy()
    fc = _forecast()
    signals = svc.evaluate_strategies(
        {
            "depth_notional": 1_000_000.0,
            "funding_rate": 0.0005,
            "spread_proxy": 0.0,
            "ret_3": 0.003,
            "ret_1": -0.002,
            "mark_price": 100.0,
            "spot_price_proxy": 99.0,
            "pairs_zscore": 1.2,
        },
        fc,
    )

    assert signals
    assert all(signal.name not in {"delta_neutral_carry", "basis", "pairs_stat_arb", "carry"} for signal in signals)
    assert all(signal.target_notional >= 0.0 for signal in signals)


def test_kraken_spot_doctrine_filter_turns_negative_directional_entry_into_no_trade() -> None:
    svc = _kraken_spot_policy()
    fc = _forecast()
    decision = svc.evaluate_decision(
        fc,
        {
            "depth_notional": 1_000_000.0,
            "funding_rate": 0.0005,
            "spread_proxy": 0.0,
            "ret_3": -0.004,
            "ret_1": 0.003,
            "mark_price": 100.0,
            "spot_price_proxy": 99.0,
            "pairs_zscore": 1.5,
        },
        1.0,
        0.1,
    )

    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason == "kraken_spot_doctrine_filter"
    assert "blocked_negative_direction_entry:trend" in decision.no_trade.reasons


def test_empty_signal_decision_prefers_external_quote_capital_truth() -> None:
    svc = _kraken_spot_policy()

    def _no_signals(features, forecast):  # noqa: ARG001
        svc.last_doctrine_filter_reasons = [
            "blocked_doctrine_incompatible_strategy:delta_neutral_carry",
            "blocked_doctrine_incompatible_strategy:basis",
        ]
        svc.last_doctrine_blocked_strategies = ["delta_neutral_carry", "basis"]
        return []

    svc.evaluate_strategies = _no_signals  # type: ignore[method-assign]
    fc = _forecast()
    profitability = {
        "capital_release": {
            "metadata": {
                "reserve_state": {
                    "quote_asset": "EUR",
                    "quote_free_balance": 0.0086,
                    "entry_buying_power_quote": 0.0086,
                    "required_quote_with_fee_buffer": 5.0,
                    "reasons": ["insufficient_quote_below_min_order_quote"],
                }
            }
        }
    }

    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0005, "spread_proxy": 0.0},
        1.0,
        0.1,
        profitability_context=profitability,
    )

    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason == "insufficient_quote_external_capital"
    assert "insufficient_quote_below_min_order_quote" in decision.no_trade.reasons
    assert decision.profitability == profitability


def test_empty_signal_decision_prefers_directional_cooldown_over_doctrine_filter() -> None:
    svc = _kraken_spot_policy()

    def _no_signals(features, forecast):  # noqa: ARG001
        svc.last_doctrine_filter_reasons = [
            "blocked_doctrine_incompatible_strategy:delta_neutral_carry",
            "blocked_doctrine_incompatible_strategy:basis",
        ]
        svc.last_doctrine_blocked_strategies = ["delta_neutral_carry", "basis"]
        return []

    svc.evaluate_strategies = _no_signals  # type: ignore[method-assign]
    svc.strategy_regime_cooldowns[("trend", "RANGE")] = 3
    svc.strategy_regime_cooldowns[("mean_reversion", "RANGE")] = 2
    fc = _forecast()

    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0005, "spread_proxy": 0.0},
        1.0,
        0.1,
    )

    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason == "directional_signal_cooldown"
    assert "directional_strategy_cooldown:trend@RANGE:3" in decision.no_trade.reasons
    assert "directional_strategy_cooldown:mean_reversion@RANGE:2" in decision.no_trade.reasons


def test_make_intent_remains_compatible_with_structured_decision():
    svc = _policy()
    fc = _forecast()
    features = {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0}
    decision = svc.evaluate_decision(
        fc,
        features,
        1.0,
        0.1,
        regime_assessment=RegimeAssessment(fc.symbol, fc.ts, "trend", 0.8, 0.7, 0.2, None, {"ret_3": 0.01}),
        execution_quality=ExecutionQualityForecast(fc.symbol, fc.ts, 0.8, 150, 1.0, 0.1, True, {}),
        portfolio_allocation=PortfolioAllocation(fc.symbol, fc.ts, 75.0, 0.1, 0.1, 0.9, 0.9, 1.0, 1.0, 0.9, 0.9, {}),
    )
    intent = svc.make_intent(fc, features, 1.0, 0.1)
    assert decision.trade_allowed is True
    assert intent is not None
    assert intent.symbol == decision.symbol
    assert intent.side == decision.side
    assert intent.target_notional == decision.target_notional
    assert "components" in intent.why
    assert "decision_doctrine" not in intent.why


def test_make_intent_ignores_live_only_spre_shadow_vetoes():
    svc = _policy()
    svc.spre_engine = SimpleNamespace(  # type: ignore[assignment]
        evaluate=lambda **kwargs: SimpleNamespace(
            dominant_action="no_trade",
            side="buy",
            size_multiplier=0.0,
            regret_score=10.0,
            no_trade_quality=10.0,
            narrative="forced_no_trade",
            reasons=["forced_no_trade"],
            heuristic=True,
            metadata={},
        )
    )
    svc.shadow_rival_service = SimpleNamespace(  # type: ignore[assignment]
        evaluate=lambda **kwargs: SimpleNamespace(
            action="no_trade",
            allowed=False,
            critique_score=1.0,
            reasons=["forced_shadow_veto"],
            narrative="forced_shadow_veto",
            heuristic=True,
            metadata={},
        )
    )
    fc = _forecast()
    features = {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0}

    intent = svc.make_intent(fc, features, 1.0, 0.1)

    assert intent is not None
    assert intent.side == "buy"
    assert "spre" not in intent.why
    assert "shadow_rival" not in intent.why


def test_evaluate_decision_blocks_bad_execution_quality():
    svc = _policy()
    fc = _forecast()
    decision = svc.evaluate_decision(
        replace(fc, confidence=0.9),
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        1.0,
        0.1,
        execution_quality=ExecutionQualityForecast(fc.symbol, fc.ts, 0.1, 3_000, 12.0, 0.9, False, {}),
    )
    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason == "execution_quality_bad"


def test_evaluate_decision_blocks_on_quantum_no_trade():
    svc = _policy()
    fc = _forecast()
    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        1.0,
        0.1,
        quantum_state=SimpleNamespace(
            scenario_tree=SimpleNamespace(dominant_state="dead_market_drift"),
            heuristic=True,
            collapse_decision=SimpleNamespace(
                recommended_action="no_trade",
                side=None,
                action_score=0.0,
                no_trade_probability=0.8,
                execution_fragility_score=0.7,
                uncertainty=0.8,
                size_multiplier=0.0,
                reasons=["no_trade_probability_high"],
            ),
        ),
    )

    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason == "quantum_no_trade"


def test_evaluate_decision_respects_edge_immunity_wait():
    svc = _policy()
    fc = _forecast()
    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        1.0,
        0.1,
        edge_immunity_decision=SimpleNamespace(
            action="wait",
            reason="wait_dominance",
            report=SimpleNamespace(
                recommended_size_multiplier=0.3,
                edge_survival_ratio=0.4,
                fragility_index=0.6,
                self_impact_penalty_bps=2.0,
                reality_gap_score=0.5,
                wait_value_score=8.0,
                recommended_execution_style="passive_limit",
                dominant_failure_modes=["wait_dominance"],
            ),
        ),
    )

    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason == "wait_dominance"


def test_evaluate_decision_respects_mastermind_veto():
    svc = _policy()
    fc = _forecast()

    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        1.0,
        0.1,
        mastermind_advisory=SimpleNamespace(
            provider="local",
            signal="fragile_edge",
            confidence=0.8,
            reason="hostile_future_breaks_thesis",
            decision="NO_TRADE",
            risk_level=92.0,
            veto=True,
            size_multiplier=0.0,
            execution_style_bias="passive_limit",
            reasons=["mastermind_no_trade"],
            heuristic=True,
            raw={},
        ),
    )

    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason == "mastermind_veto"
    assert decision.why["mastermind"]["decision"] == "NO_TRADE"


def test_evaluate_decision_uses_mastermind_probe_to_reduce_size():
    svc = _policy()
    fc = _forecast()

    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        1.0,
        0.1,
        mastermind_advisory=SimpleNamespace(
            provider="local",
            signal="probe_only",
            confidence=0.55,
            reason="edge_not_robust_enough_for_full_size",
            decision="PROBE",
            risk_level=45.0,
            veto=False,
            size_multiplier=0.2,
            execution_style_bias="passive_limit",
            reasons=["mastermind_probe"],
            heuristic=True,
            raw={},
        ),
    )

    assert decision.trade_allowed is True
    assert 0.0 < decision.target_notional <= 10.0
    assert decision.why["mastermind"]["decision"] == "PROBE"


def test_evaluate_decision_blocks_on_spre_no_trade_dominance():
    svc = _policy()
    fc = _forecast()
    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        1.0,
        0.9,
        quantum_state=SimpleNamespace(
            scenario_tree=SimpleNamespace(dominant_state="dead_market_drift"),
            heuristic=True,
            collapse_decision=SimpleNamespace(
                recommended_action="trade",
                side="buy",
                action_score=0.3,
                no_trade_probability=0.85,
                execution_fragility_score=0.8,
                uncertainty=0.85,
                size_multiplier=0.2,
                expected_move_bps=2.0,
                branch_disagreement_score=0.8,
                scenario_drift_score=0.7,
                reasons=["branch_disagreement_high"],
            ),
        ),
        edge_immunity_decision=SimpleNamespace(
            action="trade_smaller",
            reason="fragility_requires_smaller_size",
            report=SimpleNamespace(
                recommended_size_multiplier=0.25,
                edge_survival_ratio=0.3,
                fragility_index=0.8,
                self_impact_penalty_bps=4.0,
                reality_gap_score=0.7,
                wait_value_score=5.0,
                recommended_execution_style="passive_limit",
                dominant_failure_modes=["adverse_follow_through"],
            ),
        ),
        profitability_context={"round_trip": {"recommended_size_multiplier": 0.3, "action": "trade_now"}},
    )

    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason in {"quantum_signal_conflict", "spre_no_trade_dominance", "quantum_no_trade", "execution_fragility"}
    assert "spre" in decision.why
    assert "shadow_rival" in decision.why
    assert "chosen_survival_ratio" in decision.why["spre"]
    assert "action_gap_bps" in decision.why["spre"]
    assert "action_rankings" in decision.why["spre"]
    assert "internal_action" in decision.why["spre"]
    assert "action_scores" in decision.why["spre"]
    assert "thesis_break_score" in decision.why["shadow_rival"]
    assert "kill_path_score" in decision.why["shadow_rival"]
    assert "chosen_survival_ratio" in decision.why["shadow_rival"]
    assert "spre_no_trade_dominance" in decision.no_trade.reasons or "shadow_rival_veto" in decision.no_trade.reasons


def test_evaluate_decision_blocks_on_event_intelligence_no_trade():
    svc = _policy()
    fc = _forecast()
    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        1.0,
        0.1,
        event_intelligence_report=SimpleNamespace(
            recommended_action="no_trade",
            overall_risk_score=0.9,
            recommended_size_multiplier=0.0,
            reasons=["adversarial_narrative_risk_high"],
            partial=False,
            metadata={"heuristic": True},
        ),
    )

    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason == "event_intelligence_no_trade"


def test_evaluate_decision_applies_probe_only_capital_throttle():
    svc = _policy()
    fc = _forecast()
    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        1.0,
        0.1,
        capital_sovereignty_decision=SimpleNamespace(
            action="probe_only",
            freedom_envelope_score=0.3,
            reserve_pressure=0.5,
            rotation_score=0.2,
            recommended_size_multiplier=0.4,
            keep_core_ratio=0.7,
            satellite_ratio=0.3,
            probe_ratio=0.2,
            release_notional=0.0,
            rotate_notional=0.0,
            reasons=["capital_probe_only"],
            partial=False,
        ),
    )

    assert decision.trade_allowed is True
    assert 0.0 < decision.target_notional < 50.0
    assert "capital_sovereignty_probe_only" in decision.why["capital_sovereignty"]["reasons"] or "capital_probe_only" in decision.why["capital_sovereignty"]["reasons"]


def test_evaluate_decision_prioritizes_adaptive_exit_before_new_trade():
    svc = _policy()
    fc = _forecast()
    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        1.0,
        0.1,
        adaptive_exit_allocation=SimpleNamespace(
            action="partial_exit",
            core_exit_notional=0.0,
            satellite_exit_notional=20.0,
            runner_notional=0.0,
            total_exit_notional=20.0,
            execution_style="passive_limit",
            reasons=["event_wait_de_risk"],
            partial=False,
        ),
    )

    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason == "adaptive_exit_priority"


def test_evaluate_decision_uses_decision_doctrine_to_block_weak_truth():
    svc = _policy()
    fc = _forecast()
    truth_context = {
        "snapshot": {
            "fill_truth_confidence": {"level": "unavailable"},
            "fee_truth_confidence": {"level": "unavailable"},
            "realized_pnl_confidence": {"level": "partial"},
            "balance_truth_confidence": {"level": "partial"},
            "exposure_truth_confidence": {"level": "partial"},
            "market_data_truth_confidence": {"level": "partial"},
            "unrealized_pnl_confidence": {"level": "partial"},
        },
        "reconciliation_ok": False,
    }

    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        1.0,
        0.1,
        truth_context=truth_context,
        execution_quality=ExecutionQualityForecast(fc.symbol, fc.ts, 0.85, 120, 1.0, 0.1, True, {}),
        portfolio_allocation=PortfolioAllocation(fc.symbol, fc.ts, 75.0, 0.1, 0.1, 0.9, 0.9, 1.0, 1.0, 0.9, 0.9, {}),
    )

    assert decision.trade_allowed is False
    assert decision.no_trade is not None
    assert decision.no_trade.reason == "decision_doctrine_no_trade"
    assert "decision_doctrine" in decision.why
    assert decision.why["decision_doctrine"]["recommended_action"] == "no_trade"
    assert "doctrine_truth_not_strong_enough" in decision.why["decision_doctrine"]["reasons"]
    assert "doctrine_partial_truth_propagated" in decision.why["decision_doctrine"]["reasons"]


def test_evaluate_decision_uses_decision_doctrine_probe_to_shrink_size():
    svc = _policy()
    fc = _forecast()
    decision = svc.evaluate_decision(
        fc,
        {"depth_notional": 1_000_000.0, "funding_rate": 0.0, "spread_proxy": 0.0},
        1.0,
        0.1,
        execution_quality=ExecutionQualityForecast(fc.symbol, fc.ts, 0.85, 120, 1.0, 0.1, True, {}),
        portfolio_allocation=PortfolioAllocation(fc.symbol, fc.ts, 75.0, 0.1, 0.1, 0.9, 0.9, 1.0, 1.0, 0.9, 0.9, {}),
        position_morph_plan=SimpleNamespace(
            action="probe_entry",
            keep_core=False,
            trim_satellites=False,
            allow_runner=False,
            reduce_risk=False,
            core_fraction=0.0,
            satellite_fraction=0.0,
            runner_fraction=0.0,
            add_notional=0.0,
            reduce_notional=0.0,
            probe_notional=10.0,
            reasons=["probe_entry_dominates"],
            partial=False,
        ),
    )

    assert decision.trade_allowed is True
    assert decision.target_notional < 20.0
    assert "decision_doctrine" in decision.why
    assert decision.why["decision_doctrine"]["recommended_action"] == "probe"
    assert "doctrine_probe_dominates" in decision.why["decision_doctrine"]["reasons"]
