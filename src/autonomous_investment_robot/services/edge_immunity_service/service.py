from __future__ import annotations

from autonomous_investment_robot.core.contracts import EdgeImmunityDecision
from autonomous_investment_robot.services.edge_immunity_service.counterfactual_world_generator import generate_worlds
from autonomous_investment_robot.services.edge_immunity_service.fragility_engine import assess_fragility
from autonomous_investment_robot.services.edge_immunity_service.ghost_impact_model import estimate_self_impact_bps
from autonomous_investment_robot.services.edge_immunity_service.wait_dominance_engine import evaluate_wait_dominance


class EdgeImmunityService:
    def __init__(self, calibration_service: object | None = None) -> None:
        self.calibration_service = calibration_service

    def evaluate(
        self,
        *,
        symbol: str,
        ts: object,
        features: dict[str, float],
        forecast: object,
        regime_assessment: object,
        execution_quality: object,
        portfolio_allocation: object,
        quantum_state: object,
    ) -> EdgeImmunityDecision:
        base_edge_bps = max(0.0, abs(float(getattr(forecast, "mu", 0.0))) * 10000.0)
        base_edge_bps = max(base_edge_bps, abs(float(getattr(getattr(quantum_state, "collapse_decision", object()), "expected_move_bps", 0.0))) * 0.6)
        spread_bps = float(features.get("spread_proxy", 0.0)) * 10000.0
        depth_notional = max(1.0, float(features.get("depth_notional", 0.0)))
        fragility = float(getattr(getattr(quantum_state, "collapse_decision", object()), "execution_fragility_score", 0.5))
        calibration = self.calibration_service.current_profile() if self.calibration_service is not None else None
        if calibration is not None:
            fragility = min(1.0, fragility + float(getattr(calibration, "fragility_bias", 0.0) or 0.0))
        collapse = getattr(quantum_state, "collapse_decision", object())
        execution_style = "passive_limit" if fragility >= 0.4 else "unchanged"
        worlds = generate_worlds(
            ts=ts,  # type: ignore[arg-type]
            spread_bps=spread_bps,
            depth_notional=depth_notional,
            execution_fragility=fragility,
            regime_label=str(getattr(regime_assessment, "label", "mean_reversion")),
        )
        target_notional = float(getattr(portfolio_allocation, "recommended_notional", 0.0))
        self_impact_penalty = estimate_self_impact_bps(
            target_notional=target_notional,
            depth_notional=depth_notional,
            execution_fragility=fragility,
            execution_style=execution_style,
        )
        stressed_edges = []
        failure_modes: list[str] = []
        wait_bonus = 0.0
        for world in worlds:
            fill_probability_penalty = max(0.0, (1.0 - world.fill_probability_multiplier) * max(base_edge_bps, 1.0) * 0.35)
            stressed = (
                base_edge_bps
                + world.move_shock_bps
                - spread_bps * (world.spread_multiplier - 1.0)
                - self_impact_penalty * world.self_impact_multiplier
                - fill_probability_penalty
            )
            stressed_edges.append(world.probability * stressed)
            if stressed <= 0.0:
                failure_modes.append(world.dominant_failure_mode)
            wait_bonus += world.probability * world.wait_edge_bonus_bps
        stressed_edge_bps = sum(stressed_edges)
        signature, report = assess_fragility(
            symbol=symbol,
            ts=ts,
            base_edge_bps=base_edge_bps,
            stressed_edge_bps=stressed_edge_bps,
            self_impact_penalty_bps=self_impact_penalty,
            dominant_failure_modes=sorted(set(failure_modes)),
            wait_value_score=wait_bonus,
        )
        wait = evaluate_wait_dominance(
            base_edge_bps=base_edge_bps,
            stressed_edge_bps=stressed_edge_bps,
            wait_bonus_bps=wait_bonus,
            fragility_index=signature.fragility_index,
        )
        report.wait_value_score = wait.wait_value_score
        wait_advantage_bps = float(wait.metadata.get("incremental_advantage_bps", 0.0) or 0.0)
        action = "trade_now"
        reason = "edge_survives_counterfactuals"
        if report.edge_survival_ratio < 0.25 or report.fragility_index >= 0.8:
            action = "no_trade"
            reason = "edge_fragile"
        elif wait.wait_dominant and wait_advantage_bps > max(2.0, base_edge_bps * 0.05) and report.fragility_index >= 0.35:
            action = "wait"
            reason = "wait_dominance"
        elif report.fragility_index >= 0.45:
            action = "trade_smaller"
            reason = "fragility_requires_smaller_size"
        if action == "trade_now":
            report.recommended_size_multiplier = max(0.25, min(1.0, report.recommended_size_multiplier))
        if calibration is not None:
            report.recommended_size_multiplier = max(
                0.0,
                min(report.recommended_size_multiplier, float(getattr(calibration, "size_bias", 1.0) or 1.0)),
            )
            report.metadata["calibrated"] = True
        report.metadata.update({
            "worlds": [world.__dict__ for world in worlds],
            "wait_dominance": wait.__dict__,
            "fragility_signature": signature.__dict__,
            "collapse_reasons": list(getattr(collapse, "reasons", [])),
        })
        if action in {"wait", "no_trade"}:
            report.recommended_execution_style = "passive_limit"
        return EdgeImmunityDecision(
            symbol=symbol,
            ts=ts,  # type: ignore[arg-type]
            action=action,
            reason=reason,
            report=report,
            metadata={"heuristic": True},
        )
