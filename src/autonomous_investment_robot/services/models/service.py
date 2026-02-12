from __future__ import annotations

from dataclasses import dataclass
from math import exp

from autonomous_investment_robot.services.feature_store.service import FeatureVector


@dataclass
class Forecast:
    symbol: str
    ts: object
    mu: float
    sigma: float
    confidence: float
    model_version: str
    regime: str
    liquidity_regime: str


class ModelsService:
    def __init__(self, model_version: str = "baseline-prob-v2") -> None:
        self.model_version = model_version

    def detect_regime(self, fv: FeatureVector) -> tuple[str, str]:
        vol = fv.values["realized_vol"]
        trend = abs(fv.values["ret_3"])
        spread = fv.values["spread_proxy"]
        if vol > 0.015:
            regime = "PANIC"
        elif trend > 0.005:
            regime = "TREND"
        else:
            regime = "RANGE"
        liq = "THIN" if spread > 0.01 else "GOOD"
        return regime, liq

    def forecast(self, fv: FeatureVector) -> Forecast:
        edge = 0.6 * fv.values["ret_1"] + 0.4 * fv.values["ret_3"]
        sigma = max(fv.values["realized_vol"], 1e-6)
        raw = abs(edge) / (sigma + 1e-6)
        confidence = 1.0 / (1.0 + exp(-raw))
        regime, liq = self.detect_regime(fv)
        return Forecast(
            symbol=fv.symbol,
            ts=fv.ts,
            mu=edge,
            sigma=sigma,
            confidence=confidence,
            model_version=self.model_version,
            regime=regime,
            liquidity_regime=liq,
        )
