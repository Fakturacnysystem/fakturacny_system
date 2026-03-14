from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import importlib
import json
import logging
import math
import os
from typing import Any, Mapping

from autonomous_investment_robot.services.autonomous_decision.causal_market_twin import (
    CausalMarketTwinEngine,
    MarketTwinSnapshot,
    attach_market_twin_diagnostics,
    persist_market_twin_snapshot,
)
from autonomous_investment_robot.services.reliability.runtime_cache import FeatureCache, SignalCache


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


def _hard_sell_floor_bps(default: float = 30.0) -> float:
    raw = os.getenv(
        "AUTONOMOUS_SELL_HARD_MIN_PROFIT_BPS",
        os.getenv("AUTONOMOUS_SPOT_SELL_HARD_FLOOR_BPS", str(default)),
    )
    return max(0.0, _safe_float(raw, default))


def _stable_cache_key(payload: Mapping[str, Any]) -> str:
    """Build deterministic cache key from JSON-serializable mapping payload."""

    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _market_class_modifiers(market_class: str) -> dict[str, float]:
    cls = str(market_class or "crypto_spot").strip().lower()
    if cls == "xstock_etf":
        return {
            "confidence_add": 0.04,
            "uncertainty_delta_bps": -6.0,
            "latency_delta": -0.08,
            "slippage_mult": 0.82,
            "size_mult": 0.74,
        }
    if cls == "xstock":
        return {
            "confidence_add": 0.03,
            "uncertainty_delta_bps": -4.0,
            "latency_delta": -0.06,
            "slippage_mult": 0.88,
            "size_mult": 0.82,
        }
    return {
        "confidence_add": 0.0,
        "uncertainty_delta_bps": 0.0,
        "latency_delta": 0.0,
        "slippage_mult": 1.0,
        "size_mult": 1.0,
    }


def _normalize_market_class(value: str) -> str:
    cls = str(value or "crypto_spot").strip().lower()
    if cls in {"xstocks", "x_stock", "xstocks_equity"}:
        return "xstock"
    if cls in {"xstock_etfs", "xstocks_etf"}:
        return "xstock_etf"
    if cls in {"crypto", "spot", "crypto"}:
        return "crypto_spot"
    return cls


def _market_class_threshold_value(mapping: Mapping[str, float], market_class: str) -> float | None:
    cls = _normalize_market_class(market_class)
    if cls in mapping:
        return _safe_float(mapping.get(cls), 0.0)
    if cls.startswith("xstock") and "xstock" in mapping:
        return _safe_float(mapping.get("xstock"), 0.0)
    return None


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
    news_features: dict[str, float] = field(default_factory=dict)
    macro_features: dict[str, float] = field(default_factory=dict)
    fundamental_features: dict[str, float] = field(default_factory=dict)
    sentiment_features: dict[str, float] = field(default_factory=dict)
    market_class: str = "crypto_spot"
    market_session: str = "always_open_24_7"
    guards_mode: str = "strict"
    modeled_cost_floor_bps: float = 30.0
    sell_min_profit_bps: float = 30.0
    sell_target_profit_bps: float = 30.0
    signal_age_s: float = 0.0
    world_state_adapter: dict[str, Any] = field(default_factory=dict)


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


@dataclass(frozen=True)
class BackendForecastAdjustment:
    """Forecast backend adjustment applied to base probabilistic forecasts."""

    backend: str
    mean_adjust_bps: float
    std_scale: float
    confidence_scale: float
    diagnostics: dict[str, float] = field(default_factory=dict)


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


def ingest_sentiment_features(sentiment_payload: Mapping[str, float] | None = None) -> dict[str, float]:
    """Extract optional sentiment features."""

    payload = sentiment_payload or {}
    return {
        "sentiment_score": _clamp(_safe_float(payload.get("score"), 0.0), -1.0, 1.0),
        "sentiment_momentum": _clamp(_safe_float(payload.get("momentum"), 0.0), -1.0, 1.0),
        "sentiment_dispersion": max(0.0, _safe_float(payload.get("dispersion"), 0.0)),
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
    modal_payloads = {
        "news": news or {},
        "macro": macro or {},
        "fund": fundamentals or {},
        "sent": sentiment or {},
    }
    available_modalities = 1  # price/volume is always present
    for prefix, payload in modal_payloads.items():
        nonzero = 0
        if payload:
            available_modalities += 1
        for key, value in payload.items():
            val = _safe_float(value, 0.0)
            fused[f"{prefix}_{key}"] = val
            if abs(val) > 1e-9:
                nonzero += 1
        fused[f"{prefix}_feature_count"] = float(len(payload))
        fused[f"{prefix}_nonzero_count"] = float(nonzero)
        fused[f"{prefix}_available"] = 1.0 if payload else 0.0

    price_score = _safe_float(fused.get("ret_3"), 0.0)
    flow_score = _safe_float(fused.get("flow_imbalance"), 0.0)
    news_score = _safe_float(fused.get("news_news_sentiment"), 0.0)
    macro_score = _safe_float(fused.get("macro_macro_risk_on"), 0.0)
    fundamental_score = _safe_float(fused.get("fund_fundamental_growth"), 0.0)
    sentiment_score = _safe_float(fused.get("sent_sentiment_score"), 0.0)

    weighted: list[tuple[float, float]] = [
        (price_score, 0.45),
        (flow_score, 0.25),
    ]
    if modal_payloads["news"]:
        weighted.append((news_score, 0.10))
    if modal_payloads["macro"]:
        weighted.append((macro_score, 0.08))
    if modal_payloads["fund"]:
        weighted.append((fundamental_score, 0.07))
    if modal_payloads["sent"]:
        weighted.append((sentiment_score, 0.05))
    w_sum = sum(v * w for v, w in weighted)
    w_den = max(1e-9, sum(w for _v, w in weighted))
    fused["multimodal_score"] = _clamp(w_sum / w_den, -2.0, 2.0)
    fused["multimodal_coverage_ratio"] = _clamp(available_modalities / 5.0, 0.2, 1.0)
    fused["multimodal_quality"] = _clamp(
        0.6 * fused["multimodal_coverage_ratio"] + 0.4 * (1.0 - min(1.0, max(0.0, _safe_float(fused.get("spread_proxy"), 0.0)) / 0.01)),
        0.0,
        1.0,
    )
    return fused


def _extract_prefixed_features(features: Mapping[str, float], prefix: str) -> dict[str, float]:
    """Extract and de-prefix feature keys from a shared feature map."""

    out: dict[str, float] = {}
    pre = str(prefix)
    for key, value in features.items():
        k = str(key)
        if not k.startswith(pre):
            continue
        stripped = k[len(pre) :]
        if not stripped:
            continue
        out[stripped] = _safe_float(value, 0.0)
    return out


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
    modeled_floor = max(_hard_sell_floor_bps(), (2.0 * fee) + (2.0 * slip))
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


def detect_opportunity_decay(
    *,
    signal_age_s: float,
    latency_ms: float,
    regime: str,
    market_class: str,
    max_age_s: float = 45.0,
) -> float:
    """Score stale-opportunity risk in [0,1]."""

    age = max(0.0, _safe_float(signal_age_s, 0.0))
    age_cap = max(5.0, _safe_float(max_age_s, 45.0))
    age_score = _clamp(age / age_cap, 0.0, 1.0)
    latency_score = _clamp(max(0.0, _safe_float(latency_ms, 0.0)) / 1200.0, 0.0, 1.0)
    regime_mult = 1.15 if regime in {"PANIC", "HIGH_VOL"} else 0.90 if regime in {"COMPRESSION"} else 1.0
    cls_mult = 1.10 if _normalize_market_class(market_class).startswith("xstock") else 1.0
    return _clamp((0.75 * age_score + 0.25 * latency_score) * regime_mult * cls_mult, 0.0, 1.0)


def compute_cross_market_confirmation(
    *,
    market_class: str,
    fused_features: Mapping[str, float],
    market_state: Mapping[str, Any],
) -> float:
    """Estimate cross-market confirmation in [-1,1] used for buy-side gating."""

    macro_risk_on = _safe_float(fused_features.get("macro_macro_risk_on"), 0.0)
    sentiment = _safe_float(fused_features.get("sent_sentiment_score"), 0.0)
    trend_bps = _safe_float(market_state.get("trend_bps"), 0.0)
    trend = _clamp(trend_bps / 120.0, -1.0, 1.0)
    class_bias = 0.10 if _normalize_market_class(market_class).startswith("xstock") else 0.0
    return _clamp((0.50 * trend) + (0.35 * macro_risk_on) + (0.15 * sentiment) + class_bias, -1.0, 1.0)


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
    liquidity_threshold: float = -0.6,
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
    if liquidity_pressure < _safe_float(liquidity_threshold, -0.6):
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

    hard_floor_cfg = _hard_sell_floor_bps()
    hard_floor_bps = max(
        hard_floor_cfg,
        _safe_float(min_net_profit_bps, hard_floor_cfg),
        _safe_float(modeled_cost_bps, 0.0),
    )
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


class PortfolioDiversificationHook:
    def scale(
        self,
        *,
        cross_pair_score: float,
        concentration: float,
        correlation_proxy: float,
    ) -> float:
        conc = _clamp(concentration, 0.0, 1.0)
        corr = _clamp(correlation_proxy, -1.0, 1.0)
        cross = _clamp(cross_pair_score, -1.0, 1.0)
        concentration_penalty = 1.0 - (0.35 * conc)
        correlation_penalty = 1.0 - (0.20 * max(0.0, corr))
        opportunity_boost = 1.0 + (0.20 * max(0.0, cross))
        return _clamp(concentration_penalty * correlation_penalty * opportunity_boost, 0.35, 1.35)


class DynamicCapitalRotationEngine:
    def score(self, *, current_symbol_score: float, best_symbol_score: float, regime: str) -> float:
        rel = _safe_float(best_symbol_score, 0.0) - _safe_float(current_symbol_score, 0.0)
        regime_mult = 1.1 if regime in {"BULL_TREND", "TREND"} else 0.8 if regime in {"PANIC", "HIGH_VOL"} else 1.0
        return _clamp(rel * regime_mult / 40.0, -1.0, 1.0)


class ForecastBackendAdapter:
    """Adapter for transformer/foundation-ready forecast adjustments."""

    backend_name = "baseline"

    def __init__(self, backend_name: str | None = None) -> None:
        if backend_name:
            self.backend_name = str(backend_name)

    def predict_adjustment(
        self,
        *,
        fused_features: Mapping[str, float],
        regime: str,
        nowcast: Mapping[str, float],
    ) -> BackendForecastAdjustment:
        _ = fused_features
        _ = regime
        _ = nowcast
        return BackendForecastAdjustment(
            backend=self.backend_name,
            mean_adjust_bps=0.0,
            std_scale=1.0,
            confidence_scale=1.0,
            diagnostics={"enabled": 0.0},
        )


class TransformerReadyForecastBackend(ForecastBackendAdapter):
    backend_name = "transformer_ready"

    def predict_adjustment(
        self,
        *,
        fused_features: Mapping[str, float],
        regime: str,
        nowcast: Mapping[str, float],
    ) -> BackendForecastAdjustment:
        trend_bps = _safe_float(fused_features.get("ret_3"), 0.0) * 10000.0
        flow = _safe_float(fused_features.get("flow_imbalance"), 0.0)
        urgency = _safe_float(nowcast.get("execution_urgency"), 0.0)
        regime_boost = 1.0 if regime in {"BULL_TREND", "TREND"} else 0.75 if regime in {"BEAR_TREND", "PANIC"} else 0.9
        mean_adjust = _clamp((0.15 * trend_bps * regime_boost) + (12.0 * flow), -25.0, 25.0)
        std_scale = _clamp(1.0 + (0.2 * abs(flow)) + (0.15 * urgency), 0.85, 1.45)
        confidence_scale = _clamp(1.0 + (0.08 * max(0.0, trend_bps) / 80.0) - (0.10 * urgency), 0.75, 1.20)
        return BackendForecastAdjustment(
            backend=self.backend_name,
            mean_adjust_bps=mean_adjust,
            std_scale=std_scale,
            confidence_scale=confidence_scale,
            diagnostics={
                "enabled": 1.0,
                "trend_bps": trend_bps,
                "flow": flow,
                "urgency": urgency,
            },
        )


class FoundationReadyForecastBackend(ForecastBackendAdapter):
    backend_name = "foundation_ready"

    def predict_adjustment(
        self,
        *,
        fused_features: Mapping[str, float],
        regime: str,
        nowcast: Mapping[str, float],
    ) -> BackendForecastAdjustment:
        multimodal = _safe_float(fused_features.get("multimodal_score"), 0.0)
        sentiment = _safe_float(fused_features.get("sent_sentiment_score"), 0.0)
        macro = _safe_float(fused_features.get("macro_macro_risk_on"), 0.0)
        market_state_conf = _safe_float(nowcast.get("market_state_confidence"), 0.0)
        regime_sign = -1.0 if regime in {"BEAR_TREND", "PANIC"} else 1.0
        mean_adjust = _clamp((18.0 * multimodal) + (8.0 * sentiment) + (10.0 * macro * regime_sign), -30.0, 30.0)
        std_scale = _clamp(1.0 + (0.15 * (1.0 - market_state_conf)) + (0.1 * abs(multimodal)), 0.8, 1.5)
        confidence_scale = _clamp(1.0 + (0.20 * market_state_conf) - (0.05 * abs(sentiment - macro)), 0.70, 1.25)
        return BackendForecastAdjustment(
            backend=self.backend_name,
            mean_adjust_bps=mean_adjust,
            std_scale=std_scale,
            confidence_scale=confidence_scale,
            diagnostics={
                "enabled": 1.0,
                "multimodal_score": multimodal,
                "sentiment_score": sentiment,
                "macro_score": macro,
                "market_state_confidence": market_state_conf,
            },
        )


class PluginForecastBackendAdapter(ForecastBackendAdapter):
    """Thin wrapper around optional external backend plugin."""

    def __init__(self, plugin: Any, backend_name: str) -> None:
        super().__init__(backend_name=backend_name)
        self.plugin = plugin

    def predict_adjustment(
        self,
        *,
        fused_features: Mapping[str, float],
        regime: str,
        nowcast: Mapping[str, float],
    ) -> BackendForecastAdjustment:
        fn = getattr(self.plugin, "predict_adjustment", None)
        if not callable(fn):
            raise AttributeError("forecast_backend_plugin_missing_predict_adjustment")
        out = fn(fused_features=fused_features, regime=regime, nowcast=nowcast)
        if isinstance(out, BackendForecastAdjustment):
            return out
        if not isinstance(out, Mapping):
            raise TypeError("forecast_backend_plugin_invalid_output")
        return BackendForecastAdjustment(
            backend=str(out.get("backend", self.backend_name) or self.backend_name),
            mean_adjust_bps=_safe_float(out.get("mean_adjust_bps"), 0.0),
            std_scale=_clamp(_safe_float(out.get("std_scale"), 1.0), 0.5, 2.0),
            confidence_scale=_clamp(_safe_float(out.get("confidence_scale"), 1.0), 0.5, 2.0),
            diagnostics={
                str(k): _safe_float(v, 0.0)
                for k, v in dict(out.get("diagnostics", {})).items()
                if isinstance(k, str)
            },
        )


class ForecastBackendRegistry:
    """Resolve built-in or plugin forecasting backends."""

    def __init__(self) -> None:
        self._builtins: dict[str, type[ForecastBackendAdapter]] = {
            "baseline": ForecastBackendAdapter,
            "transformer": TransformerReadyForecastBackend,
            "transformer_ready": TransformerReadyForecastBackend,
            "foundation": FoundationReadyForecastBackend,
            "foundation_ready": FoundationReadyForecastBackend,
        }

    def _resolve_plugin(self, plugin_spec: str) -> ForecastBackendAdapter | None:
        spec = str(plugin_spec or "").strip()
        if not spec:
            return None
        mod_name, sep, attr_name = spec.partition(":")
        if not mod_name or not sep or not attr_name:
            LOGGER.warning("forecast_backend_plugin_invalid_spec", extra={"plugin_spec": spec})
            return None
        try:
            mod = importlib.import_module(mod_name)
            plugin_obj = getattr(mod, attr_name)
            instance = plugin_obj() if isinstance(plugin_obj, type) else plugin_obj
            return PluginForecastBackendAdapter(instance, backend_name=f"plugin:{mod_name}:{attr_name}")
        except Exception as exc:
            LOGGER.warning("forecast_backend_plugin_load_failed", extra={"plugin_spec": spec, "error": str(exc)})
            return None

    def resolve(
        self,
        *,
        backend_name: str,
        enable_transformer_backend: bool,
        enable_foundation_backend: bool,
        plugin_spec: str,
    ) -> ForecastBackendAdapter:
        plugin_adapter = self._resolve_plugin(plugin_spec)
        if plugin_adapter is not None:
            return plugin_adapter

        requested = str(backend_name or "baseline").strip().lower()
        if requested == "auto":
            if enable_foundation_backend:
                return FoundationReadyForecastBackend()
            if enable_transformer_backend:
                return TransformerReadyForecastBackend()
            return ForecastBackendAdapter()
        cls = self._builtins.get(requested)
        if cls is not None:
            return cls()
        if enable_foundation_backend:
            return FoundationReadyForecastBackend()
        if enable_transformer_backend:
            return TransformerReadyForecastBackend()
        return ForecastBackendAdapter()


def _apply_backend_adjustment_to_distribution(
    distribution: DistributionForecast,
    adjustment: BackendForecastAdjustment,
) -> DistributionForecast:
    """Apply backend adjustment while preserving quantile structure."""

    if (
        abs(adjustment.mean_adjust_bps) <= 1e-9
        and abs(adjustment.std_scale - 1.0) <= 1e-9
    ):
        return distribution
    mean_bps = distribution.mean_bps + adjustment.mean_adjust_bps
    std_bps = max(1.0, distribution.std_bps * _clamp(adjustment.std_scale, 0.5, 2.0))
    quantiles: dict[str, float] = {}
    for key in distribution.quantiles_bps.keys():
        try:
            q = float(key)
        except Exception:
            quantiles[key] = mean_bps
            continue
        z = _NORMAL_Z.get(q, 0.0)
        quantiles[key] = mean_bps + (z * std_bps)
    return DistributionForecast(mean_bps=mean_bps, std_bps=std_bps, quantiles_bps=quantiles)


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

    def ingest_sentiment_features(self, **kwargs: Any) -> dict[str, float]:
        return ingest_sentiment_features(**kwargs)

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

    def __init__(self, *, window: int = 120, min_samples: int = 24, apply_every: int = 12) -> None:
        self.history: deque[dict[str, float]] = deque(maxlen=max(20, int(window)))
        self.min_samples = max(10, int(min_samples))
        self.apply_every = max(1, int(apply_every))
        self._steps = 0

    def propose_adjustments(
        self,
        *,
        reject_rate: float,
        no_intent_rate: float,
        fill_rate: float,
        confidence_guard_rate: float = 0.0,
        liquidity_guard_rate: float = 0.0,
    ) -> dict[str, float]:
        adjustments: dict[str, float] = {}
        if reject_rate > 0.4:
            adjustments["confidence_threshold_delta"] = 0.03
            adjustments["uncertainty_threshold_delta_bps"] = -5.0
            adjustments["latency_risk_threshold_delta"] = -0.02
        elif no_intent_rate > 0.7 and fill_rate < 0.25 and confidence_guard_rate > 0.35:
            adjustments["confidence_threshold_delta"] = -0.015
            adjustments["uncertainty_threshold_delta_bps"] = 4.0
        if liquidity_guard_rate > 0.30:
            # Liquidity threshold is negative. Lowering it slightly reduces false blocks.
            adjustments["liquidity_threshold_delta"] = -0.03
        if fill_rate < 0.15:
            adjustments["max_slippage_bps_delta"] = 0.35
        return {k: v for k, v in adjustments.items() if k not in self._FORBIDDEN_KEYS}

    def _bounded_apply(self, *, engine: Any, adjustments: Mapping[str, float]) -> dict[str, float]:
        applied: dict[str, float] = {}
        if "confidence_threshold_delta" in adjustments:
            prev = float(engine.confidence_threshold)
            engine.confidence_threshold = _clamp(prev + _safe_float(adjustments["confidence_threshold_delta"], 0.0), 0.40, 0.85)
            if abs(engine.confidence_threshold - prev) > 1e-9:
                applied["confidence_threshold"] = float(engine.confidence_threshold)
        if "uncertainty_threshold_delta_bps" in adjustments:
            prev = float(engine.uncertainty_threshold_bps)
            engine.uncertainty_threshold_bps = _clamp(prev + _safe_float(adjustments["uncertainty_threshold_delta_bps"], 0.0), 45.0, 180.0)
            if abs(engine.uncertainty_threshold_bps - prev) > 1e-9:
                applied["uncertainty_threshold_bps"] = float(engine.uncertainty_threshold_bps)
        if "max_slippage_bps_delta" in adjustments:
            prev = float(engine.max_slippage_bps)
            engine.max_slippage_bps = _clamp(prev + _safe_float(adjustments["max_slippage_bps_delta"], 0.0), 2.0, 30.0)
            if abs(engine.max_slippage_bps - prev) > 1e-9:
                applied["max_slippage_bps"] = float(engine.max_slippage_bps)
        if "latency_risk_threshold_delta" in adjustments:
            prev = float(engine.latency_risk_threshold)
            engine.latency_risk_threshold = _clamp(prev + _safe_float(adjustments["latency_risk_threshold_delta"], 0.0), 0.35, 0.90)
            if abs(engine.latency_risk_threshold - prev) > 1e-9:
                applied["latency_risk_threshold"] = float(engine.latency_risk_threshold)
        if "liquidity_threshold_delta" in adjustments:
            prev = float(engine.liquidity_pressure_guard_threshold)
            engine.liquidity_pressure_guard_threshold = _clamp(prev + _safe_float(adjustments["liquidity_threshold_delta"], 0.0), -0.95, -0.20)
            if abs(engine.liquidity_pressure_guard_threshold - prev) > 1e-9:
                applied["liquidity_pressure_guard_threshold"] = float(engine.liquidity_pressure_guard_threshold)
        return applied

    def optimize(
        self,
        *,
        engine: Any,
        action: str,
        skip_reason: str,
        risk_flags: list[str],
        confidence: float,
    ) -> dict[str, Any]:
        self._steps += 1
        reason = str(skip_reason or "").lower()
        risk_flag_set = {str(r).lower() for r in risk_flags}
        row = {
            "reject": 1.0 if ("execution_risk" in risk_flag_set or "latency_guard" in risk_flag_set) else 0.0,
            "no_intent": 1.0 if reason == "no_intent" else 0.0,
            "filled": 1.0 if action in {"open", "add", "reduce", "partial_close", "full_close"} and reason in {"", "allowed"} else 0.0,
            "confidence_guard": 1.0 if "confidence_guard" in risk_flag_set else 0.0,
            "liquidity_guard": 1.0 if "liquidity_filter" in risk_flag_set else 0.0,
            "confidence": _safe_float(confidence, 0.0),
        }
        self.history.append(row)
        n = len(self.history)
        if n < self.min_samples or (self._steps % self.apply_every) != 0:
            return {"applied": {}, "samples": n}

        n_f = float(max(1, n))
        reject_rate = sum(r["reject"] for r in self.history) / n_f
        no_intent_rate = sum(r["no_intent"] for r in self.history) / n_f
        fill_rate = sum(r["filled"] for r in self.history) / n_f
        confidence_guard_rate = sum(r["confidence_guard"] for r in self.history) / n_f
        liquidity_guard_rate = sum(r["liquidity_guard"] for r in self.history) / n_f

        adjustments = self.propose_adjustments(
            reject_rate=reject_rate,
            no_intent_rate=no_intent_rate,
            fill_rate=fill_rate,
            confidence_guard_rate=confidence_guard_rate,
            liquidity_guard_rate=liquidity_guard_rate,
        )
        applied = self._bounded_apply(engine=engine, adjustments=adjustments)
        return {
            "applied": applied,
            "requested": adjustments,
            "samples": n,
            "reject_rate": reject_rate,
            "no_intent_rate": no_intent_rate,
            "fill_rate": fill_rate,
            "confidence_guard_rate": confidence_guard_rate,
            "liquidity_guard_rate": liquidity_guard_rate,
        }


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

    feature_cache_key = _stable_cache_key(
        {
            "symbol": str(context.symbol),
            "market_class": str(context.market_class),
            "bid": round(float(context.bid), 8),
            "ask": round(float(context.ask), 8),
            "depth_notional": round(float(context.depth_notional), 6),
            "features": {str(k): round(float(v), 8) for k, v in sorted(dict(context.features).items())},
            "enable_news": bool(engine.enable_news),
            "enable_macro": bool(engine.enable_macro),
            "enable_fundamentals": bool(engine.enable_fundamentals),
            "enable_sentiment": bool(engine.enable_sentiment),
        }
    )
    feature_cache_hit = False
    cached_fused = engine.feature_cache.get(feature_cache_key)
    if cached_fused is not None:
        fused = dict(cached_fused)
        feature_cache_hit = True
    else:
        price_volume = engine.multimodal.ingest_price_volume_features(features=context.features)
        news_payload = context.news_features or _extract_prefixed_features(context.features, "news_")
        macro_payload = context.macro_features or _extract_prefixed_features(context.features, "macro_")
        fundamental_payload = context.fundamental_features or _extract_prefixed_features(context.features, "fund_")
        sentiment_payload = context.sentiment_features or _extract_prefixed_features(context.features, "sent_")
        news = engine.multimodal.ingest_news_features(news_payload=news_payload)
        macro = engine.multimodal.ingest_macro_features(macro_payload=macro_payload)
        fundamentals = engine.multimodal.ingest_fundamental_features(fundamental_payload=fundamental_payload)
        sentiment = engine.multimodal.ingest_sentiment_features(sentiment_payload=sentiment_payload)
        fused = engine.multimodal.fuse_multimodal_features(
            price_volume=price_volume,
            news=news if engine.enable_news else {},
            macro=macro if engine.enable_macro else {},
            fundamentals=fundamentals if engine.enable_fundamentals else {},
            sentiment=sentiment if engine.enable_sentiment else {},
        )
        engine.feature_cache.set(feature_cache_key, dict(fused))
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
    liquidity_state = engine.liquidity_heatmap.classify(context.depth_notional, context.spread_bps)
    market_state["liquidity_state"] = liquidity_state
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
    backend_adjustment = engine.forecast_backend_adapter.predict_adjustment(
        fused_features=fused,
        regime=regime,
        nowcast=nowcast,
    )
    ret_dist = _apply_backend_adjustment_to_distribution(ret_dist, backend_adjustment)
    vol_dist = _apply_backend_adjustment_to_distribution(
        vol_dist,
        BackendForecastAdjustment(
            backend=backend_adjustment.backend,
            mean_adjust_bps=0.0,
            std_scale=max(0.8, min(1.5, backend_adjustment.std_scale)),
            confidence_scale=backend_adjustment.confidence_scale,
            diagnostics=backend_adjustment.diagnostics,
        ),
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
    prev_alpha = _safe_float(engine.model_state.get("last_alpha_ensemble"), _safe_float(alpha_signals.get("ensemble"), 0.0))
    decay_score = engine.signal_decay.score(_safe_float(alpha_signals.get("ensemble"), 0.0), prev_alpha)
    engine.model_state["last_alpha_ensemble"] = _safe_float(alpha_signals.get("ensemble"), 0.0)
    alpha_signals["signal_decay"] = float(decay_score)
    if decay_score > engine.signal_decay_guard_threshold:
        alpha_signals["ensemble"] = float(_safe_float(alpha_signals.get("ensemble"), 0.0) - min(0.5, decay_score * 0.4))
    adjusted_forecast_confidence = _clamp(
        context.forecast_confidence * _clamp(backend_adjustment.confidence_scale, 0.65, 1.25),
        0.0,
        1.0,
    )
    confidence = score_signal_confidence(
        alpha_signal_bps=_safe_float(alpha_signals.get("ensemble"), 0.0) * 25.0,
        uncertainty=uq,
        conformal_interval=conformal,
        regime=regime,
        market_state_confidence=_safe_float(nowcast.get("market_state_confidence"), 0.0),
        forecast_confidence=adjusted_forecast_confidence,
    )
    confidence = _clamp(confidence * (1.0 - min(0.25, max(0.0, decay_score) * 0.2)), 0.0, 1.0)
    signal_cache_key = _stable_cache_key(
        {
            "symbol": str(context.symbol),
            "alpha_ensemble": round(_safe_float(alpha_signals.get("ensemble"), 0.0), 8),
            "return_mean_bps": round(float(ret_dist.mean_bps), 8),
            "return_std_bps": round(float(ret_dist.std_bps), 8),
            "uncertainty_bps": round(float(uq.total_bps), 8),
            "confidence": round(float(confidence), 8),
        }
    )
    signal_cache_hit = False
    cached_signal = engine.signal_cache.get(signal_cache_key)
    if isinstance(cached_signal, dict):
        signal = TradeSignal(
            action=str(cached_signal.get("action", "hold") or "hold"),
            side=str(cached_signal.get("side", "hold") or "hold"),
            score_bps=float(cached_signal.get("score_bps", 0.0) or 0.0),
            confidence=float(cached_signal.get("confidence", confidence) or confidence),
            reason=str(cached_signal.get("reason", "cached_signal") or "cached_signal"),
        )
        signal_cache_hit = True
    else:
        signal = engine.signal.generate_trade_signal(
            alpha_signals=alpha_signals,
            return_distribution=ret_dist,
            uncertainty=uq,
            confidence=confidence,
        )
        engine.signal_cache.set(
            signal_cache_key,
            {
                "action": str(signal.action),
                "side": str(signal.side),
                "score_bps": float(signal.score_bps),
                "confidence": float(signal.confidence),
                "reason": str(signal.reason),
            },
        )

    cost = engine.execution.estimate_transaction_costs(
        fee_bps=context.fee_bps,
        slippage_bps=context.slippage_bps,
        spread_bps=context.spread_bps,
        liquidity_pressure=liquidity_pressure,
    )
    regime_params = engine.regime_params.parameters(regime)
    market_mod = _market_class_modifiers(context.market_class)
    effective_max_slippage_bps = _clamp(
        engine.max_slippage_bps * _safe_float(market_mod.get("slippage_mult"), 1.0),
        0.5,
        30.0,
    )
    effective_conf_threshold = _clamp(
        _safe_float(regime_params.get("confidence_threshold"), engine.confidence_threshold)
        + _safe_float(market_mod.get("confidence_add"), 0.0),
        0.0,
        0.95,
    )
    class_conf_floor = _market_class_threshold_value(engine.market_class_confidence_thresholds, context.market_class)
    if class_conf_floor is not None:
        effective_conf_threshold = max(effective_conf_threshold, _clamp(class_conf_floor, 0.0, 0.95))
    effective_uncertainty_threshold_bps = max(
        20.0,
        _safe_float(regime_params.get("uncertainty_threshold_bps"), engine.uncertainty_threshold_bps)
        + _safe_float(market_mod.get("uncertainty_delta_bps"), 0.0),
    )
    class_uncertainty_cap = _market_class_threshold_value(engine.market_class_uncertainty_threshold_bps, context.market_class)
    if class_uncertainty_cap is not None and class_uncertainty_cap > 0.0:
        effective_uncertainty_threshold_bps = max(20.0, min(effective_uncertainty_threshold_bps, class_uncertainty_cap))
    effective_latency_threshold = _clamp(
        engine.latency_risk_threshold + _safe_float(market_mod.get("latency_delta"), 0.0),
        0.05,
        1.0,
    )
    execution_monitor_score = engine.execution_quality_monitor.score(cost["total_bps"], signal.score_bps)
    slippage_ok = engine.execution.control_slippage(
        expected_slippage_bps=cost["slippage_bps"] + cost["impact_bps"],
        max_slippage_bps=effective_max_slippage_bps,
    )
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
    size *= _clamp(_safe_float(market_mod.get("size_mult"), 1.0), 0.25, 1.5)
    regime_size_multiplier = _clamp(
        _safe_float(engine.regime_size_multipliers.get(regime), 1.0),
        0.25,
        1.75,
    )
    size *= regime_size_multiplier
    cross_pair_score = _safe_float(alpha_signals.get("cross_pair_opportunity"), 0.0)
    portfolio_div_scale = engine.portfolio_diversifier.scale(
        cross_pair_score=cross_pair_score,
        concentration=_safe_float(context.features.get("portfolio_concentration"), 1.0),
        correlation_proxy=_safe_float(context.features.get("portfolio_corr_proxy"), 0.0),
    )
    rotation_score = engine.capital_rotation.score(
        current_symbol_score=_safe_float(context.features.get("portfolio_symbol_score"), 0.0),
        best_symbol_score=_safe_float(context.features.get("portfolio_best_symbol_score"), 0.0),
        regime=regime,
    )
    rotation_scale = _clamp(1.0 + (0.15 * rotation_score), 0.6, 1.3)
    size *= portfolio_div_scale
    size *= rotation_scale
    cross_market_score = compute_cross_market_confirmation(
        market_class=context.market_class,
        fused_features=fused,
        market_state=market_state,
    )
    cross_market_pass = (not engine.cross_market_confirmation_enabled) or (
        cross_market_score >= engine.cross_market_confirmation_min
    )
    signal_age_s = max(0.0, _safe_float(context.signal_age_s, -1.0))
    if signal_age_s <= 0.0:
        feature_ts = _safe_float(context.features.get("signal_ts"), 0.0)
        if feature_ts <= 0.0:
            feature_ts = _safe_float(context.features.get("feature_ts"), context.now_ts)
        signal_age_s = max(0.0, _safe_float(context.now_ts, 0.0) - max(0.0, feature_ts))
    opportunity_decay_score = detect_opportunity_decay(
        signal_age_s=signal_age_s,
        latency_ms=context.latency_ms,
        regime=regime,
        market_class=context.market_class,
        max_age_s=engine.opportunity_decay_max_age_s,
    )
    if opportunity_decay_score > engine.opportunity_decay_guard_threshold:
        confidence = _clamp(confidence * (1.0 - min(0.50, opportunity_decay_score * 0.6)), 0.0, 1.0)
    has_position = context.position_notional_quote > 1e-9
    market_twin_snapshot: MarketTwinSnapshot | None = None
    market_twin_best_action = "skip"
    market_twin_route_pref = ""
    market_twin_sizing_scale = 1.0
    market_twin_block_reason = ""
    market_twin_error = ""
    market_twin_exit_override = ""
    try:
        market_twin_snapshot = engine.market_twin.evaluate(
            timestamp=context.now_ts,
            symbol=context.symbol,
            market_class=context.market_class,
            regime=regime,
            market_state=market_state,
            nowcast=nowcast,
            fused_features=fused,
            confidence=confidence,
            uncertainty_bps=uq.total_bps,
            liquidity_pressure=liquidity_pressure,
            projected_edge_bps=signal.score_bps,
            fee_bps=context.fee_bps,
            slippage_bps=context.slippage_bps,
            spread_bps=context.spread_bps,
            depth_notional=context.depth_notional,
            latency_risk=latency_risk,
            signal_age_s=signal_age_s,
            cadence_s=context.order_cadence_s,
            has_position=has_position,
            current_profit_bps=context.current_profit_bps,
        )
        best_scenario = market_twin_snapshot.best_scenario()
        if best_scenario is not None:
            market_twin_best_action = str(best_scenario.action)
            if best_scenario.action == "enter_limit":
                market_twin_route_pref = "maker"
            elif best_scenario.action == "enter_market":
                market_twin_route_pref = "taker"
            if best_scenario.action in {"enter_market", "enter_limit", "scale_in_entry"}:
                market_twin_sizing_scale = _clamp(best_scenario.fill_probability, 0.35, 1.0)
            if signal.side == "buy" and best_scenario.action in {"skip", "wait_one_cadence"}:
                market_twin_sizing_scale = 0.0
                market_twin_block_reason = "counterfactual_no_edge" if best_scenario.action == "skip" else "counterfactual_wait_preferred"
            if has_position and best_scenario.action in {"partial_exit", "full_exit"}:
                market_twin_exit_override = "partial_close" if best_scenario.action == "partial_exit" else "full_close"
    except Exception as exc:
        market_twin_error = str(exc)
        LOGGER.warning("market_twin_evaluation_failed", extra={"symbol": context.symbol, "error": market_twin_error})

    alloc = engine.portfolio.allocate_portfolio_capital(
        position_size_quote=size,
        quote_free=context.quote_free,
        max_exposure_notional=context.max_exposure_notional,
        current_exposure_notional=context.signed_exposure_notional_quote,
    )
    alloc *= max(0.0, market_twin_sizing_scale)

    world_state_adapter = dict(context.world_state_adapter or {})
    world_state_available = bool(world_state_adapter.get("world_state_available", True))
    world_state_graph_available = bool(world_state_adapter.get("graph_available", world_state_available))
    world_state_safe_to_trade = bool(
        world_state_adapter.get("safe_to_trade", world_state_available and world_state_graph_available)
    )
    world_state_source = str(world_state_adapter.get("source", "none") or "none")
    world_state_freshness = world_state_adapter.get("freshness_s", {})
    world_state_freshness_s = (
        {str(k): max(0.0, _safe_float(v, 0.0)) for k, v in dict(world_state_freshness).items()}
        if isinstance(world_state_freshness, Mapping)
        else {}
    )
    stale_domains_raw = world_state_adapter.get("stale_domains", [])
    world_state_stale_domains = (
        [str(item) for item in stale_domains_raw if str(item)]
        if isinstance(stale_domains_raw, list)
        else []
    )
    stale_critical_raw = world_state_adapter.get("stale_critical_domains", [])
    world_state_stale_critical_domains = (
        [str(item) for item in stale_critical_raw if str(item)]
        if isinstance(stale_critical_raw, list)
        else []
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
        confidence_threshold=effective_conf_threshold,
        uncertainty_threshold_bps=effective_uncertainty_threshold_bps,
        latency_threshold=effective_latency_threshold,
        liquidity_threshold=engine.liquidity_pressure_guard_threshold,
    )
    if (not world_state_available) or (not world_state_graph_available):
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        if "world_state_unavailable" not in reasons:
            reasons.append("world_state_unavailable")
        risk_validation["reasons"] = reasons
    if world_state_stale_critical_domains:
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        if "world_state_stale" not in reasons:
            reasons.append("world_state_stale")
        risk_validation["reasons"] = reasons
    if not world_state_safe_to_trade:
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        if "world_state_guard" not in reasons:
            reasons.append("world_state_guard")
        risk_validation["reasons"] = reasons
    if str(context.market_session or "").lower() in {"xstock_session_closed", "xstock_weekend_closed"}:
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        if "session_closed" not in reasons:
            reasons.append("session_closed")
        risk_validation["reasons"] = reasons
    latency_allowed = engine.latency_protection.allow(latency_risk, effective_latency_threshold)
    if not latency_allowed:
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        if "latency_guard" not in reasons:
            reasons.append("latency_guard")
        risk_validation["reasons"] = reasons
    if execution_monitor_score > engine.execution_quality_guard_threshold:
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        if "execution_risk" not in reasons:
            reasons.append("execution_risk")
        risk_validation["reasons"] = reasons
    if decay_score > engine.signal_decay_guard_threshold:
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        if "signal_decay" not in reasons:
            reasons.append("signal_decay")
        risk_validation["reasons"] = reasons
    if not slippage_ok:
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        if "execution_risk" not in reasons:
            reasons.append("execution_risk")
        risk_validation["reasons"] = reasons
    if opportunity_decay_score > engine.opportunity_decay_guard_threshold:
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        if "opportunity_decay" not in reasons:
            reasons.append("opportunity_decay")
        risk_validation["reasons"] = reasons
    if signal.side == "buy" and not cross_market_pass:
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        if "cross_market_filter" not in reasons:
            reasons.append("cross_market_filter")
        risk_validation["reasons"] = reasons
    if market_twin_block_reason:
        risk_validation["allowed"] = False
        reasons = list(risk_validation.get("reasons", []))
        if market_twin_block_reason not in reasons:
            reasons.append(market_twin_block_reason)
        risk_validation["reasons"] = reasons

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
    if has_position and exit_action == "hold" and market_twin_exit_override in {"partial_close", "full_close"}:
        exit_action = market_twin_exit_override
    sell_floor_bps = _hard_sell_floor_bps()
    effective_target_bps = engine.dynamic_tp.expand(
        max(sell_floor_bps, context.sell_target_profit_bps),
        confidence,
        regime,
    )
    adaptive_hold_s = engine.adaptive_hold_base_s * (
        1.35
        if regime in {"BULL_TREND", "TREND"}
        else 0.75
        if regime in {"PANIC", "HIGH_VOL"}
        else 1.0
    ) * (1.0 + (0.5 * max(0.0, confidence - 0.5)))
    smart_hold_extend = engine.smart_hold.should_extend(
        confidence,
        _safe_float(market_state.get("trend_bps"), 0.0),
    )
    managed_action, profit_protection = engine.trade_management.manage_open_position(
        exit_action=exit_action,
        current_profit_bps=context.current_profit_bps,
        peak_profit_bps=max(context.current_profit_bps, _safe_float(engine.model_state.get("peak_profit_bps"), 0.0)),
        side="sell",
        bid=context.bid,
        avg_entry_price=context.avg_entry_price,
        modeled_cost_bps=max(cost["modeled_floor_bps"], context.modeled_cost_floor_bps),
        min_net_profit_bps=max(sell_floor_bps, context.sell_min_profit_bps),
        target_net_profit_bps=max(sell_floor_bps, effective_target_bps),
        hold_time_s=context.position_age_s,
    )
    if (
        has_position
        and managed_action in {"full_close", "partial_close", "reduce"}
        and smart_hold_extend
        and context.position_age_s < adaptive_hold_s
        and context.current_profit_bps >= max(sell_floor_bps, 0.6 * effective_target_bps)
    ):
        managed_action = "hold"
        hold_diag = {
            "reason": "smart_hold_extension",
            "adaptive_hold_s": adaptive_hold_s,
            "effective_target_net_bps": effective_target_bps,
            "hold_time_s": context.position_age_s,
        }
        if isinstance(profit_protection, dict):
            profit_protection = {**profit_protection, **hold_diag}
        else:
            profit_protection = hold_diag
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
    if action in {"open", "add"} and market_twin_route_pref == "maker":
        route["order_type"] = "maker"
        route["taker_allowed"] = False
    elif action in {"open", "add"} and market_twin_route_pref == "taker":
        route["order_type"] = "taker"
        route["taker_allowed"] = True
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

    self_optimization = engine.self_optimization.optimize(
        engine=engine,
        action=action,
        skip_reason=skip_reason,
        risk_flags=[str(r) for r in risk_validation.get("reasons", [])],
        confidence=confidence,
    )

    online_adaptation = engine.online_learning.adapt_model_online(
        drift_report=drift_report,
        online_learning_enabled=engine.online_learning_enabled,
        base_learning_rate=engine.base_learning_rate,
    )
    engine.model_state["last_pred_return_bps"] = float(ret_dist.mean_bps)
    if bool(online_adaptation.get("adapt", False)):
        engine.model_state = engine.online_learning.update_model_incrementally(
            model_state=engine.model_state,
            fused_features=fused,
            realized_return_bps=ret_dist.mean_bps,
            adaptation=online_adaptation,
        )
    if market_twin_snapshot is not None:
        engine.model_state = persist_market_twin_snapshot(
            model_state=engine.model_state,
            snapshot=market_twin_snapshot,
            max_snapshots=engine.market_twin.max_snapshots,
        )

    diagnostics_payload: dict[str, Any] = {
        "signal": signal.reason,
        "entry_action": entry_action,
        "exit_action": exit_action,
        "managed_action": managed_action,
        "feature_cache_hit": 1.0 if feature_cache_hit else 0.0,
        "signal_cache_hit": 1.0 if signal_cache_hit else 0.0,
        "feature_cache_stats": engine.feature_cache.stats().to_dict(),
        "signal_cache_stats": engine.signal_cache.stats().to_dict(),
        "slippage_ok": slippage_ok,
        "signal_decay_score": decay_score,
        "signal_decay_guard_threshold": engine.signal_decay_guard_threshold,
        "execution_quality_guard_threshold": engine.execution_quality_guard_threshold,
        "liquidity_threshold": engine.liquidity_pressure_guard_threshold,
        "adaptive_hold_s": adaptive_hold_s,
        "smart_hold_extend": 1.0 if smart_hold_extend else 0.0,
        "market_class": str(context.market_class),
        "market_session": str(context.market_session),
        "market_class_modifiers": dict(market_mod),
        "portfolio_diversification_scale": portfolio_div_scale,
        "capital_rotation_score": rotation_score,
        "capital_rotation_scale": rotation_scale,
        "regime_size_multiplier": regime_size_multiplier,
        "cross_market_confirmation_score": cross_market_score,
        "cross_market_confirmation_enabled": 1.0 if engine.cross_market_confirmation_enabled else 0.0,
        "cross_market_confirmation_min": engine.cross_market_confirmation_min,
        "cross_market_confirmation_pass": 1.0 if cross_market_pass else 0.0,
        "signal_age_s": signal_age_s,
        "opportunity_decay_score": opportunity_decay_score,
        "opportunity_decay_guard_threshold": engine.opportunity_decay_guard_threshold,
        "forecast_backend": engine.forecast_backend_adapter.backend_name,
        "forecast_backend_mean_adjust_bps": backend_adjustment.mean_adjust_bps,
        "forecast_backend_std_scale": backend_adjustment.std_scale,
        "forecast_backend_confidence_scale": backend_adjustment.confidence_scale,
        "forecast_backend_diagnostics": backend_adjustment.diagnostics,
        "drift_top_features": drift_report.get("top_features", []),
        "self_optimization": self_optimization,
        "market_twin_best_action": market_twin_best_action,
        "market_twin_route_preference": market_twin_route_pref,
        "market_twin_sizing_scale": market_twin_sizing_scale,
        "market_twin_block_reason": market_twin_block_reason,
        "market_twin_error": market_twin_error,
        "adaptive_thresholds": {
            "confidence_threshold": effective_conf_threshold,
            "uncertainty_threshold_bps": effective_uncertainty_threshold_bps,
            "market_class_confidence_floor": class_conf_floor if class_conf_floor is not None else None,
            "market_class_uncertainty_cap_bps": class_uncertainty_cap if class_uncertainty_cap is not None else None,
            "max_slippage_bps": effective_max_slippage_bps,
            "latency_risk_threshold": effective_latency_threshold,
            "liquidity_pressure_guard_threshold": engine.liquidity_pressure_guard_threshold,
        },
        "world_state_source": world_state_source,
        "world_state_available": 1.0 if world_state_available else 0.0,
        "world_state_graph_available": 1.0 if world_state_graph_available else 0.0,
        "world_state_safe_to_trade": 1.0 if world_state_safe_to_trade else 0.0,
        "world_state_freshness_s": world_state_freshness_s,
        "world_state_stale_domains": world_state_stale_domains,
        "world_state_stale_critical_domains": world_state_stale_critical_domains,
    }
    if market_twin_snapshot is not None:
        diagnostics_payload = attach_market_twin_diagnostics(
            diagnostics=diagnostics_payload,
            snapshot=market_twin_snapshot,
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
            "backend": engine.forecast_backend_adapter.backend_name,
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
            "latency_allowed": 1.0 if latency_allowed else 0.0,
            "execution_quality_ratio": execution_monitor_score,
            "liquidity_pressure": liquidity_pressure,
            "total_modeled_cost_bps": cost["total_bps"],
            "max_slippage_bps_effective": effective_max_slippage_bps,
        },
        profit_protection=profit_protection,
        online_adaptation=online_adaptation,
        diagnostics=diagnostics_payload,
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
        enable_sentiment: bool = False,
        signal_decay_guard_threshold: float = 0.6,
        execution_quality_guard_threshold: float = 2.5,
        liquidity_pressure_guard_threshold: float = -0.6,
        adaptive_hold_base_s: float = 1800.0,
        forecast_backend: str = "baseline",
        forecast_backend_plugin: str = "",
        enable_transformer_backend: bool = False,
        enable_foundation_backend: bool = False,
        self_optimization_window: int = 120,
        self_optimization_min_samples: int = 24,
        self_optimization_apply_every: int = 12,
        feature_cache_ttl_s: float = 2.0,
        signal_cache_ttl_s: float = 1.0,
        market_class_confidence_thresholds: Mapping[str, float] | None = None,
        market_class_uncertainty_threshold_bps: Mapping[str, float] | None = None,
        regime_size_multipliers: Mapping[str, float] | None = None,
        opportunity_decay_max_age_s: float = 45.0,
        opportunity_decay_guard_threshold: float = 0.65,
        cross_market_confirmation_enabled: bool = True,
        cross_market_confirmation_min: float = -0.35,
        counterfactual_min_edge_bps: float = 1.0,
        market_twin_include_advanced_scenarios: bool = True,
        market_twin_max_snapshots: int = 256,
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
        self.enable_sentiment = bool(enable_sentiment)
        self.signal_decay_guard_threshold = _clamp(signal_decay_guard_threshold, 0.1, 1.0)
        self.execution_quality_guard_threshold = _clamp(execution_quality_guard_threshold, 0.5, 5.0)
        self.liquidity_pressure_guard_threshold = _clamp(liquidity_pressure_guard_threshold, -1.0, 0.0)
        self.adaptive_hold_base_s = max(30.0, _safe_float(adaptive_hold_base_s, 1800.0))
        self.forecast_backend_name = str(forecast_backend or "baseline").strip().lower()
        self.forecast_backend_plugin = str(forecast_backend_plugin or "").strip()
        self.enable_transformer_backend = bool(enable_transformer_backend)
        self.enable_foundation_backend = bool(enable_foundation_backend)
        self.self_optimization_window = max(20, int(self_optimization_window))
        self.self_optimization_min_samples = max(10, int(self_optimization_min_samples))
        self.self_optimization_apply_every = max(1, int(self_optimization_apply_every))
        self.feature_cache_ttl_s = max(
            0.05,
            _safe_float(
                os.getenv("AUTONOMOUS_FEATURE_CACHE_TTL_S", str(feature_cache_ttl_s) or "2.0"),
                feature_cache_ttl_s,
            ),
        )
        self.signal_cache_ttl_s = max(
            0.05,
            _safe_float(
                os.getenv("AUTONOMOUS_SIGNAL_CACHE_TTL_S", str(signal_cache_ttl_s) or "1.0"),
                signal_cache_ttl_s,
            ),
        )
        self.market_class_confidence_thresholds = {
            _normalize_market_class(str(k)): _clamp(_safe_float(v, 0.0), 0.0, 0.95)
            for k, v in dict(market_class_confidence_thresholds or {}).items()
            if str(k).strip()
        }
        self.market_class_uncertainty_threshold_bps = {
            _normalize_market_class(str(k)): max(20.0, _safe_float(v, 0.0))
            for k, v in dict(market_class_uncertainty_threshold_bps or {}).items()
            if str(k).strip()
        }
        self.regime_size_multipliers = {
            str(k).strip().upper(): _clamp(_safe_float(v, 1.0), 0.25, 1.75)
            for k, v in dict(regime_size_multipliers or {}).items()
            if str(k).strip()
        }
        self.opportunity_decay_max_age_s = max(5.0, _safe_float(opportunity_decay_max_age_s, 45.0))
        self.opportunity_decay_guard_threshold = _clamp(opportunity_decay_guard_threshold, 0.1, 1.0)
        self.cross_market_confirmation_enabled = bool(cross_market_confirmation_enabled)
        self.cross_market_confirmation_min = _clamp(cross_market_confirmation_min, -1.0, 1.0)
        self.counterfactual_min_edge_bps = max(0.0, _safe_float(counterfactual_min_edge_bps, 1.0))
        self.market_twin_include_advanced_scenarios = bool(market_twin_include_advanced_scenarios)
        self.market_twin_max_snapshots = max(32, int(market_twin_max_snapshots))

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
        self.self_optimization = SelfOptimizationEngine(
            window=self.self_optimization_window,
            min_samples=self.self_optimization_min_samples,
            apply_every=self.self_optimization_apply_every,
        )
        self.feature_cache = FeatureCache(ttl_s=self.feature_cache_ttl_s, max_items=4096)
        self.signal_cache = SignalCache(ttl_s=self.signal_cache_ttl_s, max_items=8192)
        self.risk_inference = RiskCalibratedMarketInferenceEngine()

        self.smart_hold = SmartHoldExtension()
        self.dynamic_tp = DynamicTPExpansion()
        self.regime_params = RegimeSpecificTradingParameters()
        self.execution_quality_monitor = ExecutionQualityMonitor()
        self.latency_protection = LatencyArbitrageProtection()
        self.adaptive_sizing = AdaptivePositionSizing()
        self.liquidity_aware_sizing = LiquidityAwareTradeSizing()
        self.profit_compound = ProfitCompoundingAllocator()
        self.portfolio_diversifier = PortfolioDiversificationHook()
        self.capital_rotation = DynamicCapitalRotationEngine()
        self.signal_decay = SignalDecayDetector()
        self.liquidity_heatmap = LiquidityHeatmap()
        self.market_twin = CausalMarketTwinEngine(
            min_counterfactual_edge_bps=self.counterfactual_min_edge_bps,
            include_advanced_scenarios=self.market_twin_include_advanced_scenarios,
            max_snapshots=self.market_twin_max_snapshots,
        )

        self.forecast_backend_registry = ForecastBackendRegistry()
        self.forecast_backend_adapter: ForecastBackendAdapter = self.forecast_backend_registry.resolve(
            backend_name=self.forecast_backend_name,
            enable_transformer_backend=self.enable_transformer_backend,
            enable_foundation_backend=self.enable_foundation_backend,
            plugin_spec=self.forecast_backend_plugin,
        )

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
