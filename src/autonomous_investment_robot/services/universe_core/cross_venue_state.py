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
class CrossVenuePressure:
    divergence_bps: float
    spread_pressure: float
    depth_fragmentation: float
    venue_outage_risk: float
    confidence: float
    as_of_ts: float
    source_age_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "divergence_bps": float(self.divergence_bps),
            "spread_pressure": float(self.spread_pressure),
            "depth_fragmentation": float(self.depth_fragmentation),
            "venue_outage_risk": float(self.venue_outage_risk),
            "confidence": float(self.confidence),
            "as_of_ts": float(self.as_of_ts),
            "source_age_s": float(self.source_age_s),
        }


class CrossVenueStateModel:
    def assess(
        self,
        *,
        world: Any,
        payload: Mapping[str, Any] | None = None,
        as_of_ts: float,
    ) -> CrossVenuePressure:
        row = _safe_mapping(payload)
        venue = getattr(world, "venue_state", None)
        infra = getattr(world, "infra_state", None)
        market = getattr(world, "market_state", None)
        divergence_bps = _safe_float(
            row.get("divergence_bps", getattr(venue, "cross_venue_divergence_bps", 0.0)),
            0.0,
        )
        spread_bps = _safe_float(getattr(market, "spread_bps", 0.0), 0.0)
        spread_pressure = _clamp(_safe_float(row.get("spread_pressure", spread_bps / 80.0), 0.0), 0.0, 1.0)
        depth_fragmentation = _clamp(_safe_float(row.get("depth_fragmentation", abs(divergence_bps) / 120.0), 0.0), 0.0, 1.0)
        outage_seed = 0.25
        if bool(getattr(infra, "stale_feed", False)):
            outage_seed += 0.30
        if bool(getattr(infra, "desync", False)):
            outage_seed += 0.30
        outage_seed += _clamp(abs(divergence_bps) / 220.0, 0.0, 0.25)
        venue_outage_risk = _clamp(_safe_float(row.get("venue_outage_risk", outage_seed), outage_seed), 0.0, 1.0)

        source_ts = _safe_float(row.get("as_of_ts", as_of_ts), as_of_ts)
        source_age_s = max(0.0, float(as_of_ts) - source_ts)
        freshness_penalty = _clamp(source_age_s / 240.0, 0.0, 0.6)
        confidence = _clamp((0.80 if row else 0.55) - freshness_penalty, 0.05, 1.0)

        return CrossVenuePressure(
            divergence_bps=divergence_bps,
            spread_pressure=spread_pressure,
            depth_fragmentation=depth_fragmentation,
            venue_outage_risk=venue_outage_risk,
            confidence=confidence,
            as_of_ts=source_ts,
            source_age_s=source_age_s,
        )
