from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from autonomous_investment_robot.core.contracts import (
    CapitalReleaseDecision,
    EdgeImmunityDecision,
    ExecutionQualityForecast,
    ExitIntent,
    InventoryState,
    ProfitFloorDecision,
    ReserveState,
    RoundTripProfitabilityReport,
    TruthConfidenceSnapshot,
)


class ProfitabilityService:
    def __init__(self, *, base_safety_buffer_bps: float = 1.0, min_free_quote_reserve_pct: float = 0.2) -> None:
        self.base_safety_buffer_bps = float(base_safety_buffer_bps)
        self.min_free_quote_reserve_pct = float(min_free_quote_reserve_pct)

    def _truth_penalty_bps(self, truth_confidence: TruthConfidenceSnapshot | dict[str, Any] | None) -> float:
        if truth_confidence is None:
            return 2.0
        penalties = 0.0
        if isinstance(truth_confidence, dict):
            snapshot = truth_confidence
            for attr in (
                "fill_truth_confidence",
                "fee_truth_confidence",
                "realized_pnl_confidence",
                "balance_truth_confidence",
                "exposure_truth_confidence",
                "market_data_truth_confidence",
                "unrealized_pnl_confidence",
            ):
                conf = snapshot.get(attr)
                if conf is None:
                    penalties += 0.5
                    continue
                level = str(conf.get("level", ""))
                if level == "proxy":
                    penalties += 1.0
                elif level == "unavailable":
                    penalties += 3.0
            return penalties
        for attr in (
            "fill_truth_confidence",
            "fee_truth_confidence",
            "realized_pnl_confidence",
            "balance_truth_confidence",
            "exposure_truth_confidence",
            "market_data_truth_confidence",
            "unrealized_pnl_confidence",
        ):
            conf = getattr(truth_confidence, attr, None)
            if conf is None:
                penalties += 0.5
                continue
            level = getattr(getattr(conf, "level", ""), "value", str(getattr(conf, "level", "")))
            if level == "proxy":
                penalties += 1.0
            elif level == "unavailable":
                penalties += 3.0
        return penalties

    def evaluate_open(
        self,
        *,
        symbol: str,
        ts: datetime,
        target_notional: float,
        expected_edge_bps: float,
        fee_bps: float,
        slippage_bps: float,
        spread_bps: float,
        depth_notional: float,
        execution_quality: ExecutionQualityForecast | None = None,
        inventory_state: InventoryState | None = None,
        reserve_state: ReserveState | None = None,
        truth_confidence: TruthConfidenceSnapshot | None = None,
        edge_immunity_decision: EdgeImmunityDecision | None = None,
    ) -> tuple[ProfitFloorDecision, CapitalReleaseDecision, RoundTripProfitabilityReport]:
        depth_penalty = 0.0
        if depth_notional > 0.0:
            depth_penalty = min(12.0, max(0.0, target_notional / max(depth_notional, 1.0)) * 1000.0)
        quality_penalty = 0.0
        fragility = 0.0
        if execution_quality is not None:
            fragility = float(execution_quality.adverse_selection_risk)
            quality_penalty += float(execution_quality.expected_price_quality_bps)
            if execution_quality.fill_probability < 0.35:
                quality_penalty += 3.0
        truth_penalty = self._truth_penalty_bps(truth_confidence)
        fragility_penalty = 0.0
        if edge_immunity_decision is not None:
            fragility_penalty += float(edge_immunity_decision.report.self_impact_penalty_bps)
            fragility = max(fragility, float(edge_immunity_decision.report.fragility_index))
        base_threshold = fee_bps + slippage_bps + spread_bps + depth_penalty + self.base_safety_buffer_bps
        raised_by = truth_penalty + quality_penalty + fragility_penalty
        reasons: list[str] = []
        if truth_penalty > 0.0:
            reasons.append("truth_penalty")
        if quality_penalty > 0.0:
            reasons.append("execution_quality_penalty")
        if fragility_penalty > 0.0:
            reasons.append("fragility_penalty")
        threshold = base_threshold + raised_by
        inventory_pressure = 0.0 if inventory_state is None else float(inventory_state.stale_inventory_score)
        reserve_breach = bool(reserve_state is not None and reserve_state.reserve_breached)
        capital_release_pressure = min(1.0, inventory_pressure * 0.6 + (0.4 if reserve_breach else 0.0))
        capital_release_allowed = reserve_breach and inventory_pressure >= 0.35
        capital_release_action = "continue"
        capital_release_reason = "none"
        release_reasons: list[str] = []
        release_notional = 0.0
        release_multiplier = 1.0
        if capital_release_allowed:
            capital_release_action = "partial_exit"
            capital_release_reason = "reserve_breach_with_stale_inventory"
            release_reasons = ["free_quote_reserve_breached", "stale_inventory"]
            if inventory_state is not None:
                release_notional = inventory_state.gross_open_notional * min(0.5, capital_release_pressure)
            release_multiplier = max(0.2, 1.0 - capital_release_pressure)
        round_trip = expected_edge_bps - threshold
        action = "trade_now"
        recommended_size_multiplier = 1.0
        viability_reasons: list[str] = []
        if round_trip <= 0.0:
            action = "no_trade"
            viability_reasons.append("round_trip_edge_non_positive")
        elif reserve_breach:
            action = "trade_smaller"
            recommended_size_multiplier = min(recommended_size_multiplier, 0.5)
            viability_reasons.append("free_quote_reserve_breached")
        if inventory_pressure >= 0.7 and reserve_breach:
            action = "wait"
            recommended_size_multiplier = 0.0
            viability_reasons.append("inventory_release_preferred")
        if fragility >= 0.8:
            action = "no_trade"
            recommended_size_multiplier = 0.0
            viability_reasons.append("execution_fragility_extreme")
        elif fragility >= 0.45:
            action = "trade_smaller" if action == "trade_now" else action
            recommended_size_multiplier = min(recommended_size_multiplier, 0.5)
            viability_reasons.append("execution_fragility_elevated")
        floor = ProfitFloorDecision(
            symbol=symbol,
            ts=ts,
            threshold_bps=threshold,
            base_threshold_bps=base_threshold,
            raised_by_bps=raised_by,
            capital_release_allowed=capital_release_allowed,
            reasons=reasons,
            metadata={
                "truth_penalty_bps": truth_penalty,
                "quality_penalty_bps": quality_penalty,
                "depth_penalty_bps": depth_penalty,
                "fragility_penalty_bps": fragility_penalty,
            },
        )
        release = CapitalReleaseDecision(
            symbol=symbol,
            ts=ts,
            action=capital_release_action,
            allowed=capital_release_allowed,
            reason=capital_release_reason,
            pressure_score=capital_release_pressure,
            recommended_notional=release_notional,
            size_multiplier=release_multiplier,
            reasons=release_reasons,
            metadata={
                "inventory_state": {} if inventory_state is None else asdict(inventory_state),
                "reserve_state": {} if reserve_state is None else asdict(reserve_state),
            },
        )
        report = RoundTripProfitabilityReport(
            symbol=symbol,
            ts=ts,
            gross_edge_bps=expected_edge_bps,
            expected_entry_cost_bps=fee_bps + slippage_bps + spread_bps * 0.5,
            expected_exit_cost_bps=threshold - self.base_safety_buffer_bps - fee_bps,
            profit_floor_bps=threshold,
            net_edge_bps=round_trip,
            viable=action not in {"no_trade", "wait"},
            recommended_size_multiplier=recommended_size_multiplier,
            action=action,
            reasons=viability_reasons,
            metadata={
                "inventory_pressure": inventory_pressure,
                "reserve_breach": reserve_breach,
                "capital_release_pressure": capital_release_pressure,
                "minimum_reserve_pct": None if reserve_state is None else reserve_state.minimum_reserve_pct,
            },
        )
        return floor, release, report

    def evaluate_exit(
        self,
        *,
        symbol: str,
        ts: datetime,
        inventory_state: InventoryState,
        reserve_state: ReserveState | None = None,
        current_exposure: float = 0.0,
        regime_label: str = "",
        liquidity_regime: str = "",
        execution_quality: ExecutionQualityForecast | None = None,
        event_intelligence: Any | None = None,
        synthetic_affect: Any | None = None,
        position_morph_plan: Any | None = None,
    ) -> tuple[CapitalReleaseDecision, ExitIntent | None]:
        reserve_breach = bool(reserve_state is not None and reserve_state.reserve_breached)
        stale = float(inventory_state.stale_inventory_score)
        if inventory_state.gross_open_notional <= 0.0:
            decision = CapitalReleaseDecision(symbol=symbol, ts=ts, action="continue", allowed=False, reason="no_inventory", pressure_score=0.0)
            return decision, None
        if stale < 0.35 and not reserve_breach:
            decision = CapitalReleaseDecision(symbol=symbol, ts=ts, action="continue", allowed=False, reason="inventory_not_stale", pressure_score=stale)
            return decision, None
        mark_ratio = abs(float(current_exposure)) / max(float(inventory_state.gross_open_notional), 1e-9)
        cost_basis_proxy_state = "at_cost_basis_proxy"
        if mark_ratio < 0.995:
            cost_basis_proxy_state = "below_cost_basis_proxy"
        elif mark_ratio > 1.01:
            cost_basis_proxy_state = "above_cost_basis_proxy"
        event_action = "continue" if event_intelligence is None else str(getattr(event_intelligence, "recommended_action", "continue") or "continue")
        event_risk = 0.0 if event_intelligence is None else float(getattr(event_intelligence, "overall_risk_score", 0.0) or 0.0)
        stress = 0.0 if synthetic_affect is None else float(getattr(synthetic_affect, "stress", 0.0) or 0.0)
        conviction = 0.0 if synthetic_affect is None else float(getattr(synthetic_affect, "conviction", 0.0) or 0.0)
        fear = 0.0 if synthetic_affect is None else float(getattr(synthetic_affect, "fear", 0.0) or 0.0)
        fill_probability = 0.5 if execution_quality is None else float(execution_quality.fill_probability or 0.5)
        adverse_selection = 0.0 if execution_quality is None else float(execution_quality.adverse_selection_risk or 0.0)
        expected_fill_speed_ms = 0.0 if execution_quality is None else float(execution_quality.expected_fill_speed_ms or 0.0)
        oldest_age_hours = float(inventory_state.oldest_age_seconds) / 3600.0
        weighted_age_hours = float(inventory_state.weighted_age_seconds) / 3600.0
        allow_runner = bool(getattr(position_morph_plan, "allow_runner", False)) if position_morph_plan is not None else False
        runner_fraction = 0.0 if position_morph_plan is None else float(getattr(position_morph_plan, "runner_fraction", 0.0) or 0.0)

        action = "partial_exit"
        reason = "reserve_breach_with_stale_inventory" if reserve_breach else "stale_inventory_reduction"
        if reserve_breach and cost_basis_proxy_state == "below_cost_basis_proxy":
            reason = "reserve_breach_below_cost_basis_capital_release"
        elif not reserve_breach and cost_basis_proxy_state == "above_cost_basis_proxy":
            reason = "profit_lock_partial_exit"

        exit_family_candidates: list[dict[str, Any]] = []

        def _candidate(
            name: str,
            score: float,
            *,
            action_name: str,
            execution_style: str,
            target_fraction: float,
            rationale: list[str],
        ) -> None:
            exit_family_candidates.append(
                {
                    "family": name,
                    "score": max(0.0, min(1.0, score)),
                    "action": action_name,
                    "execution_style": execution_style,
                    "target_fraction": max(0.0, min(1.0, target_fraction)),
                    "rationale": rationale,
                }
            )

        _candidate(
            "staged_partial_exit",
            0.55 + max(0.0, stale - 0.35) * 0.45 + (0.12 if cost_basis_proxy_state == "above_cost_basis_proxy" else 0.0),
            action_name="partial_exit",
            execution_style="passive_limit",
            target_fraction=0.35 if cost_basis_proxy_state == "above_cost_basis_proxy" else 0.25,
            rationale=["profit_locking" if reason == "profit_lock_partial_exit" else "stale_inventory_rotation"],
        )
        _candidate(
            "volatility_trailing",
            0.25 + max(0.0, conviction - fear) * 0.35 + (0.10 if allow_runner else 0.0),
            action_name="hold_runner",
            execution_style="passive_limit",
            target_fraction=max(0.0, 1.0 - runner_fraction),
            rationale=["runner_allowed" if allow_runner else "hold_until_exit_confirmed"],
        )
        _candidate(
            "time_decay_exit",
            min(1.0, 0.20 + weighted_age_hours / 48.0 + stale * 0.35),
            action_name="partial_exit",
            execution_style="passive_limit",
            target_fraction=0.30 if oldest_age_hours >= 12.0 else 0.15,
            rationale=["weighted_inventory_age_high"],
        )
        _candidate(
            "regime_failure_exit",
            min(1.0, 0.25 + (0.45 if regime_label.upper() in {"PANIC", "BREAKDOWN"} else 0.0) + event_risk * 0.20),
            action_name="risk_exit",
            execution_style="marketable_limit",
            target_fraction=0.60,
            rationale=["regime_failure" if regime_label.upper() in {"PANIC", "BREAKDOWN"} else "regime_not_failed"],
        )
        _candidate(
            "momentum_exhaustion_exit",
            min(1.0, 0.15 + max(0.0, 0.55 - conviction) * 0.50 + max(0.0, fear - 0.35) * 0.25),
            action_name="partial_exit",
            execution_style="passive_limit",
            target_fraction=0.25,
            rationale=["conviction_softening"],
        )
        _candidate(
            "liquidity_shock_exit",
            min(1.0, 0.20 + adverse_selection * 0.45 + (0.25 if liquidity_regime.upper() == "THIN" else 0.0) + (0.15 if expected_fill_speed_ms > 800.0 else 0.0)),
            action_name="risk_exit",
            execution_style="marketable_limit",
            target_fraction=0.50,
            rationale=["liquidity_shock" if liquidity_regime.upper() == "THIN" else "execution_fragility"],
        )
        _candidate(
            "reacceleration_hold",
            min(1.0, 0.20 + max(0.0, conviction - fear) * 0.45 + fill_probability * 0.20 + (0.10 if allow_runner else 0.0)),
            action_name="hold",
            execution_style="passive_limit",
            target_fraction=0.0,
            rationale=["runner_retention" if allow_runner else "hold_bias"],
        )
        if event_action in {"no_trade", "wait"}:
            for row in exit_family_candidates:
                if row["family"] in {"regime_failure_exit", "liquidity_shock_exit"}:
                    row["score"] = min(1.0, float(row["score"]) + 0.20)
                    row["rationale"] = list(row["rationale"]) + [f"event_intelligence:{event_action}"]
        if reserve_breach:
            for row in exit_family_candidates:
                if row["family"] in {"staged_partial_exit", "time_decay_exit", "regime_failure_exit"}:
                    row["score"] = min(1.0, float(row["score"]) + 0.10)

        chosen_family = max(exit_family_candidates, key=lambda item: float(item["score"]))
        target_fraction = float(chosen_family.get("target_fraction", 0.0) or 0.0)
        if reserve_breach:
            target_fraction = max(target_fraction, 0.5)
        elif reason == "profit_lock_partial_exit":
            target_fraction = max(target_fraction, 0.30)
        notional = inventory_state.gross_open_notional * max(0.15, min(0.75, target_fraction if target_fraction > 0.0 else (0.5 if reserve_breach else 0.25)))
        decision_reasons = ["free_quote_reserve_breached"] if reserve_breach else ["stale_inventory"]
        if cost_basis_proxy_state == "below_cost_basis_proxy":
            decision_reasons.append("below_cost_basis_proxy")
        elif cost_basis_proxy_state == "above_cost_basis_proxy":
            decision_reasons.append("above_cost_basis_proxy")
        if reason == "profit_lock_partial_exit":
            decision_reasons.append("profit_locking")
        decision = CapitalReleaseDecision(
            symbol=symbol,
            ts=ts,
            action=action,
            allowed=True,
            reason=reason,
            pressure_score=max(stale, 0.5 if reserve_breach else stale),
            recommended_notional=notional,
            size_multiplier=max(0.2, 1.0 - stale),
            reasons=decision_reasons,
            metadata={
                "cost_basis_proxy_state": cost_basis_proxy_state,
                "mark_to_entry_ratio": mark_ratio,
                "current_mark_notional": float(current_exposure),
                "entry_notional": float(inventory_state.gross_open_notional),
                "inventory_state": asdict(inventory_state),
                "reserve_state": {} if reserve_state is None else asdict(reserve_state),
                "profit_locking": reason == "profit_lock_partial_exit",
                "requires_doctrine_sell_eligibility": True,
                "winner_monetization": {
                    "state": chosen_family.get("family"),
                    "selected_action": chosen_family.get("action"),
                    "reacceleration_hold": chosen_family.get("family") == "reacceleration_hold",
                    "runner_fraction": runner_fraction,
                },
                "exit_path_comparison": {
                    "selected_family": chosen_family.get("family"),
                    "families": exit_family_candidates,
                },
            },
        )
        side = "sell" if current_exposure >= 0.0 else "buy"
        exit_intent = ExitIntent(
            symbol=symbol,
            ts=ts,
            side=side,
            target_notional=notional,
            reason=reason,
            reduce_only=True,
            execution_style="passive_limit" if not reserve_breach else "marketable_limit",
            metadata={
                "stale_inventory_score": stale,
                "cost_basis_proxy_state": cost_basis_proxy_state,
                "profit_locking": reason == "profit_lock_partial_exit",
                "capital_release_allowed": True,
                "requires_doctrine_sell_eligibility": True,
                "selected_exit_family": str(chosen_family.get("family", "")),
                "selected_exit_action": str(chosen_family.get("action", action)),
                "winner_monetization": {
                    "state": chosen_family.get("family"),
                    "selected_action": chosen_family.get("action"),
                    "target_fraction": target_fraction,
                    "runner_fraction": runner_fraction,
                    "hold_bias": chosen_family.get("family") in {"volatility_trailing", "reacceleration_hold"},
                },
                "exit_state_machine": {
                    "stage": "sell_eligible_gate_pending",
                    "selected_family": chosen_family.get("family"),
                    "family_score": chosen_family.get("score"),
                    "regime_label": regime_label,
                    "liquidity_regime": liquidity_regime,
                    "reserve_breach": reserve_breach,
                },
                "exit_path_comparison": {
                    "selected_family": chosen_family.get("family"),
                    "selected_score": chosen_family.get("score"),
                    "families": exit_family_candidates,
                },
            },
        )
        return decision, exit_intent
