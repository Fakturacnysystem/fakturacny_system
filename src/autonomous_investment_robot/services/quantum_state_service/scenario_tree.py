from __future__ import annotations

from datetime import datetime

from autonomous_investment_robot.core.contracts import ScenarioBranch, ScenarioTree
from autonomous_investment_robot.services.quantum_state_service.probability_field import build_probability_field, normalize
from autonomous_investment_robot.services.quantum_state_service.state_transition_engine import (
    branch_disagreement_score,
    build_confidence_decomposition,
    build_state_transitions,
    horizon_top_states,
    scenario_drift_score,
)


def _branch_horizon(label: str) -> str:
    if label in {"failed_breakout", "liquidity_sweep_reversal", "panic_flush", "squeeze"}:
        return "ultra_short"
    if label in {"bullish_continuation", "mean_reversion_snapback", "volatility_expansion"}:
        return "short"
    return "tactical"


def _branch_move(label: str, mu_bps: float, ret1_bps: float, ret3_bps: float, vol_bps: float, flow: float) -> float:
    sign = 1.0 if mu_bps >= 0.0 else -1.0
    if label == "bullish_continuation":
        return max(abs(mu_bps), abs(ret3_bps) * 0.7) * max(0.3, sign)
    if label == "failed_breakout":
        return -max(abs(ret3_bps) * 0.8, 6.0)
    if label == "mean_reversion_snapback":
        base = -ret1_bps if abs(ret1_bps) > 1e-9 else -mu_bps * 0.5
        return base or 4.0
    if label == "volatility_expansion":
        return sign * max(abs(mu_bps), vol_bps * 0.35)
    if label == "liquidity_sweep_reversal":
        return (-1.0 if flow >= 0.0 else 1.0) * max(8.0, abs(flow) * 12.0)
    if label == "dead_market_drift":
        return mu_bps * 0.15
    if label == "panic_flush":
        return -max(abs(mu_bps), vol_bps * 0.45, 8.0)
    if label == "squeeze":
        return (1.0 if flow >= 0.0 else -1.0) * max(abs(mu_bps), vol_bps * 0.3, 6.0)
    return mu_bps


def build_scenario_tree(
    *,
    symbol: str,
    ts: datetime,
    features: dict[str, float],
    forecast: object,
    regime_assessment: object,
    execution_quality: object,
    portfolio_allocation: object | None = None,
) -> ScenarioTree:
    mu_bps = float(getattr(forecast, "mu", 0.0)) * 10000.0
    ret1_bps = float(features.get("ret_1", 0.0)) * 10000.0
    ret3_bps = float(features.get("ret_3", 0.0)) * 10000.0
    vol_bps = float(features.get("realized_vol", 0.0)) * 10000.0
    flow = float(features.get("flow_imbalance", 0.0))
    spread_bps = float(features.get("spread_proxy", 0.0)) * 10000.0
    liquidations = float(features.get("liquidations", 0.0))
    regime_label = str(getattr(regime_assessment, "label", "mean_reversion"))
    fill_probability = float(getattr(execution_quality, "fill_probability", 0.5))

    raw = {
        "bullish_continuation": 0.14 + max(mu_bps, 0.0) / 90.0 + (0.18 if regime_label == "trend" else 0.0),
        "failed_breakout": 0.10 + (0.22 if regime_label == "fake_breakout" else 0.0) + (0.08 if flow * ret3_bps < 0.0 else 0.0),
        "mean_reversion_snapback": 0.12 + min(abs(ret1_bps) / 80.0, 0.2) + (0.16 if regime_label in {"mean_reversion", "low_vol_chop"} else 0.0),
        "volatility_expansion": 0.12 + min(vol_bps / 120.0, 0.22) + (0.18 if regime_label in {"high_vol_expansion", "news_chaos"} else 0.0),
        "liquidity_sweep_reversal": 0.08 + min(liquidations / 120000.0, 0.2) + (0.16 if regime_label == "liquidity_vacuum" else 0.0),
        "dead_market_drift": 0.08 + (0.28 if regime_label == "dead_market" else 0.0) + (0.08 if abs(mu_bps) < 4.0 else 0.0),
        "panic_flush": 0.08 + (0.28 if regime_label in {"liquidity_vacuum", "news_chaos"} else 0.0) + max(-mu_bps, 0.0) / 100.0,
        "squeeze": 0.08 + max(abs(flow) - 0.2, 0.0) * 0.35 + (0.08 if spread_bps <= 6.0 else 0.0),
    }
    probabilities = normalize(raw)
    fragility = max(0.0, min(1.0, (1.0 - fill_probability) + spread_bps / 40.0))

    branches = []
    for label, probability in probabilities.items():
        expected_move = _branch_move(label, mu_bps, ret1_bps, ret3_bps, vol_bps, flow)
        branches.append(
            ScenarioBranch(
                horizon=_branch_horizon(label),
                label=label,
                probability=probability,
                expected_move_bps=expected_move,
                expected_duration_minutes=2.0 if _branch_horizon(label) == "ultra_short" else (12.0 if _branch_horizon(label) == "short" else 45.0),
                downside_risk_bps=max(4.0, abs(expected_move) * 0.75),
                execution_fragility=max(0.0, min(1.0, fragility + (0.15 if label in {"panic_flush", "liquidity_sweep_reversal"} else 0.0))),
                evidence={"regime_label": regime_label, "fill_probability": fill_probability},
            )
        )

    dominant = max(branches, key=lambda item: item.probability).label if branches else "dead_market_drift"
    transitions = build_state_transitions(regime_label=regime_label, branches=branches)
    confidence = build_confidence_decomposition(
        forecast=forecast,
        regime_assessment=regime_assessment,
        execution_quality=execution_quality,
        features=features,
        portfolio_allocation=portfolio_allocation,
    )
    disagreement = branch_disagreement_score(branches)
    drift = scenario_drift_score(regime_label=regime_label, branches=branches)
    field = build_probability_field(
        symbol,
        ts,
        branches,
        confidence_decomposition=confidence,
        branch_disagreement_score=disagreement,
        scenario_drift_score=drift,
    )
    top_states = horizon_top_states(branches)
    return ScenarioTree(
        symbol=symbol,
        ts=ts,
        branches=branches,
        transitions=transitions,
        probability_field=field,
        dominant_state=dominant,
        metadata={"heuristic": True, "top_states": top_states},
    )
