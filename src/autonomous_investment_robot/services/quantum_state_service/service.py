from __future__ import annotations

from datetime import datetime

from autonomous_investment_robot.core.contracts import QuantumState
from autonomous_investment_robot.services.quantum_state_service.collapse_policy import collapse_decision
from autonomous_investment_robot.services.quantum_state_service.interference_engine import build_interference_report
from autonomous_investment_robot.services.quantum_state_service.scenario_tree import build_scenario_tree


class QuantumStateService:
    def __init__(self, calibration_service: object | None = None) -> None:
        self.calibration_service = calibration_service

    def evaluate(
        self,
        *,
        symbol: str,
        ts: datetime,
        features: dict[str, float],
        forecast: object,
        regime_assessment: object,
        alpha_signals: list[object],
        execution_quality: object,
        portfolio_allocation: object | None = None,
    ) -> QuantumState:
        tree = build_scenario_tree(
            symbol=symbol,
            ts=ts,
            features=features,
            forecast=forecast,
            regime_assessment=regime_assessment,
            execution_quality=execution_quality,
            portfolio_allocation=portfolio_allocation,
        )
        interference = build_interference_report(symbol=symbol, ts=ts, forecast=forecast, alpha_signals=alpha_signals)
        collapse_ctx, collapse = collapse_decision(symbol=symbol, ts=ts, scenario_tree=tree, interference=interference)
        calibration = self.calibration_service.current_profile() if self.calibration_service is not None else None
        if calibration is not None:
            collapse.no_trade_probability = min(1.0, collapse.no_trade_probability + float(getattr(calibration, "no_trade_bias", 0.0) or 0.0))
            collapse.execution_fragility_score = min(1.0, collapse.execution_fragility_score + float(getattr(calibration, "fragility_bias", 0.0) or 0.0))
            collapse.size_multiplier = max(0.0, min(collapse.size_multiplier, float(getattr(calibration, "size_bias", 1.0) or 1.0)))
            if collapse.no_trade_probability >= 0.7 and collapse.recommended_action != "no_trade":
                collapse.recommended_action = "no_trade"
                collapse.side = None
                collapse.size_multiplier = 0.0
                collapse.reasons.append("calibration_no_trade_bias")
            collapse.metadata["calibrated"] = True
            collapse_ctx.metadata["calibrated"] = True
        return QuantumState(
            symbol=symbol,
            ts=ts,
            scenario_tree=tree,
            interference_report=interference,
            collapse_context=collapse_ctx,
            collapse_decision=collapse,
            heuristic=True,
            metadata={"heuristic": True},
        )
