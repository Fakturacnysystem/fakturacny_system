from __future__ import annotations

from autonomous_investment_robot.core.contracts import ExecutionQualityForecast, ExpertSignal, RegimeAssessment
from autonomous_investment_robot.services.models.service import Forecast


class AlphaService:
    def evaluate(
        self,
        symbol: str,
        ts: object,
        features: dict[str, float],
        forecast: Forecast,
        regime: RegimeAssessment,
        execution_quality: ExecutionQualityForecast | None = None,
    ) -> list[ExpertSignal]:
        depth = max(float(features.get("depth_notional", 1.0)), 1.0)
        spread_bps = float(features.get("spread_proxy", 0.0)) * 10000.0
        vol_bps = float(features.get("realized_vol", 0.0)) * 10000.0
        ret_1_bps = float(features.get("ret_1", 0.0)) * 10000.0
        ret_3_bps = float(features.get("ret_3", 0.0)) * 10000.0
        flow = float(features.get("flow_imbalance", 0.0))
        liq = float(features.get("liquidations", 0.0))
        eq = execution_quality or ExecutionQualityForecast(symbol, ts, 0.5, 500, spread_bps, 0.5, spread_bps <= 10.0, {})
        capacity = max(50.0, depth * 0.1)

        def _signal(
            name: str,
            directional: float,
            move_bps: float,
            stop_prob: float,
            exec_risk: float,
            confidence: float,
            uncertainty: float,
            regime_fit: float,
            reasons: dict[str, float],
        ) -> ExpertSignal:
            return ExpertSignal(
                expert_name=name,
                symbol=symbol,
                ts=ts,  # type: ignore[arg-type]
                directional_probability=max(0.0, min(1.0, directional)),
                follow_through_probability=max(0.0, min(1.0, confidence * 0.9 + regime_fit * 0.1)),
                expected_move_bps=move_bps,
                stop_out_probability=max(0.0, min(1.0, stop_prob)),
                execution_risk=max(0.0, min(1.0, exec_risk)),
                expected_edge_bps=move_bps * confidence - spread_bps * (1.0 + exec_risk),
                confidence=max(0.0, min(1.0, confidence)),
                uncertainty=max(0.0, min(1.0, uncertainty)),
                regime_fit=max(0.0, min(1.0, regime_fit)),
                capacity_limit=capacity,
                reasons=reasons,
            )

        return [
            _signal("trend_expert", 0.5 + max(-0.4, min(0.4, ret_3_bps / 100.0)), abs(ret_3_bps) + abs(forecast.mu) * 10000.0, 0.25, 0.2, forecast.confidence, 0.25, 1.0 if regime.label == "trend" else 0.45, {"ret_3_bps": ret_3_bps}),
            _signal("mean_reversion_expert", 0.5 - max(-0.35, min(0.35, ret_1_bps / 60.0)), abs(ret_1_bps) * 0.8, 0.35, 0.15, max(0.3, 1.0 - forecast.confidence * 0.4), 0.35, 1.0 if regime.label in {"mean_reversion", "low_vol_chop"} else 0.4, {"ret_1_bps": ret_1_bps}),
            _signal("breakout_expert", 0.5 + max(-0.3, min(0.3, flow * 0.6)), abs(ret_3_bps) + vol_bps * 0.25, 0.4, 0.3, forecast.confidence * 0.9, 0.4, 0.95 if regime.label in {"trend", "high_vol_expansion"} else 0.3, {"flow_imbalance": flow}),
            _signal("volatility_expansion_expert", 0.5 + max(-0.25, min(0.25, ret_1_bps / 80.0)), vol_bps * 0.6, 0.45, 0.35, min(1.0, vol_bps / 100.0), 0.45, 1.0 if regime.label in {"high_vol_expansion", "news_chaos"} else 0.35, {"vol_bps": vol_bps}),
            _signal("microstructure_expert", 0.5 + max(-0.3, min(0.3, flow)), abs(flow) * 12.0, 0.3, 1.0 - eq.fill_probability, min(1.0, abs(flow) + 0.3), 0.3, 0.9 if spread_bps <= 10.0 else 0.4, {"spread_bps": spread_bps}),
            _signal("liquidity_sweep_expert", 0.5 + max(-0.25, min(0.25, -flow * 0.5)), liq / 10000.0, 0.5, 0.4, min(1.0, liq / 100000.0 + 0.2), 0.55, 0.85 if regime.label in {"liquidity_vacuum", "news_chaos"} else 0.25, {"liquidations": liq}),
            _signal("execution_quality_forecaster", eq.fill_probability, max(0.0, 10.0 - eq.expected_price_quality_bps), 1.0 - eq.fill_probability, 1.0 - eq.fill_probability, 1.0 - eq.adverse_selection_risk, eq.adverse_selection_risk, 1.0, {"expected_fill_speed_ms": float(eq.expected_fill_speed_ms)}),
            _signal("failure_risk_forecaster", 0.5, -spread_bps, min(1.0, spread_bps / 25.0), max(0.0, 1.0 - regime.confidence), max(0.2, 1.0 - regime.transition_probability), regime.transition_probability, 1.0 if regime.degradation_warning else 0.5, {"degradation_warning": 1.0 if regime.degradation_warning else 0.0}),
        ]
