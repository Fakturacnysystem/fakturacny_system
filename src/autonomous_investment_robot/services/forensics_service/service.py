from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable

from autonomous_investment_robot.core.contracts import (
    ExecutionCostAttribution,
    LossAutopsyReport,
    LossReviewSummary,
    PnLAttributionBreakdown,
    PnLAttributionRecord,
    PostTradeSummary,
    TradeEpisode,
    TradeForensicsContext,
    TruthConfidenceLevel,
    TruthQualityWarning,
)
from autonomous_investment_robot.services.analog_trade_lookup.service import AnalogTradeLookup
from autonomous_investment_robot.services.calibration_service.service import CalibrationService
from autonomous_investment_robot.services.counterfactual_evaluator.service import CounterfactualEvaluator
from autonomous_investment_robot.services.episodic_trade_memory.service import EpisodicTradeMemory
from autonomous_investment_robot.services.forensics_service.exit_hierarchy import classify_exit_hierarchy


class ForensicsService:
    def __init__(self, run_dir: str, observability: Any | None = None) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.observability = observability
        self.memory = EpisodicTradeMemory(run_dir)
        self.analog_lookup = AnalogTradeLookup(self.memory)
        self.counterfactual = CounterfactualEvaluator()
        self.calibration = CalibrationService(run_dir)

    def _serialize(self, payload: Any) -> dict[str, Any]:
        if is_dataclass(payload):
            return json.loads(json.dumps(asdict(payload), sort_keys=True, default=str))
        return json.loads(json.dumps(payload, sort_keys=True, default=str))

    def _append(self, channel: str, payload: Any) -> None:
        serializable = self._serialize(payload)
        out = self.run_dir / f"{channel}.jsonl"
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(serializable, sort_keys=True, default=str) + "\n")
        if self.observability is not None:
            self.observability.journal(channel, serializable)

    def _route_optional(self, route_name: str, channel: str, payload: Any) -> None:
        if self.observability is None:
            self._append(channel, payload)
            return
        route = getattr(self.observability, route_name, None)
        if callable(route):
            route(payload)
        else:
            self.observability.journal(channel, self._serialize(payload))

    def _truth_state_label(self, truth_confidence: Any | None) -> str:
        warnings = self._truth_warnings(truth_confidence)
        if not warnings:
            return "authoritative"
        if any(w.level == TruthConfidenceLevel.UNAVAILABLE.value for w in warnings):
            return "degraded_unavailable"
        if any(w.level == TruthConfidenceLevel.PROXY.value for w in warnings):
            return "degraded_proxy"
        return "degraded_partial"

    def _execution_state_label(self, execution_quality: Any | None, execution_plan: Any | None, observed_cost_bps: float) -> str:
        if execution_quality is not None:
            fill_probability = float(getattr(execution_quality, "fill_probability", 0.0) or 0.0)
            adverse = float(getattr(execution_quality, "adverse_selection_risk", 0.0) or 0.0)
            if fill_probability < 0.3 or adverse > 0.7:
                return "fragile"
            if fill_probability < 0.55 or adverse > 0.45:
                return "stressed"
        if execution_plan is not None and str(getattr(execution_plan, "style", "")) in {"aggressive_limit", "market"}:
            return "aggressive"
        if observed_cost_bps > 10.0:
            return "stressed"
        return "stable"

    def _truth_warnings(self, truth_confidence: Any | None) -> list[TruthQualityWarning]:
        if truth_confidence is None:
            return []
        snapshot = self._serialize(truth_confidence)
        warnings: list[TruthQualityWarning] = []
        for key, value in snapshot.items():
            if not key.endswith("_confidence") or not isinstance(value, dict):
                continue
            level = str(value.get("level", ""))
            if level in {TruthConfidenceLevel.AUTHORITATIVE.value, ""}:
                continue
            warnings.append(
                TruthQualityWarning(
                    domain=str(value.get("domain", key)),
                    level=level,
                    reason=str(value.get("reason", "truth_confidence_degraded")),
                    metadata=dict(value.get("evidence", {})) if isinstance(value.get("evidence", {}), dict) else {},
                )
            )
        return warnings

    def _profitability_context(self, context: TradeForensicsContext) -> dict[str, Any]:
        return dict(context.profitability_context or {})

    def _capital_release_context(self, context: TradeForensicsContext) -> dict[str, Any]:
        return dict(context.capital_release_context or {})

    def _summary_outcome(self, realized_pnl: float) -> str:
        if realized_pnl > 0.0:
            return "win"
        if realized_pnl < 0.0:
            return "loss"
        return "flat"

    def _loss_review_summary(
        self,
        *,
        autopsy: LossAutopsyReport,
        profitability_context: dict[str, Any],
        truth_warnings: list[TruthQualityWarning],
    ) -> LossReviewSummary:
        severity = "info"
        if autopsy.category in {"recovery", "reconciliation"} or autopsy.reason in {
            "live_realized_pnl_mismatch",
            "live_fee_mismatch",
            "recovery_halt",
        }:
            severity = "critical"
        elif autopsy.category in {"trade_loss", "execution"} or autopsy.realized_pnl is not None:
            severity = "warning"
        recommendations: list[str] = []
        if truth_warnings:
            recommendations.append("review_truth_confidence_and_exchange_evidence")
        if profitability_context:
            round_trip = profitability_context.get("round_trip", {})
            if str(round_trip.get("action", "")) in {"wait", "no_trade"}:
                recommendations.append("review_round_trip_profitability_gate")
        if "execution_slippage" in autopsy.dominant_failure_modes:
            recommendations.append("review_execution_style_and_depth_constraints")
        if "fee_drag" in autopsy.dominant_failure_modes:
            recommendations.append("review_fee_budget_and_venue_costs")
        if "truth_confidence_degraded" in autopsy.dominant_failure_modes:
            recommendations.append("review_truth_gaps_before_next_live_action")
        return LossReviewSummary(
            symbol=autopsy.symbol,
            ts=autopsy.ts,
            venue=autopsy.venue,
            category=autopsy.category,
            reason=autopsy.reason,
            severity=severity,
            recommendations=recommendations,
            metadata={
                "dominant_failure_modes": list(autopsy.dominant_failure_modes),
                "dominant_failure_chain": list(autopsy.dominant_failure_chain),
            },
        )

    def analyze_trade(
        self,
        *,
        context: TradeForensicsContext,
        fills: Iterable[Any],
        filled_notional: float,
        realized_pnl: float,
        execution_plan: Any | None = None,
        execution_quality: Any | None = None,
        additional_metadata: dict[str, Any] | None = None,
    ) -> tuple[PnLAttributionRecord, LossAutopsyReport | None]:
        fills = list(fills)
        exit_hierarchy_rank, exit_hierarchy_reason = classify_exit_hierarchy(context)
        total_fee = sum(float(getattr(fill, "fee", 0.0)) for fill in fills)
        total_slippage = sum(float(getattr(fill, "slippage_cost", 0.0)) for fill in fills)
        observed_cost_bps = 0.0 if filled_notional <= 0.0 else ((total_fee + total_slippage) / filled_notional) * 10000.0
        profitability_context = self._profitability_context(context)
        capital_release_context = self._capital_release_context(context)
        expected_price_quality_bps = None
        if execution_quality is not None:
            expected_price_quality_bps = float(getattr(execution_quality, "expected_price_quality_bps", 0.0))
        elif execution_plan is not None:
            reasons = getattr(execution_plan, "reasons", {})
            if isinstance(reasons, dict):
                raw = reasons.get("expected_price_quality_bps")
                if raw is not None:
                    expected_price_quality_bps = float(raw)

        directional_pnl = realized_pnl + total_fee + total_slippage
        unexplained_pnl = realized_pnl - directional_pnl + total_fee + total_slippage
        expected_edge_pnl = filled_notional * (context.expected_edge_bps / 10000.0)
        execution_vs_signal_gap = realized_pnl - expected_edge_pnl
        hold_seconds = float(context.metadata.get("hold_seconds", 0.0) or 0.0)
        inventory_carry_cost = None if hold_seconds <= 0.0 else -abs(filled_notional) * min(0.0005, hold_seconds / 86400.0 * 0.0001)
        truth_penalty_bps = float(
            profitability_context.get("profit_floor", {}).get("metadata", {}).get("truth_penalty_bps", 0.0) or 0.0
        )
        truth_quality_penalty = None
        if truth_penalty_bps > 0.0 and filled_notional > 0.0:
            truth_quality_penalty = -(filled_notional * truth_penalty_bps / 10000.0)
        exit_timing_pnl = context.metadata.get("exit_timing_pnl")
        if exit_timing_pnl is not None:
            exit_timing_pnl = float(exit_timing_pnl)
        reasons: list[str] = []
        partial = False
        if filled_notional <= 0.0:
            partial = True
            reasons.append("filled_notional_missing")
        if abs(unexplained_pnl) > 1e-9:
            partial = True
            reasons.append("unexplained_pnl_present")
        truth_warnings = self._truth_warnings(context.truth_confidence)
        if truth_warnings:
            partial = True
            reasons.append("truth_confidence_degraded")
        if exit_timing_pnl is None:
            partial = True
            reasons.append("exit_timing_unknown")
        if inventory_carry_cost is None and hold_seconds <= 0.0:
            reasons.append("inventory_carry_cost_unknown")

        breakdown = PnLAttributionBreakdown(
            directional_pnl=directional_pnl,
            fee_pnl=-total_fee,
            slippage_pnl=-total_slippage,
            holding_timing_pnl=None,
            exit_timing_pnl=exit_timing_pnl,
            execution_vs_signal_gap=execution_vs_signal_gap,
            inventory_carry_cost=inventory_carry_cost,
            truth_quality_penalty=truth_quality_penalty,
            unexplained_pnl=unexplained_pnl,
            partial=partial,
            reasons=reasons,
        )
        execution_costs = ExecutionCostAttribution(
            fee_cost=total_fee,
            slippage_cost=total_slippage,
            observed_execution_cost_bps=observed_cost_bps,
            expected_execution_quality_bps=expected_price_quality_bps,
            partial=expected_price_quality_bps is None,
            metadata={
                "fill_count": len(fills),
                "expected_vs_observed_gap_bps": None
                if expected_price_quality_bps is None
                else observed_cost_bps - expected_price_quality_bps,
            },
        )
        record = PnLAttributionRecord(
            symbol=context.symbol,
            ts=context.ts,
            venue=context.venue,
            order_id=context.order_id,
            side=context.side,
            filled_notional=filled_notional,
            realized_pnl=realized_pnl,
            expected_edge_bps=context.expected_edge_bps,
            expected_edge_pnl=filled_notional * (context.expected_edge_bps / 10000.0),
            regime_label=context.regime_label,
            breakdown=breakdown,
            execution_costs=execution_costs,
            truth_warnings=truth_warnings,
            partial=partial,
            metadata={
                "policy_confidence": context.policy_confidence,
                "policy_uncertainty": context.policy_uncertainty,
                "execution_plan": self._serialize(execution_plan) if execution_plan is not None else {},
                "reconciliation": dict(context.reconciliation),
                "lifecycle": dict(context.lifecycle),
                "profitability_context": profitability_context,
                "capital_release_context": capital_release_context,
                "quantum_context": dict(context.quantum_context),
                "edge_immunity_context": dict(context.edge_immunity_context),
                "unrealized_truth_source": context.unrealized_truth_source,
                "inventory_age": context.inventory_age,
                "exit_hierarchy_rank": exit_hierarchy_rank,
                "exit_hierarchy_reason": exit_hierarchy_reason,
                **({} if additional_metadata is None else additional_metadata),
                **dict(context.metadata),
            },
        )
        self._append("pnl_attribution", record)
        self._append(
            "post_trade_summary",
            PostTradeSummary(
                symbol=context.symbol,
                ts=context.ts,
                venue=context.venue,
                order_id=context.order_id,
                realized_pnl=realized_pnl,
                net_edge_bps=0.0 if filled_notional <= 0.0 else (realized_pnl / filled_notional) * 10000.0,
                outcome=self._summary_outcome(realized_pnl),
                reasons=sorted(set(reasons)),
                metadata={
                    "expected_edge_bps": context.expected_edge_bps,
                    "execution_vs_signal_gap": execution_vs_signal_gap,
                    "truth_warning_count": len(truth_warnings),
                    "exit_hierarchy_rank": exit_hierarchy_rank,
                    "exit_hierarchy_reason": exit_hierarchy_reason,
                },
            ),
        )

        autopsy: LossAutopsyReport | None = None
        failure_modes: list[str] = []
        if realized_pnl < 0.0:
            if directional_pnl < 0.0:
                failure_modes.append("thesis_failed")
            if total_slippage > max(abs(realized_pnl) * 0.25, 1e-9):
                failure_modes.append("execution_slippage")
            if total_fee > max(abs(realized_pnl) * 0.15, 1e-9):
                failure_modes.append("fee_drag")
            if truth_warnings:
                failure_modes.append("truth_confidence_degraded")
            if abs(unexplained_pnl) > 1e-9:
                failure_modes.append("unexplained_pnl_component")
            counterfactual_no_trade = False
            counterfactual_wait = False
            if profitability_context:
                round_trip = profitability_context.get("round_trip", {})
                counterfactual_no_trade = str(round_trip.get("action", "")) == "no_trade"
                counterfactual_wait = str(round_trip.get("action", "")) == "wait"
            elif context.edge_immunity_context:
                action = str(context.edge_immunity_context.get("action", ""))
                counterfactual_no_trade = action == "no_trade"
                counterfactual_wait = action == "wait"
            autopsy = LossAutopsyReport(
                symbol=context.symbol,
                ts=context.ts,
                venue=context.venue,
                category="trade_loss",
                reason="realized_pnl_negative",
                order_id=context.order_id,
                realized_pnl=realized_pnl,
                dominant_failure_modes=failure_modes or ["loss_unclassified"],
                dominant_failure_chain=(failure_modes or ["loss_unclassified"])[:3],
                counterfactual_no_trade=counterfactual_no_trade,
                counterfactual_wait=counterfactual_wait,
                runtime_degradation_context={
                    "truth_warning_count": len(truth_warnings),
                    "capital_release_context": capital_release_context,
                    "unrealized_truth_source": context.unrealized_truth_source,
                    "exit_hierarchy_rank": exit_hierarchy_rank,
                    "exit_hierarchy_reason": exit_hierarchy_reason,
                },
                truth_warnings=truth_warnings,
                evidence={
                    "attribution": self._serialize(record),
                    "execution_costs": self._serialize(execution_costs),
                    "reconciliation": dict(context.reconciliation),
                    "profitability_context": profitability_context,
                    "capital_release_context": capital_release_context,
                    "quantum_context": dict(context.quantum_context),
                    "edge_immunity_context": dict(context.edge_immunity_context),
                },
                partial=partial,
            )
            self._append("loss_autopsy", autopsy)
            self._append(
                "loss_review_summary",
                self._loss_review_summary(
                    autopsy=autopsy,
                    profitability_context=profitability_context,
                    truth_warnings=truth_warnings,
                ),
            )
        analog_matches = self.analog_lookup.lookup(
            symbol=context.symbol,
            regime_label=context.regime_label,
            side=context.side,
            truth_confidence_state=self._truth_state_label(context.truth_confidence),
            execution_quality_state=self._execution_state_label(execution_quality, execution_plan, observed_cost_bps),
            event_context={"quantum": dict(context.quantum_context), "edge": dict(context.edge_immunity_context)},
        )
        self._route_optional("route_analog_lookup", "analog_trade_lookup", {
            "symbol": context.symbol,
            "ts": context.ts,
            "order_id": context.order_id,
            "matches": [self._serialize(item) for item in analog_matches],
        })
        counterfactual_review = self.counterfactual.evaluate(
            symbol=context.symbol,
            ts=context.ts,
            chosen_action=context.side,
            realized_pnl=realized_pnl,
            profitability_context=profitability_context,
            edge_immunity_context=context.edge_immunity_context,
            quantum_context=context.quantum_context,
            similar_episodes=analog_matches,
        )
        self._route_optional("route_counterfactual", "counterfactual_review", counterfactual_review)
        episode = TradeEpisode(
            symbol=context.symbol,
            ts=context.ts,
            episode_id=f"{context.symbol}:{context.order_id or 'na'}:{int(context.ts.timestamp())}",
            order_id=context.order_id,
            side=context.side,
            regime_label=context.regime_label,
            realized_pnl=realized_pnl,
            result=self._summary_outcome(realized_pnl),
            truth_confidence_state=self._truth_state_label(context.truth_confidence),
            execution_quality_state=self._execution_state_label(execution_quality, execution_plan, observed_cost_bps),
            event_context={
                "unrealized_truth_source": context.unrealized_truth_source,
                "quantum": dict(context.quantum_context),
                "edge": dict(context.edge_immunity_context),
            },
            failure_mode="|".join((autopsy.dominant_failure_modes if autopsy is not None else [])[:3]),
            attribution_summary={
                "expected_edge_bps": context.expected_edge_bps,
                "realized_pnl": realized_pnl,
                "execution_vs_signal_gap": execution_vs_signal_gap,
            },
            metadata={"order_id": context.order_id, "venue": context.venue},
        )
        self.memory.record(episode)
        calibration_profile = self.calibration.update_from_episodes(self.memory.recent(100))
        self._route_optional("route_calibration", "calibration_profile", calibration_profile)
        return record, autopsy

    def record_runtime_anomaly(
        self,
        *,
        symbol: str,
        ts: Any,
        venue: str,
        category: str,
        reason: str,
        truth_confidence: Any | None = None,
        evidence: dict[str, Any] | None = None,
        order_id: str = "",
        realized_pnl: float | None = None,
    ) -> LossAutopsyReport:
        warnings = self._truth_warnings(truth_confidence)
        report = LossAutopsyReport(
            symbol=symbol,
            ts=ts,
            venue=venue,
            category=category,
            reason=reason,
            order_id=order_id,
            realized_pnl=realized_pnl,
            dominant_failure_modes=[reason] + (["truth_confidence_degraded"] if warnings else []),
            dominant_failure_chain=[reason] + (["truth_confidence_degraded"] if warnings else []),
            truth_warnings=warnings,
            evidence={} if evidence is None else dict(evidence),
            runtime_degradation_context={"truth_warning_count": len(warnings)},
            partial=bool(warnings),
        )
        self._append("loss_autopsy", report)
        self._append(
            "loss_review_summary",
            self._loss_review_summary(
                autopsy=report,
                profitability_context={},
                truth_warnings=warnings,
            ),
        )
        return report
