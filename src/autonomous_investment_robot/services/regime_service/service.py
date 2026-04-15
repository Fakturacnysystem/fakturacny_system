from __future__ import annotations

from autonomous_investment_robot.config.settings import RegimeSettings
from autonomous_investment_robot.core.contracts import RegimeAssessment
from autonomous_investment_robot.services.models.service import Forecast
from autonomous_investment_robot.services.policy.regime import detect_regime_state


class RegimeService:
    def __init__(self, settings: RegimeSettings | None = None) -> None:
        self.settings = settings or RegimeSettings()
        self._memory: dict[str, dict[str, float | str]] = {}

    def _healthy_microstructure(self, *, spread: float, depth_notional: float, liveliness: float, age_seconds: float, repeat_count: int, public_market_data_connected: bool) -> bool:
        tight_spread = spread <= max(self.settings.thin_spread * 0.15, 0.0004)
        deep_book = depth_notional >= 75000.0
        lively_book = liveliness >= 0.55 and age_seconds <= 8.0 and repeat_count <= 2
        return bool(public_market_data_connected and tight_spread and deep_book and lively_book)

    def assess(self, symbol: str, ts: object, features: dict[str, float], forecast: Forecast | None = None) -> RegimeAssessment:
        regime = detect_regime_state(features, self.settings)
        ret_3 = float(features.get("ret_3", 0.0))
        vol = float(features.get("realized_vol", 0.0))
        spread = float(features.get("spread_proxy", 0.0))
        liquidations = float(features.get("liquidations", 0.0))
        flow = float(features.get("flow_imbalance", 0.0))
        depth_notional = float(features.get("depth_notional", 0.0) or 0.0)
        history_points = max(0, int(features.get("history_points", 4.0) or 0.0))
        history_ready_for_dead_market = history_points >= 4
        book_repeat_count = max(0, int(features.get("book_repeat_count", 0.0) or 0.0))
        seconds_since_distinct_book_change = max(0.0, float(features.get("seconds_since_distinct_book_change", 0.0) or 0.0))
        book_liveliness_score = max(0.0, min(1.0, float(features.get("book_liveliness_score", 0.0) or 0.0)))
        public_market_data_connected = bool(float(features.get("public_market_data_connected", 0.0) or 0.0) > 0.0)
        dead_market_candidate = history_ready_for_dead_market and vol <= self.settings.panic_vol * 0.25 and abs(ret_3) <= self.settings.trend_ret3_abs * 0.3
        healthy_microstructure = self._healthy_microstructure(
            spread=spread,
            depth_notional=depth_notional,
            liveliness=book_liveliness_score,
            age_seconds=seconds_since_distinct_book_change,
            repeat_count=book_repeat_count,
            public_market_data_connected=public_market_data_connected,
        )

        label = "mean_reversion"
        degradation = None
        dead_market_reason = ""
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
        elif dead_market_candidate:
            if not public_market_data_connected:
                label = "dead_market"
                dead_market_reason = "public_market_data_unavailable_under_low_energy"
            elif healthy_microstructure:
                label = "mean_reversion"
                dead_market_reason = "healthy_microstructure_overrides_low_energy"
                degradation = "low_energy_but_book_alive"
            elif book_liveliness_score < 0.35 or seconds_since_distinct_book_change >= 15.0 or book_repeat_count >= 4:
                label = "dead_market"
                dead_market_reason = "book_activity_absent_under_low_energy"
            else:
                label = "low_vol_chop"
                dead_market_reason = "low_energy_without_inactivity_confirmation"
        elif not history_ready_for_dead_market:
            degradation = "insufficient_history_for_dead_market_label"
        elif spread >= self.settings.thin_spread * 0.75:
            label = "low_vol_chop"
        if liquidations > self.settings.panic_liquidations * 0.75:
            label = "news_chaos"
            degradation = "liquidation_cluster"

        persistence = min(0.99, max(0.1, (abs(ret_3) / max(self.settings.trend_ret3_abs, 1e-9)) * 0.4 + regime.confidence * 0.6))
        transition_probability = min(0.95, max(0.05, vol / max(self.settings.panic_vol, 1e-9) * 0.5 + spread / max(self.settings.thin_spread, 1e-9) * 0.2))
        if forecast is not None and forecast.regime == "TREND" and label == "mean_reversion":
            degradation = "forecast_regime_disagreement"
        previous = dict(self._memory.get(symbol, {}))
        previous_label = str(previous.get("label", "") or "")
        previous_confidence = float(previous.get("confidence", 0.0) or 0.0)
        hysteresis_applied = False
        if previous_label and previous_label != label and regime.confidence < 0.65 and transition_probability < 0.60:
            label = previous_label
            persistence = min(0.99, max(persistence, previous_confidence * 0.9))
            degradation = degradation or "regime_hysteresis_hold"
            hysteresis_applied = True
        regime_uncertainty = max(0.0, min(1.0, 1.0 - regime.confidence + transition_probability * 0.25))
        exit_family = "alpha_capture_exit"
        if label in {"trend", "high_vol_expansion"}:
            exit_family = "trailing_profit_exit"
        elif label in {"news_chaos", "liquidity_vacuum"}:
            exit_family = "regime_invalidation_exit"
        elif label in {"dead_market", "low_vol_chop"}:
            exit_family = "time_stop_exit"
        self._memory[symbol] = {
            "label": label,
            "confidence": max(0.0, min(1.0, regime.confidence)),
            "transition_probability": transition_probability,
        }

        return RegimeAssessment(
            symbol=symbol,
            ts=ts,  # type: ignore[arg-type]
            label=label,
            confidence=max(0.0, min(1.0, regime.confidence)),
            persistence=persistence,
            transition_probability=transition_probability,
            degradation_warning=degradation,
            evidence={
                "history_points": history_points,
                "ret_3": ret_3,
                "realized_vol": vol,
                "spread_proxy": spread,
                "liquidations": liquidations,
                "flow_imbalance": flow,
                "depth_notional": depth_notional,
                "book_repeat_count": float(book_repeat_count),
                "seconds_since_distinct_book_change": seconds_since_distinct_book_change,
                "book_liveliness_score": book_liveliness_score,
                "public_market_data_connected": 1.0 if public_market_data_connected else 0.0,
                "dead_market_candidate": 1.0 if dead_market_candidate else 0.0,
                "healthy_microstructure": 1.0 if healthy_microstructure else 0.0,
                "dead_market_reason": dead_market_reason,
                "previous_label": previous_label,
                "hysteresis_applied": 1.0 if hysteresis_applied else 0.0,
                "regime_uncertainty": regime_uncertainty,
                "regime_exit_family": exit_family,
            },
        )
