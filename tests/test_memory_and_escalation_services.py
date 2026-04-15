from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from autonomous_investment_robot.core.contracts import TradeEpisode
from autonomous_investment_robot.services.calibration_service.service import CalibrationService
from autonomous_investment_robot.services.counterfactual_evaluator.service import CounterfactualEvaluator
from autonomous_investment_robot.services.episodic_trade_memory.service import EpisodicTradeMemory
from autonomous_investment_robot.services.execution_simulation_sandbox.service import ExecutionSimulationSandbox
from autonomous_investment_robot.services.human_escalation_layer.service import HumanEscalationLayer
from autonomous_investment_robot.main import acknowledge_manual_review


def test_execution_simulation_sandbox_blocks_when_worst_case_breaks_edge():
    report = ExecutionSimulationSandbox().simulate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        intent=SimpleNamespace(side="buy"),
        snapshot=SimpleNamespace(spread_bps=8.0, depth_notional=250.0),
        execution_quality=SimpleNamespace(fill_probability=0.4, adverse_selection_risk=0.7),
        expected_edge_bps=4.0,
        market_integrity=SimpleNamespace(action="continue"),
        venue_limit_decision=None,
        synthetic_affect=SimpleNamespace(aggression_clamp=0.8),
    )

    assert report.recommended_action == "no_trade"
    assert report.worst_case_cost_bps >= 4.0


def test_human_escalation_layer_requests_manual_review_on_strong_disagreement():
    decision = HumanEscalationLayer().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        market_integrity=SimpleNamespace(action="continue"),
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(recommended_action="no_trade", uncertainty=0.85)),
        edge_immunity_decision=SimpleNamespace(action="trade_smaller"),
        event_intelligence=SimpleNamespace(recommended_action="wait"),
        synthetic_affect=SimpleNamespace(recommended_action="trade_smaller", stress=0.85, fear=0.75),
        capital_sovereignty=SimpleNamespace(action="continue"),
        execution_simulation=SimpleNamespace(recommended_action="no_trade", stressed_fill_probability=0.15),
    )

    assert decision.action in {"manual_review", "flatten_only"}
    assert decision.manual_review_required is True


def test_human_escalation_layer_does_not_require_manual_review_for_reasonless_action_disagreement():
    decision = HumanEscalationLayer().evaluate(
        symbol="SOL/EUR",
        ts=datetime.now(timezone.utc),
        market_integrity=SimpleNamespace(action="continue"),
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(recommended_action="probe", uncertainty=0.45)),
        edge_immunity_decision=SimpleNamespace(action="trade_now"),
        event_intelligence=SimpleNamespace(recommended_action="continue"),
        synthetic_affect=SimpleNamespace(recommended_action="controlled_expand", stress=0.08, fear=0.08),
        capital_sovereignty=SimpleNamespace(action="no_trade"),
        execution_simulation=SimpleNamespace(recommended_action="no_trade", stressed_fill_probability=0.441),
    )

    assert decision.action == "continue"
    assert decision.manual_review_required is False
    assert decision.reasons == []
    assert decision.metadata["disagreement_without_risk"] is True


def test_human_escalation_layer_persists_manual_review_marker(tmp_path):
    decision = HumanEscalationLayer(str(tmp_path)).evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        market_integrity=SimpleNamespace(action="flatten_only"),
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(recommended_action="no_trade", uncertainty=0.9)),
        edge_immunity_decision=SimpleNamespace(action="wait"),
        event_intelligence=SimpleNamespace(recommended_action="no_trade"),
        synthetic_affect=SimpleNamespace(recommended_action="trade_smaller", stress=0.9, fear=0.85),
        capital_sovereignty=SimpleNamespace(action="trade_smaller"),
        execution_simulation=SimpleNamespace(recommended_action="no_trade", stressed_fill_probability=0.1),
    )

    marker = Path(tmp_path) / "MANUAL_REVIEW_REQUIRED.json"
    assert decision.manual_review_required is True
    assert marker.exists()
    assert "\"action\": \"flatten_only\"" in marker.read_text(encoding="utf-8")


def test_human_escalation_layer_allows_only_explicit_ack_for_manual_review(tmp_path):
    layer = HumanEscalationLayer(str(tmp_path), ack_ttl_minutes=60)
    kwargs = {
        "symbol": "BTCUSDT",
        "ts": datetime.now(timezone.utc),
        "market_integrity": SimpleNamespace(action="continue"),
        "quantum_state": SimpleNamespace(collapse_decision=SimpleNamespace(recommended_action="no_trade", uncertainty=0.85)),
        "edge_immunity_decision": SimpleNamespace(action="trade_smaller"),
        "event_intelligence": SimpleNamespace(recommended_action="wait"),
        "synthetic_affect": SimpleNamespace(recommended_action="trade_smaller", stress=0.85, fear=0.75),
        "capital_sovereignty": SimpleNamespace(action="continue"),
        "execution_simulation": SimpleNamespace(recommended_action="no_trade", stressed_fill_probability=0.15),
    }

    first = layer.evaluate(**kwargs)
    assert first.action == "manual_review"
    assert first.acknowledged is False

    ack = layer.acknowledge(decision_key=first.decision_key, reviewer="qa", notes="reviewed")
    second = layer.evaluate(**kwargs)

    assert ack["decision_key"] == first.decision_key
    assert second.action == "continue_acknowledged"
    assert second.manual_review_required is False
    assert second.acknowledged is True
    assert second.acknowledgment_source == "qa"
    assert Path(tmp_path / "MANUAL_REVIEW_ACK.json").exists()


def test_acknowledge_manual_review_helper_uses_required_marker(tmp_path):
    layer = HumanEscalationLayer(str(tmp_path), ack_ttl_minutes=60)
    first = layer.evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        market_integrity=SimpleNamespace(action="continue"),
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(recommended_action="no_trade", uncertainty=0.85)),
        edge_immunity_decision=SimpleNamespace(action="trade_smaller"),
        event_intelligence=SimpleNamespace(recommended_action="wait"),
        synthetic_affect=SimpleNamespace(recommended_action="trade_smaller", stress=0.85, fear=0.75),
        capital_sovereignty=SimpleNamespace(action="continue"),
        execution_simulation=SimpleNamespace(recommended_action="no_trade", stressed_fill_probability=0.15),
    )

    out = acknowledge_manual_review(str(tmp_path), reviewer="ops", notes="approved")

    assert first.action == "manual_review"
    assert out["status"] == "acknowledged"
    assert out["decision_key"] == first.decision_key


def test_memory_counterfactual_and_calibration_services_work_together(tmp_path):
    memory = EpisodicTradeMemory(str(tmp_path))
    calibration = CalibrationService(str(tmp_path))
    episode = TradeEpisode(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        episode_id="ep-1",
        order_id="ord-1",
        side="buy",
        regime_label="trend",
        realized_pnl=-12.0,
        result="loss",
        truth_confidence_state="degraded_proxy",
        execution_quality_state="fragile",
        event_context={"event": "earnings_like"},
        failure_mode="execution_truth",
        attribution_summary={},
        metadata={},
    )
    memory.record(episode)
    profile = calibration.update_from_episodes(memory.recent())
    review = CounterfactualEvaluator().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        chosen_action="buy",
        realized_pnl=-12.0,
        profitability_context={"round_trip": {"action": "wait"}},
        edge_immunity_context={"action": "wait"},
        quantum_context={"no_trade_probability": 0.75},
        similar_episodes=[],
    )

    assert profile.recent_loss_rate > 0.0
    assert review.best_alternative_action in {"wait", "no_trade"}
    assert Path(tmp_path / "calibration_profile.json").exists()
