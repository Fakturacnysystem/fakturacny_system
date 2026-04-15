from __future__ import annotations

from autonomous_investment_robot.core.contracts import ScenarioBranch, StateTransition


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def build_confidence_decomposition(
    *,
    forecast: object,
    regime_assessment: object,
    execution_quality: object,
    features: dict[str, float],
    portfolio_allocation: object | None = None,
) -> dict[str, float]:
    realized_vol = abs(float(features.get("realized_vol", 0.0)))
    spread_proxy = abs(float(features.get("spread_proxy", 0.0))) * 10000.0
    depth_notional = max(1.0, float(features.get("depth_notional", 0.0)))
    signal_conf = clamp01(float(getattr(forecast, "confidence", 0.0)))
    regime_conf = clamp01(float(getattr(regime_assessment, "confidence", 0.0)) * float(getattr(regime_assessment, "persistence", 0.0)))
    execution_conf = clamp01(
        float(getattr(execution_quality, "fill_probability", 0.0)) * (1.0 - float(getattr(execution_quality, "adverse_selection_risk", 0.0)))
    )
    market_quality_conf = clamp01((1.0 - min(1.0, spread_proxy / 20.0)) * min(1.0, depth_notional / 100000.0) * (1.0 - min(1.0, realized_vol * 120.0)))
    portfolio_conf = 0.5
    if portfolio_allocation is not None:
        portfolio_conf = clamp01(
            float(getattr(portfolio_allocation, "confidence_scalar", 0.5))
            * float(getattr(portfolio_allocation, "regime_scalar", 1.0))
            * float(getattr(portfolio_allocation, "liquidity_scalar", 1.0))
        )
    return {
        "signal": signal_conf,
        "regime": regime_conf,
        "execution": execution_conf,
        "market_quality": market_quality_conf,
        "portfolio": portfolio_conf,
    }


def branch_disagreement_score(branches: list[ScenarioBranch]) -> float:
    if not branches:
        return 1.0
    dominant = max(branch.probability for branch in branches)
    return clamp01(1.0 - dominant)


def scenario_drift_score(*, regime_label: str, branches: list[ScenarioBranch]) -> float:
    if not branches:
        return 1.0
    regime_hint = regime_label.lower()
    aligned = 0.0
    mean_reversion_family = any(token in regime_hint for token in {"mean", "dead", "chop", "range"})
    for branch in branches:
        label = branch.label.lower()
        if "trend" in regime_hint and label in {"bullish_continuation", "squeeze"}:
            aligned += branch.probability
        elif mean_reversion_family and label in {"mean_reversion_snapback", "dead_market_drift"}:
            aligned += branch.probability
        elif "vol" in regime_hint and label in {"volatility_expansion", "panic_flush"}:
            aligned += branch.probability
        elif "liquidity" in regime_hint and label in {"liquidity_sweep_reversal", "panic_flush"}:
            aligned += branch.probability
    return clamp01(1.0 - aligned)


def build_state_transitions(*, regime_label: str, branches: list[ScenarioBranch]) -> list[StateTransition]:
    return [
        StateTransition(
            from_state=regime_label,
            to_state=branch.label,
            probability=branch.probability,
            horizon=branch.horizon,
            evidence={"expected_move_bps": branch.expected_move_bps, "execution_fragility": branch.execution_fragility},
        )
        for branch in branches
    ]


def horizon_top_states(branches: list[ScenarioBranch]) -> dict[str, str]:
    leaders: dict[str, tuple[str, float]] = {}
    for branch in branches:
        current = leaders.get(branch.horizon)
        if current is None or branch.probability > current[1]:
            leaders[branch.horizon] = (branch.label, branch.probability)
    return {horizon: label for horizon, (label, _prob) in leaders.items()}
