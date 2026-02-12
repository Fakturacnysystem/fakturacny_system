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


class ModelsService:
    def __init__(self, model_version: str = "baseline-prob-v1") -> None:
        self.model_version = model_version

    def forecast(self, fv: FeatureVector) -> Forecast:
        edge = 0.6 * fv.values["ret_1"] + 0.4 * fv.values["ret_3"]
        sigma = max(fv.values["realized_vol"], 1e-6)
        raw = abs(edge) / (sigma + 1e-6)
        confidence = 1.0 / (1.0 + exp(-raw))
        return Forecast(symbol=fv.symbol, ts=fv.ts, mu=edge, sigma=sigma, confidence=confidence, model_version=self.model_version)
