from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass(frozen=True)
class UniverseAllocationInput:
    universe_id: str
    market_class: str
    edge_score: float
    regime_fit: float
    execution_quality: float
    telemetry_health: float
    capital_capacity: float = 1.0
    enabled: bool = True


@dataclass(frozen=True)
class UniverseAllocation:
    universe_id: str
    market_class: str
    weight: float
    score: float

    def to_dict(self) -> dict[str, object]:
        return {
            "universe_id": self.universe_id,
            "market_class": self.market_class,
            "weight": self.weight,
            "score": self.score,
        }


class CrossAssetAllocator:
    """Allocates attention/capital across universes once the core brain is in place."""

    def allocate(self, inputs: Iterable[UniverseAllocationInput]) -> list[UniverseAllocation]:
        candidates: list[UniverseAllocation] = []
        for item in inputs:
            if not item.enabled:
                continue
            score = max(
                0.0,
                float(item.edge_score)
                * _clamp(item.regime_fit, 0.0, 1.0)
                * _clamp(item.execution_quality, 0.0, 1.0)
                * _clamp(item.telemetry_health, 0.0, 1.0)
                * max(0.0, float(item.capital_capacity)),
            )
            candidates.append(
                UniverseAllocation(
                    universe_id=str(item.universe_id),
                    market_class=str(item.market_class),
                    weight=0.0,
                    score=score,
                )
            )
        total = sum(row.score for row in candidates) or 1.0
        return [
            UniverseAllocation(
                universe_id=row.universe_id,
                market_class=row.market_class,
                weight=row.score / total,
                score=row.score,
            )
            for row in candidates
        ]
