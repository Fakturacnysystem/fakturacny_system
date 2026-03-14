from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
import math
from typing import Any, Mapping


LOGGER = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    if not math.isfinite(out):
        return float(default)
    return float(out)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, _safe_float(value, lo)))


def _normalize_market_class(value: str) -> str:
    cls = str(value or "crypto_spot").strip().lower()
    if cls in {"xstocks", "x_stock", "xstocks_equity"}:
        return "xstock"
    if cls in {"xstock_etfs", "xstocks_etf"}:
        return "xstock_etf"
    if cls in {"crypto", "spot"}:
        return "crypto_spot"
    return cls or "crypto_spot"


@dataclass(frozen=True)
class PathRiskProfile:
    """Path-aware risk profile for one simulated decision scenario."""

    interim_drawdown_risk: float
    false_breakout_risk: float
    signal_decay_risk: float
    adverse_move_risk: float
    expected_path_quality: float


@dataclass(frozen=True)
class ExecutionScenario:
    """Execution-path properties for a simulated decision scenario."""

    order_type: str
    fill_probability: float
    adverse_selection_risk: float
    execution_path_cost_bps: float
    latency_sensitivity: float


@dataclass(frozen=True)
class DecisionScenario:
    """Counterfactual decision scenario used by arbitration."""

    scenario_id: str
    action: str
    side: str
    expected_net_edge_bps: float
    fill_probability: float
    slippage_risk_bps: float
    adverse_move_risk_bps: float
    expected_confidence_decay: float
    expected_path_quality: float
    path_risk: PathRiskProfile
    execution: ExecutionScenario
    diagnostics: dict[str, float] = field(default_factory=dict)

    def utility(self) -> float:
        """Scenario utility score used for ranking."""

        edge_term = self.expected_net_edge_bps * _clamp(self.fill_probability, 0.0, 1.0)
        risk_term = (
            6.0 * _clamp(self.path_risk.interim_drawdown_risk, 0.0, 1.0)
            + 4.0 * _clamp(self.path_risk.false_breakout_risk, 0.0, 1.0)
            + 4.0 * _clamp(self.path_risk.signal_decay_risk, 0.0, 1.0)
            + 4.0 * _clamp(self.execution.adverse_selection_risk, 0.0, 1.0)
        )
        quality_bonus = 8.0 * _clamp(self.expected_path_quality, 0.0, 1.0)
        decay_penalty = 6.0 * _clamp(self.expected_confidence_decay, 0.0, 1.0)
        return edge_term + quality_bonus - risk_term - decay_penalty

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["utility"] = float(self.utility())
        return out


@dataclass(frozen=True)
class CausalExplanation:
    """Causal explanation object with ranked hypotheses and confidence."""

    primary_driver: str
    confidence: float
    hypotheses: list[dict[str, float | str]]
    driver_scores: dict[str, float]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketTwinSnapshot:
    """Full market-twin snapshot for one decision tick."""

    timestamp: float
    symbol: str
    market_class: str
    regime: str
    market_state: dict[str, Any]
    causal_explanation: CausalExplanation
    scenarios: list[DecisionScenario]
    best_scenario_id: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def best_scenario(self) -> DecisionScenario | None:
        for scenario in self.scenarios:
            if scenario.scenario_id == self.best_scenario_id:
                return scenario
        return self.scenarios[0] if self.scenarios else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": float(self.timestamp),
            "symbol": str(self.symbol),
            "market_class": str(self.market_class),
            "regime": str(self.regime),
            "market_state": dict(self.market_state),
            "causal_explanation": self.causal_explanation.to_dict(),
            "best_scenario_id": str(self.best_scenario_id),
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
            "diagnostics": dict(self.diagnostics),
        }


def build_market_twin_state(
    *,
    symbol: str,
    market_class: str,
    regime: str,
    market_state: Mapping[str, Any],
    nowcast: Mapping[str, float],
    fused_features: Mapping[str, float],
    confidence: float,
    uncertainty_bps: float,
    liquidity_pressure: float,
) -> dict[str, Any]:
    """Build normalized live market twin state from runtime features."""

    state = {
        "symbol": str(symbol),
        "market_class": _normalize_market_class(market_class),
        "regime": str(regime),
        "state": str(market_state.get("state", "balanced")),
        "trend_bps": _safe_float(market_state.get("trend_bps"), 0.0),
        "vol": max(0.0, _safe_float(market_state.get("vol"), 0.0)),
        "spread_bps": max(0.0, _safe_float(market_state.get("spread_bps"), 0.0)),
        "liquidity_state": str(market_state.get("liquidity_state", "normal")),
        "order_flow_pressure": _clamp(_safe_float(nowcast.get("order_flow_pressure"), 0.0), -1.0, 1.0),
        "execution_urgency": _clamp(_safe_float(nowcast.get("execution_urgency"), 0.0), 0.0, 1.0),
        "market_state_confidence": _clamp(_safe_float(nowcast.get("market_state_confidence"), 0.0), 0.0, 1.0),
        "confidence": _clamp(confidence, 0.0, 1.0),
        "uncertainty_bps": max(0.0, _safe_float(uncertainty_bps, 0.0)),
        "liquidity_pressure": _clamp(_safe_float(liquidity_pressure, 0.0), -1.0, 1.0),
        "multimodal_score": _clamp(_safe_float(fused_features.get("multimodal_score"), 0.0), -2.0, 2.0),
        "multimodal_quality": _clamp(_safe_float(fused_features.get("multimodal_quality"), 0.0), 0.0, 1.0),
        "ret_1": _safe_float(fused_features.get("ret_1"), 0.0),
        "ret_3": _safe_float(fused_features.get("ret_3"), 0.0),
        "realized_vol": max(0.0, _safe_float(fused_features.get("realized_vol"), 0.0)),
        "flow_imbalance": _clamp(_safe_float(fused_features.get("flow_imbalance"), 0.0), -1.0, 1.0),
        "macro_risk_on": _clamp(_safe_float(fused_features.get("macro_macro_risk_on"), 0.0), -1.0, 1.0),
        "sentiment_score": _clamp(_safe_float(fused_features.get("sent_sentiment_score"), 0.0), -1.0, 1.0),
        "portfolio_corr_proxy": _clamp(_safe_float(fused_features.get("portfolio_corr_proxy"), 0.0), -1.0, 1.0),
    }
    return state


def score_causal_hypotheses(state: Mapping[str, Any]) -> dict[str, float]:
    """Score likely causal hypotheses from market twin state."""

    trend_bps = _safe_float(state.get("trend_bps"), 0.0)
    flow = _safe_float(state.get("order_flow_pressure"), _safe_float(state.get("flow_imbalance"), 0.0))
    spread_bps = max(0.0, _safe_float(state.get("spread_bps"), 0.0))
    vol = max(0.0, _safe_float(state.get("vol"), _safe_float(state.get("realized_vol"), 0.0)))
    liq = _safe_float(state.get("liquidity_pressure"), 0.0)
    multimodal = _safe_float(state.get("multimodal_score"), 0.0)
    macro = _safe_float(state.get("macro_risk_on"), 0.0)
    sentiment = _safe_float(state.get("sentiment_score"), 0.0)

    squeeze = _clamp((abs(trend_bps) / 80.0) + (0.5 * max(0.0, liq)) - (spread_bps / 140.0), 0.0, 1.0)
    flow_impulse = _clamp(abs(flow) * (1.0 + min(0.8, abs(trend_bps) / 120.0)), 0.0, 1.0)
    cross_market = _clamp(abs(0.6 * macro + 0.4 * sentiment) * (1.0 + 0.4 * abs(multimodal)), 0.0, 1.0)
    fake_breakout = _clamp((abs(trend_bps) / 90.0) + (spread_bps / 120.0) + max(0.0, -liq) - 0.7 * abs(flow), 0.0, 1.0)
    vol_shock = _clamp((vol / 0.02) + (spread_bps / 150.0), 0.0, 1.0)
    range_reversion = _clamp((1.0 - min(1.0, abs(trend_bps) / 70.0)) * (1.0 - min(1.0, vol / 0.02)), 0.0, 1.0)
    return {
        "liquidity_squeeze_breakout": squeeze,
        "order_flow_impulse": flow_impulse,
        "cross_market_driver": cross_market,
        "fake_breakout_risk": fake_breakout,
        "volatility_shock": vol_shock,
        "range_reversion": range_reversion,
    }


def estimate_causal_drivers(state: Mapping[str, Any]) -> list[dict[str, float | str]]:
    """Estimate and rank likely active causal drivers."""

    scores = score_causal_hypotheses(state)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    out: list[dict[str, float | str]] = []
    for name, score in ranked:
        out.append({"driver": str(name), "score": float(score)})
    return out


def build_causal_explanation(
    *,
    state: Mapping[str, Any],
    ranked_drivers: list[dict[str, float | str]],
) -> CausalExplanation:
    """Build causal explanation payload from ranked hypotheses."""

    primary = str(ranked_drivers[0]["driver"]) if ranked_drivers else "unknown"
    primary_score = _safe_float(ranked_drivers[0]["score"], 0.0) if ranked_drivers else 0.0
    confidence = _clamp(0.55 + 0.35 * primary_score, 0.05, 0.95)
    scores = score_causal_hypotheses(state)
    notes = "Probabilistic causal attribution from market twin features."
    return CausalExplanation(
        primary_driver=primary,
        confidence=confidence,
        hypotheses=list(ranked_drivers[:5]),
        driver_scores=scores,
        notes=notes,
    )


def estimate_interim_drawdown_risk(
    *,
    volatility_bps: float,
    uncertainty_bps: float,
    horizon_s: float,
    regime: str,
) -> float:
    """Estimate interim drawdown probability proxy in [0,1]."""

    vol_term = _clamp(max(0.0, volatility_bps) / 120.0, 0.0, 1.0)
    uq_term = _clamp(max(0.0, uncertainty_bps) / 220.0, 0.0, 1.0)
    horizon_term = _clamp(max(1.0, horizon_s) / 180.0, 0.0, 1.0)
    regime_mult = 1.25 if regime in {"PANIC", "HIGH_VOL"} else 0.80 if regime in {"COMPRESSION"} else 1.0
    return _clamp((0.45 * vol_term + 0.35 * uq_term + 0.20 * horizon_term) * regime_mult, 0.0, 1.0)


def estimate_false_breakout_risk(
    *,
    trend_bps: float,
    flow_imbalance: float,
    spread_bps: float,
    liquidity_pressure: float,
    regime: str,
) -> float:
    """Estimate probability proxy that breakout signal is fake."""

    trend_term = _clamp(abs(trend_bps) / 120.0, 0.0, 1.0)
    unsupported_move = _clamp(1.0 - min(1.0, abs(flow_imbalance)), 0.0, 1.0)
    spread_term = _clamp(spread_bps / 120.0, 0.0, 1.0)
    liq_term = _clamp(max(0.0, -liquidity_pressure), 0.0, 1.0)
    regime_term = 0.2 if regime in {"RANGE", "CHOP"} else 0.0
    return _clamp(0.4 * trend_term + 0.25 * unsupported_move + 0.2 * spread_term + 0.15 * liq_term + regime_term, 0.0, 1.0)


def estimate_signal_decay_risk(
    *,
    signal_age_s: float,
    cadence_s: float,
    regime: str,
    market_class: str,
) -> float:
    """Estimate signal-decay risk in [0,1]."""

    age = max(0.0, _safe_float(signal_age_s, 0.0))
    cadence = max(1.0, _safe_float(cadence_s, 5.0))
    age_term = _clamp(age / (3.0 * cadence), 0.0, 1.0)
    regime_mult = 1.20 if regime in {"PANIC", "HIGH_VOL"} else 0.9 if regime in {"TREND", "BULL_TREND"} else 1.0
    class_mult = 1.15 if _normalize_market_class(market_class).startswith("xstock") else 1.0
    return _clamp(age_term * regime_mult * class_mult, 0.0, 1.0)


def estimate_fill_probability(
    *,
    order_type: str,
    spread_bps: float,
    depth_notional: float,
    liquidity_pressure: float,
    horizon_s: float,
    market_class: str,
) -> float:
    """Estimate fill probability for execution scenario."""

    spread = max(0.0, _safe_float(spread_bps, 0.0))
    depth = max(0.0, _safe_float(depth_notional, 0.0))
    liq = _safe_float(liquidity_pressure, 0.0)
    depth_term = _clamp(depth / 1200.0, 0.0, 1.0)
    spread_term = _clamp(1.0 - spread / 120.0, 0.0, 1.0)
    liq_term = _clamp(0.5 + 0.5 * liq, 0.0, 1.0)
    horizon_term = _clamp(max(1.0, horizon_s) / 120.0, 0.1, 1.0)
    cls = _normalize_market_class(market_class)
    class_mult = 0.92 if cls.startswith("xstock") else 1.0
    base = 0.35 * depth_term + 0.30 * spread_term + 0.20 * liq_term + 0.15 * horizon_term
    if order_type == "market":
        return _clamp(0.90 + 0.08 * spread_term, 0.65, 0.99)
    if order_type == "limit":
        return _clamp(base * class_mult, 0.05, 0.96)
    return _clamp(0.70 * base * class_mult, 0.05, 0.95)


def estimate_adverse_selection_risk(
    *,
    order_type: str,
    flow_imbalance: float,
    latency_risk: float,
    regime: str,
) -> float:
    """Estimate adverse selection risk proxy in [0,1]."""

    flow = abs(_safe_float(flow_imbalance, 0.0))
    lat = _clamp(_safe_float(latency_risk, 0.0), 0.0, 1.0)
    base = 0.45 * flow + 0.40 * lat + (0.15 if regime in {"PANIC", "HIGH_VOL"} else 0.0)
    if order_type == "market":
        base += 0.12
    return _clamp(base, 0.0, 1.0)


def estimate_execution_path_cost(
    *,
    fee_bps: float,
    slippage_bps: float,
    spread_bps: float,
    order_type: str,
    market_class: str,
    liquidity_pressure: float,
    expected_wait_s: float,
) -> float:
    """Estimate execution-path cost including spread, impact and wait penalty."""

    fee = max(0.0, _safe_float(fee_bps, 0.0))
    slip = max(0.0, _safe_float(slippage_bps, 0.0))
    spread = max(0.0, _safe_float(spread_bps, 0.0))
    liq = _safe_float(liquidity_pressure, 0.0)
    wait_s = max(0.0, _safe_float(expected_wait_s, 0.0))
    half_spread = 0.5 * spread
    if order_type == "limit":
        spread_cost = 0.25 * spread
        impact = max(0.0, 1.2 - 0.9 * liq)
    elif order_type == "market":
        spread_cost = half_spread
        impact = max(0.0, 2.0 - 0.7 * liq)
    else:
        spread_cost = 0.40 * spread
        impact = max(0.0, 1.6 - 0.8 * liq)
    class_mult = 1.10 if _normalize_market_class(market_class).startswith("xstock") else 1.0
    wait_penalty = min(3.0, wait_s / 45.0)
    return max(0.0, (fee + slip + spread_cost + impact + wait_penalty) * class_mult)


def forecast_trade_path(
    *,
    trend_bps: float,
    volatility_bps: float,
    uncertainty_bps: float,
    signal_age_s: float,
    cadence_s: float,
    regime: str,
    market_class: str,
    flow_imbalance: float,
    spread_bps: float,
    liquidity_pressure: float,
) -> PathRiskProfile:
    """Forecast short-horizon trade path risk profile."""

    interim_dd = estimate_interim_drawdown_risk(
        volatility_bps=volatility_bps,
        uncertainty_bps=uncertainty_bps,
        horizon_s=max(20.0, 2.0 * _safe_float(cadence_s, 5.0)),
        regime=regime,
    )
    false_breakout = estimate_false_breakout_risk(
        trend_bps=trend_bps,
        flow_imbalance=flow_imbalance,
        spread_bps=spread_bps,
        liquidity_pressure=liquidity_pressure,
        regime=regime,
    )
    decay = estimate_signal_decay_risk(
        signal_age_s=signal_age_s,
        cadence_s=cadence_s,
        regime=regime,
        market_class=market_class,
    )
    adverse_move = _clamp(0.45 * interim_dd + 0.35 * false_breakout + 0.20 * decay, 0.0, 1.0)
    quality = _clamp(1.0 - (0.5 * interim_dd + 0.35 * false_breakout + 0.25 * decay), 0.0, 1.0)
    return PathRiskProfile(
        interim_drawdown_risk=interim_dd,
        false_breakout_risk=false_breakout,
        signal_decay_risk=decay,
        adverse_move_risk=adverse_move,
        expected_path_quality=quality,
    )


def _build_execution_scenario(
    *,
    order_type: str,
    spread_bps: float,
    depth_notional: float,
    liquidity_pressure: float,
    flow_imbalance: float,
    latency_risk: float,
    regime: str,
    market_class: str,
    fee_bps: float,
    slippage_bps: float,
    expected_wait_s: float,
) -> ExecutionScenario:
    fill_probability = estimate_fill_probability(
        order_type=order_type,
        spread_bps=spread_bps,
        depth_notional=depth_notional,
        liquidity_pressure=liquidity_pressure,
        horizon_s=max(5.0, expected_wait_s),
        market_class=market_class,
    )
    adverse_selection = estimate_adverse_selection_risk(
        order_type=order_type,
        flow_imbalance=flow_imbalance,
        latency_risk=latency_risk,
        regime=regime,
    )
    execution_cost = estimate_execution_path_cost(
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        order_type=order_type,
        market_class=market_class,
        liquidity_pressure=liquidity_pressure,
        expected_wait_s=expected_wait_s,
    )
    return ExecutionScenario(
        order_type=order_type,
        fill_probability=fill_probability,
        adverse_selection_risk=adverse_selection,
        execution_path_cost_bps=execution_cost,
        latency_sensitivity=_clamp(latency_risk, 0.0, 1.0),
    )


def _make_scenario(
    *,
    scenario_id: str,
    action: str,
    side: str,
    projected_edge_bps: float,
    execution: ExecutionScenario,
    path: PathRiskProfile,
    confidence_decay: float,
    edge_adjust_bps: float = 0.0,
) -> DecisionScenario:
    net_edge = projected_edge_bps + edge_adjust_bps - execution.execution_path_cost_bps - 8.0 * path.adverse_move_risk
    return DecisionScenario(
        scenario_id=scenario_id,
        action=action,
        side=side,
        expected_net_edge_bps=float(net_edge),
        fill_probability=float(execution.fill_probability),
        slippage_risk_bps=float(max(0.0, execution.execution_path_cost_bps * 0.35)),
        adverse_move_risk_bps=float(25.0 * path.adverse_move_risk),
        expected_confidence_decay=float(_clamp(confidence_decay, 0.0, 1.0)),
        expected_path_quality=float(path.expected_path_quality),
        path_risk=path,
        execution=execution,
        diagnostics={
            "execution_cost_bps": float(execution.execution_path_cost_bps),
            "path_adverse_move_risk": float(path.adverse_move_risk),
        },
    )


def simulate_entry_now(
    *,
    projected_edge_bps: float,
    market_state: Mapping[str, Any],
    fee_bps: float,
    slippage_bps: float,
    spread_bps: float,
    depth_notional: float,
    liquidity_pressure: float,
    latency_risk: float,
    signal_age_s: float,
    cadence_s: float,
    market_class: str,
) -> DecisionScenario:
    """Simulate immediate market-entry scenario."""

    regime = str(market_state.get("regime", "RANGE"))
    path = forecast_trade_path(
        trend_bps=_safe_float(market_state.get("trend_bps"), 0.0),
        volatility_bps=max(1.0, 10000.0 * _safe_float(market_state.get("vol"), 0.0)),
        uncertainty_bps=max(1.0, _safe_float(market_state.get("uncertainty_bps"), 80.0)),
        signal_age_s=signal_age_s,
        cadence_s=cadence_s,
        regime=regime,
        market_class=market_class,
        flow_imbalance=_safe_float(market_state.get("order_flow_pressure"), 0.0),
        spread_bps=spread_bps,
        liquidity_pressure=liquidity_pressure,
    )
    execution = _build_execution_scenario(
        order_type="market",
        spread_bps=spread_bps,
        depth_notional=depth_notional,
        liquidity_pressure=liquidity_pressure,
        flow_imbalance=_safe_float(market_state.get("order_flow_pressure"), 0.0),
        latency_risk=latency_risk,
        regime=regime,
        market_class=market_class,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        expected_wait_s=2.0,
    )
    return _make_scenario(
        scenario_id="entry_now_market",
        action="enter_market",
        side="buy",
        projected_edge_bps=projected_edge_bps,
        execution=execution,
        path=path,
        confidence_decay=path.signal_decay_risk * 0.75,
        edge_adjust_bps=0.0,
    )


def simulate_limit_entry(
    *,
    projected_edge_bps: float,
    market_state: Mapping[str, Any],
    fee_bps: float,
    slippage_bps: float,
    spread_bps: float,
    depth_notional: float,
    liquidity_pressure: float,
    latency_risk: float,
    signal_age_s: float,
    cadence_s: float,
    market_class: str,
) -> DecisionScenario:
    """Simulate immediate limit-entry scenario."""

    regime = str(market_state.get("regime", "RANGE"))
    path = forecast_trade_path(
        trend_bps=_safe_float(market_state.get("trend_bps"), 0.0),
        volatility_bps=max(1.0, 10000.0 * _safe_float(market_state.get("vol"), 0.0)),
        uncertainty_bps=max(1.0, _safe_float(market_state.get("uncertainty_bps"), 80.0)),
        signal_age_s=signal_age_s + 0.4 * cadence_s,
        cadence_s=cadence_s,
        regime=regime,
        market_class=market_class,
        flow_imbalance=_safe_float(market_state.get("order_flow_pressure"), 0.0),
        spread_bps=spread_bps,
        liquidity_pressure=liquidity_pressure,
    )
    execution = _build_execution_scenario(
        order_type="limit",
        spread_bps=spread_bps,
        depth_notional=depth_notional,
        liquidity_pressure=liquidity_pressure,
        flow_imbalance=_safe_float(market_state.get("order_flow_pressure"), 0.0),
        latency_risk=latency_risk,
        regime=regime,
        market_class=market_class,
        fee_bps=fee_bps,
        slippage_bps=max(0.1, slippage_bps * 0.7),
        expected_wait_s=max(3.0, 0.7 * cadence_s),
    )
    return _make_scenario(
        scenario_id="entry_now_limit",
        action="enter_limit",
        side="buy",
        projected_edge_bps=projected_edge_bps,
        execution=execution,
        path=path,
        confidence_decay=min(1.0, path.signal_decay_risk * 1.05),
        edge_adjust_bps=1.5,
    )


def simulate_wait_one_cadence(
    *,
    projected_edge_bps: float,
    market_state: Mapping[str, Any],
    fee_bps: float,
    slippage_bps: float,
    spread_bps: float,
    depth_notional: float,
    liquidity_pressure: float,
    latency_risk: float,
    signal_age_s: float,
    cadence_s: float,
    market_class: str,
) -> DecisionScenario:
    """Simulate waiting one cadence before entry."""

    regime = str(market_state.get("regime", "RANGE"))
    path = forecast_trade_path(
        trend_bps=_safe_float(market_state.get("trend_bps"), 0.0) * 0.85,
        volatility_bps=max(1.0, 10000.0 * _safe_float(market_state.get("vol"), 0.0)),
        uncertainty_bps=max(1.0, _safe_float(market_state.get("uncertainty_bps"), 80.0) * 1.05),
        signal_age_s=signal_age_s + cadence_s,
        cadence_s=cadence_s,
        regime=regime,
        market_class=market_class,
        flow_imbalance=_safe_float(market_state.get("order_flow_pressure"), 0.0),
        spread_bps=spread_bps,
        liquidity_pressure=liquidity_pressure,
    )
    execution = _build_execution_scenario(
        order_type="limit",
        spread_bps=spread_bps,
        depth_notional=depth_notional,
        liquidity_pressure=liquidity_pressure,
        flow_imbalance=_safe_float(market_state.get("order_flow_pressure"), 0.0),
        latency_risk=latency_risk,
        regime=regime,
        market_class=market_class,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        expected_wait_s=max(5.0, cadence_s),
    )
    edge_decay_penalty = -2.0 - 3.0 * path.signal_decay_risk
    return _make_scenario(
        scenario_id="wait_one_cadence",
        action="wait_one_cadence",
        side="buy",
        projected_edge_bps=projected_edge_bps,
        execution=execution,
        path=path,
        confidence_decay=min(1.0, 0.20 + path.signal_decay_risk),
        edge_adjust_bps=edge_decay_penalty,
    )


def simulate_scale_in_entry(
    *,
    projected_edge_bps: float,
    market_state: Mapping[str, Any],
    fee_bps: float,
    slippage_bps: float,
    spread_bps: float,
    depth_notional: float,
    liquidity_pressure: float,
    latency_risk: float,
    signal_age_s: float,
    cadence_s: float,
    market_class: str,
) -> DecisionScenario:
    """Simulate scaled entry (fragmented execution)."""

    regime = str(market_state.get("regime", "RANGE"))
    path = forecast_trade_path(
        trend_bps=_safe_float(market_state.get("trend_bps"), 0.0),
        volatility_bps=max(1.0, 10000.0 * _safe_float(market_state.get("vol"), 0.0)),
        uncertainty_bps=max(1.0, _safe_float(market_state.get("uncertainty_bps"), 80.0) * 0.95),
        signal_age_s=signal_age_s + 0.5 * cadence_s,
        cadence_s=cadence_s,
        regime=regime,
        market_class=market_class,
        flow_imbalance=_safe_float(market_state.get("order_flow_pressure"), 0.0),
        spread_bps=spread_bps,
        liquidity_pressure=liquidity_pressure,
    )
    execution = _build_execution_scenario(
        order_type="mixed",
        spread_bps=spread_bps,
        depth_notional=depth_notional,
        liquidity_pressure=liquidity_pressure,
        flow_imbalance=_safe_float(market_state.get("order_flow_pressure"), 0.0),
        latency_risk=latency_risk,
        regime=regime,
        market_class=market_class,
        fee_bps=fee_bps,
        slippage_bps=max(0.1, slippage_bps * 0.85),
        expected_wait_s=max(4.0, 0.5 * cadence_s),
    )
    return _make_scenario(
        scenario_id="scale_in_entry",
        action="scale_in_entry",
        side="buy",
        projected_edge_bps=projected_edge_bps * 0.9,
        execution=execution,
        path=path,
        confidence_decay=min(1.0, path.signal_decay_risk * 0.95),
        edge_adjust_bps=0.8,
    )


def simulate_skip_decision(
    *,
    market_state: Mapping[str, Any],
    cadence_s: float,
    market_class: str,
) -> DecisionScenario:
    """Simulate skip decision as baseline safe alternative."""

    regime = str(market_state.get("regime", "RANGE"))
    path = forecast_trade_path(
        trend_bps=0.0,
        volatility_bps=max(1.0, 10000.0 * _safe_float(market_state.get("vol"), 0.0)),
        uncertainty_bps=max(1.0, _safe_float(market_state.get("uncertainty_bps"), 80.0)),
        signal_age_s=0.0,
        cadence_s=cadence_s,
        regime=regime,
        market_class=market_class,
        flow_imbalance=0.0,
        spread_bps=max(0.0, _safe_float(market_state.get("spread_bps"), 0.0)),
        liquidity_pressure=_safe_float(market_state.get("liquidity_pressure"), 0.0),
    )
    execution = ExecutionScenario(
        order_type="none",
        fill_probability=1.0,
        adverse_selection_risk=0.0,
        execution_path_cost_bps=0.0,
        latency_sensitivity=0.0,
    )
    return _make_scenario(
        scenario_id="skip",
        action="skip",
        side="hold",
        projected_edge_bps=0.0,
        execution=execution,
        path=path,
        confidence_decay=0.0,
        edge_adjust_bps=0.0,
    )


def simulate_partial_exit(
    *,
    projected_exit_edge_bps: float,
    market_state: Mapping[str, Any],
    fee_bps: float,
    slippage_bps: float,
    spread_bps: float,
    depth_notional: float,
    liquidity_pressure: float,
    latency_risk: float,
    cadence_s: float,
    market_class: str,
) -> DecisionScenario:
    """Simulate partial position exit scenario."""

    regime = str(market_state.get("regime", "RANGE"))
    path = forecast_trade_path(
        trend_bps=-_safe_float(market_state.get("trend_bps"), 0.0),
        volatility_bps=max(1.0, 10000.0 * _safe_float(market_state.get("vol"), 0.0)),
        uncertainty_bps=max(1.0, _safe_float(market_state.get("uncertainty_bps"), 80.0)),
        signal_age_s=0.0,
        cadence_s=cadence_s,
        regime=regime,
        market_class=market_class,
        flow_imbalance=-_safe_float(market_state.get("order_flow_pressure"), 0.0),
        spread_bps=spread_bps,
        liquidity_pressure=liquidity_pressure,
    )
    execution = _build_execution_scenario(
        order_type="market",
        spread_bps=spread_bps,
        depth_notional=depth_notional,
        liquidity_pressure=liquidity_pressure,
        flow_imbalance=-_safe_float(market_state.get("order_flow_pressure"), 0.0),
        latency_risk=latency_risk,
        regime=regime,
        market_class=market_class,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        expected_wait_s=2.0,
    )
    return _make_scenario(
        scenario_id="partial_exit",
        action="partial_exit",
        side="sell",
        projected_edge_bps=projected_exit_edge_bps,
        execution=execution,
        path=path,
        confidence_decay=0.0,
        edge_adjust_bps=0.0,
    )


def simulate_full_exit(
    *,
    projected_exit_edge_bps: float,
    market_state: Mapping[str, Any],
    fee_bps: float,
    slippage_bps: float,
    spread_bps: float,
    depth_notional: float,
    liquidity_pressure: float,
    latency_risk: float,
    cadence_s: float,
    market_class: str,
) -> DecisionScenario:
    """Simulate full position exit scenario."""

    partial = simulate_partial_exit(
        projected_exit_edge_bps=projected_exit_edge_bps,
        market_state=market_state,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        depth_notional=depth_notional,
        liquidity_pressure=liquidity_pressure,
        latency_risk=latency_risk,
        cadence_s=cadence_s,
        market_class=market_class,
    )
    return DecisionScenario(
        scenario_id="full_exit",
        action="full_exit",
        side="sell",
        expected_net_edge_bps=partial.expected_net_edge_bps + 0.6,
        fill_probability=min(1.0, partial.fill_probability + 0.04),
        slippage_risk_bps=partial.slippage_risk_bps,
        adverse_move_risk_bps=partial.adverse_move_risk_bps,
        expected_confidence_decay=partial.expected_confidence_decay,
        expected_path_quality=partial.expected_path_quality,
        path_risk=partial.path_risk,
        execution=partial.execution,
        diagnostics={**partial.diagnostics, "full_exit_bonus_bps": 0.6},
    )


def generate_counterfactual_scenarios(
    *,
    market_state: Mapping[str, Any],
    projected_edge_bps: float,
    fee_bps: float,
    slippage_bps: float,
    spread_bps: float,
    depth_notional: float,
    liquidity_pressure: float,
    latency_risk: float,
    signal_age_s: float,
    cadence_s: float,
    market_class: str,
    has_position: bool,
    current_profit_bps: float,
    include_advanced: bool = True,
) -> list[DecisionScenario]:
    """Generate counterfactual decision scenarios for arbitration."""

    scenarios = [
        simulate_entry_now(
            projected_edge_bps=projected_edge_bps,
            market_state=market_state,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            spread_bps=spread_bps,
            depth_notional=depth_notional,
            liquidity_pressure=liquidity_pressure,
            latency_risk=latency_risk,
            signal_age_s=signal_age_s,
            cadence_s=cadence_s,
            market_class=market_class,
        ),
        simulate_limit_entry(
            projected_edge_bps=projected_edge_bps,
            market_state=market_state,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            spread_bps=spread_bps,
            depth_notional=depth_notional,
            liquidity_pressure=liquidity_pressure,
            latency_risk=latency_risk,
            signal_age_s=signal_age_s,
            cadence_s=cadence_s,
            market_class=market_class,
        ),
        simulate_wait_one_cadence(
            projected_edge_bps=projected_edge_bps,
            market_state=market_state,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            spread_bps=spread_bps,
            depth_notional=depth_notional,
            liquidity_pressure=liquidity_pressure,
            latency_risk=latency_risk,
            signal_age_s=signal_age_s,
            cadence_s=cadence_s,
            market_class=market_class,
        ),
        simulate_skip_decision(
            market_state=market_state,
            cadence_s=cadence_s,
            market_class=market_class,
        ),
    ]
    if include_advanced:
        scenarios.append(
            simulate_scale_in_entry(
                projected_edge_bps=projected_edge_bps,
                market_state=market_state,
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
                spread_bps=spread_bps,
                depth_notional=depth_notional,
                liquidity_pressure=liquidity_pressure,
                latency_risk=latency_risk,
                signal_age_s=signal_age_s,
                cadence_s=cadence_s,
                market_class=market_class,
            )
        )
    if has_position:
        projected_exit_edge = max(0.0, current_profit_bps) + 0.20 * max(0.0, projected_edge_bps)
        scenarios.append(
            simulate_partial_exit(
                projected_exit_edge_bps=projected_exit_edge,
                market_state=market_state,
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
                spread_bps=spread_bps,
                depth_notional=depth_notional,
                liquidity_pressure=liquidity_pressure,
                latency_risk=latency_risk,
                cadence_s=cadence_s,
                market_class=market_class,
            )
        )
        scenarios.append(
            simulate_full_exit(
                projected_exit_edge_bps=projected_exit_edge,
                market_state=market_state,
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
                spread_bps=spread_bps,
                depth_notional=depth_notional,
                liquidity_pressure=liquidity_pressure,
                latency_risk=latency_risk,
                cadence_s=cadence_s,
                market_class=market_class,
            )
        )
    return scenarios


def compare_decision_scenarios(left: DecisionScenario, right: DecisionScenario) -> float:
    """Compare two scenarios by utility score difference."""

    return float(left.utility() - right.utility())


def rank_decision_scenarios(scenarios: list[DecisionScenario]) -> list[DecisionScenario]:
    """Rank scenarios by utility, then by net edge."""

    return sorted(
        scenarios,
        key=lambda scenario: (scenario.utility(), scenario.expected_net_edge_bps),
        reverse=True,
    )


def choose_best_counterfactual_action(
    *,
    scenarios: list[DecisionScenario],
    min_counterfactual_edge_bps: float,
) -> DecisionScenario:
    """Choose best scenario with safe fallback to skip."""

    if not scenarios:
        return simulate_skip_decision(market_state={}, cadence_s=5.0, market_class="crypto_spot")
    ranked = rank_decision_scenarios(scenarios)
    best = ranked[0]
    if best.action in {"enter_market", "enter_limit", "scale_in_entry"} and best.expected_net_edge_bps < min_counterfactual_edge_bps:
        for scenario in ranked:
            if scenario.action in {"skip", "wait_one_cadence"}:
                return scenario
    return best


def attach_market_twin_diagnostics(
    *,
    diagnostics: dict[str, Any],
    snapshot: MarketTwinSnapshot,
) -> dict[str, Any]:
    """Attach market twin diagnostics into a decision diagnostics object."""

    out = dict(diagnostics)
    best = snapshot.best_scenario()
    out["market_twin"] = {
        "symbol": snapshot.symbol,
        "market_class": snapshot.market_class,
        "regime": snapshot.regime,
        "primary_driver": snapshot.causal_explanation.primary_driver,
        "causal_confidence": snapshot.causal_explanation.confidence,
        "best_scenario_id": snapshot.best_scenario_id,
        "best_action": best.action if best is not None else "skip",
        "best_side": best.side if best is not None else "hold",
        "best_expected_net_edge_bps": best.expected_net_edge_bps if best is not None else 0.0,
        "best_fill_probability": best.fill_probability if best is not None else 1.0,
        "best_order_type": best.execution.order_type if best is not None else "none",
        "scenario_count": len(snapshot.scenarios),
        "top_scenarios": [scenario.to_dict() for scenario in rank_decision_scenarios(snapshot.scenarios)[:3]],
    }
    return out


def persist_market_twin_snapshot(
    *,
    model_state: dict[str, Any],
    snapshot: MarketTwinSnapshot,
    max_snapshots: int = 256,
) -> dict[str, Any]:
    """Persist market twin snapshot in bounded in-memory model state."""

    state = dict(model_state)
    history_raw = state.get("market_twin_snapshots", [])
    if not isinstance(history_raw, list):
        history_raw = []
    history = list(history_raw[-max(1, int(max_snapshots) - 1) :])
    history.append(snapshot.to_dict())
    state["market_twin_snapshots"] = history
    state["market_twin_latest"] = snapshot.to_dict()
    return state


class RealityStateBuilder:
    def build_market_twin_state(self, **kwargs: Any) -> dict[str, Any]:
        return build_market_twin_state(**kwargs)


class CausalDriverEstimator:
    def estimate_causal_drivers(self, state: Mapping[str, Any]) -> list[dict[str, float | str]]:
        """Estimate ranked causal drivers from normalized market twin state."""

        return estimate_causal_drivers(state)

    def score_causal_hypotheses(self, state: Mapping[str, Any]) -> dict[str, float]:
        """Score causal hypotheses from normalized market twin state."""

        return score_causal_hypotheses(state)


class PathForecastEngine:
    def forecast_trade_path(self, **kwargs: Any) -> PathRiskProfile:
        return forecast_trade_path(**kwargs)

    def estimate_interim_drawdown_risk(self, **kwargs: Any) -> float:
        return estimate_interim_drawdown_risk(**kwargs)

    def estimate_false_breakout_risk(self, **kwargs: Any) -> float:
        return estimate_false_breakout_risk(**kwargs)

    def estimate_signal_decay_risk(self, **kwargs: Any) -> float:
        return estimate_signal_decay_risk(**kwargs)


class ExecutionTwinEngine:
    def estimate_fill_probability(self, **kwargs: Any) -> float:
        return estimate_fill_probability(**kwargs)

    def estimate_adverse_selection_risk(self, **kwargs: Any) -> float:
        return estimate_adverse_selection_risk(**kwargs)

    def estimate_execution_path_cost(self, **kwargs: Any) -> float:
        return estimate_execution_path_cost(**kwargs)


class CounterfactualScenarioEngine:
    def generate_counterfactual_scenarios(self, **kwargs: Any) -> list[DecisionScenario]:
        return generate_counterfactual_scenarios(**kwargs)

    def simulate_entry_now(self, **kwargs: Any) -> DecisionScenario:
        return simulate_entry_now(**kwargs)

    def simulate_limit_entry(self, **kwargs: Any) -> DecisionScenario:
        return simulate_limit_entry(**kwargs)

    def simulate_wait_one_cadence(self, **kwargs: Any) -> DecisionScenario:
        return simulate_wait_one_cadence(**kwargs)

    def simulate_scale_in_entry(self, **kwargs: Any) -> DecisionScenario:
        return simulate_scale_in_entry(**kwargs)

    def simulate_skip_decision(self, **kwargs: Any) -> DecisionScenario:
        return simulate_skip_decision(**kwargs)

    def simulate_partial_exit(self, **kwargs: Any) -> DecisionScenario:
        return simulate_partial_exit(**kwargs)

    def simulate_full_exit(self, **kwargs: Any) -> DecisionScenario:
        return simulate_full_exit(**kwargs)


class DecisionArbitrationEngine:
    def compare_decision_scenarios(self, left: DecisionScenario, right: DecisionScenario) -> float:
        return compare_decision_scenarios(left, right)

    def rank_decision_scenarios(self, scenarios: list[DecisionScenario]) -> list[DecisionScenario]:
        return rank_decision_scenarios(scenarios)

    def choose_best_counterfactual_action(
        self,
        *,
        scenarios: list[DecisionScenario],
        min_counterfactual_edge_bps: float,
    ) -> DecisionScenario:
        return choose_best_counterfactual_action(
            scenarios=scenarios,
            min_counterfactual_edge_bps=min_counterfactual_edge_bps,
        )


class CausalMarketTwinEngine:
    """Live causal market twin with counterfactual action arbitration."""

    def __init__(
        self,
        *,
        min_counterfactual_edge_bps: float = 1.0,
        include_advanced_scenarios: bool = True,
        max_snapshots: int = 256,
    ) -> None:
        self.min_counterfactual_edge_bps = max(0.0, _safe_float(min_counterfactual_edge_bps, 1.0))
        self.include_advanced_scenarios = bool(include_advanced_scenarios)
        self.max_snapshots = max(32, int(max_snapshots))
        self.reality = RealityStateBuilder()
        self.causal = CausalDriverEstimator()
        self.scenarios = CounterfactualScenarioEngine()
        self.path = PathForecastEngine()
        self.execution = ExecutionTwinEngine()
        self.arbitration = DecisionArbitrationEngine()

    def evaluate(
        self,
        *,
        timestamp: float,
        symbol: str,
        market_class: str,
        regime: str,
        market_state: Mapping[str, Any],
        nowcast: Mapping[str, float],
        fused_features: Mapping[str, float],
        confidence: float,
        uncertainty_bps: float,
        liquidity_pressure: float,
        projected_edge_bps: float,
        fee_bps: float,
        slippage_bps: float,
        spread_bps: float,
        depth_notional: float,
        latency_risk: float,
        signal_age_s: float,
        cadence_s: float,
        has_position: bool,
        current_profit_bps: float,
    ) -> MarketTwinSnapshot:
        """Build live market twin snapshot and choose best counterfactual action."""

        reality_state = self.reality.build_market_twin_state(
            symbol=symbol,
            market_class=market_class,
            regime=regime,
            market_state=market_state,
            nowcast=nowcast,
            fused_features=fused_features,
            confidence=confidence,
            uncertainty_bps=uncertainty_bps,
            liquidity_pressure=liquidity_pressure,
        )
        ranked_drivers = self.causal.estimate_causal_drivers(reality_state)
        explanation = build_causal_explanation(state=reality_state, ranked_drivers=ranked_drivers)
        scenario_list = self.scenarios.generate_counterfactual_scenarios(
            market_state={**reality_state, "uncertainty_bps": uncertainty_bps},
            projected_edge_bps=projected_edge_bps,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            spread_bps=spread_bps,
            depth_notional=depth_notional,
            liquidity_pressure=liquidity_pressure,
            latency_risk=latency_risk,
            signal_age_s=signal_age_s,
            cadence_s=cadence_s,
            market_class=market_class,
            has_position=has_position,
            current_profit_bps=current_profit_bps,
            include_advanced=self.include_advanced_scenarios,
        )
        best = self.arbitration.choose_best_counterfactual_action(
            scenarios=scenario_list,
            min_counterfactual_edge_bps=self.min_counterfactual_edge_bps,
        )
        diagnostics = {
            "projected_edge_bps": float(projected_edge_bps),
            "min_counterfactual_edge_bps": float(self.min_counterfactual_edge_bps),
            "has_position": 1.0 if has_position else 0.0,
            "include_advanced_scenarios": 1.0 if self.include_advanced_scenarios else 0.0,
        }
        snapshot = MarketTwinSnapshot(
            timestamp=float(timestamp),
            symbol=str(symbol),
            market_class=_normalize_market_class(market_class),
            regime=str(regime),
            market_state=reality_state,
            causal_explanation=explanation,
            scenarios=rank_decision_scenarios(scenario_list),
            best_scenario_id=str(best.scenario_id),
            diagnostics=diagnostics,
        )
        LOGGER.debug(
            "market_twin_snapshot",
            extra={
                "symbol": snapshot.symbol,
                "market_class": snapshot.market_class,
                "regime": snapshot.regime,
                "best_scenario_id": snapshot.best_scenario_id,
            },
        )
        return snapshot
