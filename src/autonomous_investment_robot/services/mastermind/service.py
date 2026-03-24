from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MastermindAdvisory:
    provider: str
    signal: str
    confidence: float
    reason: str
    decision: str = "CONTINUE"
    risk_level: float = 0.0
    veto: bool = False
    size_multiplier: float = 1.0
    execution_style_bias: str = "unchanged"
    reasons: list[str] = field(default_factory=list)
    heuristic: bool = True
    raw: dict[str, Any] = field(default_factory=dict)


class MastermindService:
    def __init__(self, provider: str | None = None) -> None:
        self.provider = (provider or os.getenv("ADVISORY_PROVIDER", "local")).strip().lower() or "local"
        self.groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

    def _clamp(self, value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, float(value)))

    def _truth_penalty(self, truth_context: dict[str, Any] | None) -> tuple[float, list[str]]:
        if not truth_context:
            return 0.25, ["truth_context_missing"]
        snapshot = truth_context.get("snapshot", truth_context.get("truth_confidence", truth_context))
        if not isinstance(snapshot, dict):
            return 0.35, ["truth_context_unstructured"]
        penalties: list[float] = []
        reasons: list[str] = []
        for key, value in snapshot.items():
            if not key.endswith("_confidence"):
                continue
            if isinstance(value, dict):
                level = str(value.get("level", "") or "").lower()
            else:
                level = str(getattr(value, "level", "") or "").lower()
            if level in {"authoritative", "exchange"}:
                penalties.append(0.0)
            elif level in {"partial", "proxy", "degraded"}:
                penalties.append(0.4)
                reasons.append(f"{key}_partial")
            elif level == "weak":
                penalties.append(0.65)
                reasons.append(f"{key}_weak")
            elif level in {"unavailable", "missing"}:
                penalties.append(0.9)
                reasons.append(f"{key}_unavailable")
        if truth_context.get("reconciliation_ok") is False:
            penalties.append(0.9)
            reasons.append("reconciliation_not_ok")
        if not penalties:
            return 0.2, ["truth_context_empty"]
        return self._clamp(sum(penalties) / len(penalties)), sorted(set(reasons))

    def _provider_penalty(self, provider_capability: object | None) -> tuple[float, list[str]]:
        if provider_capability is None:
            return 0.2, ["provider_capability_missing"]
        reasons: list[str] = []
        penalty = 0.0
        lifecycle = str(getattr(provider_capability, "lifecycle_completeness", "") or "").lower()
        user_stream = str(getattr(provider_capability, "user_stream_confidence", "") or "").lower()
        fee_truth = str(getattr(provider_capability, "fee_truth_confidence", "") or "").lower()
        if lifecycle and "partial" in lifecycle:
            penalty += 0.2
            reasons.append("lifecycle_partial")
        if lifecycle and "weak" in lifecycle:
            penalty += 0.35
            reasons.append("lifecycle_weak")
        if user_stream == "rest_history_only":
            penalty += 0.2
            reasons.append("user_stream_rest_only")
        if fee_truth and ("partial" in fee_truth or "proxy" in fee_truth):
            penalty += 0.1
            reasons.append("fee_truth_partial")
        return self._clamp(penalty), sorted(set(reasons))

    def _market_penalty(self, market_integrity: object | None) -> tuple[float, str, list[str]]:
        if market_integrity is None:
            return 0.2, "continue", ["market_integrity_missing"]
        action = str(getattr(market_integrity, "action", "continue") or "continue").lower()
        score = self._clamp(float(getattr(market_integrity, "score", 0.75) or 0.75))
        penalty = max(0.0, 1.0 - score)
        if action == "degrade":
            penalty = max(penalty, 0.45)
        elif action == "flatten_only":
            penalty = max(penalty, 0.75)
        elif action == "halt":
            penalty = 1.0
        return self._clamp(penalty), action, list(getattr(market_integrity, "reasons", []) or [])

    def _local_advisory(self, symbol: str, features: dict[str, Any], regime: str, **context: Any) -> MastermindAdvisory:
        forecast = context.get("forecast")
        execution_quality = context.get("execution_quality")
        market_integrity = context.get("market_integrity")
        provider_capability = context.get("provider_capability")
        event_report = context.get("event_intelligence_report")
        quantum_state = context.get("quantum_state")
        edge_immunity = context.get("edge_immunity_decision")
        truth_context = context.get("truth_context")

        ret1_bps = float(features.get("ret_1", 0.0) or 0.0) * 10000.0
        ret3_bps = float(features.get("ret_3", 0.0) or 0.0) * 10000.0
        realized_vol_bps = abs(float(features.get("realized_vol", 0.0) or 0.0)) * 10000.0
        spread_bps = abs(float(features.get("spread_proxy", 0.0) or 0.0)) * 10000.0
        depth_notional = max(1.0, float(features.get("depth_notional", 0.0) or 0.0))
        flow_imbalance = float(features.get("flow_imbalance", features.get("imbalance", 0.0)) or 0.0)
        forecast_confidence = self._clamp(0.5 if forecast is None else float(getattr(forecast, "confidence", 0.5) or 0.5))
        forecast_edge_bps = abs(float(getattr(forecast, "mu", 0.0) or 0.0)) * 10000.0
        fill_probability = self._clamp(0.6 if execution_quality is None else float(getattr(execution_quality, "fill_probability", 0.6) or 0.6))
        adverse_selection = self._clamp(0.0 if execution_quality is None else float(getattr(execution_quality, "adverse_selection_risk", 0.0) or 0.0))
        event_risk = self._clamp(0.0 if event_report is None else float(getattr(event_report, "overall_risk_score", 0.0) or 0.0))
        event_action = str("continue" if event_report is None else getattr(event_report, "recommended_action", "continue") or "continue").lower()
        quantum_uncertainty = self._clamp(0.0 if quantum_state is None else float(getattr(getattr(quantum_state, "collapse_decision", None), "uncertainty", 0.0) or 0.0))
        edge_survival = self._clamp(0.7 if edge_immunity is None else float(getattr(getattr(edge_immunity, "report", None), "edge_survival_ratio", 0.7) or 0.7))
        edge_fragility = self._clamp(0.0 if edge_immunity is None else float(getattr(getattr(edge_immunity, "report", None), "fragility_index", 0.0) or 0.0))
        truth_penalty, truth_reasons = self._truth_penalty(truth_context if isinstance(truth_context, dict) else None)
        provider_penalty, provider_reasons = self._provider_penalty(provider_capability)
        market_penalty, market_action, market_reasons = self._market_penalty(market_integrity)

        market_quality = self._clamp(
            min(1.0, depth_notional / 100000.0)
            * max(0.0, 1.0 - spread_bps / 25.0)
            * max(0.0, 1.0 - realized_vol_bps / 120.0)
        )
        momentum_support = self._clamp(0.5 + max(-0.45, min(0.45, (ret1_bps + ret3_bps * 0.5) / 50.0)))
        flow_support = self._clamp(0.5 + max(-0.35, min(0.35, flow_imbalance)))
        execution_toxicity = self._clamp(max(1.0 - fill_probability, adverse_selection))
        fragility = self._clamp(
            max(
                1.0 - market_quality,
                event_risk,
                quantum_uncertainty,
                edge_fragility,
                truth_penalty,
                provider_penalty,
                market_penalty,
                execution_toxicity,
            )
        )
        survival_support = self._clamp(0.35 * edge_survival + 0.25 * market_quality + 0.20 * forecast_confidence + 0.20 * (1.0 - execution_toxicity))
        conviction = self._clamp(
            0.30 * forecast_confidence
            + 0.20 * momentum_support
            + 0.10 * flow_support
            + 0.20 * (1.0 - event_risk)
            + 0.20 * (1.0 - quantum_uncertainty)
        )
        reasons = truth_reasons + provider_reasons + market_reasons

        decision = "CONTINUE"
        reason = "local_survival_ok"
        signal = "bounded_support"
        size_multiplier = 1.0
        execution_style_bias = "unchanged"
        veto = False

        if market_action in {"halt", "flatten_only"}:
            decision = "NO_TRADE"
            reason = "market_integrity_block"
            signal = "integrity_block"
            veto = True
            size_multiplier = 0.0
        elif truth_penalty >= 0.8:
            decision = "NO_TRADE"
            reason = "truth_not_strong_enough"
            signal = "truth_block"
            veto = True
            size_multiplier = 0.0
        elif event_action == "no_trade" or execution_toxicity >= 0.8 or fragility >= 0.85:
            decision = "NO_TRADE"
            reason = "hostile_future_breaks_thesis"
            signal = "fragile_edge"
            veto = True
            size_multiplier = 0.0
        elif event_action == "wait" or quantum_uncertainty >= 0.7 or fragility >= 0.65 or survival_support < 0.45:
            decision = "WAIT"
            reason = "uncertainty_requires_wait"
            signal = "wait_dominates"
            size_multiplier = 0.0
            execution_style_bias = "passive_limit"
        elif forecast_edge_bps < 8.0 or conviction < 0.45 or edge_survival < 0.55:
            decision = "PROBE"
            reason = "edge_not_robust_enough_for_full_size"
            signal = "probe_only"
            size_multiplier = 0.2
            execution_style_bias = "passive_limit"
        elif fragility >= 0.45 or event_action == "trade_smaller" or market_action == "degrade":
            decision = "TRADE_SMALLER"
            reason = "bounded_risk_requires_smaller_size"
            signal = "size_down"
            size_multiplier = 0.45
            execution_style_bias = "passive_limit"
        elif regime.lower() in {"panic", "news_chaos", "dead_market"}:
            decision = "WAIT"
            reason = "regime_unfavorable_for_fresh_risk"
            signal = "regime_wait"
            size_multiplier = 0.0
            execution_style_bias = "passive_limit"

        confidence = self._clamp(
            0.45 * (1.0 - fragility)
            + 0.25 * survival_support
            + 0.20 * conviction
            + 0.10 * max(0.0, min(1.0, forecast_edge_bps / 25.0))
        )
        risk_level = self._clamp(
            max(
                fragility,
                truth_penalty,
                provider_penalty,
                market_penalty,
                execution_toxicity,
            )
        ) * 100.0
        reasons.append(f"mastermind_{decision.lower()}")

        return MastermindAdvisory(
            provider="local",
            signal=signal,
            confidence=confidence,
            reason=reason,
            decision=decision,
            risk_level=risk_level,
            veto=veto,
            size_multiplier=size_multiplier,
            execution_style_bias=execution_style_bias,
            reasons=sorted(set(reasons)),
            heuristic=True,
            raw={
                "symbol": symbol,
                "regime": regime,
                "forecast_edge_bps": forecast_edge_bps,
                "forecast_confidence": forecast_confidence,
                "market_quality": market_quality,
                "momentum_support": momentum_support,
                "flow_support": flow_support,
                "fragility": fragility,
                "survival_support": survival_support,
                "conviction": conviction,
                "event_action": event_action,
                "event_risk": event_risk,
                "quantum_uncertainty": quantum_uncertainty,
                "edge_survival": edge_survival,
                "edge_fragility": edge_fragility,
                "truth_penalty": truth_penalty,
                "provider_penalty": provider_penalty,
                "market_penalty": market_penalty,
                "execution_toxicity": execution_toxicity,
                "spread_bps": spread_bps,
                "depth_notional": depth_notional,
                "realized_vol_bps": realized_vol_bps,
                "ret1_bps": ret1_bps,
                "ret3_bps": ret3_bps,
                "market_action": market_action,
            },
        )

    def _unavailable(self, provider: str, symbol: str, features: dict[str, Any], regime: str, reason: str, error: str | None = None) -> MastermindAdvisory:
        payload: dict[str, Any] = {
            "provider": provider,
            "symbol": symbol,
            "regime": regime,
            "features": features,
        }
        if error:
            payload["error"] = error
        return MastermindAdvisory(
            provider=provider,
            signal="unavailable",
            confidence=0.0,
            reason=reason,
            decision="HOLD",
            risk_level=100.0,
            veto=False,
            size_multiplier=0.0,
            execution_style_bias="unchanged",
            reasons=[reason],
            heuristic=True,
            raw=payload,
        )

    def advise(self, symbol: str, features: dict[str, Any], regime: str, **context: Any) -> MastermindAdvisory | None:
        if self.provider == "noop":
            return None

        if self.provider in {"local", "heuristic"}:
            return self._local_advisory(symbol, features, regime, **context)

        if self.provider == "groq":
            if not self.groq_api_key:
                return self._unavailable(
                    provider="groq",
                    symbol=symbol,
                    features=features,
                    regime=regime,
                    reason="unavailable_or_missing_key",
                    error="missing_groq_api_key",
                )

            return self._unavailable(
                provider="groq",
                symbol=symbol,
                features=features,
                regime=regime,
                reason="provider_not_implemented",
            )

        if self.provider == "openai":
            if not self.openai_api_key:
                return self._unavailable(
                    provider="openai",
                    symbol=symbol,
                    features=features,
                    regime=regime,
                    reason="unavailable_or_missing_key",
                    error="missing_openai_api_key",
                )

            return self._unavailable(
                provider="openai",
                symbol=symbol,
                features=features,
                regime=regime,
                reason="provider_not_implemented",
            )

        return self._unavailable(
            provider=self.provider,
            symbol=symbol,
            features=features,
            regime=regime,
            reason="unknown_provider",
        )
