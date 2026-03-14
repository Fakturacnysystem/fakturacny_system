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
class SentimentPressure:
    sentiment_score: float
    panic_index: float
    crowding_index: float
    confidence: float
    as_of_ts: float
    source_age_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentiment_score": float(self.sentiment_score),
            "panic_index": float(self.panic_index),
            "crowding_index": float(self.crowding_index),
            "confidence": float(self.confidence),
            "as_of_ts": float(self.as_of_ts),
            "source_age_s": float(self.source_age_s),
        }


class SentimentStateModel:
    def assess(
        self,
        *,
        world: Any,
        payload: Mapping[str, Any] | None = None,
        as_of_ts: float,
    ) -> SentimentPressure:
        row = _safe_mapping(payload)
        market = getattr(world, "market_state", None)
        regime = str(getattr(market, "regime", "RANGE") or "RANGE")
        realized_vol = _safe_float(getattr(market, "realized_vol", 0.0), 0.0)
        trend_bias = abs(_safe_float(getattr(market, "trend_bias_bps", 0.0), 0.0))
        baseline_sentiment = 0.45 if regime == "RANGE" else 0.65 if regime == "TREND" else 0.20
        sentiment_score = _clamp(_safe_float(row.get("sentiment_score", baseline_sentiment), baseline_sentiment), 0.0, 1.0)
        panic_seed = _clamp(max(realized_vol / 0.05, 0.0), 0.0, 1.0)
        if regime == "PANIC":
            panic_seed = max(panic_seed, 0.80)
        panic_index = _clamp(_safe_float(row.get("panic_index", panic_seed), panic_seed), 0.0, 1.0)
        crowding_seed = _clamp(trend_bias / 240.0, 0.0, 1.0)
        crowding_index = _clamp(_safe_float(row.get("crowding_index", crowding_seed), crowding_seed), 0.0, 1.0)
        source_ts = _safe_float(row.get("as_of_ts", as_of_ts), as_of_ts)
        source_age_s = max(0.0, float(as_of_ts) - source_ts)
        freshness_penalty = _clamp(source_age_s / 240.0, 0.0, 0.65)
        confidence = _clamp((0.75 if row else 0.50) - freshness_penalty, 0.05, 1.0)
        return SentimentPressure(
            sentiment_score=sentiment_score,
            panic_index=panic_index,
            crowding_index=crowding_index,
            confidence=confidence,
            as_of_ts=source_ts,
            source_age_s=source_age_s,
        )
