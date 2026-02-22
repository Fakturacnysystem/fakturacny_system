from __future__ import annotations

from dataclasses import dataclass

from autonomous_investment_robot.config.settings import RegimeSettings


@dataclass
class RegimeState:
    market: str
    liquidity: str
    confidence: float


def detect_regime_state(features: dict[str, float], settings: RegimeSettings | None = None) -> RegimeState:
    cfg = settings or RegimeSettings()
    vol = features.get("realized_vol", 0.0)
    trend = abs(features.get("ret_3", 0.0))
    spread = features.get("spread_proxy", 0.0)
    funding = abs(features.get("funding_rate", 0.0))
    liq = features.get("liquidations", 0.0)

    if vol > cfg.panic_vol or liq > cfg.panic_liquidations or funding > cfg.panic_funding_abs:
        market, conf = "PANIC", 0.8
    elif trend > cfg.trend_ret3_abs:
        market, conf = "TREND", 0.7
    else:
        market, conf = "RANGE", 0.65

    liquidity = "THIN" if spread > cfg.thin_spread else "GOOD"
    return RegimeState(market=market, liquidity=liquidity, confidence=conf)
