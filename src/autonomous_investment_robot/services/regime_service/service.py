from __future__ import annotations

from autonomous_investment_robot.config.settings import RegimeSettings
from autonomous_investment_robot.core.contracts import RegimeAssessment
from autonomous_investment_robot.services.models.service import Forecast
from autonomous_investment_robot.services.policy.regime import detect_regime_state


class RegimeService:
    def __init__(self, settings: RegimeSettings | None = None) -> None:
        self.settings = settings or RegimeSettings()

    def assess(self, symbol: str, ts: object, features: dict[str, float], forecast: Forecast | None = None) -> RegimeAssessment:
        regime = detect_regime_state(features, self.settings)
        ret_3 = float(features.get("ret_3", 0.0))
        vol = float(features.get("realized_vol", 0.0))
        spread = float(features.get("spread_proxy", 0.0))
        liquidations = float(features.get("liquidations", 0.0))
        flow = float(features.get("flow_imbalance", 0.0))

        label = "mean_reversion"
        degradation = None
        if regime.market == "PANIC" and regime.liquidity == "THIN":
            label = "liquidity_vacuum"
            degradation = "panic_liquidity_break"
        elif regime.market == "PANIC":
            label = "high_vol_expansion"
            degradation = "panic_mode"
        elif abs(ret_3) >= self.settings.trend_ret3_abs and vol >= self.settings.panic_vol * 0.5:
            label = "trend"
        elif abs(ret_3) >= self.settings.trend_ret3_abs and flow * ret_3 < 0:
            label = "fake_breakout"
            degradation = "trend_flow_divergence"
        elif vol <= self.settings.panic_vol * 0.25 and abs(ret_3) <= self.settings.trend_ret3_abs * 0.3:
            label = "dead_market"
        elif spread >= self.settings.thin_spread * 0.75:
            label = "low_vol_chop"
        if liquidations > self.settings.panic_liquidations * 0.75:
            label = "news_chaos"
            degradation = "liquidation_cluster"

        persistence = min(0.99, max(0.1, (abs(ret_3) / max(self.settings.trend_ret3_abs, 1e-9)) * 0.4 + regime.confidence * 0.6))
        transition_probability = min(0.95, max(0.05, vol / max(self.settings.panic_vol, 1e-9) * 0.5 + spread / max(self.settings.thin_spread, 1e-9) * 0.2))
        if forecast is not None and forecast.regime == "TREND" and label == "mean_reversion":
            degradation = "forecast_regime_disagreement"

        return RegimeAssessment(
            symbol=symbol,
            ts=ts,  # type: ignore[arg-type]
            label=label,
            confidence=max(0.0, min(1.0, regime.confidence)),
            persistence=persistence,
            transition_probability=transition_probability,
            degradation_warning=degradation,
            evidence={
                "ret_3": ret_3,
                "realized_vol": vol,
                "spread_proxy": spread,
                "liquidations": liquidations,
                "flow_imbalance": flow,
            },
        )
