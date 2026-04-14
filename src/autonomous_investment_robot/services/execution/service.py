from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256

from autonomous_investment_robot.config.settings import ExecutionMode, ExecutionSettings
from autonomous_investment_robot.core.contracts import ExecutionPlan, ExecutionQualityForecast
from autonomous_investment_robot.services.execution.constraints import VenueConstraintsNormalizer, provider_capability_matrix
from autonomous_investment_robot.services.execution.tco import anti_toxic_block, slice_notional
from autonomous_investment_robot.services.policy.service import OrderIntent


@dataclass
class Fill:
    venue: str
    order_id: str
    fill_id: str
    symbol: str
    side: str
    notional: float
    fee: float
    slippage_cost: float
    latency_ms: int
    status: str
    metadata: dict[str, object] = field(default_factory=dict)


class ExecutionService:
    def __init__(self, settings: ExecutionSettings) -> None:
        self.settings = settings
        self.fill_seen: set[tuple[str, str, str]] = set()
        self.live_service = None
        self.constraints = VenueConstraintsNormalizer()

    def _paper_taker_fallback_allowed(self, intent: OrderIntent) -> bool:
        comps = intent.why.get("components", []) if isinstance(intent.why, dict) else []
        if not comps:
            return True
        for c in comps:
            edge = float(c.get("final_edge_bps", c.get("edge_bps", 0.0)))
            cost = float(c.get("cost_total_bps", 0.0))
            if edge > cost:
                return True
        return False

    def attach_live_service(self, live_service: object) -> None:
        self.live_service = live_service

    def venue_constraints(self, symbol: str):
        return self.constraints.for_provider(self.settings.provider_id, symbol)

    def provider_capability_matrix(self):
        return provider_capability_matrix(self.settings.provider_id)

    def _doctrine_payload(self, intent: OrderIntent) -> dict[str, object]:
        if not isinstance(intent.why, dict):
            return {}
        payload = intent.why.get("decision_doctrine", {})
        return payload if isinstance(payload, dict) else {}

    def _execution_simulation_payload(self, intent: OrderIntent) -> dict[str, object]:
        if not isinstance(intent.why, dict):
            return {}
        payload = intent.why.get("execution_simulation", {})
        return payload if isinstance(payload, dict) else {}

    def _market_integrity_payload(self, intent: OrderIntent) -> dict[str, object]:
        if not isinstance(intent.why, dict):
            return {}
        payload = intent.why.get("market_integrity", {})
        return payload if isinstance(payload, dict) else {}

    def _trade_admission_payload(self, intent: OrderIntent) -> dict[str, object]:
        if not isinstance(intent.why, dict):
            return {}
        payload = intent.why.get("trade_admission", {})
        return payload if isinstance(payload, dict) else {}

    def _doctrine_target_payload(self, intent: OrderIntent) -> dict[str, object]:
        if not isinstance(intent.why, dict):
            return {}
        payload = intent.why.get("doctrine_target", {})
        return payload if isinstance(payload, dict) else {}

    def _execution_calibration_payload(self, intent: OrderIntent) -> dict[str, object]:
        if not isinstance(intent.why, dict):
            return {}
        payload = intent.why.get("execution_calibration_feedback", {})
        return payload if isinstance(payload, dict) else {}

    def _mastermind_payload(self, intent: OrderIntent) -> dict[str, object]:
        if not isinstance(intent.why, dict):
            return {}
        payload = intent.why.get("mastermind", {})
        return payload if isinstance(payload, dict) else {}

    def _global_execution_adjustments(self, intent: OrderIntent, *, reduce_only: bool) -> dict[str, object]:
        doctrine = self._doctrine_payload(intent)
        execution_simulation = self._execution_simulation_payload(intent)
        market_integrity = self._market_integrity_payload(intent)
        trade_admission = self._trade_admission_payload(intent)
        mastermind = self._mastermind_payload(intent)
        meta_governor = intent.why.get("meta_governor", {}) if isinstance(intent.why, dict) and isinstance(intent.why.get("meta_governor", {}), dict) else {}
        human_escalation = intent.why.get("human_escalation", {}) if isinstance(intent.why, dict) and isinstance(intent.why.get("human_escalation", {}), dict) else {}
        doctrine_target = self._doctrine_target_payload(intent)
        calibration_feedback = self._execution_calibration_payload(intent)

        doctrine_action = str(doctrine.get("recommended_action", "continue") or "continue")
        doctrine_size_multiplier = float(doctrine.get("size_multiplier", 1.0) or 1.0)
        uncertainty_pressure = float(doctrine.get("uncertainty_pressure", 0.0) or 0.0)
        partial_truth_penalty = float(doctrine.get("partial_truth_penalty", 0.0) or 0.0)
        execution_survivability = float(doctrine.get("execution_survivability_score", 1.0) or 1.0)
        robustness_score = float(doctrine.get("robustness_score", 1.0) or 1.0)
        simulation_action = str(execution_simulation.get("recommended_action", "continue") or "continue")
        market_integrity_action = str(market_integrity.get("action", "continue") or "continue")
        admission_action = str(trade_admission.get("recommended_action", "continue") or "continue")
        admission_size_multiplier = float(trade_admission.get("recommended_size_multiplier", 1.0) or 1.0)
        signal_decay_risk = float(trade_admission.get("signal_decay_risk", 0.0) or 0.0)
        execution_survivability = min(
            execution_survivability,
            float(trade_admission.get("execution_survivability_score", execution_survivability) or execution_survivability),
        )
        floor_compatibility = float(trade_admission.get("floor_compatibility_score", 1.0) or 1.0)
        recommended_execution_style = str(trade_admission.get("recommended_execution_style", "limit") or "limit")
        calibration_confidence = float(calibration_feedback.get("confidence", 0.0) or 0.0)
        realized_slippage_overshoot_bps = float(calibration_feedback.get("realized_slippage_overshoot_bps", 0.0) or 0.0)
        fill_delay_destruction_bps = float(calibration_feedback.get("fill_delay_destruction_bps", 0.0) or 0.0)
        edge_capture_efficiency = float(calibration_feedback.get("edge_capture_efficiency", 1.0) or 1.0)
        calibration_conservative = False
        mastermind_action = str(mastermind.get("decision", "CONTINUE") or "CONTINUE").lower()
        mastermind_size_multiplier = float(mastermind.get("size_multiplier", 1.0) or 1.0)
        mastermind_execution_style = str(mastermind.get("execution_style_bias", "unchanged") or "unchanged")
        meta_action = str(meta_governor.get("action", "continue") or "continue")
        escalation_action = str(human_escalation.get("action", "continue") or "continue")

        hard_block = False
        if (
            not reduce_only
            and str(intent.side).lower() == "sell"
            and bool(doctrine_target.get("long_only", False))
        ):
            hard_block = True
        if not reduce_only and doctrine_action in {"no_trade", "wait"}:
            hard_block = True
        if not reduce_only and admission_action in {"no_trade", "wait"}:
            hard_block = True
        if not reduce_only and simulation_action in {"no_trade", "wait"}:
            hard_block = True
        if not reduce_only and mastermind_action in {"no_trade", "wait", "hold"}:
            hard_block = True

        if reduce_only:
            preferred_exit_style = "passive_limit"
            if escalation_action == "flatten_only" or meta_action in {"force_halt_and_flatten", "force_flatten_only"}:
                preferred_exit_style = "marketable_limit"
            elif market_integrity_action in {"flatten_only", "halt"} or partial_truth_penalty >= 0.70:
                preferred_exit_style = "marketable_limit"
        else:
            preferred_exit_style = "limit"
            if recommended_execution_style == "marketable_limit" and signal_decay_risk >= 0.65 and execution_survivability >= 0.75 and floor_compatibility >= 0.80:
                preferred_exit_style = "marketable_limit"
            elif doctrine_action in {"probe", "trade_smaller"} or admission_action in {"probe", "trade_smaller"} or simulation_action == "trade_smaller" or mastermind_action in {"probe", "trade_smaller"}:
                preferred_exit_style = "limit"
            elif market_integrity_action in {"degrade", "flatten_only"}:
                preferred_exit_style = "limit"
            if calibration_confidence >= 0.50 and (
                realized_slippage_overshoot_bps > 3.0
                or fill_delay_destruction_bps > 6.0
                or edge_capture_efficiency < 0.65
            ):
                calibration_conservative = True
                preferred_exit_style = "limit"
                admission_size_multiplier = min(admission_size_multiplier, 0.75 if edge_capture_efficiency >= 0.50 else 0.60)

        return {
            "hard_block": hard_block,
            "doctrine_action": doctrine_action,
            "admission_action": admission_action,
            "simulation_action": simulation_action,
            "market_integrity_action": market_integrity_action,
            "mastermind_action": mastermind_action,
            "size_multiplier": max(0.0, min(1.0, min(doctrine_size_multiplier, mastermind_size_multiplier, admission_size_multiplier))),
            "uncertainty_pressure": max(0.0, min(1.0, uncertainty_pressure)),
            "partial_truth_penalty": max(0.0, min(1.0, partial_truth_penalty)),
            "execution_survivability_score": max(0.0, min(1.0, execution_survivability)),
            "robustness_score": max(0.0, min(1.0, robustness_score)),
            "preferred_exit_style": preferred_exit_style,
            "mastermind_execution_style": mastermind_execution_style,
            "doctrine_long_only": bool(doctrine_target.get("long_only", False)),
            "signal_decay_risk": max(0.0, min(1.0, signal_decay_risk)),
            "floor_compatibility_score": max(0.0, min(1.0, floor_compatibility)),
            "execution_calibration_feedback": calibration_feedback,
            "calibration_conservative": calibration_conservative,
        }

    def forecast_execution_quality(
        self,
        intent: OrderIntent,
        *,
        depth_notional: float,
        spread_bps: float,
        regime: str,
        liquidity_regime: str,
    ) -> ExecutionQualityForecast:
        ts = datetime.now(timezone.utc)
        passive = self.settings.maker_preference and regime != "PANIC" and liquidity_regime == "GOOD" and spread_bps <= 15.0
        depth_ratio = min(1.0, max(0.0, depth_notional / max(abs(intent.target_notional) * 10.0, 1.0)))
        fill_probability = max(0.05, min(0.98, depth_ratio * (0.8 if passive else 0.95) - spread_bps / 200.0 + 0.2))
        adverse_selection = max(0.0, min(1.0, spread_bps / 50.0 + (0.15 if regime == "PANIC" else 0.0)))
        expected_speed = int(250 if passive else 100)
        if liquidity_regime == "THIN":
            expected_speed *= 4
        return ExecutionQualityForecast(
            symbol=intent.symbol,
            ts=ts,
            fill_probability=fill_probability,
            expected_fill_speed_ms=expected_speed,
            expected_price_quality_bps=max(0.0, spread_bps * (0.5 if passive else 1.2)),
            adverse_selection_risk=adverse_selection,
            passive_preferred=passive,
            reasons={
                "depth_ratio": depth_ratio,
                "regime": regime,
                "liquidity_regime": liquidity_regime,
            },
        )

    def build_execution_plan(
        self,
        intent: OrderIntent,
        *,
        depth_notional: float,
        spread_bps: float,
        regime: str,
        liquidity_regime: str,
        reduce_only: bool = False,
    ) -> ExecutionPlan:
        forecast = self.forecast_execution_quality(
            intent,
            depth_notional=depth_notional,
            spread_bps=spread_bps,
            regime=regime,
            liquidity_regime=liquidity_regime,
        )
        constraints = self.venue_constraints(intent.symbol)
        doctrine_adjustments = self._global_execution_adjustments(intent, reduce_only=reduce_only)
        proof_payload = {}
        if isinstance(intent.why, dict):
            raw_proof = intent.why.get("lifecycle_proof", {})
            if isinstance(raw_proof, dict):
                proof_payload = dict(raw_proof)
        policy_requested_notional = max(0.0, float(intent.target_notional))
        constraint_notional, constraint_meta = self.constraints.normalize_target_notional(
            target_notional=policy_requested_notional,
            constraints=constraints,
            reduce_only=reduce_only,
        )
        doctrine_scaled_notional = constraint_notional * float(doctrine_adjustments["size_multiplier"])
        submitted_target_notional = doctrine_scaled_notional
        if bool(proof_payload.get("enabled", False)):
            submitted_target_notional = max(
                float(proof_payload.get("submitted_target_notional", 0.0) or 0.0),
                float(proof_payload.get("proof_target_notional", 0.0) or 0.0),
                float(constraints.min_notional or 0.0),
            )
        normalized_notional = submitted_target_notional
        if bool(doctrine_adjustments["hard_block"]):
            normalized_notional = 0.0
        passive = forecast.passive_preferred and self.settings.maker_preference
        child_orders = max(1, min(self.settings.max_child_orders, self.settings.slicing_parts))
        order_style = "limit" if passive else "marketable_limit"
        if spread_bps > 20.0 or liquidity_regime == "THIN":
            child_orders = max(1, min(child_orders, 2))
        if (
            str(doctrine_adjustments["doctrine_action"]) in {"probe", "trade_smaller"}
            or str(doctrine_adjustments["admission_action"]) in {"probe", "trade_smaller"}
            or str(doctrine_adjustments["simulation_action"]) == "trade_smaller"
            or str(doctrine_adjustments["mastermind_action"]) in {"probe", "trade_smaller"}
            or float(doctrine_adjustments["uncertainty_pressure"]) >= 0.55
            or float(doctrine_adjustments["partial_truth_penalty"]) >= 0.40
            or float(doctrine_adjustments["execution_survivability_score"]) < 0.55
            or float(doctrine_adjustments["robustness_score"]) < 0.55
            or str(doctrine_adjustments["market_integrity_action"]) in {"degrade", "flatten_only"}
            or str(doctrine_adjustments["mastermind_execution_style"]) == "passive_limit"
        ):
            passive = True
            order_style = "limit"
            child_orders = 1 if str(doctrine_adjustments["doctrine_action"]) == "probe" else max(1, min(child_orders, 2))
        elif (
            not bool(doctrine_adjustments.get("calibration_conservative", False))
            and float(doctrine_adjustments["signal_decay_risk"]) >= 0.65
            and float(doctrine_adjustments["execution_survivability_score"]) >= 0.75
            and float(doctrine_adjustments["floor_compatibility_score"]) >= 0.80
        ):
            passive = False
            order_style = "marketable_limit"
            child_orders = 1
        max_participation_rate = self.settings.max_participation_rate
        if passive:
            max_participation_rate = min(
                max_participation_rate,
                max(
                    0.05,
                    self.settings.max_participation_rate
                    * max(
                        0.25,
                        1.0
                        - float(doctrine_adjustments["uncertainty_pressure"]) * 0.50
                        - float(doctrine_adjustments["partial_truth_penalty"]) * 0.35,
                    ),
                ),
            )
        return ExecutionPlan(
            symbol=intent.symbol,
            ts=datetime.now(timezone.utc),
            side=intent.side,
            target_notional=normalized_notional,
            order_style=order_style,
            passive=passive,
            child_orders=child_orders,
            slippage_budget_bps=max(self.settings.slippage_bps, spread_bps * 1.25),
            max_participation_rate=max_participation_rate,
            anti_chase_enabled=regime != "PANIC" or passive,
            reasons={
                "fill_probability": forecast.fill_probability,
                "expected_fill_speed_ms": forecast.expected_fill_speed_ms,
                "expected_price_quality_bps": forecast.expected_price_quality_bps,
                "venue_constraints": constraints.__dict__,
                "constraint_adjustment": constraint_meta,
                "notional_breakdown": {
                    "policy_requested_notional": policy_requested_notional,
                    "constraint_normalized_notional": constraint_notional,
                    "doctrine_scaled_notional": doctrine_scaled_notional,
                    "proof_override_notional": submitted_target_notional if bool(proof_payload.get("enabled", False)) else 0.0,
                    "submitted_target_notional": normalized_notional,
                },
                "decision_doctrine": self._doctrine_payload(intent),
                "execution_simulation": self._execution_simulation_payload(intent),
                "market_integrity": self._market_integrity_payload(intent),
                "mastermind": self._mastermind_payload(intent),
                "global_execution_adjustments": doctrine_adjustments,
            },
            reduce_only=reduce_only,
        )

    def build_exit_plan(
        self,
        intent: OrderIntent,
        *,
        depth_notional: float,
        spread_bps: float,
        regime: str,
        liquidity_regime: str,
        execution_style: str = "passive_limit",
    ) -> ExecutionPlan:
        plan = self.build_execution_plan(
            intent,
            depth_notional=depth_notional,
            spread_bps=spread_bps,
            regime=regime,
            liquidity_regime=liquidity_regime,
            reduce_only=True,
        )
        constraints = self.venue_constraints(intent.symbol)
        normalized_notional, constraint_meta = self.constraints.normalize_target_notional(
            target_notional=float(intent.target_notional),
            constraints=constraints,
            reduce_only=True,
        )
        doctrine_adjustments = self._global_execution_adjustments(intent, reduce_only=True)
        order_style = execution_style
        if execution_style not in {"passive_limit", "marketable_limit", "limit"}:
            order_style = "passive_limit"
        if str(doctrine_adjustments["preferred_exit_style"]) == "marketable_limit":
            order_style = "marketable_limit"
        return ExecutionPlan(
            symbol=plan.symbol,
            ts=plan.ts,
            side=plan.side,
            target_notional=normalized_notional,
            order_style=order_style,
            passive=order_style == "passive_limit",
            child_orders=1 if order_style == "marketable_limit" else max(1, min(plan.child_orders, 2)),
            slippage_budget_bps=max(plan.slippage_budget_bps, spread_bps),
            max_participation_rate=plan.max_participation_rate,
            anti_chase_enabled=plan.anti_chase_enabled,
            reasons={
                **plan.reasons,
                "exit_plan": True,
                "venue_constraints": constraints.__dict__,
                "constraint_adjustment": constraint_meta,
                "global_execution_adjustments": doctrine_adjustments,
            },
            reduce_only=True,
        )

    def execute_paper(
        self,
        order_id: str,
        intent: OrderIntent,
        mid_price: float,
        depth_notional: float,
        oi_spike_pct: float,
        liquidations: float,
        funding_rate: float,
        spread_bps: float,
        regime: str,
        liquidity_regime: str,
    ) -> list[Fill]:
        if anti_toxic_block(oi_spike_pct, liquidations, funding_rate, spread_bps):
            return []

        slices = slice_notional(intent.target_notional, self.settings.slicing_parts, self.settings.max_participation_rate, depth_notional)
        fills = []
        for i, sl in enumerate(slices):
            partial = max(0.0, min(1.0, self.settings.partial_fill_ratio))
            maker_ok = self.settings.maker_preference and regime != "PANIC" and liquidity_regime == "GOOD" and spread_bps <= 15
            if maker_ok:
                # Deterministic maker queue realism: some slices timeout and fallback.
                timeout_score = sha256(f"{order_id}:{i}:{intent.symbol}:{regime}:{liquidity_regime}".encode()).digest()[0] / 255.0
                maker_fill_prob = max(0.1, min(0.95, 0.75 - (spread_bps / 200.0)))
                if timeout_score <= maker_fill_prob:
                    fill_mode = "maker"
                    fee_bps = self.settings.fee_bps * 0.6
                    slippage_bps = self.settings.slippage_bps * 0.5
                    latency_ms = 120 + i * 20
                elif self._paper_taker_fallback_allowed(intent):
                    fill_mode = "taker_timeout"
                    fee_bps = self.settings.fee_bps
                    slippage_bps = self.settings.slippage_bps * 1.5
                    latency_ms = 1000 + int(self.settings.maker_timeout_s * 1000) + i * 20
                else:
                    continue
            else:
                fill_mode = "taker_timeout"
                fee_bps = self.settings.fee_bps
                slippage_bps = self.settings.slippage_bps * 1.5
                latency_ms = 100 + i * 20

            filled_notional = sl * partial
            fee = filled_notional * (fee_bps / 10000)
            spread_slip = filled_notional * (slippage_bps / 10000)
            fill_id = sha256(f"{order_id}:{i}:{filled_notional}:{fill_mode}".encode()).hexdigest()[:16]
            dedupe_key = ("paper", order_id, fill_id)
            if dedupe_key in self.fill_seen:
                continue
            self.fill_seen.add(dedupe_key)
            fills.append(
                Fill(
                    venue="paper",
                    order_id=order_id,
                    fill_id=fill_id,
                    symbol=intent.symbol,
                    side=intent.side,
                    notional=filled_notional,
                    fee=fee,
                    slippage_cost=spread_slip,
                    latency_ms=latency_ms,
                    status=f"filled_partial_{fill_mode}" if partial < 1.0 else f"filled_{fill_mode}",
                )
            )
        return fills

    def execute_live(self, intent: OrderIntent):
        mode = ExecutionMode(self.settings.mode)
        if self.live_service is None:
            raise RuntimeError("live_service_not_configured")
        if mode == ExecutionMode.LIVE_READONLY:
            return self.live_service.execute_readonly(intent)
        if mode in {ExecutionMode.LIVE_TESTNET, ExecutionMode.LIVE}:
            return self.live_service.execute_intent(intent)
        raise RuntimeError("execute_live_called_in_paper_mode")

    def flatten_worst_case(self, symbol: str, exposure_notional: float) -> Fill:
        fee = abs(exposure_notional) * (self.settings.fee_bps / 10000)
        slippage = abs(exposure_notional) * max(self.settings.slippage_bps, 40) / 10000
        return Fill("paper", "flatten-order", "flatten-fill", symbol, "sell" if exposure_notional > 0 else "buy", abs(exposure_notional), fee, slippage, 250, "flattened")
