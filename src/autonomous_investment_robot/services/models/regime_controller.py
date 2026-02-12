from __future__ import annotations


def detect_regime(features: dict[str, float]) -> tuple[str, str, float]:
    vol = features.get("realized_vol", 0.0)
    trend = abs(features.get("ret_3", 0.0))
    spread = features.get("spread_proxy", 0.0)
    if vol > 0.015:
        regime = "PANIC"
        conf = 0.8
    elif trend > 0.004:
        regime = "TREND"
        conf = 0.7
    else:
        regime = "RANGE"
        conf = 0.65
    liquidity = "THIN" if spread > 0.01 else "GOOD"
    return regime, liquidity, conf
