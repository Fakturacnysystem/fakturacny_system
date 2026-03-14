from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class MacroLiquiditySnapshot:
    liquidity_regime: str
    liquidity_score: float
    funding_pressure: float
    rates_pressure: float
    inflation_pressure: float
    policy_tightness: float
    confidence: float
    as_of_ts: float
    source_age_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "liquidity_regime": self.liquidity_regime,
            "liquidity_score": float(self.liquidity_score),
            "funding_pressure": float(self.funding_pressure),
            "rates_pressure": float(self.rates_pressure),
            "inflation_pressure": float(self.inflation_pressure),
            "policy_tightness": float(self.policy_tightness),
            "confidence": float(self.confidence),
            "as_of_ts": float(self.as_of_ts),
            "source_age_s": float(self.source_age_s),
        }


class MacroLiquidityStateModel:
    """Deterministic macro/liquidity inference with conservative partial-data fallback."""

    def assess(
        self,
        *,
        world: Any,
        payload: Mapping[str, Any] | None = None,
        as_of_ts: float,
    ) -> MacroLiquiditySnapshot:
        row = _safe_mapping(payload)
        market = getattr(world, "market_state", None)
        venue = getattr(world, "venue_state", None)
        depth_notional = _safe_float(getattr(market, "depth_notional", 0.0), 0.0)
        spread_bps = _safe_float(getattr(market, "spread_bps", 0.0), 0.0)
        funding_stress_world = _safe_float(getattr(venue, "funding_stress", 0.0), 0.0)
        funding_pressure = _clamp(_safe_float(row.get("funding_pressure", funding_stress_world), funding_stress_world), 0.0, 1.0)
        rates_pressure = _clamp(_safe_float(row.get("rates_pressure", 0.45), 0.45), 0.0, 1.0)
        inflation_pressure = _clamp(_safe_float(row.get("inflation_pressure", 0.40), 0.40), 0.0, 1.0)
        policy_tightness = _clamp(_safe_float(row.get("policy_tightness", max(rates_pressure, inflation_pressure)), 0.5), 0.0, 1.0)

        liquidity_from_depth = _clamp(depth_notional / 25_000.0, 0.0, 1.0)
        spread_penalty = _clamp(spread_bps / 120.0, 0.0, 1.0)
        external_score = _safe_float(row.get("liquidity_score", liquidity_from_depth * (1.0 - 0.40 * spread_penalty)), liquidity_from_depth)
        liquidity_score = _clamp(external_score, 0.0, 1.0)
        liquidity_regime = "tight" if liquidity_score < 0.35 else "neutral" if liquidity_score < 0.65 else "loose"

        source_ts = _safe_float(row.get("as_of_ts", as_of_ts), as_of_ts)
        source_age_s = max(0.0, float(as_of_ts) - source_ts)
        freshness_penalty = _clamp(source_age_s / 300.0, 0.0, 0.6)
        payload_confidence = 0.80 if row else 0.45
        confidence = _clamp(payload_confidence - freshness_penalty, 0.05, 1.0)

        return MacroLiquiditySnapshot(
            liquidity_regime=liquidity_regime,
            liquidity_score=liquidity_score,
            funding_pressure=funding_pressure,
            rates_pressure=rates_pressure,
            inflation_pressure=inflation_pressure,
            policy_tightness=policy_tightness,
            confidence=confidence,
            as_of_ts=source_ts,
            source_age_s=source_age_s,
        )
