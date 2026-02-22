from __future__ import annotations

from dataclasses import dataclass
from math import exp

from autonomous_investment_robot.config.settings import RegimeSettings
from autonomous_investment_robot.services.feature_store.service import FeatureVector
from autonomous_investment_robot.services.models.regime_controller import detect_regime


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
    def __init__(self, model_version: str = "baseline-prob-v3", regime_settings: RegimeSettings | None = None) -> None:
        self.model_version = model_version
        self.regime_settings = regime_settings or RegimeSettings()

    def forecast(self, fv: FeatureVector) -> Forecast:
        edge = 0.55 * fv.values["ret_1"] + 0.30 * fv.values["ret_3"] + 0.15 * fv.values["flow_imbalance"]
        sigma = max(fv.values["realized_vol"], 1e-6)
        raw = abs(edge) / (sigma + 1e-6)
        confidence = 1.0 / (1.0 + exp(-raw))
        regime, liq, reg_conf = detect_regime(fv.values, settings=self.regime_settings)
        confidence = 0.5 * confidence + 0.5 * reg_conf
        return Forecast(fv.symbol, fv.ts, edge, sigma, confidence, self.model_version, regime, liq)
