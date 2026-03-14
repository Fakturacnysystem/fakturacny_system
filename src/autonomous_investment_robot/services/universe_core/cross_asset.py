from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


MARKET_CLASS_ALIASES: dict[str, str] = {
    "spot": "crypto_spot",
    "crypto": "crypto_spot",
    "crypto_spot": "crypto_spot",
    "crypto-spot": "crypto_spot",
    "perp": "crypto_perp",
    "perpetual": "crypto_perp",
    "crypto_perp": "crypto_perp",
    "crypto-perp": "crypto_perp",
    "future": "futures",
    "futures": "futures",
    "index_futures": "futures",
    "xstock": "xstock",
    "stock": "xstock",
    "equity": "xstock",
    "xstock_etf": "xstock_etf",
    "etf": "xstock_etf",
    "xstock_perp": "xstock_perp",
    "xstock_etf_perp": "xstock_etf_perp",
    "fx": "fx",
    "forex": "fx",
}

DEFAULT_MARKET_CLASS_WEIGHT_CAPS: dict[str, float] = {
    "crypto_spot": 0.80,
    "crypto_perp": 0.60,
    "futures": 0.60,
    "xstock": 0.45,
    "xstock_etf": 0.40,
    "xstock_perp": 0.45,
    "xstock_etf_perp": 0.40,
    "fx": 0.50,
    "unknown": 0.35,
}

DEFAULT_MARKET_CLASS_SCORE_MULTIPLIERS: dict[str, float] = {
    "crypto_spot": 1.00,
    "crypto_perp": 0.94,
    "futures": 0.96,
    "xstock": 0.90,
    "xstock_etf": 0.88,
    "xstock_perp": 0.86,
    "xstock_etf_perp": 0.84,
    "fx": 0.92,
    "unknown": 0.80,
}


def normalize_market_class(value: str, *, aliases: Mapping[str, str] | None = None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "unknown"
    merged_aliases = dict(MARKET_CLASS_ALIASES)
    if aliases:
        merged_aliases.update({str(k).strip().lower(): str(v).strip().lower() for k, v in aliases.items() if str(k).strip()})
    return merged_aliases.get(raw, raw)


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


@dataclass(frozen=True)
class _ScoredCandidate:
    universe_id: str
    market_class: str
    score: float


class CrossAssetAllocator:
    """Normalize cross-asset opportunity scoring with deterministic market-class caps."""

    def __init__(
        self,
        *,
        market_class_weight_caps: Mapping[str, float] | None = None,
        market_class_score_multipliers: Mapping[str, float] | None = None,
        market_class_aliases: Mapping[str, str] | None = None,
        max_cap_iterations: int = 4,
    ) -> None:
        self.market_class_aliases = {
            str(k).strip().lower(): str(v).strip().lower()
            for k, v in dict(market_class_aliases or {}).items()
            if str(k).strip()
        }
        raw_caps = dict(DEFAULT_MARKET_CLASS_WEIGHT_CAPS)
        if market_class_weight_caps:
            for key, value in market_class_weight_caps.items():
                normalized = normalize_market_class(str(key), aliases=self.market_class_aliases)
                raw_caps[normalized] = _clamp(float(value), 0.0, 1.0)
        self.market_class_weight_caps = raw_caps
        raw_multipliers = dict(DEFAULT_MARKET_CLASS_SCORE_MULTIPLIERS)
        if market_class_score_multipliers:
            for key, value in market_class_score_multipliers.items():
                normalized = normalize_market_class(str(key), aliases=self.market_class_aliases)
                raw_multipliers[normalized] = max(0.0, float(value))
        self.market_class_score_multipliers = raw_multipliers
        self.max_cap_iterations = max(1, int(max_cap_iterations))

    def _class_cap(self, market_class: str) -> float:
        normalized = normalize_market_class(market_class, aliases=self.market_class_aliases)
        return _clamp(float(self.market_class_weight_caps.get(normalized, self.market_class_weight_caps.get("unknown", 0.35))), 0.0, 1.0)

    def _class_multiplier(self, market_class: str) -> float:
        normalized = normalize_market_class(market_class, aliases=self.market_class_aliases)
        return max(0.0, float(self.market_class_score_multipliers.get(normalized, self.market_class_score_multipliers.get("unknown", 0.80))))

    def _score(self, item: UniverseAllocationInput) -> float:
        normalized_class = normalize_market_class(item.market_class, aliases=self.market_class_aliases)
        return max(
            0.0,
            float(item.edge_score)
            * _clamp(item.regime_fit, 0.0, 1.0)
            * _clamp(item.execution_quality, 0.0, 1.0)
            * _clamp(item.telemetry_health, 0.0, 1.0)
            * max(0.0, float(item.capital_capacity))
            * self._class_multiplier(normalized_class),
        )

    def _redistribute_within_class(
        self,
        *,
        weights: dict[str, float],
        class_members: dict[str, list[str]],
        class_topup: dict[str, float],
    ) -> None:
        for market_class in sorted(class_topup.keys()):
            topup = max(0.0, float(class_topup.get(market_class, 0.0)))
            if topup <= 1e-12:
                continue
            members = class_members.get(market_class, [])
            if not members:
                continue
            current_total = sum(max(0.0, float(weights.get(row, 0.0))) for row in members)
            if current_total <= 1e-12:
                share = topup / float(len(members))
                for universe_id in members:
                    weights[universe_id] = float(weights.get(universe_id, 0.0)) + share
                continue
            for universe_id in members:
                base_weight = max(0.0, float(weights.get(universe_id, 0.0)))
                weights[universe_id] = base_weight + (topup * (base_weight / current_total))

    def _apply_class_caps(self, candidates: list[_ScoredCandidate], base_weights: dict[str, float]) -> dict[str, float]:
        if not candidates:
            return {}
        classes = {row.market_class for row in candidates}
        if len(classes) <= 1:
            return dict(base_weights)

        class_members: dict[str, list[str]] = {}
        for row in candidates:
            class_members.setdefault(row.market_class, []).append(row.universe_id)
        for market_class in class_members:
            class_members[market_class] = sorted(class_members[market_class])

        weights = dict(base_weights)
        for _ in range(self.max_cap_iterations):
            class_totals = {
                market_class: sum(max(0.0, float(weights.get(universe_id, 0.0))) for universe_id in members)
                for market_class, members in class_members.items()
            }
            leftover = 0.0
            for market_class, total in class_totals.items():
                cap = self._class_cap(market_class)
                if total <= cap + 1e-12:
                    continue
                scale = cap / max(total, 1e-12)
                for universe_id in class_members[market_class]:
                    current = max(0.0, float(weights.get(universe_id, 0.0)))
                    capped = current * scale
                    leftover += max(0.0, current - capped)
                    weights[universe_id] = capped
            if leftover <= 1e-12:
                break

            class_totals = {
                market_class: sum(max(0.0, float(weights.get(universe_id, 0.0))) for universe_id in members)
                for market_class, members in class_members.items()
            }
            class_headroom = {
                market_class: max(0.0, self._class_cap(market_class) - total)
                for market_class, total in class_totals.items()
            }
            total_headroom = sum(class_headroom.values())
            if total_headroom <= 1e-12:
                break
            class_topup = {
                market_class: leftover * (headroom / total_headroom)
                for market_class, headroom in class_headroom.items()
                if headroom > 1e-12
            }
            self._redistribute_within_class(weights=weights, class_members=class_members, class_topup=class_topup)
        return weights

    def allocate(self, inputs: Iterable[UniverseAllocationInput]) -> list[UniverseAllocation]:
        candidates: list[_ScoredCandidate] = []
        for item in inputs:
            if not item.enabled:
                continue
            normalized_class = normalize_market_class(item.market_class, aliases=self.market_class_aliases)
            score = self._score(item)
            candidates.append(
                _ScoredCandidate(
                    universe_id=str(item.universe_id),
                    market_class=normalized_class,
                    score=score,
                )
            )

        if not candidates:
            return []
        candidates.sort(key=lambda row: (-float(row.score), row.universe_id, row.market_class))
        total_score = sum(row.score for row in candidates)
        if total_score <= 1e-12:
            equal = 1.0 / float(len(candidates))
            return [
                UniverseAllocation(
                    universe_id=row.universe_id,
                    market_class=row.market_class,
                    weight=equal,
                    score=float(row.score),
                )
                for row in candidates
            ]

        base_weights = {row.universe_id: float(row.score) / float(total_score) for row in candidates}
        capped_weights = self._apply_class_caps(candidates, base_weights)
        weight_sum = sum(max(0.0, float(capped_weights.get(row.universe_id, 0.0))) for row in candidates)
        if weight_sum <= 1e-12:
            equal = 1.0 / float(len(candidates))
            return [
                UniverseAllocation(
                    universe_id=row.universe_id,
                    market_class=row.market_class,
                    weight=equal,
                    score=float(row.score),
                )
                for row in candidates
            ]

        return [
            UniverseAllocation(
                universe_id=row.universe_id,
                market_class=row.market_class,
                weight=max(0.0, float(capped_weights.get(row.universe_id, 0.0))) / float(weight_sum),
                score=float(row.score),
            )
            for row in candidates
        ]

