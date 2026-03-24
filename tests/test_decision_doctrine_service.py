from datetime import datetime, timezone
from types import SimpleNamespace

from autonomous_investment_robot.services.decision_doctrine_service.service import DecisionDoctrineService


def test_decision_doctrine_blocks_when_truth_is_not_proved():
    svc = DecisionDoctrineService()

    report = svc.evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        base_uncertainty=0.1,
        truth_context={
            "snapshot": {
                "fill_truth_confidence": {"level": "unavailable"},
                "fee_truth_confidence": {"level": "partial"},
                "realized_pnl_confidence": {"level": "partial"},
                "balance_truth_confidence": {"level": "partial"},
                "exposure_truth_confidence": {"level": "partial"},
                "market_data_truth_confidence": {"level": "partial"},
                "unrealized_pnl_confidence": {"level": "partial"},
            },
            "reconciliation_ok": False,
        },
        market_integrity_status=SimpleNamespace(score=0.9, action="continue", reasons=[]),
        execution_quality=SimpleNamespace(fill_probability=0.9, adverse_selection_risk=0.1, expected_fill_speed_ms=120),
        portfolio_allocation=SimpleNamespace(),
        profitability_context={"round_trip": {"net_edge_bps": 25.0}},
    )

    assert report.recommended_action == "no_trade"
    assert "doctrine_truth_not_strong_enough" in report.reasons
    assert report.partial is True
    assert report.partial_truth_penalty >= 0.7


def test_decision_doctrine_prefers_probe_when_partial_entry_dominates():
    svc = DecisionDoctrineService()

    report = svc.evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        base_uncertainty=0.1,
        truth_context={
            "snapshot": {
                "fill_truth_confidence": {"level": "authoritative"},
                "fee_truth_confidence": {"level": "authoritative"},
                "realized_pnl_confidence": {"level": "authoritative"},
                "balance_truth_confidence": {"level": "authoritative"},
                "exposure_truth_confidence": {"level": "authoritative"},
                "market_data_truth_confidence": {"level": "authoritative"},
                "unrealized_pnl_confidence": {"level": "authoritative"},
            },
            "reconciliation_ok": True,
        },
        market_integrity_status=SimpleNamespace(score=0.95, action="continue", reasons=[]),
        provider_capability=SimpleNamespace(
            user_stream_confidence="user_stream_plus_rest_repair",
            lifecycle_completeness="strong_without_replace",
            fee_truth_confidence="authoritative_exchange_history",
        ),
        execution_quality=SimpleNamespace(fill_probability=0.92, adverse_selection_risk=0.05, expected_fill_speed_ms=100),
        portfolio_allocation=SimpleNamespace(),
        profitability_context={"round_trip": {"net_edge_bps": 40.0}},
        synthetic_affect_state=SimpleNamespace(no_trade_threshold_shift=0.0, aggression_clamp=0.8),
        capital_sovereignty_decision=SimpleNamespace(action="continue", freedom_envelope_score=0.8, keep_core_ratio=0.5),
        position_morph_plan=SimpleNamespace(probe_notional=15.0, runner_fraction=0.1),
        execution_simulation_report=SimpleNamespace(
            stressed_fill_probability=0.9,
            worst_case_cost_bps=5.0,
            recommended_action="continue",
        ),
        spre_decision=SimpleNamespace(regret_score=1.0, metadata={"chosen_survival_ratio": 0.8}),
        shadow_rival_report=SimpleNamespace(action="continue", critique_score=0.1),
        edge_immunity_decision=SimpleNamespace(report=SimpleNamespace(edge_survival_ratio=0.85, fragility_index=0.1)),
    )

    assert report.recommended_action == "probe"
    assert report.size_multiplier <= 0.8
    assert "doctrine_probe_dominates" in report.reasons
    assert report.robustness_score > 0.5


def test_decision_doctrine_respects_mastermind_veto():
    svc = DecisionDoctrineService()

    report = svc.evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        base_uncertainty=0.1,
        truth_context={
            "snapshot": {
                "fill_truth_confidence": {"level": "authoritative"},
                "fee_truth_confidence": {"level": "authoritative"},
                "realized_pnl_confidence": {"level": "authoritative"},
                "balance_truth_confidence": {"level": "authoritative"},
                "exposure_truth_confidence": {"level": "authoritative"},
                "market_data_truth_confidence": {"level": "authoritative"},
                "unrealized_pnl_confidence": {"level": "authoritative"},
            },
            "reconciliation_ok": True,
        },
        market_integrity_status=SimpleNamespace(score=0.95, action="continue", reasons=[]),
        provider_capability=SimpleNamespace(
            user_stream_confidence="user_stream_plus_rest_repair",
            lifecycle_completeness="strong_without_replace",
            fee_truth_confidence="authoritative_exchange_history",
        ),
        execution_quality=SimpleNamespace(fill_probability=0.92, adverse_selection_risk=0.05, expected_fill_speed_ms=100),
        portfolio_allocation=SimpleNamespace(),
        profitability_context={"round_trip": {"net_edge_bps": 40.0}},
        mastermind_advisory=SimpleNamespace(decision="NO_TRADE", confidence=0.8, risk_level=90.0, size_multiplier=0.0, reasons=["mastermind_no_trade"]),
    )

    assert report.recommended_action == "no_trade"
    assert "doctrine_mastermind_veto" in report.reasons
    assert report.metadata["mastermind_action"] == "no_trade"
