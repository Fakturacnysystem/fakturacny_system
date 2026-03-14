from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .cross_venue_state import CrossVenuePressure, CrossVenueStateModel
from .macro_liquidity_state import MacroLiquiditySnapshot, MacroLiquidityStateModel
from .market_context_fusion import MarketContextConfidence, MarketContextFreshness, MarketContextFusion
from .sentiment_state import SentimentPressure, SentimentStateModel


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass(frozen=True)
class GlobalMarketState:
    regime: str
    market_stress: float
    risk_on_score: float
    macro_liquidity: MacroLiquiditySnapshot
    cross_venue: CrossVenuePressure
    sentiment: SentimentPressure
    confidence: MarketContextConfidence
    freshness: MarketContextFreshness
    partial_data: bool
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "market_stress": float(self.market_stress),
            "risk_on_score": float(self.risk_on_score),
            "macro_liquidity": self.macro_liquidity.to_dict(),
            "cross_venue": self.cross_venue.to_dict(),
            "sentiment": self.sentiment.to_dict(),
            "confidence": self.confidence.to_dict(),
            "freshness": self.freshness.to_dict(),
            "partial_data": bool(self.partial_data),
            "diagnostics": dict(self.diagnostics),
        }


class GlobalMarketBrain:
    """Phase 26 global market intelligence layer (read-only, deterministic)."""

    def __init__(
        self,
        *,
        macro_model: MacroLiquidityStateModel | None = None,
        cross_venue_model: CrossVenueStateModel | None = None,
        sentiment_model: SentimentStateModel | None = None,
        fusion: MarketContextFusion | None = None,
    ) -> None:
        self.macro_model = macro_model or MacroLiquidityStateModel()
        self.cross_venue_model = cross_venue_model or CrossVenueStateModel()
        self.sentiment_model = sentiment_model or SentimentStateModel()
        self.fusion = fusion or MarketContextFusion()

    def assess(
        self,
        *,
        world: Any,
        payload: Mapping[str, Any] | None = None,
    ) -> GlobalMarketState:
        raw = _safe_mapping(payload)
        as_of_ts = _safe_float(raw.get("as_of_ts", getattr(world, "as_of_time", 0.0)), _safe_float(getattr(world, "as_of_time", 0.0), 0.0))
        macro = self.macro_model.assess(
            world=world,
            payload=_safe_mapping(raw.get("macro_liquidity", {})),
            as_of_ts=as_of_ts,
        )
        cross_venue = self.cross_venue_model.assess(
            world=world,
            payload=_safe_mapping(raw.get("cross_venue", {})),
            as_of_ts=as_of_ts,
        )
        sentiment = self.sentiment_model.assess(
            world=world,
            payload=_safe_mapping(raw.get("sentiment", {})),
            as_of_ts=as_of_ts,
        )
        confidence = self.fusion.fuse_confidence(macro=macro, cross_venue=cross_venue, sentiment=sentiment)
        freshness = self.fusion.fuse_freshness(
            as_of_ts=as_of_ts,
            macro=macro,
            cross_venue=cross_venue,
            sentiment=sentiment,
        )
        regime = str(getattr(getattr(world, "market_state", None), "regime", "RANGE") or "RANGE")
        stress_seed = (
            max(0.0, 1.0 - macro.liquidity_score) * 0.35
            + cross_venue.venue_outage_risk * 0.30
            + sentiment.panic_index * 0.20
            + _clamp(abs(cross_venue.divergence_bps) / 180.0, 0.0, 1.0) * 0.15
        )
        market_stress = _clamp(stress_seed, 0.0, 1.0)
        risk_on_seed = (
            macro.liquidity_score * 0.40
            + (1.0 - sentiment.panic_index) * 0.25
            + sentiment.sentiment_score * 0.20
            + (1.0 - cross_venue.spread_pressure) * 0.15
        )
        risk_on_score = _clamp(risk_on_seed, 0.0, 1.0)
        partial_data = bool(
            confidence.overall < 0.45
            or freshness.max_age_s > 300.0
            or bool(freshness.stale_components)
        )
        diagnostics = {
            "phase": 26,
            "confidence_reason_codes": list(confidence.reason_codes),
            "stale_components": list(freshness.stale_components),
            "market_stress_band": "high" if market_stress >= 0.70 else "medium" if market_stress >= 0.40 else "low",
            "risk_on_band": "risk_on" if risk_on_score >= 0.65 else "neutral" if risk_on_score >= 0.35 else "risk_off",
        }
        return GlobalMarketState(
            regime=regime,
            market_stress=market_stress,
            risk_on_score=risk_on_score,
            macro_liquidity=macro,
            cross_venue=cross_venue,
            sentiment=sentiment,
            confidence=confidence,
            freshness=freshness,
            partial_data=partial_data,
            diagnostics=diagnostics,
        )
