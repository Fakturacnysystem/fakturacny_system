from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import logging
import math
from typing import Any, Mapping


LOGGER = logging.getLogger(__name__)


_NORMAL_Z = {
    0.01: -2.326,
    0.05: -1.645,
    0.1: -1.282,
    0.5: 0.0,
    0.9: 1.282,
    0.95: 1.645,
    0.99: 2.326,
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    if not math.isfinite(out):
        return float(default)
    return float(out)


@dataclass(frozen=True)
class DistributionForecast:
    """Parametric forecast represented as normal distribution in basis points."""

    mean_bps: float
    std_bps: float
    quantiles_bps: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ConformalInterval:
    """Conformal prediction interval around the point forecast."""

    lower_bps: float
    upper_bps: float
    alpha: float
    half_width_bps: float


@dataclass(frozen=True)
class UncertaintyEstimate:
    """Uncertainty decomposition used for decision gating."""

    aleatoric_bps: float
    epistemic_bps: float
    conformal_width_bps: float
    drift_penalty_bps: float
    total_bps: float


@dataclass(frozen=True)
class TradeSignal:
    """Decision-centric signal with explicit side and confidence."""

    action: str
    side: str
    score_bps: float
    confidence: float
    reason: str


@dataclass
class DecisionContext:
    """Per-tick runtime snapshot consumed by the central decision algorithm."""

    symbol: str
    now_ts: float
    bid: float
    ask: float
    mid: float
    spread_bps: float
    depth_notional: float
    features: dict[str, float]
    market_watch: dict[str, float]
    forecast_mu: float
    forecast_sigma: float
    forecast_confidence: float
    position_notional_quote: float = 0.0
    signed_exposure_notional_quote: float = 0.0
    avg_entry_price: float = 0.0
    position_age_s: float = 0.0
    current_profit_bps: float = 0.0
    drawdown_pct: float = 0.0
    quote_free: float = 0.0
    max_exposure_notional: float = 0.0
    order_cadence_s: float = 5.0
    last_submission_ts: float = 0.0
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    latency_ms: float = 0.0
    guards_mode: str = "strict"
    modeled_cost_floor_bps: float = 120.0
    sell_min_profit_bps: float = 120.0
    sell_target_profit_bps: float = 120.0


@dataclass(frozen=True)
class DecisionOutcome:
    """Output of the central decision brain."""

    action: str
    side: str
    skip_reason: str
    confidence: float
    uncertainty_bps: float
    drift_score: float
    regime: str
    position_size_scale: float
    recommended_notional_quote: float
    risk_flags: list[str]
    route: dict[str, Any]
    alpha_signals: dict[str, float]
    market_state: dict[str, Any]
    nowcast: dict[str, Any]
    forecast: dict[str, Any]
    conformal_interval: dict[str, float]
    execution_risk: dict[str, float]
    profit_protection: dict[str, Any]
    online_adaptation: dict[str, Any]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ingest_price_volume_features(features: Mapping[str, float]) -> dict[str, float]:
    """Extract normalized price/volume features with safe defaults."""

    return {
        "ret_1": _safe_float(features.get("ret_1"), 0.0),
        "ret_3": _safe_float(features.get("ret_3"), 0.0),
        "realized_vol": max(0.0, _safe_float(features.get("realized_vol"), 0.0)),
        "spread_proxy": max(0.0, _safe_float(features.get("spread_proxy"), 0.0)),
        "depth_notional": max(0.0, _safe_float(features.get("depth_notional"), 0.0)),
        "orderbook_imbalance": _clamp(_safe_float(features.get("orderbook_imbalance"), 0.0), -1.0, 1.0),
        "flow_imbalance": _clamp(_safe_float(features.get("flow_imbalance"), 0.0), -1.0, 1.0),
    }


def ingest_news_features(news_payload: Mapping[str, float] | None = None) -> dict[str, float]:
    """Extract optional news sentiment features."""

    payload = news_payload or {}
    return {
        "news_sentiment": _clamp(_safe_float(payload.get("sentiment"), 0.0), -1.0, 1.0),
        "news_surprise": _clamp(_safe_float(payload.get("surprise"), 0.0), -2.0, 2.0),
        "news_intensity": max(0.0, _safe_float(payload.get("intensity"), 0.0)),
    }


def ingest_macro_features(macro_payload: Mapping[str, float] | None = None) -> dict[str, float]:
    """Extract optional macro drivers."""

    payload = macro_payload or {}
    return {
        "macro_risk_on": _clamp(_safe_float(payload.get("risk_on"), 0.0), -1.0, 1.0),
        "macro_liquidity": _clamp(_safe_float(payload.get("liquidity"), 0.0), -1.0, 1.0),
        "macro_surprise": _clamp(_safe_float(payload.get("surprise"), 0.0), -2.0, 2.0),
    }


def ingest_fundamental_features(fundamental_payload: Mapping[str, float] | None = None) -> dict[str, float]:
    """Extract optional fundamentals/valuation signals."""

    payload = fundamental_payload or {}
    return {
        "fundamental_value_gap": _clamp(_safe_float(payload.get("value_gap"), 0.0), -3.0, 3.0),
        "fundamental_growth": _clamp(_safe_float(payload.get("growth"), 0.0), -2.0, 2.0),
        "fundamental_quality": _clamp(_safe_float(payload.get("quality"), 0.0), -2.0, 2.0),
    }


def fuse_multimodal_features(
    *,
    price_volume: Mapping[str, float],
    news: Mapping[str, float] | None = None,
    macro: Mapping[str, float] | None = None,
    fundamentals: Mapping[str, float] | None = None,
    sentiment: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Fuse multimodal signals into one normalized feature set."""

    fused = dict(price_volume)
    for key, value in (news or {}).items():
        fused[f"news_{key}"] = _safe_float(value, 0.0)
    for key, value in (macro or {}).items():
        fused[f"macro_{key}"] = _safe_float(value, 0.0)
    for key, value in (fundamentals or {}).items():
        fused[f"fund_{key}"] = _safe_float(value, 0.0)
    for key, value in (sentiment or {}).items():
        fused[f"sent_{key}"] = _safe_float(value, 0.0)
    fused["multimodal_score"] = (
        0.55 * _safe_float(fused.get("ret_3"), 0.0)
        + 0.25 * _safe_float(fused.get("flow_imbalance"), 0.0)
        + 0.10 * _safe_float(fused.get("news_news_sentiment"), 0.0)
        + 0.05 * _safe_float(fused.get("macro_macro_risk_on"), 0.0)
        + 0.05 * _safe_float(fused.get("fund_fundamental_growth"), 0.0)
    )
    return fused


def analyze_order_flow_imbalance(
    *,
    bid_size: float,
    ask_size: float,
    trade_imbalance: float = 0.0,
) -> float:
    """Estimate short-horizon order-flow pressure in [-1, 1]."""

    bid = max(0.0, _safe_float(bid_size, 0.0))
    ask = max(0.0, _safe_float(ask_size, 0.0))
    queue_imbalance = 0.0 if (bid + ask) <= 0 else (bid - ask) / (bid + ask)
    return _clamp(0.7 * queue_imbalance + 0.3 * _clamp(trade_imbalance, -1.0, 1.0), -1.0, 1.0)


def model_limit_order_book(
    *,
    bid: float,
    ask: float,
    bid_size: float,
    ask_size: float,
    depth_notional: float,
) -> dict[str, float]:
    """Build compact LOB state used by execution/risk decisions."""

    b = max(0.0, _safe_float(bid, 0.0))
    a = max(0.0, _safe_float(ask, 0.0))
    mid = (a + b) / 2.0 if (a > 0 and b > 0) else 0.0
    spread_bps = 0.0 if mid <= 0 else ((a - b) / max(mid, 1e-9)) * 10000.0
    imbalance = analyze_order_flow_imbalance(
        bid_size=bid_size,
        ask_size=ask_size,
        trade_imbalance=0.0,
    )
    return {
        "mid": mid,
        "spread_bps": max(0.0, spread_bps),
        "imbalance": imbalance,
        "depth_notional": max(0.0, _safe_float(depth_notional, 0.0)),
    }


def estimate_liquidity_pressure(order_flow_imbalance: float, lob_state: Mapping[str, float]) -> float:
    """Estimate liquidity pressure where positive means favorable for aggressive buys."""

    depth = max(1.0, _safe_float(lob_state.get("depth_notional"), 0.0))
    spread_bps = max(0.0, _safe_float(lob_state.get("spread_bps"), 0.0))
    depth_penalty = min(1.0, 100.0 / depth)
    spread_penalty = min(1.0, spread_bps / 100.0)
    return _clamp(order_flow_imbalance - (0.4 * depth_penalty) - (0.3 * spread_penalty), -1.0, 1.0)


def estimate_execution_latency_risk(
    *,
    latency_ms: float,
    spread_bps: float,
    realized_vol: float,
) -> float:
    """Estimate [0,1] latency execution risk."""

    latency_term = min(1.0, max(0.0, _safe_float(latency_ms, 0.0)) / 750.0)
    spread_term = min(1.0, max(0.0, _safe_float(spread_bps, 0.0)) / 60.0)
    vol_term = min(1.0, max(0.0, _safe_float(realized_vol, 0.0)) / 0.03)
    return _clamp((0.5 * latency_term) + (0.3 * spread_term) + (0.2 * vol_term), 0.0, 1.0)


def estimate_transaction_costs(
    *,
    fee_bps: float,
    slippage_bps: float,
    spread_bps: float,
    liquidity_pressure: float,
) -> dict[str, float]:
    """Estimate all-in execution cost in basis points."""

    impact_bps = max(0.0, 2.5 - (1.5 * max(-1.0, min(1.0, liquidity_pressure))))
    spread_cost_bps = max(0.0, _safe_float(spread_bps, 0.0) * 0.5)
    fee = max(0.0, _safe_float(fee_bps, 0.0))
    slip = max(0.0, _safe_float(slippage_bps, 0.0))
    total = fee + slip + spread_cost_bps + impact_bps
    modeled_floor = max(120.0, (2.0 * fee) + (2.0 * slip))
    return {
        "fees_bps": fee,
        "slippage_bps": slip,
        "spread_cost_bps": spread_cost_bps,
        "impact_bps": impact_bps,
        "total_bps": total,
        "modeled_floor_bps": modeled_floor,
    }


def control_slippage(*, expected_slippage_bps: float, max_slippage_bps: float) -> bool:
    """Return True when expected slippage stays under configured guardrail."""

    return _safe_float(expected_slippage_bps, 0.0) <= max(0.0, _safe_float(max_slippage_bps, 0.0))


def detect_market_regime(
    *,
    trend_bps: float,
    realized_vol: float,
    spread_bps: float,
    liquidity_pressure: float,
) -> str:
    """Detect high-level regime from micro/macro state."""

    abs_trend = abs(_safe_float(trend_bps, 0.0))
    rv = max(0.0, _safe_float(realized_vol, 0.0))
    spread = max(0.0, _safe_float(spread_bps, 0.0))
    liq = _safe_float(liquidity_pressure, 0.0)
    if spread > 90.0 or rv > 0.03:
        return "PANIC"
    if spread > 40.0 and rv > 0.015:
        return "HIGH_VOL"
    if spread < 8.0 and rv < 0.004:
        return "COMPRESSION"
    if abs_trend > 45.0 and trend_bps > 0:
        return "BULL_TREND"
    if abs_trend > 45.0 and trend_bps < 0:
        return "BEAR_TREND"
    if abs_trend > 20.0:
        return "TREND"
    if abs_trend < 8.0 and rv < 0.01:
        return "CHOP"
    if liq < -0.5:
        return "LOW_LIQUIDITY"
    return "RANGE"


def switch_trading_regime(
    *,
    current_regime: str,
    target_regime: str,
    now_ts: float,
    last_switch_ts: float,
    min_hold_s: float = 30.0,
) -> tuple[str, float]:
    """Switch regime with hysteresis to prevent oscillation."""

    if not current_regime:
        return target_regime, now_ts
    if current_regime == target_regime:
        return current_regime, last_switch_ts
    if (now_ts - last_switch_ts) < max(1.0, _safe_float(min_hold_s, 30.0)):
        return current_regime, last_switch_ts
    return target_regime, now_ts


def estimate_market_state(
    *,
    regime: str,
    fused_features: Mapping[str, float],
    liquidity_pressure: float,
) -> dict[str, Any]:
    """Estimate current market state representation used by decisions."""

    trend = _safe_float(fused_features.get("ret_3"), 0.0) * 10000.0
    vol = max(0.0, _safe_float(fused_features.get("realized_vol"), 0.0))
    spread = max(0.0, _safe_float(fused_features.get("spread_proxy"), 0.0) * 10000.0)
    state = "balanced"
    if regime in {"PANIC", "HIGH_VOL"}:
        state = "unstable"
    elif regime in {"BULL_TREND", "TREND"} and liquidity_pressure > 0.0:
        state = "risk_on"
    elif regime in {"BEAR_TREND"} or liquidity_pressure < -0.3:
        state = "risk_off"
    return {
        "regime": regime,
        "state": state,
        "trend_bps": trend,
        "vol": vol,
        "spread_bps": spread,
        "liquidity_pressure": liquidity_pressure,
    }


def nowcast_market_conditions(
    *,
    market_state: Mapping[str, Any],
    order_flow_imbalance: float,
    latency_risk: float,
) -> dict[str, float]:
    """Nowcast near-term market conditions for execution-aware decisions."""

    trend = _safe_float(market_state.get("trend_bps"), 0.0)
    pressure = _safe_float(order_flow_imbalance, 0.0)
    urgency = _clamp((abs(trend) / 120.0) + 0.4 * abs(pressure) + 0.3 * _safe_float(latency_risk, 0.0), 0.0, 1.0)
    return {
        "micro_trend_bps": trend * 0.35,
        "order_flow_pressure": pressure,
        "execution_urgency": urgency,
        "market_state_confidence": _clamp(0.65 - (0.4 * _safe_float(latency_risk, 0.0)), 0.05, 0.95),
    }


def forecast_return_distribution(
    *,
    fused_features: Mapping[str, float],
    regime: str,
) -> DistributionForecast:
    """Forecast return distribution in basis points."""

    base_mu = (
        0.55 * _safe_float(fused_features.get("ret_1"), 0.0)
        + 0.45 * _safe_float(fused_features.get("ret_3"), 0.0)
        + 0.25 * _safe_float(fused_features.get("flow_imbalance"), 0.0)
        + 0.10 * _safe_float(fused_features.get("news_news_sentiment"), 0.0)
    ) * 10000.0
    if regime in {"BULL_TREND", "TREND"}:
        base_mu *= 1.2
    elif regime in {"BEAR_TREND", "PANIC"}:
        base_mu *= 0.7
    std = max(8.0, _safe_float(fused_features.get("realized_vol"), 0.0) * 10000.0)
    quantiles = {str(k): base_mu + (_NORMAL_Z[k] * std) for k in (0.05, 0.1, 0.5, 0.9, 0.95)}
    return DistributionForecast(mean_bps=base_mu, std_bps=std, quantiles_bps=quantiles)


def forecast_volatility_distribution(
    *,
    fused_features: Mapping[str, float],
    regime: str,
) -> DistributionForecast:
    """Forecast volatility distribution in basis points."""

    realized = max(1e-6, _safe_float(fused_features.get("realized_vol"), 0.0))
    mean_bps = realized * 10000.0
    if regime in {"PANIC", "HIGH_VOL"}:
        mean_bps *= 1.35
    elif regime in {"COMPRESSION"}:
        mean_bps *= 0.75
    std_bps = max(1.0, 0.35 * mean_bps)
    quantiles = {str(k): max(0.0, mean_bps + (_NORMAL_Z[k] * std_bps)) for k in (0.05, 0.5, 0.95)}
    return DistributionForecast(mean_bps=mean_bps, std_bps=std_bps, quantiles_bps=quantiles)


def forecast_drawdown_risk(
    *,
    return_distribution: DistributionForecast,
    volatility_distribution: DistributionForecast,
    position_notional_quote: float,
) -> float:
    """Forecast one-step drawdown risk as percentage of position."""

    left_tail_bps = _safe_float(return_distribution.quantiles_bps.get("0.05"), return_distribution.mean_bps)
    vol_penalty_bps = 0.5 * volatility_distribution.mean_bps
    risk_bps = max(0.0, abs(min(0.0, left_tail_bps)) + vol_penalty_bps)
    if position_notional_quote <= 0.0:
        return 0.0
    return _clamp(risk_bps / 100.0, 0.0, 100.0)


def build_conformal_prediction_interval(
    *,
    point_forecast_bps: float,
    residual_history: list[float],
    alpha: float = 0.1,
    fallback_std_bps: float = 12.0,
) -> ConformalInterval:
    """Build conformal interval from absolute residual quantile."""

    a = _clamp(alpha, 0.01, 0.4)
    abs_res = sorted(abs(_safe_float(v, 0.0)) for v in residual_history if math.isfinite(_safe_float(v, 0.0)))
    if abs_res:
        idx = int(max(0, min(len(abs_res) - 1, math.ceil((1.0 - a) * len(abs_res)) - 1)))
        half_width = max(2.0, abs_res[idx])
    else:
        half_width = max(2.0, fallback_std_bps * 1.645)
    center = _safe_float(point_forecast_bps, 0.0)
    return ConformalInterval(
        lower_bps=center - half_width,
        upper_bps=center + half_width,
        alpha=a,
        half_width_bps=half_width,
    )


def quantify_prediction_uncertainty(
    *,
    return_distribution: DistributionForecast,
    volatility_distribution: DistributionForecast,
    conformal_interval: ConformalInterval,
    drift_score: float,
) -> UncertaintyEstimate:
    """Quantify total uncertainty used for uncertainty-aware gating."""

    aleatoric = max(0.0, return_distribution.std_bps)
    epistemic = max(0.0, volatility_distribution.std_bps * 0.5)
    conf_width = max(0.0, conformal_interval.half_width_bps)
    drift_penalty = max(0.0, _safe_float(drift_score, 0.0) * 120.0)
    total = aleatoric + epistemic + (0.35 * conf_width) + drift_penalty
    return UncertaintyEstimate(
        aleatoric_bps=aleatoric,
        epistemic_bps=epistemic,
        conformal_width_bps=conf_width,
        drift_penalty_bps=drift_penalty,
        total_bps=total,
    )


def score_signal_confidence(
    *,
    alpha_signal_bps: float,
    uncertainty: UncertaintyEstimate,
    conformal_interval: ConformalInterval,
    regime: str,
    market_state_confidence: float,
    forecast_confidence: float,
) -> float:
    """Score final signal confidence in [0, 1]."""

    signal_strength = min(1.0, abs(_safe_float(alpha_signal_bps, 0.0)) / 40.0)
    uncertainty_penalty = min(0.95, uncertainty.total_bps / 220.0)
    interval_penalty = min(0.8, max(0.0, conformal_interval.half_width_bps) / 120.0)
    regime_bonus = 0.08 if regime in {"BULL_TREND", "TREND", "RANGE"} else -0.08
    score = (
        0.35 * signal_strength
        + 0.30 * _clamp(market_state_confidence, 0.0, 1.0)
        + 0.25 * _clamp(forecast_confidence, 0.0, 1.0)
        + regime_bonus
        - 0.30 * uncertainty_penalty
        - 0.15 * interval_penalty
    )
    return _clamp(score, 0.0, 1.0)


def detect_concept_drift(
    *,
    fused_features: Mapping[str, float],
    baseline_feature_means: Mapping[str, float],
    threshold: float,
) -> dict[str, Any]:
    """Detect concept drift with a lightweight normalized shift score."""

    keys = sorted(set(fused_features.keys()) & set(baseline_feature_means.keys()))
    if not keys:
        return {"drift_score": 0.0, "drifted": False, "threshold": threshold, "top_features": []}
    contrib: list[tuple[str, float]] = []
    for key in keys:
        cur = _safe_float(fused_features.get(key), 0.0)
        base = _safe_float(baseline_feature_means.get(key), 0.0)
        denom = max(1e-6, abs(base) + 0.05)
        contrib.append((key, abs(cur - base) / denom))
    contrib.sort(key=lambda row: row[1], reverse=True)
    score = sum(v for _k, v in contrib) / len(contrib)
    drift_score = _clamp(score, 0.0, 5.0)
    return {
        "drift_score": drift_score,
        "drifted": drift_score >= max(0.01, _safe_float(threshold, 0.2)),
        "threshold": _safe_float(threshold, 0.2),
        "top_features": [{"feature": k, "shift": v} for k, v in contrib[:5]],
    }


def adapt_model_online(
    *,
    drift_report: Mapping[str, Any],
    online_learning_enabled: bool,
    base_learning_rate: float,
) -> dict[str, Any]:
    """Compute bounded online adaptation action."""

    if not online_learning_enabled:
        return {"adapt": False, "reason": "online_learning_disabled", "learning_rate": 0.0}
    drifted = bool(drift_report.get("drifted", False))
    drift_score = _safe_float(drift_report.get("drift_score"), 0.0)
    lr = _clamp(base_learning_rate, 1e-5, 0.2)
    if drifted:
        return {
            "adapt": True,
            "reason": "drift_detected",
            "learning_rate": _clamp(lr * min(3.0, 1.0 + drift_score), 1e-5, 0.2),
        }
    return {"adapt": False, "reason": "drift_below_threshold", "learning_rate": lr}


def update_model_incrementally(
    *,
    model_state: dict[str, Any],
    fused_features: Mapping[str, float],
    realized_return_bps: float,
    adaptation: Mapping[str, Any],
) -> dict[str, Any]:
    """Update online model state with bounded EWMA adaptation."""

    state = dict(model_state)
    lr = _clamp(_safe_float(adaptation.get("learning_rate"), 0.02), 1e-5, 0.2)
    means = dict(state.get("feature_means", {}))
    for key, value in fused_features.items():
        v = _safe_float(value, 0.0)
        prev = _safe_float(means.get(key), v)
        means[key] = prev + lr * (v - prev)
    state["feature_means"] = means
    residuals = deque(state.get("residual_history", []), maxlen=512)
    pred = _safe_float(state.get("last_pred_return_bps"), 0.0)
    residuals.append(realized_return_bps - pred)
    state["residual_history"] = list(residuals)
    state["last_realized_return_bps"] = _safe_float(realized_return_bps, 0.0)
    return state


def optimize_risk_budget(
    *,
    base_risk_budget_quote: float,
    regime: str,
    uncertainty_bps: float,
    drawdown_pct: float,
) -> float:
    """Optimize risk budget using regime and uncertainty aware throttles."""

    budget = max(0.0, _safe_float(base_risk_budget_quote, 0.0))
    if regime in {"PANIC", "HIGH_VOL", "LOW_LIQUIDITY"}:
        budget *= 0.45
    elif regime in {"BULL_TREND", "TREND"}:
        budget *= 1.10
    uncertainty_scale = _clamp(1.0 - min(0.7, uncertainty_bps / 300.0), 0.2, 1.0)
    dd_scale = _clamp(1.0 - max(0.0, drawdown_pct) / 30.0, 0.2, 1.0)
    return max(0.0, budget * uncertainty_scale * dd_scale)


def calculate_position_size(
    *,
    risk_budget_quote: float,
    confidence: float,
    alpha_score_bps: float,
    execution_risk: float,
) -> float:
    """Calculate bounded position size from risk/confidence/execution risk."""

    budget = max(0.0, _safe_float(risk_budget_quote, 0.0))
    conf = _clamp(confidence, 0.0, 1.0)
    alpha_scale = _clamp(abs(_safe_float(alpha_score_bps, 0.0)) / 40.0, 0.1, 1.5)
    risk_scale = _clamp(1.0 - _safe_float(execution_risk, 0.0), 0.1, 1.0)
    return budget * conf * alpha_scale * risk_scale


def allocate_portfolio_capital(
    *,
    position_size_quote: float,
    quote_free: float,
    max_exposure_notional: float,
    current_exposure_notional: float,
) -> float:
    """Allocate capital while respecting available quote and exposure cap."""

    target = max(0.0, _safe_float(position_size_quote, 0.0))
    free = max(0.0, _safe_float(quote_free, 0.0))
    cap = max(0.0, _safe_float(max_exposure_notional, 0.0))
    current = max(0.0, abs(_safe_float(current_exposure_notional, 0.0)))
    room = cap if cap <= 0.0 else max(0.0, cap - current)
    if cap > 0.0:
        target = min(target, room)
    return min(target, free)


def enforce_cooldown(*, now_ts: float, last_submission_ts: float, order_cadence_s: float) -> tuple[bool, str]:
    """Enforce decision cooldown."""

    if _safe_float(now_ts, 0.0) - _safe_float(last_submission_ts, 0.0) < max(0.1, _safe_float(order_cadence_s, 1.0)):
        return False, "cooldown_active"
    return True, ""


def enforce_drawdown_limits(*, drawdown_pct: float, max_drawdown_pct: float) -> tuple[bool, str]:
    """Enforce drawdown ceiling."""

    if max_drawdown_pct > 0.0 and _safe_float(drawdown_pct, 0.0) >= max_drawdown_pct:
        return False, "drawdown_guard"
    return True, ""


def enforce_max_exposure(
    *,
    current_exposure_notional: float,
    incoming_notional: float,
    max_exposure_notional: float,
) -> tuple[bool, str]:
    """Enforce max exposure before opening/adding risk."""

    max_exp = _safe_float(max_exposure_notional, 0.0)
    if max_exp <= 0.0:
        return True, ""
    if abs(_safe_float(current_exposure_notional, 0.0)) + max(0.0, _safe_float(incoming_notional, 0.0)) > max_exp:
        return False, "portfolio_exposure_limit"
    return True, ""


def validate_risk_constraints(
    *,
    confidence: float,
    uncertainty_bps: float,
    drift_report: Mapping[str, Any],
    regime: str,
    liquidity_pressure: float,
    latency_risk: float,
    drawdown_pct: float,
    max_drawdown_pct: float,
    now_ts: float,
    last_submission_ts: float,
    order_cadence_s: float,
    current_exposure_notional: float,
    incoming_notional: float,
    max_exposure_notional: float,
    confidence_threshold: float,
    uncertainty_threshold_bps: float,
    latency_threshold: float,
) -> dict[str, Any]:
    """Evaluate aggregated risk constraints and return explicit guard reasons."""

    reasons: list[str] = []
    ok_cooldown, reason = enforce_cooldown(
        now_ts=now_ts,
        last_submission_ts=last_submission_ts,
        order_cadence_s=order_cadence_s,
    )
    if not ok_cooldown:
        reasons.append(reason)
    ok_dd, reason = enforce_drawdown_limits(
        drawdown_pct=drawdown_pct,
        max_drawdown_pct=max_drawdown_pct,
    )
    if not ok_dd:
        reasons.append(reason)
    ok_exp, reason = enforce_max_exposure(
        current_exposure_notional=current_exposure_notional,
        incoming_notional=incoming_notional,
        max_exposure_notional=max_exposure_notional,
    )
    if not ok_exp:
        reasons.append(reason)
    if confidence < confidence_threshold:
        reasons.append("confidence_guard")
    if uncertainty_bps > uncertainty_threshold_bps:
        reasons.append("uncertainty_guard")
    if bool(drift_report.get("drifted", False)):
        reasons.append("drift_guard")
    if regime in {"PANIC", "HIGH_VOL"}:
        reasons.append("regime_filter")
    if liquidity_pressure < -0.6:
        reasons.append("liquidity_filter")
    if latency_risk > latency_threshold:
        reasons.append("latency_guard")
    return {
        "allowed": len(reasons) == 0,
        "reasons": reasons,
    }


def decide_trade_entry(
    *,
    trade_signal: TradeSignal,
    has_open_position: bool,
    risk_allowed: bool,
) -> str:
    """Decide entry action: open/add/hold/skip."""

    if not risk_allowed:
        return "skip"
    if trade_signal.side != "buy":
        return "hold" if has_open_position else "skip"
    if has_open_position and trade_signal.confidence >= 0.65:
        return "add"
    if not has_open_position and trade_signal.confidence >= 0.55:
        return "open"
    return "hold" if has_open_position else "skip"


def decide_trade_exit(
    *,
    trade_signal: TradeSignal,
    has_open_position: bool,
    current_profit_bps: float,
) -> str:
    """Decide exit action: reduce/partial/full/hold."""

    if not has_open_position:
        return "hold"
    if trade_signal.side == "sell" and trade_signal.confidence > 0.7:
        return "full_close"
    if trade_signal.side == "sell" and trade_signal.confidence > 0.55:
        return "partial_close"
    if current_profit_bps < -150.0:
        return "reduce"
    return "hold"


def apply_stop_loss_logic(*, current_profit_bps: float, stop_loss_bps: float = -180.0) -> tuple[bool, str]:
    """Apply stop-loss logic."""

    if _safe_float(current_profit_bps, 0.0) <= _safe_float(stop_loss_bps, -180.0):
        return True, "stop_loss_triggered"
    return False, ""


def apply_trailing_stop_logic(
    *,
    peak_profit_bps: float,
    current_profit_bps: float,
    trailing_delta_bps: float = 90.0,
) -> tuple[bool, str]:
    """Apply trailing stop logic."""

    peak = _safe_float(peak_profit_bps, 0.0)
    cur = _safe_float(current_profit_bps, 0.0)
    if peak <= 0.0:
        return False, ""
    if (peak - cur) >= max(1.0, _safe_float(trailing_delta_bps, 90.0)):
        return True, "trailing_stop_triggered"
    return False, ""


def apply_profit_lock(
    *,
    side: str,
    bid: float,
    avg_entry_price: float,
    modeled_cost_bps: float,
    min_net_profit_bps: float,
    target_net_profit_bps: float,
    hold_time_s: float,
) -> dict[str, Any]:
    """Hard profit protection rule-set."""

    hard_floor_bps = max(120.0, _safe_float(min_net_profit_bps, 120.0), _safe_float(modeled_cost_bps, 0.0))
    target_bps = max(hard_floor_bps, _safe_float(target_net_profit_bps, hard_floor_bps))
    if hold_time_s > 7200.0:
        target_bps = max(hard_floor_bps, target_bps * 0.9)
    if side.lower() != "sell":
        return {
            "allowed": True,
            "hard_min_net_bps": hard_floor_bps,
            "effective_target_net_bps": target_bps,
            "modeled_cost_bps": _safe_float(modeled_cost_bps, 0.0),
            "min_sell_price": 0.0,
            "target_sell_price": 0.0,
            "reason": "not_sell",
        }
    entry = _safe_float(avg_entry_price, 0.0)
    bid_px = _safe_float(bid, 0.0)
    if entry <= 0.0:
        return {
            "allowed": False,
            "hard_min_net_bps": hard_floor_bps,
            "effective_target_net_bps": target_bps,
            "modeled_cost_bps": _safe_float(modeled_cost_bps, 0.0),
            "min_sell_price": 0.0,
            "target_sell_price": 0.0,
            "reason": "profit_lock_missing_cost_basis",
        }
    min_sell_price = entry * (1.0 + hard_floor_bps / 10000.0)
    target_sell_price = entry * (1.0 + target_bps / 10000.0)
    if bid_px < entry:
        return {
            "allowed": False,
            "hard_min_net_bps": hard_floor_bps,
            "effective_target_net_bps": target_bps,
            "modeled_cost_bps": _safe_float(modeled_cost_bps, 0.0),
            "min_sell_price": min_sell_price,
            "target_sell_price": target_sell_price,
            "reason": "profit_lock_sell_below_entry",
        }
    if bid_px < min_sell_price:
        return {
            "allowed": False,
            "hard_min_net_bps": hard_floor_bps,
            "effective_target_net_bps": target_bps,
            "modeled_cost_bps": _safe_float(modeled_cost_bps, 0.0),
            "min_sell_price": min_sell_price,
            "target_sell_price": target_sell_price,
            "reason": "profit_lock_sell_below_min_profit",
        }
    return {
        "allowed": True,
        "hard_min_net_bps": hard_floor_bps,
        "effective_target_net_bps": target_bps,
        "modeled_cost_bps": _safe_float(modeled_cost_bps, 0.0),
        "min_sell_price": min_sell_price,
        "target_sell_price": target_sell_price,
        "reason": "ok",
    }


def manage_open_position(
    *,
    exit_action: str,
    current_profit_bps: float,
    peak_profit_bps: float,
    side: str,
    bid: float,
    avg_entry_price: float,
    modeled_cost_bps: float,
    min_net_profit_bps: float,
    target_net_profit_bps: float,
    hold_time_s: float,
) -> tuple[str, dict[str, Any]]:
    """Manage open position with stop-loss/trailing/profit-lock policies."""

    stop_hit, stop_reason = apply_stop_loss_logic(current_profit_bps=current_profit_bps)
    if stop_hit:
        return "reduce", {"reason": stop_reason}
    trail_hit, trail_reason = apply_trailing_stop_logic(
        peak_profit_bps=peak_profit_bps,
        current_profit_bps=current_profit_bps,
    )
    if trail_hit:
        return "partial_close", {"reason": trail_reason}
    if exit_action in {"full_close", "partial_close", "reduce"}:
        lock = apply_profit_lock(
            side=side,
            bid=bid,
            avg_entry_price=avg_entry_price,
            modeled_cost_bps=modeled_cost_bps,
            min_net_profit_bps=min_net_profit_bps,
            target_net_profit_bps=target_net_profit_bps,
            hold_time_s=hold_time_s,
        )
        if not bool(lock.get("allowed", False)):
            return "hold", lock
        return exit_action, lock
    return "hold", {"reason": "hold"}


def route_order(
    *,
    action: str,
    side: str,
    execution_urgency: float,
    spread_bps: float,
) -> dict[str, Any]:
    """Route order with execution-aware heuristics."""

    urgency = _clamp(execution_urgency, 0.0, 1.0)
    spread = max(0.0, _safe_float(spread_bps, 0.0))
    order_type = "maker"
    if urgency > 0.8 and spread < 20.0:
        order_type = "taker"
    return {
        "action": action,
        "side": side,
        "order_type": order_type,
        "taker_allowed": urgency > 0.55,
        "execution_urgency": urgency,
    }


def execute_order_safely(
    *,
    action: str,
    side: str,
    route: Mapping[str, Any],
    risk_validation: Mapping[str, Any],
    guards_mode: str,
) -> tuple[bool, str]:
    """Final execution safety gate."""

    if action in {"skip", "hold"}:
        return False, "no_intent"
    if bool(risk_validation.get("allowed", False)):
        return True, "allowed"
    reasons = [str(r) for r in risk_validation.get("reasons", [])]
    fatal_reasons = {"profit_lock_sell_below_entry", "profit_lock_sell_below_min_profit", "idempotency_duplicate"}
    if guards_mode == "fatal_only":
        non_fatal = [r for r in reasons if r not in fatal_reasons]
        if non_fatal and len(non_fatal) == len(reasons):
            return True, "warn_only_override"
    return False, reasons[0] if reasons else "risk_block"


class TrendAccelerationDetector:
    def score(self, trend_bps: float, nowcast_trend_bps: float) -> float:
        return _clamp((nowcast_trend_bps - trend_bps) / 80.0, -1.0, 1.0)


class MomentumContinuationFilter:
    def score(self, trend_bps: float, flow: float) -> float:
        return _clamp((trend_bps / 120.0) + (0.4 * flow), -1.0, 1.0)


class VolatilityExpansionStrategy:
    def score(self, vol_bps: float, prev_vol_bps: float) -> float:
        if prev_vol_bps <= 0.0:
            return 0.0
        return _clamp((vol_bps / prev_vol_bps) - 1.0, -1.0, 1.0)


class LiquidityImbalanceSignal:
    def score(self, liquidity_pressure: float, spread_bps: float) -> float:
        return _clamp(liquidity_pressure - min(1.0, spread_bps / 100.0), -1.0, 1.0)


class SpreadCompressionDetection:
    def score(self, spread_bps: float, baseline_spread_bps: float) -> float:
        if baseline_spread_bps <= 0.0:
            return 0.0
        return _clamp((baseline_spread_bps - spread_bps) / baseline_spread_bps, -1.0, 1.0)


class BreakoutProbabilityScoring:
    def score(self, trend_bps: float, vol_bps: float) -> float:
        return _clamp((abs(trend_bps) / 80.0) * (1.0 + min(1.0, vol_bps / 80.0)), 0.0, 1.0)


class SmartHoldExtension:
    def should_extend(self, confidence: float, trend_bps: float) -> bool:
        return confidence >= 0.7 and trend_bps > 20.0


class DynamicTPExpansion:
    def expand(self, target_bps: float, confidence: float, regime: str) -> float:
        if confidence < 0.75:
            return target_bps
        if regime in {"BULL_TREND", "TREND"}:
            return target_bps * 1.2
        return target_bps


class RegimeSpecificTradingParameters:
    def parameters(self, regime: str) -> dict[str, float]:
        if regime in {"PANIC", "HIGH_VOL"}:
            return {"confidence_threshold": 0.70, "uncertainty_threshold_bps": 60.0}
        if regime in {"BULL_TREND", "TREND"}:
            return {"confidence_threshold": 0.50, "uncertainty_threshold_bps": 95.0}
        return {"confidence_threshold": 0.55, "uncertainty_threshold_bps": 80.0}


class MicrostructureAlpha:
    def score(self, order_flow: float, liquidity_pressure: float) -> float:
        return _clamp(0.6 * order_flow + 0.4 * liquidity_pressure, -1.0, 1.0)


class LiquidityHeatmap:
    def classify(self, depth_notional: float, spread_bps: float) -> str:
        if depth_notional < 50.0 or spread_bps > 80.0:
            return "thin"
        if depth_notional > 1000.0 and spread_bps < 15.0:
            return "deep"
        return "normal"


class TimeOfDayEdge:
    def score(self, timestamp: float) -> float:
        hour = int(timestamp // 3600) % 24
        if hour in {7, 8, 13, 14, 15}:
            return 0.25
        if hour in {0, 1, 2, 3}:
            return -0.15
        return 0.0


class SignalEnsembleModel:
    def combine(self, signals: Mapping[str, float]) -> float:
        if not signals:
            return 0.0
        vals = [float(v) for v in signals.values()]
        return sum(vals) / len(vals)


class SignalDecayDetector:
    def score(self, current_signal: float, prev_signal: float) -> float:
        return _clamp(prev_signal - current_signal, -1.0, 1.0)


class ExecutionQualityMonitor:
    def score(self, total_cost_bps: float, alpha_bps: float) -> float:
        if abs(alpha_bps) <= 1e-9:
            return 1.0
        ratio = total_cost_bps / max(1.0, abs(alpha_bps))
        return _clamp(ratio, 0.0, 5.0)


class LatencyArbitrageProtection:
    def allow(self, latency_risk: float, threshold: float) -> bool:
        return latency_risk <= threshold


class AdaptivePositionSizing:
    def scale(self, confidence: float, uncertainty_bps: float) -> float:
        return _clamp(confidence * (1.0 - min(0.75, uncertainty_bps / 300.0)), 0.1, 1.25)


class CrossPairOpportunityDetector:
    def score(self, symbol: str, fused_features: Mapping[str, float]) -> float:
        if "XBT" in symbol.upper():
            return _clamp(_safe_float(fused_features.get("macro_macro_risk_on"), 0.0), -1.0, 1.0)
        return 0.0


class LiquidityAwareTradeSizing:
    def scale(self, depth_notional: float, spread_bps: float) -> float:
        depth_scale = _clamp(depth_notional / 500.0, 0.2, 1.2)
        spread_scale = _clamp(1.0 - (spread_bps / 100.0), 0.2, 1.0)
        return _clamp(depth_scale * spread_scale, 0.1, 1.25)


class ProfitCompoundingAllocator:
    def allocate(self, base_budget: float, realized_profit_bps: float) -> float:
        boost = _clamp(realized_profit_bps / 800.0, -0.15, 0.25)
        return max(0.0, base_budget * (1.0 + boost))


class SignalEngine:
    def generate_trade_signal(self, **kwargs: Any) -> TradeSignal:
        return generate_trade_signal(**kwargs)


class ProbabilisticForecastEngine:
    def forecast_return_distribution(self, **kwargs: Any) -> DistributionForecast:
        return forecast_return_distribution(**kwargs)

    def forecast_volatility_distribution(self, **kwargs: Any) -> DistributionForecast:
        return forecast_volatility_distribution(**kwargs)

    def forecast_drawdown_risk(self, **kwargs: Any) -> float:
        return forecast_drawdown_risk(**kwargs)


class RegimeEngine:
    def detect_market_regime(self, **kwargs: Any) -> str:
        return detect_market_regime(**kwargs)

    def switch_trading_regime(self, **kwargs: Any) -> tuple[str, float]:
        return switch_trading_regime(**kwargs)


class RiskEngine:
    def validate_risk_constraints(self, **kwargs: Any) -> dict[str, Any]:
        return validate_risk_constraints(**kwargs)


class PositionSizingEngine:
    def optimize_risk_budget(self, **kwargs: Any) -> float:
        return optimize_risk_budget(**kwargs)

    def calculate_position_size(self, **kwargs: Any) -> float:
        return calculate_position_size(**kwargs)


class ExecutionEngine:
    def estimate_transaction_costs(self, **kwargs: Any) -> dict[str, float]:
        return estimate_transaction_costs(**kwargs)

    def estimate_execution_latency_risk(self, **kwargs: Any) -> float:
        return estimate_execution_latency_risk(**kwargs)

    def control_slippage(self, **kwargs: Any) -> bool:
        return control_slippage(**kwargs)

    def route_order(self, **kwargs: Any) -> dict[str, Any]:
        return route_order(**kwargs)

    def execute_order_safely(self, **kwargs: Any) -> tuple[bool, str]:
        return execute_order_safely(**kwargs)


class PortfolioAllocationEngine:
    def allocate_portfolio_capital(self, **kwargs: Any) -> float:
        return allocate_portfolio_capital(**kwargs)


class DriftDetectionEngine:
    def detect_concept_drift(self, **kwargs: Any) -> dict[str, Any]:
        return detect_concept_drift(**kwargs)


class TradeDecisionEngine:
    def decide_trade_entry(self, **kwargs: Any) -> str:
        return decide_trade_entry(**kwargs)

    def decide_trade_exit(self, **kwargs: Any) -> str:
        return decide_trade_exit(**kwargs)


class MarketStateEstimator:
    def estimate_market_state(self, **kwargs: Any) -> dict[str, Any]:
        return estimate_market_state(**kwargs)


class NowcastingEngine:
    def nowcast_market_conditions(self, **kwargs: Any) -> dict[str, float]:
        return nowcast_market_conditions(**kwargs)


class AlphaSignalEngine:
    def __init__(self) -> None:
        self.trend_acceleration = TrendAccelerationDetector()
        self.momentum_filter = MomentumContinuationFilter()
        self.vol_expansion = VolatilityExpansionStrategy()
        self.liquidity_imbalance = LiquidityImbalanceSignal()
        self.spread_compression = SpreadCompressionDetection()
        self.breakout_prob = BreakoutProbabilityScoring()
        self.time_of_day_edge = TimeOfDayEdge()
        self.microstructure_alpha = MicrostructureAlpha()
        self.signal_ensemble = SignalEnsembleModel()
        self.cross_pair = CrossPairOpportunityDetector()

    def compute_alpha_signals(
        self,
        *,
        symbol: str,
        fused_features: Mapping[str, float],
        market_state: Mapping[str, Any],
        nowcast: Mapping[str, float],
        liquidity_pressure: float,
        previous_vol_bps: float,
    ) -> dict[str, float]:
        trend_bps = _safe_float(market_state.get("trend_bps"), 0.0)
        vol_bps = max(0.0, _safe_float(market_state.get("vol"), 0.0) * 10000.0)
        spread_bps = max(0.0, _safe_float(market_state.get("spread_bps"), 0.0))
        flow = _safe_float(nowcast.get("order_flow_pressure"), 0.0)
        components = {
            "trend_acceleration": self.trend_acceleration.score(trend_bps, _safe_float(nowcast.get("micro_trend_bps"), 0.0)),
            "momentum_continuation": self.momentum_filter.score(trend_bps, flow),
            "volatility_expansion": self.vol_expansion.score(vol_bps, previous_vol_bps),
            "liquidity_imbalance": self.liquidity_imbalance.score(liquidity_pressure, spread_bps),
            "spread_compression": self.spread_compression.score(spread_bps, max(6.0, spread_bps + 10.0)),
            "breakout_probability": self.breakout_prob.score(trend_bps, vol_bps),
            "microstructure_alpha": self.microstructure_alpha.score(flow, liquidity_pressure),
            "time_of_day_edge": self.time_of_day_edge.score(_safe_float(fused_features.get("timestamp"), 0.0)),
            "cross_pair_opportunity": self.cross_pair.score(symbol, fused_features),
        }
        components["ensemble"] = self.signal_ensemble.combine(components)
        return components


class UncertaintyQuantificationEngine:
    def quantify_prediction_uncertainty(self, **kwargs: Any) -> UncertaintyEstimate:
        return quantify_prediction_uncertainty(**kwargs)


class ConformalPredictionEngine:
    def build_conformal_prediction_interval(self, **kwargs: Any) -> ConformalInterval:
        return build_conformal_prediction_interval(**kwargs)


class ConceptDriftDetectionEngine:
    def detect_concept_drift(self, **kwargs: Any) -> dict[str, Any]:
        return detect_concept_drift(**kwargs)


class OnlineLearningEngine:
    def adapt_model_online(self, **kwargs: Any) -> dict[str, Any]:
        return adapt_model_online(**kwargs)

    def update_model_incrementally(self, **kwargs: Any) -> dict[str, Any]:
        return update_model_incrementally(**kwargs)


class MultimodalForecastEngine:
    def ingest_price_volume_features(self, **kwargs: Any) -> dict[str, float]:
        return ingest_price_volume_features(**kwargs)

    def ingest_news_features(self, **kwargs: Any) -> dict[str, float]:
        return ingest_news_features(**kwargs)

    def ingest_macro_features(self, **kwargs: Any) -> dict[str, float]:
        return ingest_macro_features(**kwargs)

    def ingest_fundamental_features(self, **kwargs: Any) -> dict[str, float]:
        return ingest_fundamental_features(**kwargs)

    def fuse_multimodal_features(self, **kwargs: Any) -> dict[str, float]:
        return fuse_multimodal_features(**kwargs)


class OrderFlowIntelligenceEngine:
    def analyze_order_flow_imbalance(self, **kwargs: Any) -> float:
        return analyze_order_flow_imbalance(**kwargs)

    def estimate_liquidity_pressure(self, **kwargs: Any) -> float:
        return estimate_liquidity_pressure(**kwargs)


class LimitOrderBookModel:
    def model_limit_order_book(self, **kwargs: Any) -> dict[str, float]:
        return model_limit_order_book(**kwargs)


class TradeManagementEngine:
    def manage_open_position(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return manage_open_position(**kwargs)

    def apply_stop_loss_logic(self, **kwargs: Any) -> tuple[bool, str]:
        return apply_stop_loss_logic(**kwargs)

    def apply_trailing_stop_logic(self, **kwargs: Any) -> tuple[bool, str]:
        return apply_trailing_stop_logic(**kwargs)


class ProfitProtectionEngine:
    def apply_profit_lock(self, **kwargs: Any) -> dict[str, Any]:
        return apply_profit_lock(**kwargs)


class SelfOptimizationEngine:
    """Bounded online optimizer that never weakens hard sell invariants."""

    _FORBIDDEN_KEYS = {
        "sell_min_profit_bps",
        "min_net_profit_bps",
        "profit_lock_floor_bps",
        "allow_sell_below_entry",
    }

    def propose_adjustments(self, *, reject_rate: float, no_intent_rate: float, fill_rate: float) -> dict[str, float]:
        adjustments: dict[str, float] = {}
        if reject_rate > 0.4:
            adjustments["confidence_threshold_delta"] = 0.03
            adjustments["uncertainty_threshold_delta_bps"] = -5.0
        elif no_intent_rate > 0.7 and fill_rate < 0.25:
            adjustments["confidence_threshold_delta"] = -0.02
            adjustments["uncertainty_threshold_delta_bps"] = 5.0
        if fill_rate < 0.15:
            adjustments["max_slippage_bps_delta"] = 0.5
        return {k: v for k, v in adjustments.items() if k not in self._FORBIDDEN_KEYS}


class ProbabilisticMarketForecastingEngine(ProbabilisticForecastEngine):
    """Extended name for compatibility with architecture map."""


class RegimeAwareTradingDecisionSystem(TradeDecisionEngine):
    """Extended name for compatibility with architecture map."""


class AdaptiveAlphaForecastingFramework(AlphaSignalEngine):
    """Extended name for compatibility with architecture map."""


class RiskCalibratedMarketInferenceEngine:
    def infer(
        self,
        *,
        return_distribution: DistributionForecast,
        uncertainty: UncertaintyEstimate,
        drawdown_risk_pct: float,
    ) -> dict[str, float]:
        expected_return = return_distribution.mean_bps
        risk_adjusted = expected_return - (0.35 * uncertainty.total_bps) - (0.25 * drawdown_risk_pct)
        return {
            "expected_return_bps": expected_return,
            "risk_adjusted_return_bps": risk_adjusted,
        }


def compute_alpha_signals(
    *,
    symbol: str,
    fused_features: Mapping[str, float],
    market_state: Mapping[str, Any],
    nowcast: Mapping[str, float],
    liquidity_pressure: float,
    previous_vol_bps: float,
    alpha_engine: AlphaSignalEngine,
) -> dict[str, float]:
    """Compute multi-signal alpha components and ensemble consensus."""

    return alpha_engine.compute_alpha_signals(
        symbol=symbol,
        fused_features=fused_features,
        market_state=market_state,
        nowcast=nowcast,
        liquidity_pressure=liquidity_pressure,
        previous_vol_bps=previous_vol_bps,
    )


def generate_trade_signal(
    *,
    alpha_signals: Mapping[str, float],
    return_distribution: DistributionForecast,
    uncertainty: UncertaintyEstimate,
    confidence: float,
) -> TradeSignal:
    """Generate action-oriented trade signal from alpha + forecast + UQ."""

    alpha_raw = _safe_float(alpha_signals.get("ensemble"), 0.0)
    alpha_bps = alpha_raw * 25.0 + (0.25 * return_distribution.mean_bps)
    effective_score = alpha_bps - (0.30 * uncertainty.total_bps)
    if effective_score > 8.0 and confidence >= 0.5:
        return TradeSignal(action="enter", side="buy", score_bps=effective_score, confidence=confidence, reason="alpha_long")
    if effective_score < -8.0 and confidence >= 0.55:
        return TradeSignal(action="exit", side="sell", score_bps=effective_score, confidence=confidence, reason="alpha_exit")
    return TradeSignal(action="hold", side="hold", score_bps=effective_score, confidence=confidence, reason="signal_weak")


def run_decision_algorithm(
    context: DecisionContext,
    engine: "AutonomousMarketPredictionAndDecisionEngine",
) -> DecisionOutcome:
    """
    Central decision brain that fuses probabilistic forecasts, UQ, conformal,
    regime, drift, multimodal, microstructure, risk, and execution awareness.
    """

    price_volume = engine.multimodal.ingest_price_volume_features(features=context.features)
    news = engine.multimodal.ingest_news_features(news_payload={})
    macro = engine.multimodal.ingest_macro_features(macro_payload={})
    fundamentals = engine.multimodal.ingest_fundamental_features(fundamental_payload={})
    fused = engine.multimodal.fuse_multimodal_features(
        price_volume=price_volume,
        news=news if engine.enable_news else {},
        macro=macro if engine.enable_macro else {},
        fundamentals=fundamentals if engine.enable_fundamentals else {},
        sentiment={},
    )
    fused["timestamp"] = float(context.now_ts)

    lob_state = engine.lob.model_limit_order_book(
        bid=context.bid,
        ask=context.ask,
        bid_size=max(1.0, context.depth_notional * 0.5),
        ask_size=max(1.0, context.depth_notional * 0.5),
        depth_notional=context.depth_notional,
    )
    flow_imbalance = engine.order_flow.analyze_order_flow_imbalance(
        bid_size=max(1.0, context.depth_notional * (1.0 + _safe_float(context.features.get("orderbook_imbalance"), 0.0))),
        ask_size=max(1.0, context.depth_notional * (1.0 - _safe_float(context.features.get("orderbook_imbalance"), 0.0))),
        trade_imbalance=_safe_float(context.features.get("flow_imbalance"), 0.0),
    )
    liquidity_pressure = engine.order_flow.estimate_liquidity_pressure(
        order_flow_imbalance=flow_imbalance,
        lob_state=lob_state,
    )
    target_regime = engine.regime.detect_market_regime(
        trend_bps=_safe_float(context.market_watch.get("trend_2m_bps"), _safe_float(context.features.get("ret_3"), 0.0) * 10000.0),
        realized_vol=_safe_float(context.features.get("realized_vol"), 0.0),
        spread_bps=context.spread_bps,
        liquidity_pressure=liquidity_pressure,
    )
    regime, last_switch_ts = engine.regime.switch_trading_regime(
        current_regime=engine.current_regime,
        target_regime=target_regime,
        now_ts=context.now_ts,
        last_switch_ts=engine.last_regime_switch_ts,
        min_hold_s=engine.regime_hold_s,
    )
    engine.current_regime = regime
    engine.last_regime_switch_ts = last_switch_ts

    market_state = engine.market_state.estimate_market_state(
        regime=regime,
        fused_features=fused,
        liquidity_pressure=liquidity_pressure,
    )
    latency_risk = engine.execution.estimate_execution_latency_risk(
        latency_ms=context.latency_ms,
        spread_bps=context.spread_bps,
        realized_vol=_safe_float(context.features.get("realized_vol"), 0.0),
    )
    nowcast = engine.nowcasting.nowcast_market_conditions(
        market_state=market_state,
        order_flow_imbalance=flow_imbalance,
        latency_risk=latency_risk,
    )
    ret_dist = engine.forecasting.forecast_return_distribution(
        fused_features=fused,
        regime=regime,
    )
    vol_dist = engine.forecasting.forecast_volatility_distribution(
        fused_features=fused,
        regime=regime,
    )
    drawdown_risk = engine.forecasting.forecast_drawdown_risk(
        return_distribution=ret_dist,
        volatility_distribution=vol_dist,
        position_notional_quote=context.position_notional_quote,
    )
    drift_report = engine.drift.detect_concept_drift(
        fused_features=fused,
        baseline_feature_means=engine.model_state.get("feature_means", {}),
        threshold=engine.drift_threshold,
    )
    conformal = engine.conformal.build_conformal_prediction_interval(
        point_forecast_bps=ret_dist.mean_bps,
        residual_history=list(engine.model_state.get("residual_history", [])),
        alpha=engine.conformal_alpha,
        fallback_std_bps=ret_dist.std_bps,
    )
    uq = engine.uq.quantify_prediction_uncertainty(
        return_distribution=ret_dist,
        volatility_distribution=vol_dist,
        conformal_interval=conformal,
        drift_score=_safe_float(drift_report.get("drift_score"), 0.0),
    )

    alpha_signals = compute_alpha_signals(
        symbol=context.symbol,
        fused_features=fused,
        market_state=market_state,
        nowcast=nowcast,
        liquidity_pressure=liquidity_pressure,
        previous_vol_bps=engine.prev_vol_bps,
        alpha_engine=engine.alpha,
    )
    engine.prev_vol_bps = vol_dist.mean_bps
    confidence = score_signal_confidence(
        alpha_signal_bps=_safe_float(alpha_signals.get("ensemble"), 0.0) * 25.0,
        uncertainty=uq,
        conformal_interval=conformal,
        regime=regime,
        market_state_confidence=_safe_float(nowcast.get("market_state_confidence"), 0.0),
        forecast_confidence=context.forecast_confidence,
    )
    signal = engine.signal.generate_trade_signal(
        alpha_signals=alpha_signals,
        return_distribution=ret_dist,
        uncertainty=uq,
        confidence=confidence,
    )

    cost = engine.execution.estimate_transaction_costs(
        fee_bps=context.fee_bps,
        slippage_bps=context.slippage_bps,
        spread_bps=context.spread_bps,
        liquidity_pressure=liquidity_pressure,
    )
    execution_monitor_score = engine.execution_quality_monitor.score(cost["total_bps"], signal.score_bps)
    slippage_ok = engine.execution.control_slippage(
        expected_slippage_bps=cost["slippage_bps"] + cost["impact_bps"],
        max_slippage_bps=engine.max_slippage_bps,
    )

    regime_params = engine.regime_params.parameters(regime)
    budget = engine.sizing.optimize_risk_budget(
        base_risk_budget_quote=engine.base_risk_budget_quote,
        regime=regime,
        uncertainty_bps=uq.total_bps,
        drawdown_pct=context.drawdown_pct,
    )
    budget = engine.profit_compound.allocate(budget, context.current_profit_bps)
    size = engine.sizing.calculate_position_size(
        risk_budget_quote=budget,
        confidence=confidence,
        alpha_score_bps=signal.score_bps,
        execution_risk=max(latency_risk, min(1.0, execution_monitor_score / 5.0)),
    )
    size *= engine.adaptive_sizing.scale(confidence, uq.total_bps)
    size *= engine.liquidity_aware_sizing.scale(context.depth_notional, context.spread_bps)
    alloc = engine.portfolio.allocate_portfolio_capital(
        position_size_quote=size,
        quote_free=context.quote_free,
        max_exposure_notional=context.max_exposure_notional,
        current_exposure_notional=context.signed_exposure_notional_quote,
    )

    risk_validation = engine.risk.validate_risk_constraints(
        confidence=confidence,
        uncertainty_bps=uq.total_bps,
        drift_report=drift_report,
        regime=regime,
        liquidity_pressure=liquidity_pressure,
        latency_risk=latency_risk,
        drawdown_pct=context.drawdown_pct,
        max_drawdown_pct=engine.max_drawdown_pct,
        now_ts=context.now_ts,
        last_submission_ts=context.last_submission_ts,
        order_cadence_s=context.order_cadence_s,
        current_exposure_notional=context.signed_exposure_notional_quote,
        incoming_notional=alloc,
        max_exposure_notional=context.max_exposure_notional,
        confidence_threshold=_safe_float(regime_params.get("confidence_threshold"), engine.confidence_threshold),
        uncertainty_threshold_bps=_safe_float(regime_params.get("uncertainty_threshold_bps"), engine.uncertainty_threshold_bps),
        latency_threshold=engine.latency_risk_threshold,
    )
    if not slippage_ok:
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        reasons.append("execution_risk")
        risk_validation["reasons"] = reasons

    has_position = context.position_notional_quote > 1e-9
    entry_action = engine.trade_decision.decide_trade_entry(
        trade_signal=signal,
        has_open_position=has_position,
        risk_allowed=bool(risk_validation.get("allowed", False)),
    )
    exit_action = engine.trade_decision.decide_trade_exit(
        trade_signal=signal,
        has_open_position=has_position,
        current_profit_bps=context.current_profit_bps,
    )
    managed_action, profit_protection = engine.trade_management.manage_open_position(
        exit_action=exit_action,
        current_profit_bps=context.current_profit_bps,
        peak_profit_bps=max(context.current_profit_bps, _safe_float(engine.model_state.get("peak_profit_bps"), 0.0)),
        side="sell",
        bid=context.bid,
        avg_entry_price=context.avg_entry_price,
        modeled_cost_bps=max(cost["modeled_floor_bps"], context.modeled_cost_floor_bps),
        min_net_profit_bps=max(120.0, context.sell_min_profit_bps),
        target_net_profit_bps=max(120.0, context.sell_target_profit_bps),
        hold_time_s=context.position_age_s,
    )
    engine.model_state["peak_profit_bps"] = max(
        _safe_float(engine.model_state.get("peak_profit_bps"), 0.0),
        context.current_profit_bps,
    )

    action = "hold"
    side = "hold"
    if managed_action in {"full_close", "partial_close", "reduce"}:
        action = managed_action
        side = "sell"
    elif entry_action in {"open", "add"}:
        action = entry_action
        side = "buy"
    elif entry_action == "skip":
        action = "skip"
        side = "hold"

    route = engine.execution.route_order(
        action=action,
        side=side,
        execution_urgency=_safe_float(nowcast.get("execution_urgency"), 0.0),
        spread_bps=context.spread_bps,
    )
    allow_exec, exec_reason = engine.execution.execute_order_safely(
        action=action,
        side=side,
        route=route,
        risk_validation=risk_validation,
        guards_mode=context.guards_mode,
    )
    skip_reason = ""
    if not allow_exec:
        action = "skip" if action != "hold" else "hold"
        side = "hold"
        skip_reason = exec_reason
    elif action == "hold":
        skip_reason = "hold"

    online_adaptation = engine.online_learning.adapt_model_online(
        drift_report=drift_report,
        online_learning_enabled=engine.online_learning_enabled,
        base_learning_rate=engine.base_learning_rate,
    )
    if bool(online_adaptation.get("adapt", False)):
        engine.model_state = engine.online_learning.update_model_incrementally(
            model_state=engine.model_state,
            fused_features=fused,
            realized_return_bps=ret_dist.mean_bps,
            adaptation=online_adaptation,
        )

    return DecisionOutcome(
        action=action,
        side=side,
        skip_reason=skip_reason,
        confidence=confidence,
        uncertainty_bps=uq.total_bps,
        drift_score=_safe_float(drift_report.get("drift_score"), 0.0),
        regime=regime,
        position_size_scale=_clamp(alloc / max(engine.base_risk_budget_quote, 1e-9), 0.0, 2.0),
        recommended_notional_quote=max(0.0, alloc),
        risk_flags=[str(r) for r in risk_validation.get("reasons", [])],
        route=route,
        alpha_signals={k: float(v) for k, v in alpha_signals.items()},
        market_state={k: (float(v) if isinstance(v, (int, float)) else v) for k, v in market_state.items()},
        nowcast={k: float(v) for k, v in nowcast.items()},
        forecast={
            "return_mean_bps": ret_dist.mean_bps,
            "return_std_bps": ret_dist.std_bps,
            "vol_mean_bps": vol_dist.mean_bps,
            "drawdown_risk_pct": drawdown_risk,
            "risk_adjusted_return_bps": engine.risk_inference.infer(
                return_distribution=ret_dist,
                uncertainty=uq,
                drawdown_risk_pct=drawdown_risk,
            )["risk_adjusted_return_bps"],
        },
        conformal_interval={
            "lower_bps": conformal.lower_bps,
            "upper_bps": conformal.upper_bps,
            "alpha": conformal.alpha,
        },
        execution_risk={
            "latency_risk": latency_risk,
            "execution_quality_ratio": execution_monitor_score,
            "liquidity_pressure": liquidity_pressure,
            "total_modeled_cost_bps": cost["total_bps"],
        },
        profit_protection=profit_protection,
        online_adaptation=online_adaptation,
        diagnostics={
            "signal": signal.reason,
            "entry_action": entry_action,
            "exit_action": exit_action,
            "managed_action": managed_action,
            "slippage_ok": slippage_ok,
            "drift_top_features": drift_report.get("top_features", []),
            "self_optimization_hint": engine.self_optimization.propose_adjustments(
                reject_rate=0.0,
                no_intent_rate=1.0 if action in {"skip", "hold"} else 0.0,
                fill_rate=0.0,
            ),
        },
    )


class AutonomousMarketPredictionAndDecisionEngine:
    """
    Central autonomous market prediction and decision system.
    This is the integration point used by the live orchestrator runtime path.
    """

    def __init__(
        self,
        *,
        base_risk_budget_quote: float = 25.0,
        confidence_threshold: float = 0.55,
        uncertainty_threshold_bps: float = 80.0,
        drift_threshold: float = 0.2,
        conformal_alpha: float = 0.1,
        regime_hold_s: float = 30.0,
        max_drawdown_pct: float = 8.0,
        max_slippage_bps: float = 6.0,
        latency_risk_threshold: float = 0.65,
        online_learning_enabled: bool = True,
        base_learning_rate: float = 0.02,
        enable_news: bool = False,
        enable_macro: bool = False,
        enable_fundamentals: bool = False,
    ) -> None:
        self.base_risk_budget_quote = max(0.0, _safe_float(base_risk_budget_quote, 25.0))
        self.confidence_threshold = _clamp(confidence_threshold, 0.0, 1.0)
        self.uncertainty_threshold_bps = max(1.0, _safe_float(uncertainty_threshold_bps, 80.0))
        self.drift_threshold = max(0.01, _safe_float(drift_threshold, 0.2))
        self.conformal_alpha = _clamp(conformal_alpha, 0.01, 0.4)
        self.regime_hold_s = max(1.0, _safe_float(regime_hold_s, 30.0))
        self.max_drawdown_pct = max(0.0, _safe_float(max_drawdown_pct, 8.0))
        self.max_slippage_bps = max(0.0, _safe_float(max_slippage_bps, 6.0))
        self.latency_risk_threshold = _clamp(latency_risk_threshold, 0.05, 1.0)
        self.online_learning_enabled = bool(online_learning_enabled)
        self.base_learning_rate = _clamp(base_learning_rate, 1e-5, 0.2)
        self.enable_news = bool(enable_news)
        self.enable_macro = bool(enable_macro)
        self.enable_fundamentals = bool(enable_fundamentals)

        self.signal = SignalEngine()
        self.forecasting = ProbabilisticMarketForecastingEngine()
        self.regime = RegimeEngine()
        self.risk = RiskEngine()
        self.sizing = PositionSizingEngine()
        self.execution = ExecutionEngine()
        self.portfolio = PortfolioAllocationEngine()
        self.drift = DriftDetectionEngine()
        self.trade_decision = RegimeAwareTradingDecisionSystem()
        self.market_state = MarketStateEstimator()
        self.nowcasting = NowcastingEngine()
        self.alpha = AdaptiveAlphaForecastingFramework()
        self.uq = UncertaintyQuantificationEngine()
        self.conformal = ConformalPredictionEngine()
        self.concept_drift = ConceptDriftDetectionEngine()
        self.online_learning = OnlineLearningEngine()
        self.multimodal = MultimodalForecastEngine()
        self.order_flow = OrderFlowIntelligenceEngine()
        self.lob = LimitOrderBookModel()
        self.trade_management = TradeManagementEngine()
        self.profit_protection = ProfitProtectionEngine()
        self.self_optimization = SelfOptimizationEngine()
        self.risk_inference = RiskCalibratedMarketInferenceEngine()

        self.smart_hold = SmartHoldExtension()
        self.dynamic_tp = DynamicTPExpansion()
        self.regime_params = RegimeSpecificTradingParameters()
        self.execution_quality_monitor = ExecutionQualityMonitor()
        self.latency_protection = LatencyArbitrageProtection()
        self.adaptive_sizing = AdaptivePositionSizing()
        self.liquidity_aware_sizing = LiquidityAwareTradeSizing()
        self.profit_compound = ProfitCompoundingAllocator()

        self.current_regime = ""
        self.last_regime_switch_ts = 0.0
        self.prev_vol_bps = 0.0
        self.model_state: dict[str, Any] = {
            "feature_means": {},
            "residual_history": list(deque(maxlen=512)),
            "peak_profit_bps": 0.0,
            "last_pred_return_bps": 0.0,
        }

    def run_decision_algorithm(self, context: DecisionContext) -> DecisionOutcome:
        return run_decision_algorithm(context, self)
