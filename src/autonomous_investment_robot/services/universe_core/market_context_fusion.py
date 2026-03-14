from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cross_venue_state import CrossVenuePressure
from .macro_liquidity_state import MacroLiquiditySnapshot
from .sentiment_state import SentimentPressure


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass(frozen=True)
class MarketContextConfidence:
    overall: float
    components: dict[str, float] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": float(self.overall),
            "components": {str(k): float(v) for k, v in dict(self.components).items()},
            "reason_codes": [str(code) for code in self.reason_codes],
        }


@dataclass(frozen=True)
class MarketContextFreshness:
    as_of_ts: float
    component_age_s: dict[str, float] = field(default_factory=dict)
    stale_components: tuple[str, ...] = field(default_factory=tuple)
    max_age_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_ts": float(self.as_of_ts),
            "component_age_s": {str(k): float(v) for k, v in dict(self.component_age_s).items()},
            "stale_components": [str(item) for item in self.stale_components],
            "max_age_s": float(self.max_age_s),
        }


class MarketContextFusion:
    """Fuses phase-26 component states into deterministic confidence/freshness diagnostics."""

    def fuse_confidence(
        self,
        *,
        macro: MacroLiquiditySnapshot,
        cross_venue: CrossVenuePressure,
        sentiment: SentimentPressure,
    ) -> MarketContextConfidence:
        components = {
            "macro_liquidity": float(macro.confidence),
            "cross_venue": float(cross_venue.confidence),
            "sentiment": float(sentiment.confidence),
        }
        weighted = (
            components["macro_liquidity"] * 0.40
            + components["cross_venue"] * 0.35
            + components["sentiment"] * 0.25
        )
        reason_codes: list[str] = []
        for name, value in components.items():
            if value < 0.35:
                reason_codes.append(f"low_confidence:{name}")
        return MarketContextConfidence(
            overall=_clamp(weighted, 0.0, 1.0),
            components=components,
            reason_codes=tuple(reason_codes),
        )

    def fuse_freshness(
        self,
        *,
        as_of_ts: float,
        macro: MacroLiquiditySnapshot,
        cross_venue: CrossVenuePressure,
        sentiment: SentimentPressure,
    ) -> MarketContextFreshness:
        age = {
            "macro_liquidity": max(0.0, float(macro.source_age_s)),
            "cross_venue": max(0.0, float(cross_venue.source_age_s)),
            "sentiment": max(0.0, float(sentiment.source_age_s)),
        }
        max_age_s = max(age.values()) if age else 0.0
        stale = tuple(sorted(name for name, value in age.items() if value > 300.0))
        return MarketContextFreshness(
            as_of_ts=float(as_of_ts),
            component_age_s=age,
            stale_components=stale,
            max_age_s=float(max_age_s),
        )
