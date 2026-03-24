from __future__ import annotations

from datetime import datetime

from autonomous_investment_robot.core.contracts import CollapseDecision, CollapseDecisionContext, ScenarioTree, SignalInterferenceReport


def collapse_decision(*, symbol: str, ts: datetime, scenario_tree: ScenarioTree, interference: SignalInterferenceReport) -> tuple[CollapseDecisionContext, CollapseDecision]:
    expected_move = sum(branch.probability * branch.expected_move_bps for branch in scenario_tree.branches)
    downside = sum(branch.probability * branch.downside_risk_bps for branch in scenario_tree.branches)
    branch_disagreement = float(scenario_tree.probability_field.branch_disagreement_score)
    scenario_drift = float(scenario_tree.probability_field.scenario_drift_score)
    uncertainty = max(
        0.0,
        min(
            1.0,
            scenario_tree.probability_field.entropy / 2.2
            + interference.uncertainty_penalty * 0.45
            + branch_disagreement * 0.25
            + scenario_drift * 0.2,
        ),
    )
    no_trade_probability = max(
        scenario_tree.probability_field.no_trade_probability,
        min(1.0, uncertainty * 0.55 + scenario_tree.probability_field.execution_fragility_score * 0.25 + branch_disagreement * 0.15),
    )
    fragility = max(scenario_tree.probability_field.execution_fragility_score, interference.uncertainty_penalty)
    action_score = max(0.0, abs(expected_move) - downside * 0.35) * max(0.0, 1.0 - uncertainty) * max(0.0, 1.0 - fragility)
    recommended_action = "no_trade"
    side = None
    reasons: list[str] = []
    if no_trade_probability >= 0.55:
        reasons.append("no_trade_probability_high")
    if fragility >= 0.75:
        reasons.append("execution_fragility_high")
    if branch_disagreement >= 0.55:
        reasons.append("branch_disagreement_high")
    if scenario_drift >= 0.55:
        reasons.append("scenario_drift_high")
    if abs(expected_move) < 2.0:
        reasons.append("expected_move_too_small")
    if not reasons and action_score > 0.25:
        recommended_action = "trade"
        side = "buy" if expected_move >= 0.0 else "sell"
    else:
        recommended_action = "no_trade"
    size_multiplier = max(0.1, min(1.0, (1.0 - uncertainty) * (1.0 - fragility))) if recommended_action == "trade" else 0.0
    ctx = CollapseDecisionContext(
        symbol=symbol,
        ts=ts,
        scenario_tree=scenario_tree,
        interference_report=interference,
        expected_move_distribution_bps={branch.label: branch.expected_move_bps for branch in scenario_tree.branches},
        uncertainty_decomposition={
            "entropy": scenario_tree.probability_field.entropy,
            "interference_penalty": interference.uncertainty_penalty,
            "execution_fragility": scenario_tree.probability_field.execution_fragility_score,
            "branch_disagreement": branch_disagreement,
            "scenario_drift": scenario_drift,
        },
        no_trade_probability=no_trade_probability,
        execution_fragility_score=fragility,
        top_states=dict(scenario_tree.metadata.get("top_states", {})),
        metadata={"heuristic": True},
    )
    decision = CollapseDecision(
        symbol=symbol,
        ts=ts,
        recommended_action=recommended_action,
        side=side,
        action_score=action_score,
        no_trade_probability=no_trade_probability,
        execution_fragility_score=fragility,
        size_multiplier=size_multiplier,
        expected_move_bps=expected_move,
        uncertainty=uncertainty,
        branch_disagreement_score=branch_disagreement,
        scenario_drift_score=scenario_drift,
        reasons=reasons or ["trade_supported"],
        metadata={"heuristic": True},
    )
    return ctx, decision
