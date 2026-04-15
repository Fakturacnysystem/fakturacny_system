from __future__ import annotations

from datetime import datetime

from autonomous_investment_robot.core.contracts import CollapseDecision, CollapseDecisionContext, ScenarioTree, SignalInterferenceReport


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _negative_branch_mass(scenario_tree: ScenarioTree) -> float:
    negative_mass = 0.0
    for branch in scenario_tree.branches:
        expected_move = abs(float(branch.expected_move_bps))
        downside = max(0.0, float(branch.downside_risk_bps))
        if expected_move <= 1e-9 and downside <= 1e-9:
            continue
        edge_ratio = expected_move / max(downside, 1e-9)
        if edge_ratio >= 1.35:
            branch_negative = 0.2
        elif edge_ratio >= 1.0:
            branch_negative = 0.4
        elif edge_ratio >= 0.6:
            branch_negative = 0.7
        else:
            branch_negative = 1.0
        label = str(branch.label or "").lower()
        if label.startswith(("dead_market", "panic", "liquidity", "failed_breakout", "volatility")):
            branch_negative = max(branch_negative, 0.8)
        negative_mass += max(0.0, float(branch.probability)) * branch_negative
    return _clamp(negative_mass)


def _observability_uncertainty(*, interference_penalty: float, branch_disagreement: float, scenario_drift: float) -> float:
    return _clamp(interference_penalty * 0.45 + max(0.0, branch_disagreement - 0.35) * 0.15 + max(0.0, scenario_drift - 0.35) * 0.10)


def collapse_decision(*, symbol: str, ts: datetime, scenario_tree: ScenarioTree, interference: SignalInterferenceReport) -> tuple[CollapseDecisionContext, CollapseDecision]:
    expected_move = sum(branch.probability * branch.expected_move_bps for branch in scenario_tree.branches)
    downside = sum(branch.probability * branch.downside_risk_bps for branch in scenario_tree.branches)
    branch_disagreement = float(scenario_tree.probability_field.branch_disagreement_score)
    scenario_drift = float(scenario_tree.probability_field.scenario_drift_score)
    entropy_component = _clamp(scenario_tree.probability_field.entropy / 3.0)
    policy_disagreement = _clamp(max(branch_disagreement, scenario_drift * 0.85))
    execution_fragility = _clamp(
        max(
            float(scenario_tree.probability_field.execution_fragility_score),
            float(interference.uncertainty_penalty) * 0.55,
        )
    )
    observability_uncertainty = _observability_uncertainty(
        interference_penalty=float(interference.uncertainty_penalty),
        branch_disagreement=branch_disagreement,
        scenario_drift=scenario_drift,
    )
    negative_evidence_mass = _negative_branch_mass(scenario_tree)
    uncertainty = _clamp(
        entropy_component * 0.35
        + policy_disagreement * 0.25
        + execution_fragility * 0.20
        + observability_uncertainty * 0.20
    )
    no_trade_probability = max(
        float(scenario_tree.probability_field.no_trade_probability),
        _clamp(
            negative_evidence_mass * 0.45
            + execution_fragility * 0.20
            + branch_disagreement * 0.06
            + observability_uncertainty * 0.08
        ),
    )
    fragility = execution_fragility
    action_score = max(0.0, abs(expected_move) - downside * 0.35) * max(0.15, 1.0 - uncertainty * 0.45) * max(0.2, 1.0 - fragility * 0.35)
    recommended_action = "wait"
    side = None
    reasons: list[str] = []
    thresholds = {
        "no_trade_probability_high": no_trade_probability >= 0.65,
        "negative_evidence_dominant": negative_evidence_mass >= 0.72,
        "execution_fragility_high": fragility >= 0.75,
        "branch_disagreement_high": branch_disagreement >= 0.75,
        "scenario_drift_high": scenario_drift >= 0.65,
        "expected_move_too_small": abs(expected_move) < 2.0,
        "probe_supported": action_score >= 2.5 and uncertainty < 0.70 and negative_evidence_mass < 0.60,
        "trade_supported": action_score >= 6.0 and uncertainty < 0.45 and fragility < 0.55 and negative_evidence_mass < 0.50,
    }
    if thresholds["no_trade_probability_high"]:
        reasons.append("no_trade_probability_high")
    if thresholds["negative_evidence_dominant"]:
        reasons.append("negative_evidence_dominant")
    if thresholds["execution_fragility_high"]:
        reasons.append("execution_fragility_high")
    if thresholds["branch_disagreement_high"]:
        reasons.append("branch_disagreement_high")
    if thresholds["scenario_drift_high"]:
        reasons.append("scenario_drift_high")
    if thresholds["expected_move_too_small"]:
        reasons.append("expected_move_too_small")
    if thresholds["negative_evidence_dominant"] or (thresholds["no_trade_probability_high"] and fragility >= 0.55):
        recommended_action = "no_trade"
    elif thresholds["trade_supported"]:
        recommended_action = "trade"
        side = "buy" if expected_move >= 0.0 else "sell"
    elif thresholds["probe_supported"]:
        recommended_action = "probe"
        side = "buy" if expected_move >= 0.0 else "sell"
    else:
        recommended_action = "wait"
    if recommended_action == "trade":
        size_multiplier = max(0.2, min(1.0, (1.0 - uncertainty * 0.55) * (1.0 - fragility * 0.45)))
    elif recommended_action == "probe":
        size_multiplier = max(0.1, min(0.35, (1.0 - uncertainty * 0.30) * (1.0 - fragility * 0.20)))
    else:
        size_multiplier = 0.0
    ctx = CollapseDecisionContext(
        symbol=symbol,
        ts=ts,
        scenario_tree=scenario_tree,
        interference_report=interference,
        expected_move_distribution_bps={branch.label: branch.expected_move_bps for branch in scenario_tree.branches},
        uncertainty_decomposition={
            "entropy": entropy_component,
            "interference_penalty": float(interference.uncertainty_penalty),
            "epistemic_uncertainty": entropy_component,
            "policy_disagreement": policy_disagreement,
            "execution_fragility": execution_fragility,
            "observability_uncertainty": observability_uncertainty,
            "negative_evidence_mass": negative_evidence_mass,
            "branch_disagreement": branch_disagreement,
            "scenario_drift": scenario_drift,
        },
        no_trade_probability=no_trade_probability,
        execution_fragility_score=fragility,
        top_states=dict(scenario_tree.metadata.get("top_states", {})),
        metadata={
            "heuristic": True,
            "thresholds": thresholds,
        },
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
        metadata={
            "heuristic": True,
            "thresholds": thresholds,
            "negative_evidence_mass": negative_evidence_mass,
            "uncertainty_components": {
                "epistemic_uncertainty": entropy_component,
                "policy_disagreement": policy_disagreement,
                "execution_fragility": execution_fragility,
                "observability_uncertainty": observability_uncertainty,
            },
        },
    )
    return ctx, decision
