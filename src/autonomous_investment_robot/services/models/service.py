from __future__ import annotations

from dataclasses import dataclass, field
from math import exp
import os

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
    diagnostics: dict[str, float] = field(default_factory=dict)


class ModelsService:
    def __init__(self, model_version: str = "baseline-prob-v3", regime_settings: RegimeSettings | None = None) -> None:
        self.model_version = model_version
        self.regime_settings = regime_settings or RegimeSettings()

    def forecast(self, fv: FeatureVector) -> Forecast:
        use_v2 = os.getenv("AUTONOMOUS_MODEL_STACK_V2", "false").strip().lower() in {"1", "true", "yes", "on"}
        if not use_v2:
            edge = 0.55 * fv.values["ret_1"] + 0.30 * fv.values["ret_3"] + 0.15 * fv.values["flow_imbalance"]
            sigma = max(fv.values["realized_vol"], 1e-6)
            raw = abs(edge) / (sigma + 1e-6)
            confidence = 1.0 / (1.0 + exp(-raw))
            regime, liq, reg_conf = detect_regime(fv.values, settings=self.regime_settings)
            confidence = 0.5 * confidence + 0.5 * reg_conf
            return Forecast(
                fv.symbol,
                fv.ts,
                edge,
                sigma,
                confidence,
                self.model_version,
                regime,
                liq,
                diagnostics={
                    "trend_component": fv.values.get("ret_3", 0.0),
                    "mean_rev_component": 0.0,
                    "flow_component": fv.values.get("flow_imbalance", 0.0),
                    "ensemble_dispersion": 0.0,
                    "uncertainty_penalty": 0.0,
                    "base_confidence": confidence,
                },
            )
        regime, liq, reg_conf = detect_regime(fv.values, settings=self.regime_settings)
        trend_component = 0.65 * float(fv.values.get("ret_3", 0.0)) + 0.35 * float(fv.values.get("ret_1", 0.0))
        mean_rev_component = -0.45 * float(fv.values.get("pairs_zscore", 0.0)) * max(float(fv.values.get("realized_vol", 0.0)), 1e-4)
        flow_component = 0.8 * float(fv.values.get("flow_imbalance", 0.0)) + 0.2 * float(fv.values.get("orderbook_imbalance", 0.0))

        if regime == "TREND":
            w_trend, w_mean, w_flow = 0.55, 0.15, 0.30
        elif regime == "PANIC":
            w_trend, w_mean, w_flow = 0.25, 0.35, 0.40
        else:
            w_trend, w_mean, w_flow = 0.30, 0.45, 0.25

        edge = (w_trend * trend_component) + (w_mean * mean_rev_component) + (w_flow * flow_component)
        sigma = max(float(fv.values.get("realized_vol", 0.0)), 1e-6)
        components = [trend_component, mean_rev_component, flow_component]
        ensemble_dispersion = max(0.0, max(components) - min(components))
        # Uncertainty calibration: penalize confidence when ensemble members disagree.
        uncertainty_penalty = min(0.45, ensemble_dispersion / max(sigma * 10.0, 1e-6))
        raw = abs(edge) / (sigma + 1e-6)
        base_confidence = 1.0 / (1.0 + exp(-raw))
        confidence = max(0.0, min(1.0, (0.55 * base_confidence + 0.45 * reg_conf) - uncertainty_penalty))
        return Forecast(
            fv.symbol,
            fv.ts,
            edge,
            sigma,
            confidence,
            self.model_version,
            regime,
            liq,
            diagnostics={
                "trend_component": trend_component,
                "mean_rev_component": mean_rev_component,
                "flow_component": flow_component,
                "ensemble_dispersion": ensemble_dispersion,
                "uncertainty_penalty": uncertainty_penalty,
                "base_confidence": base_confidence,
            },
        )
