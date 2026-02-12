from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RegimeState:
    market: str
    liquidity: str
    confidence: float


def detect_regime_state(features: dict[str, float]) -> RegimeState:
    vol = features.get("realized_vol", 0.0)
    trend = abs(features.get("ret_3", 0.0))
    spread = features.get("spread_proxy", 0.0)
    funding = abs(features.get("funding_rate", 0.0))
    liq = features.get("liquidations", 0.0)

    if vol > 0.015 or liq > 100000 or funding > 0.0005:
        market, conf = "PANIC", 0.8
    elif trend > 0.004:
        market, conf = "TREND", 0.7
    else:
        market, conf = "RANGE", 0.65

    liquidity = "THIN" if spread > 0.01 else "GOOD"
    return RegimeState(market=market, liquidity=liquidity, confidence=conf)
