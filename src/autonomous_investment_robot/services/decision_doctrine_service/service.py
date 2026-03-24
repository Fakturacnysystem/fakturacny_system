from __future__ import annotations

from datetime import datetime
from typing import Any

from autonomous_investment_robot.core.contracts import DecisionDoctrineReport


class DecisionDoctrineService:
    def _clamp(self, value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, float(value)))

    def _level_score(self, level: str | None) -> float:
        normalized = str(level or "").lower()
        if normalized in {"authoritative", "strong", "exchange"}:
            return 1.0
        if normalized in {"proxy", "partial", "degraded"}:
            return 0.55
        if normalized in {"weak"}:
            return 0.35
        if normalized in {"unavailable", "missing"}:
            return 0.0
        return 0.65

    def _provider_score(self, provider_capability: object | None) -> tuple[float, list[str], bool]:
        if provider_capability is None:
            return 0.65, ["provider_capability_missing"], True
        user_stream = str(getattr(provider_capability, "user_stream_confidence", "partial") or "partial")
        lifecycle = str(getattr(provider_capability, "lifecycle_completeness", "partial") or "partial")
        fee_truth = str(getattr(provider_capability, "fee_truth_confidence", "partial") or "partial")
        score = (
            0.40 * self._level_score("strong" if user_stream == "user_stream_plus_rest_repair" else "partial" if user_stream == "rest_history_only" else user_stream)
            + 0.35 * self._level_score("strong" if lifecycle == "strong_without_replace" else "partial" if "partial" in lifecycle else lifecycle)
            + 0.25 * self._level_score("strong" if "authoritative" in fee_truth else "partial" if "partial" in fee_truth or "proxy" in fee_truth else fee_truth)
        )
        reasons: list[str] = []
        partial = False
        if user_stream == "rest_history_only":
            reasons.append("provider_user_stream_partial")
            partial = True
        if lifecycle != "strong_without_replace":
            reasons.append("provider_lifecycle_partial")
            partial = True
        return self._clamp(score), reasons, partial

    def _truth_strength(self, truth_context: dict[str, Any] | None) -> tuple[float, float, list[str], bool]:
        if not truth_context:
            return 0.70, 0.30, ["truth_context_missing"], True
        snapshot = truth_context.get("snapshot", truth_context.get("truth_confidence", truth_context))
        if not isinstance(snapshot, dict):
            return 0.60, 0.40, ["truth_context_unstructured"], True
        domains = [
            "fill_truth_confidence",
            "fee_truth_confidence",
            "realized_pnl_confidence",
            "balance_truth_confidence",
            "exposure_truth_confidence",
            "market_data_truth_confidence",
            "unrealized_pnl_confidence",
        ]
        scores: list[float] = []
        reasons: list[str] = []
        partial = False
        for domain in domains:
            payload = snapshot.get(domain)
            if payload is None:
                continue
            level = payload.get("level") if isinstance(payload, dict) else getattr(payload, "level", None)
            if hasattr(level, "value"):
                level = level.value
            score = self._level_score(None if level is None else str(level))
            scores.append(score)
            if score < 1.0:
                partial = True
            if score <= 0.0:
                reasons.append(f"{domain}_unavailable")
            elif score < 0.6:
                reasons.append(f"{domain}_partial")
        if not scores:
            return 0.65, 0.35, ["truth_context_empty"], True
        strength = sum(scores) / len(scores)
        penalty = 1.0 - strength
        if truth_context.get("reconciliation_ok") is False:
            strength = min(strength, 0.30)
            penalty = max(penalty, 0.70)
            reasons.append("reconciliation_not_ok")
            partial = True
        return self._clamp(strength), self._clamp(penalty), sorted(set(reasons)), partial

    def evaluate(
        self,
        *,
        symbol: str,
        ts: datetime,
        base_uncertainty: float,
        truth_context: dict[str, Any] | None = None,
        market_integrity_status: object | None = None,
        provider_capability: object | None = None,
        execution_quality: object | None = None,
        portfolio_allocation: object | None = None,
        profitability_context: dict[str, Any] | None = None,
        event_intelligence_report: object | None = None,
        synthetic_affect_state: object | None = None,
        capital_sovereignty_decision: object | None = None,
        position_morph_plan: object | None = None,
        execution_simulation_report: object | None = None,
        spre_decision: object | None = None,
        shadow_rival_report: object | None = None,
        edge_immunity_decision: object | None = None,
        quantum_state: object | None = None,
        mastermind_advisory: object | None = None,
    ) -> DecisionDoctrineReport:
        raw_truth_strength, partial_truth_penalty, truth_reasons, truth_partial = self._truth_strength(truth_context)
        provider_score, provider_reasons, provider_partial = self._provider_score(provider_capability)

        market_score = 0.75
        market_action = "continue"
        market_reasons: list[str] = []
        if market_integrity_status is not None:
            market_score = self._clamp(float(getattr(market_integrity_status, "score", 0.75) or 0.75))
            market_action = str(getattr(market_integrity_status, "action", "continue") or "continue")
            market_reasons = list(getattr(market_integrity_status, "reasons", []) or [])

        truth_strength = self._clamp(raw_truth_strength * 0.60 + market_score * 0.25 + provider_score * 0.15)
        # Partial truth cannot be upgraded to full truth by cleaner secondary signals.
        truth_strength = self._clamp(min(truth_strength, raw_truth_strength + 0.15))
        partial_truth_penalty = self._clamp(max(partial_truth_penalty, 1.0 - truth_strength))

        fill_probability = 0.65 if execution_quality is None else float(getattr(execution_quality, "fill_probability", 0.65) or 0.65)
        adverse_selection = 0.0 if execution_quality is None else float(getattr(execution_quality, "adverse_selection_risk", 0.0) or 0.0)
        expected_fill_speed_ms = 0.0 if execution_quality is None else float(getattr(execution_quality, "expected_fill_speed_ms", 0.0) or 0.0)
        stressed_fill_probability = fill_probability if execution_simulation_report is None else float(getattr(execution_simulation_report, "stressed_fill_probability", fill_probability) or fill_probability)
        worst_case_cost_bps = 0.0 if execution_simulation_report is None else float(getattr(execution_simulation_report, "worst_case_cost_bps", 0.0) or 0.0)
        recommended_sim_action = "continue" if execution_simulation_report is None else str(getattr(execution_simulation_report, "recommended_action", "continue") or "continue")
        expected_edge = 0.0
        if profitability_context is not None:
            expected_edge = float((profitability_context.get("round_trip", {}) or {}).get("net_edge_bps", 0.0) or 0.0)
        execution_survivability = self._clamp(
            0.35 * fill_probability
            + 0.30 * stressed_fill_probability
            + 0.20 * (1.0 - adverse_selection)
            + 0.15 * (1.0 - min(1.0, worst_case_cost_bps / max(expected_edge, 10.0)))
        )
        if expected_fill_speed_ms > 2500:
            execution_survivability = self._clamp(execution_survivability - 0.15)

        edge_survival = 0.70
        edge_fragility = 0.0
        if edge_immunity_decision is not None:
            report = getattr(edge_immunity_decision, "report", None)
            edge_survival = float(getattr(report, "edge_survival_ratio", 0.70) or 0.70)
            edge_fragility = float(getattr(report, "fragility_index", 0.0) or 0.0)
        spre_meta = {} if spre_decision is None else dict(getattr(spre_decision, "metadata", {}) or {})
        spre_survival = float(spre_meta.get("chosen_survival_ratio", 0.70) or 0.70)
        spre_regret = float(getattr(spre_decision, "regret_score", 0.0) or 0.0)
        shadow_critique = 0.0 if shadow_rival_report is None else float(getattr(shadow_rival_report, "critique_score", 0.0) or 0.0)
        quantum_uncertainty = 0.0
        if quantum_state is not None:
            quantum_uncertainty = float(getattr(getattr(quantum_state, "collapse_decision", None), "uncertainty", 0.0) or 0.0)
        event_risk = 0.0 if event_intelligence_report is None else float(getattr(event_intelligence_report, "overall_risk_score", 0.0) or 0.0)
        affect_shift = 0.0 if synthetic_affect_state is None else float(getattr(synthetic_affect_state, "no_trade_threshold_shift", 0.0) or 0.0)
        aggression_clamp = 1.0 if synthetic_affect_state is None else float(getattr(synthetic_affect_state, "aggression_clamp", 1.0) or 1.0)
        mastermind_action = "continue" if mastermind_advisory is None else str(getattr(mastermind_advisory, "decision", "continue") or "continue").lower()
        mastermind_confidence = 0.0 if mastermind_advisory is None else self._clamp(float(getattr(mastermind_advisory, "confidence", 0.0) or 0.0))
        mastermind_risk = 0.0 if mastermind_advisory is None else self._clamp(float(getattr(mastermind_advisory, "risk_level", 0.0) or 0.0) / 100.0)
        mastermind_size_multiplier = 1.0 if mastermind_advisory is None else self._clamp(float(getattr(mastermind_advisory, "size_multiplier", 1.0) or 1.0))
        mastermind_reasons = [] if mastermind_advisory is None else list(getattr(mastermind_advisory, "reasons", []) or [])

        robustness_score = self._clamp(
            0.28 * edge_survival
            + 0.24 * spre_survival
            + 0.22 * execution_survivability
            + 0.14 * truth_strength
            + 0.12 * market_score
            + 0.08 * (1.0 - mastermind_risk)
            - 0.12 * edge_fragility
            - 0.10 * event_risk
        )
        uncertainty_pressure = self._clamp(
            max(
                base_uncertainty,
                quantum_uncertainty,
                affect_shift,
                partial_truth_penalty,
                1.0 - market_score,
                event_risk * 0.85,
                max(0.0, mastermind_risk * 0.9 + (1.0 - mastermind_confidence) * 0.35),
            )
        )

        capital_freedom = 0.70
        capital_action = "continue"
        if capital_sovereignty_decision is not None:
            capital_freedom = self._clamp(float(getattr(capital_sovereignty_decision, "freedom_envelope_score", 0.70) or 0.70))
            capital_action = str(getattr(capital_sovereignty_decision, "action", "continue") or "continue")
        keep_core_ratio = 0.0 if capital_sovereignty_decision is None else float(getattr(capital_sovereignty_decision, "keep_core_ratio", 0.0) or 0.0)
        runner_fraction = 0.0 if position_morph_plan is None else float(getattr(position_morph_plan, "runner_fraction", 0.0) or 0.0)

        survival_score = self._clamp(
            0.30 * truth_strength
            + 0.25 * execution_survivability
            + 0.20 * robustness_score
            + 0.15 * capital_freedom
            + 0.10 * (1.0 - uncertainty_pressure)
        )
        regret_pressure = self._clamp(
            min(1.0, spre_regret / 10.0) * 0.45
            + shadow_critique * 0.35
            + max(0.0, 0.45 - spre_survival) * 0.20
            + (0.20 if mastermind_action in {"wait", "no_trade"} else 0.10 if mastermind_action in {"probe", "trade_smaller"} else 0.0)
        )

        doctrine_size_multiplier = self._clamp(
            min(
                aggression_clamp,
                mastermind_size_multiplier,
                1.0 - uncertainty_pressure * 0.65,
                max(0.15, robustness_score),
                max(0.15, execution_survivability),
                max(0.15, capital_freedom),
            )
        )
        if capital_action in {"probe_only", "trade_smaller"}:
            doctrine_size_multiplier = min(doctrine_size_multiplier, float(getattr(capital_sovereignty_decision, "recommended_size_multiplier", doctrine_size_multiplier) or doctrine_size_multiplier))

        recommended_action = "continue"
        reasons = list(truth_reasons) + list(provider_reasons) + list(market_reasons)
        if market_action in {"flatten_only", "halt"}:
            recommended_action = "no_trade"
            reasons.append("doctrine_market_integrity_blocks_action")
        elif raw_truth_strength < 0.35 or partial_truth_penalty >= 0.70 or "reconciliation_not_ok" in truth_reasons:
            recommended_action = "no_trade"
            reasons.append("doctrine_truth_not_strong_enough")
        elif mastermind_action in {"no_trade", "hold"} and mastermind_confidence >= 0.45:
            recommended_action = "no_trade"
            reasons.append("doctrine_mastermind_veto")
        elif execution_survivability < 0.35 or robustness_score < 0.35:
            recommended_action = "no_trade"
            reasons.append("doctrine_robust_edge_not_proved")
        elif recommended_sim_action == "no_trade":
            recommended_action = "no_trade"
            reasons.append("doctrine_execution_toxic")
        elif mastermind_action == "wait" and mastermind_confidence >= 0.40:
            recommended_action = "wait"
            reasons.append("doctrine_mastermind_wait")
        elif uncertainty_pressure > 0.75 or (shadow_rival_report is not None and str(getattr(shadow_rival_report, "action", "continue")) == "wait"):
            recommended_action = "wait"
            reasons.append("doctrine_uncertainty_requires_wait")
        elif mastermind_action == "probe" or capital_action == "probe_only" or str(spre_meta.get("internal_action", "")) == "probe" or float(getattr(position_morph_plan, "probe_notional", 0.0) or 0.0) > 0.0:
            recommended_action = "probe"
            reasons.append("doctrine_probe_dominates")
        elif mastermind_action == "trade_smaller" or doctrine_size_multiplier < 0.60 or str(getattr(shadow_rival_report, "action", "continue")) == "trade_smaller":
            recommended_action = "trade_smaller"
            reasons.append("doctrine_trade_smaller")

        partial = truth_partial or provider_partial
        if partial:
            reasons.append("doctrine_partial_truth_propagated")
        if expected_edge <= 0.0 and profitability_context is not None:
            reasons.append("doctrine_round_trip_not_positive")
        reasons.extend(mastermind_reasons)

        return DecisionDoctrineReport(
            symbol=symbol,
            ts=ts,
            recommended_action=recommended_action,
            size_multiplier=doctrine_size_multiplier,
            truth_strength=truth_strength,
            survival_score=survival_score,
            robustness_score=robustness_score,
            execution_survivability_score=execution_survivability,
            capital_freedom_score=capital_freedom,
            uncertainty_pressure=uncertainty_pressure,
            partial_truth_penalty=partial_truth_penalty,
            regret_pressure=regret_pressure,
            reasons=sorted(set(reasons)),
            partial=partial,
            metadata={
                "market_integrity_action": market_action,
                "raw_truth_strength": raw_truth_strength,
                "provider_score": provider_score,
                "edge_survival_ratio": edge_survival,
                "spre_survival_ratio": spre_survival,
                "shadow_critique_score": shadow_critique,
                "expected_fill_probability": fill_probability,
                "stressed_fill_probability": stressed_fill_probability,
                "worst_case_cost_bps": worst_case_cost_bps,
                "capital_action": capital_action,
                "keep_core_ratio": keep_core_ratio,
                "runner_fraction": runner_fraction,
                "event_risk": event_risk,
                "quantum_uncertainty": quantum_uncertainty,
                "aggression_clamp": aggression_clamp,
                "expected_edge_bps": expected_edge,
                "mastermind_action": mastermind_action,
                "mastermind_confidence": mastermind_confidence,
                "mastermind_risk": mastermind_risk,
            },
        )
