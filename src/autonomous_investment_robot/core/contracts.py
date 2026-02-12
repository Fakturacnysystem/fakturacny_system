from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DataEvent:
    venue: str
    symbol: str
    ts: datetime
    payload: dict[str, Any]
    stale: bool = False


@dataclass
class FeatureVector:
    feature_version: str
    symbol: str
    ts: datetime
    values: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ForecastDistribution:
    model_version: str
    symbol: str
    ts: datetime
    horizon: str
    mu: float
    sigma: float
    entropy: float
    quantiles: dict[float, float]


@dataclass
class RegimeProbabilities:
    ts: datetime
    probabilities: dict[str, float]
    selected: str


@dataclass
class OrderIntent:
    symbol: str
    side: str
    qty: float
    reason: str
    max_slippage_bps: float


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    throttle: float = 1.0
    kill_action: str | None = None
