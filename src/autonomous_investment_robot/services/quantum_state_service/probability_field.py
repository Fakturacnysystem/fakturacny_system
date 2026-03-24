from __future__ import annotations

import math
from datetime import datetime

from autonomous_investment_robot.core.contracts import ProbabilityField, ScenarioBranch


def normalize(weights: dict[str, float]) -> dict[str, float]:
    clipped = {key: max(0.0, float(value)) for key, value in weights.items()}
    total = sum(clipped.values())
    if total <= 0.0:
        n = max(1, len(clipped))
        return {key: 1.0 / n for key in clipped}
    return {key: value / total for key, value in clipped.items()}


def build_probability_field(
    symbol: str,
    ts: datetime,
    branches: list[ScenarioBranch],
    *,
    confidence_decomposition: dict[str, float] | None = None,
    branch_disagreement_score: float = 0.0,
    scenario_drift_score: float = 0.0,
) -> ProbabilityField:
    horizon_map: dict[str, dict[str, float]] = {}
    entropy = 0.0
    no_trade_probability = 0.0
    execution_fragility = 0.0
    for branch in branches:
        horizon_map.setdefault(branch.horizon, {})[branch.label] = branch.probability
        if branch.probability > 0.0:
            entropy -= branch.probability * math.log(branch.probability)
        if branch.label == "dead_market_drift":
            no_trade_probability += branch.probability
        execution_fragility += branch.probability * branch.execution_fragility
    return ProbabilityField(
        symbol=symbol,
        ts=ts,
        horizons=horizon_map,
        entropy=entropy,
        no_trade_probability=min(1.0, no_trade_probability),
        execution_fragility_score=max(0.0, min(1.0, execution_fragility)),
        confidence_decomposition={} if confidence_decomposition is None else dict(confidence_decomposition),
        branch_disagreement_score=max(0.0, min(1.0, branch_disagreement_score)),
        scenario_drift_score=max(0.0, min(1.0, scenario_drift_score)),
        metadata={"branch_count": len(branches)},
    )
