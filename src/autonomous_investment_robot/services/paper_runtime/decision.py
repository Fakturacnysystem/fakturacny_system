from __future__ import annotations

from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Any, Callable

from autonomous_investment_robot.core.contracts import LearningRecord, TradeForensicsContext
from autonomous_investment_robot.services.oms.service import ManagedOrder
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.paper_runtime.metrics import MetricsCoordinator
from autonomous_investment_robot.services.replay.events import FillEvent, OrderEvent, OrderIntentEvent, RiskEvent, make_event, make_idempotency_key


@dataclass
class PaperDecisionState:
    equity: float
    peak: float
    exposure: float
    funding_paid_pct: float
    strategy_perf: dict[str, float]
    fills_all: list[Any]
    plans: list[dict[str, Any]]
    trade_log: list[dict[str, Any]]


class PaperDecisionCoordinator:
    def __init__(
        self,
        *,
        settings: Any,
        qa: Any,
        features: Any,
        event_store: Any,
        alpha: Any,
        models: Any,
        regime_service: Any,
        policy: Any,
        risk: Any,
        execution: Any,
        oms: Any,
        portfolio: Any,
        inventory: Any | None,
        profitability: Any | None,
        learning: Any,
        forensics: Any,
        observability: Any,
        ops: Any,
        reporting: Any | None,
        quantum_state_service: Any | None,
        edge_immunity_service: Any | None,
        event_intelligence_service: Any | None,
        synthetic_affect_service: Any | None,
        capital_sovereignty_service: Any | None,
        position_morphing_service: Any | None,
        adaptive_exit_allocator: Any | None,
        execution_simulation_sandbox: Any | None,
        human_escalation_layer: Any | None,
        mastermind_service: Any | None,
        metrics: MetricsCoordinator,
        legacy_risk_details: Callable[[dict[str, Any]], dict[str, Any]],
        legacy_fill_payload: Callable[[Any], dict[str, Any]],
    ) -> None:
        self.settings = settings
        self.qa = qa
        self.features = features
        self.event_store = event_store
        self.alpha = alpha
        self.models = models
        self.regime_service = regime_service
        self.policy = policy
        self.risk = risk
        self.execution = execution
        self.oms = oms
        self.portfolio = portfolio
        self.inventory = inventory
        self.profitability = profitability
        self.learning = learning
        self.forensics = forensics
        self.observability = observability
        self.ops = ops
        self.reporting = reporting
        self.quantum_state_service = quantum_state_service
        self.edge_immunity_service = edge_immunity_service
        self.event_intelligence_service = event_intelligence_service
        self.synthetic_affect_service = synthetic_affect_service
        self.capital_sovereignty_service = capital_sovereignty_service
        self.position_morphing_service = position_morphing_service
        self.adaptive_exit_allocator = adaptive_exit_allocator
        self.execution_simulation_sandbox = execution_simulation_sandbox
        self.human_escalation_layer = human_escalation_layer
        self.mastermind_service = mastermind_service
        self.metrics = metrics
        self.legacy_risk_details = legacy_risk_details
        self.legacy_fill_payload = legacy_fill_payload

    def _route(self, route_name: str, channel: str, payload: Any) -> None:
        route = getattr(self.observability, route_name, None)
        if callable(route):
            route(payload)
        else:
            self.observability.journal(channel, payload)

    def _route_truth_evidence(self, channel: str, payload: Any) -> None:
        route = getattr(self.observability, "route_truth_evidence", None)
        if callable(route):
            route(channel, payload)
        else:
            self.observability.journal(channel, payload)

    def _route_event_intelligence(self, *, symbol: str, ts: Any, report: Any) -> None:
        self.observability.journal("event_intelligence_journal", report)
        self._route_truth_evidence("source_trust_journal", {"symbol": symbol, "ts": ts, **asdict(getattr(report, "source_trust"))})
        self._route_truth_evidence("freshness_novelty_journal", {"symbol": symbol, "ts": ts, **asdict(getattr(report, "freshness_novelty"))})
        self._route_truth_evidence("asset_relevance_journal", {"symbol": symbol, "ts": ts, **asdict(getattr(report, "asset_relevance"))})
        self._route_truth_evidence("market_impact_journal", {"symbol": symbol, "ts": ts, **asdict(getattr(report, "market_impact"))})
        self._route_truth_evidence("priced_in_journal", {"symbol": symbol, "ts": ts, **asdict(getattr(report, "priced_in"))})
        self._route_truth_evidence("adversarial_narrative_journal", {"symbol": symbol, "ts": ts, **asdict(getattr(report, "adversarial"))})
        self._route_truth_evidence("data_provenance_journal", {"symbol": symbol, "ts": ts, **asdict(getattr(report, "provenance"))})

    def _journal_signal_context(
        self,
        *,
        symbol: str,
        ts: Any,
        forecast: Any,
        regime_assessment: Any,
        alpha_signals: list[Any],
        portfolio_allocation: Any,
        mastermind_advisory: Any | None = None,
    ) -> None:
        self.observability.journal(
            "signal_journal",
            {
                "symbol": symbol,
                "ts": ts,
                "forecast": asdict(forecast),
                "regime": asdict(regime_assessment),
                "alpha_experts": [asdict(sig) for sig in alpha_signals],
                "portfolio_allocation": asdict(portfolio_allocation),
                "mastermind": None
                if mastermind_advisory is None
                else {
                    "provider": getattr(mastermind_advisory, "provider", ""),
                    "signal": getattr(mastermind_advisory, "signal", ""),
                    "confidence": getattr(mastermind_advisory, "confidence", 0.0),
                    "reason": getattr(mastermind_advisory, "reason", ""),
                    "decision": getattr(mastermind_advisory, "decision", "CONTINUE"),
                    "risk_level": getattr(mastermind_advisory, "risk_level", 0.0),
                    "veto": getattr(mastermind_advisory, "veto", False),
                    "size_multiplier": getattr(mastermind_advisory, "size_multiplier", 1.0),
                    "execution_style_bias": getattr(mastermind_advisory, "execution_style_bias", "unchanged"),
                    "reasons": list(getattr(mastermind_advisory, "reasons", []) or []),
                },
            },
        )

    def _journal_policy_context(
        self,
        *,
        symbol: str,
        ts: Any,
        intent: Any,
        regime_assessment: Any,
        execution_quality: Any,
        portfolio_allocation: Any,
    ) -> None:
        self.observability.journal(
            "policy_journal",
            {
                "symbol": symbol,
                "ts": ts,
                "trade_allowed": intent is not None,
                "side": None if intent is None else intent.side,
                "target_notional": 0.0 if intent is None else intent.target_notional,
                "why": None if intent is None else intent.why,
                "no_trade_reason": None if intent is not None else (self.policy.last_veto_reasons[0] if self.policy.last_veto_reasons else "no_intent"),
                "regime_assessment": asdict(regime_assessment),
                "execution_quality": asdict(execution_quality),
                "portfolio_allocation": asdict(portfolio_allocation),
            },
        )

    def _initialize_state(self) -> PaperDecisionState:
        return PaperDecisionState(
            equity=1.0,
            peak=1.0,
            exposure=0.0,
            funding_paid_pct=0.0,
            strategy_perf={s.name: 0.0 for s in self.policy.strategies},
            fills_all=[],
            plans=[],
            trade_log=[],
        )

    def run(self, *, symbol: str, bars: list[Any], fvs: list[Any]) -> PaperDecisionState:
        state = self._initialize_state()
        for i in range(1, len(fvs)):
            fv = fvs[i - 1]
            bar = bars[i]
            prev_bar = bars[i - 1]
            self.features.assert_no_leakage(fv.ts, bar.ts)
            profitability_context: dict[str, Any] = {}
            capital_release_context: dict[str, Any] = {}
            inventory_state = None
            reserve_state = None

            if self._handle_divergence(symbol=symbol, bar=bar, state=state):
                break

            fc = self.models.forecast(fv)
            regime_assessment = self.regime_service.assess(symbol, fv.ts, fv.values, fc)
            preview_intent = OrderIntent(symbol=symbol, side="buy" if fc.mu >= 0 else "sell", target_notional=self.settings.policy.base_risk_budget, why={})
            execution_quality = self.execution.forecast_execution_quality(
                preview_intent,
                depth_notional=bar.depth_notional,
                spread_bps=bar.spread_bps,
                regime=fc.regime,
                liquidity_regime=fc.liquidity_regime,
            )
            alpha_signals = self.alpha.evaluate(symbol, fv.ts, fv.values, fc, regime_assessment, execution_quality)
            portfolio_allocation = self.portfolio.recommend_allocation(
                symbol=symbol,
                ts=fv.ts,
                base_budget=self.settings.policy.base_risk_budget,
                expected_edge_bps=max(abs(fc.mu) * 10000.0, 0.0),
                confidence=fc.confidence,
                uncertainty=max(0.0, 1.0 - fc.confidence),
                realized_vol=fv.values.get("realized_vol", 0.0),
                depth_notional=bar.depth_notional,
                current_exposure=abs(state.exposure),
                drawdown_pct=(state.equity / state.peak - 1) * 100,
                regime_fit=max(0.0, min(1.0, regime_assessment.confidence * regime_assessment.persistence)),
            )
            self._journal_signal_context(
                symbol=symbol,
                ts=fv.ts,
                forecast=fc,
                regime_assessment=regime_assessment,
                alpha_signals=alpha_signals,
                portfolio_allocation=portfolio_allocation,
            )

            quantum_state = None
            edge_immunity_decision = None
            event_intelligence_report = None
            synthetic_affect_state = None
            capital_sovereignty_decision = None
            position_morph_plan = None
            adaptive_exit_allocation = None
            execution_simulation_report = None
            human_escalation_decision = None
            mastermind_advisory = None
            if self.quantum_state_service is not None:
                quantum_state = self.quantum_state_service.evaluate(
                    symbol=symbol,
                    ts=fv.ts,
                    features=fv.values,
                    forecast=fc,
                    regime_assessment=regime_assessment,
                    alpha_signals=alpha_signals,
                    execution_quality=execution_quality,
                    portfolio_allocation=portfolio_allocation,
                )
                self.observability.journal("quantum_state_journal", quantum_state)
            if self.edge_immunity_service is not None and quantum_state is not None:
                edge_immunity_decision = self.edge_immunity_service.evaluate(
                    symbol=symbol,
                    ts=fv.ts,
                    features=fv.values,
                    forecast=fc,
                    regime_assessment=regime_assessment,
                    execution_quality=execution_quality,
                    portfolio_allocation=portfolio_allocation,
                    quantum_state=quantum_state,
                )
                self.observability.journal("edge_immunity_journal", edge_immunity_decision)
            if self.event_intelligence_service is not None:
                event_intelligence_report = self.event_intelligence_service.evaluate(
                    symbol=symbol,
                    ts=fv.ts,
                    features=fv.values,
                    forecast=fc,
                    events=[],
                )
                self._route_event_intelligence(symbol=symbol, ts=fv.ts, report=event_intelligence_report)
            if self.mastermind_service is not None:
                mastermind_advisory = self.mastermind_service.advise(
                    symbol,
                    fv.values,
                    fc.regime,
                    forecast=fc,
                    regime_assessment=regime_assessment,
                    execution_quality=execution_quality,
                    portfolio_allocation=portfolio_allocation,
                    event_intelligence_report=event_intelligence_report,
                    quantum_state=quantum_state,
                    edge_immunity_decision=edge_immunity_decision,
                )
                if mastermind_advisory is not None:
                    route = getattr(self.observability, "route_mastermind", None)
                    payload = {
                        "symbol": symbol,
                        "ts": fv.ts,
                        "provider": mastermind_advisory.provider,
                        "signal": mastermind_advisory.signal,
                        "confidence": mastermind_advisory.confidence,
                        "reason": mastermind_advisory.reason,
                        "decision": mastermind_advisory.decision,
                        "risk_level": mastermind_advisory.risk_level,
                        "veto": mastermind_advisory.veto,
                        "size_multiplier": mastermind_advisory.size_multiplier,
                        "execution_style_bias": mastermind_advisory.execution_style_bias,
                        "reasons": list(mastermind_advisory.reasons),
                        "heuristic": mastermind_advisory.heuristic,
                        "raw": dict(mastermind_advisory.raw),
                    }
                    if callable(route):
                        route(payload)
                    else:
                        self.observability.journal("mastermind_journal", payload)
            policy_snapshot = {
                "last_veto_reasons": list(getattr(self.policy, "last_veto_reasons", [])),
                "last_veto_counts": dict(getattr(self.policy, "last_veto_counts", {})),
                "strategy_regime_cooldowns": getattr(self.policy, "strategy_regime_cooldowns", {}).copy(),
                "strategy_regime_veto_streaks": getattr(self.policy, "strategy_regime_veto_streaks", {}).copy(),
            }
            evidence_decision = self.policy.evaluate_decision(
                fc,
                fv.values,
                self.settings.execution.fee_bps,
                self.settings.execution.slippage_bps,
                regime_assessment=regime_assessment,
                execution_quality=execution_quality,
                portfolio_allocation=portfolio_allocation,
                quantum_state=quantum_state,
                edge_immunity_decision=edge_immunity_decision,
                event_intelligence_report=event_intelligence_report,
                mastermind_advisory=mastermind_advisory,
            )
            self.policy.last_veto_reasons = policy_snapshot["last_veto_reasons"]
            self.policy.last_veto_counts = policy_snapshot["last_veto_counts"]
            self.policy.strategy_regime_cooldowns = policy_snapshot["strategy_regime_cooldowns"]
            self.policy.strategy_regime_veto_streaks = policy_snapshot["strategy_regime_veto_streaks"]
            spre_payload = evidence_decision.why.get("spre") if isinstance(evidence_decision.why, dict) else None
            if spre_payload is not None:
                self._route("route_spre", "spre_journal", {"symbol": symbol, "ts": fv.ts, **dict(spre_payload)})
            shadow_payload = evidence_decision.why.get("shadow_rival") if isinstance(evidence_decision.why, dict) else None
            if shadow_payload is not None:
                self._route("route_shadow", "shadow_rival_journal", {"symbol": symbol, "ts": fv.ts, **dict(shadow_payload)})
            doctrine_payload = evidence_decision.why.get("decision_doctrine") if isinstance(evidence_decision.why, dict) else None
            if doctrine_payload is not None:
                self._route("route_decision_doctrine", "decision_doctrine_journal", {"symbol": symbol, "ts": fv.ts, **dict(doctrine_payload)})
                if self.reporting is not None:
                    self.reporting.report_decision_doctrine(
                        symbol=symbol,
                        decision_doctrine=doctrine_payload,
                        truth_context=evidence_decision.why.get("truth_context"),
                        market_integrity=evidence_decision.why.get("market_integrity"),
                        provider_capability=evidence_decision.why.get("provider_capability"),
                    )

            intent = self.policy.make_intent(fc, fv.values, self.settings.execution.fee_bps, self.settings.execution.slippage_bps)
            if self.profitability is not None and self.inventory is not None and intent is not None:
                reserve_state = self.inventory.reserve_state(
                    ts=fv.ts,
                    exchange_balance=max(self.settings.policy.base_risk_budget * state.equity, 0.0),
                    local_cash_delta=0.0,
                    gross_exposure_notional=abs(state.exposure),
                    minimum_reserve_pct=float(self.settings.policy.min_free_quote_reserve_pct),
                    capital_floor=float(self.settings.policy.base_risk_budget),
                )
                inventory_state = self.inventory.inventory_pressure(
                    symbol=symbol,
                    ts=fv.ts,
                    opportunity_cost_score=float(portfolio_allocation.opportunity_cost_score),
                    unrealized_pnl=0.0,
                    execution_fragility=float(execution_quality.adverse_selection_risk),
                )
                floor, release, round_trip = self.profitability.evaluate_open(
                    symbol=symbol,
                    ts=fv.ts,
                    target_notional=float(intent.target_notional),
                    expected_edge_bps=max(abs(fc.mu) * 10000.0, 0.0),
                    fee_bps=float(self.settings.execution.fee_bps),
                    slippage_bps=float(self.settings.execution.slippage_bps),
                    spread_bps=float(bar.spread_bps),
                    depth_notional=float(bar.depth_notional),
                    execution_quality=execution_quality,
                    inventory_state=inventory_state,
                    reserve_state=reserve_state,
                )
                profitability_context = {
                    "profit_floor": asdict(floor),
                    "capital_release": asdict(release),
                    "round_trip": asdict(round_trip),
                }
                capital_release_context = asdict(release)
                self.observability.journal("profitability_journal", profitability_context)
                if self.reporting is not None:
                    self.reporting.report_profitability(
                        symbol=symbol,
                        profitability=profitability_context,
                        reserve_state=reserve_state,
                        inventory_state=inventory_state,
                    )
            if self.synthetic_affect_service is not None:
                synthetic_affect_state = self.synthetic_affect_service.evaluate(
                    symbol=symbol,
                    ts=fv.ts,
                    forecast=fc,
                    regime_assessment=regime_assessment,
                    execution_quality=execution_quality,
                    inventory_state=inventory_state,
                    reserve_state=reserve_state,
                    quantum_state=quantum_state,
                    edge_immunity_decision=edge_immunity_decision,
                    event_intelligence=event_intelligence_report,
                )
                self.observability.journal("synthetic_affect_journal", synthetic_affect_state)
            if self.capital_sovereignty_service is not None:
                capital_sovereignty_decision = self.capital_sovereignty_service.evaluate(
                    symbol=symbol,
                    ts=fv.ts,
                    reserve_state=reserve_state,
                    inventory_state=inventory_state,
                    portfolio_allocation=portfolio_allocation,
                    round_trip=profitability_context.get("round_trip") if profitability_context else None,
                    event_intelligence=event_intelligence_report,
                    synthetic_affect=synthetic_affect_state,
                    quantum_state=quantum_state,
                    edge_immunity_decision=edge_immunity_decision,
                )
                self.observability.journal("capital_sovereignty_journal", capital_sovereignty_decision)
            if self.position_morphing_service is not None and capital_sovereignty_decision is not None:
                position_morph_plan = self.position_morphing_service.evaluate(
                    symbol=symbol,
                    ts=fv.ts,
                    current_exposure=abs(state.exposure),
                    capital_sovereignty=capital_sovereignty_decision,
                    synthetic_affect=synthetic_affect_state,
                    quantum_state=quantum_state,
                    edge_immunity_decision=edge_immunity_decision,
                )
                self.observability.journal("position_morphing_journal", position_morph_plan)
            if self.adaptive_exit_allocator is not None and abs(state.exposure) > 1e-9:
                capital_release_payload = capital_release_context or None
                adaptive_exit_allocation = self.adaptive_exit_allocator.evaluate(
                    symbol=symbol,
                    ts=fv.ts,
                    current_exposure=abs(state.exposure),
                    capital_release_decision=SimpleNamespace(
                        allowed=bool(capital_release_payload.get("allowed", False)),
                        recommended_notional=float(capital_release_payload.get("recommended_notional", 0.0) or 0.0),
                        reason=str(capital_release_payload.get("reason", "")),
                    )
                    if capital_release_payload is not None
                    else None,
                    position_morph_plan=position_morph_plan,
                    synthetic_affect=synthetic_affect_state,
                    event_intelligence=event_intelligence_report,
                )
                self.observability.journal("adaptive_exit_journal", adaptive_exit_allocation)
            if self.execution_simulation_sandbox is not None:
                simulation_probe = intent or OrderIntent(symbol=symbol, side="buy", target_notional=self.settings.policy.base_risk_budget, why={})
                execution_simulation_report = self.execution_simulation_sandbox.simulate(
                    symbol=symbol,
                    ts=fv.ts,
                    intent=simulation_probe,
                    snapshot=SimpleNamespace(spread_bps=bar.spread_bps, depth_notional=bar.depth_notional),
                    execution_quality=execution_quality,
                    expected_edge_bps=max(abs(fc.mu) * 10000.0, 0.0),
                    market_integrity=None,
                    venue_limit_decision=None,
                    synthetic_affect=synthetic_affect_state,
                )
                self._route("route_execution_simulation", "execution_simulation_journal", execution_simulation_report)
            if self.human_escalation_layer is not None:
                human_escalation_decision = self.human_escalation_layer.evaluate(
                    symbol=symbol,
                    ts=fv.ts,
                    quantum_state=quantum_state,
                    edge_immunity_decision=edge_immunity_decision,
                    event_intelligence=event_intelligence_report,
                    synthetic_affect=synthetic_affect_state,
                    capital_sovereignty=capital_sovereignty_decision,
                    execution_simulation=execution_simulation_report,
                )
                self._route("route_escalation", "human_escalation_journal", human_escalation_decision)
            if self.reporting is not None:
                self.reporting.report_capital_strategy(
                    symbol=symbol,
                    event_intelligence=event_intelligence_report,
                    synthetic_affect=synthetic_affect_state,
                    capital_sovereignty=capital_sovereignty_decision,
                    position_morph=position_morph_plan,
                    adaptive_exit=adaptive_exit_allocation,
                )
                if mastermind_advisory is not None:
                    self.reporting.report_mastermind(symbol=symbol, mastermind=mastermind_advisory)

            self._journal_policy_context(
                symbol=symbol,
                ts=fv.ts,
                intent=intent,
                regime_assessment=regime_assessment,
                execution_quality=execution_quality,
                portfolio_allocation=portfolio_allocation,
            )
            if intent is None:
                self.ops_inc_rejects()
                if self.policy.last_veto_reasons:
                    self.ops.inc_metric("veto_tco_total", float(len(self.policy.last_veto_reasons)))
                    for reason, count in self.policy.last_veto_counts.items():
                        self.ops.inc_metric(f"veto_{reason}_total", float(count))
                continue

            oi_prev = max(1.0, prev_bar.oi)
            oi_spike = (bar.oi - oi_prev) / oi_prev * 100
            divergence_bps = abs(bar.mark_price - bar.secondary_price) / max(bar.mark_price, 1e-9) * 10000
            margin_buffer = 2.5

            decision = self.risk.evaluate(
                intent,
                current_exposure=abs(state.exposure),
                drawdown_pct=(state.equity / state.peak - 1) * 100,
                daily_loss_pct=min(0.0, (state.equity - 1.0) * 100),
                data_lag_seconds=0.0,
                spread_bps=bar.spread_bps,
                depth_notional=bar.depth_notional,
                reconciliation_ok=True,
                funding_paid_pct=state.funding_paid_pct,
                oi_spike_pct=oi_spike,
                liquidation_spike=bar.liquidations,
                divergence_bps=divergence_bps,
                margin_buffer=margin_buffer,
                funding_rate_abs=abs(bar.funding_rate),
                market_regime=fc.regime,
                liquidity_regime=fc.liquidity_regime,
                abnormal_latency_ms=float(execution_quality.expected_fill_speed_ms),
            )
            self.metrics.update_risk_metrics(decision=decision, oi_spike=oi_spike, liquidations=bar.liquidations)
            if not decision.allowed:
                self.event_store.append("risk", make_event(RiskEvent, "RISK_REJECT", symbol, "paper", self.event_store.next_seq("risk"), {"reason": decision.reason}))
                self.ops_inc_rejects()
                if decision.flatten:
                    state.fills_all.append(self.execution.flatten_worst_case(symbol, state.exposure))
                    state.exposure = 0.0
                    break
                continue

            adjusted_why = dict(intent.why)
            adjusted_why["risk"] = {"decision_reason": decision.reason, **self.legacy_risk_details(decision.details)}
            adjusted = OrderIntent(intent.symbol, intent.side, decision.adjusted_notional, adjusted_why)
            plan = self.execution.build_execution_plan(
                adjusted,
                depth_notional=bar.depth_notional,
                spread_bps=bar.spread_bps,
                regime=fc.regime,
                liquidity_regime=fc.liquidity_regime,
            )
            if plan.target_notional <= 0.0:
                self.event_store.append(
                    "risk",
                    make_event(
                        RiskEvent,
                        "VENUE_CONSTRAINTS_BLOCK",
                        symbol,
                        "paper",
                        self.event_store.next_seq("risk"),
                        {"order_id": f"ord-{i}", "reasons": plan.reasons.get("constraint_adjustment", {})},
                    ),
                )
                self.ops_inc_rejects()
                continue
            self.observability.journal("execution_journal", {"plan": asdict(plan), "forecast": asdict(execution_quality)})
            idem = make_idempotency_key(asdict(adjusted), "perps-intraday", i)
            order_id = f"ord-{i}"
            self.event_store.append("orders", make_event(OrderIntentEvent, "ORDER_INTENT", symbol, "paper", self.event_store.next_seq("orders"), asdict(adjusted), idempotency_key=idem))
            ok_submit, _ = self.oms.submit_intent(ManagedOrder(order_id=order_id, symbol=symbol, side=adjusted.side, notional=adjusted.target_notional, idempotency_key=idem))
            if not ok_submit:
                self.ops_inc_rejects()
                continue
            self.oms.transition(order_id, "ACK")
            self.event_store.append("orders", make_event(OrderEvent, "ORDER_ACK", symbol, "paper", self.event_store.next_seq("orders"), {"order_id": order_id}, idempotency_key=idem))

            fills = self.execution.execute_paper(order_id, adjusted, bar.mark_price, bar.depth_notional, oi_spike, bar.liquidations, bar.funding_rate, bar.spread_bps, fc.regime, fc.liquidity_regime)
            if not fills:
                self.ops_inc_rejects()
                continue

            accepted_fills = []
            for fill in fills:
                ok_fill, fill_reason = self.oms.apply_fill(order_id, fill.notional, fill.fill_id)
                if not ok_fill:
                    self.ops_inc_rejects()
                    self.event_store.append(
                        "risk",
                        make_event(
                            RiskEvent,
                            "FILL_REJECT",
                            symbol,
                            "paper",
                            self.event_store.next_seq("risk"),
                            {"order_id": order_id, "fill_id": fill.fill_id, "reason": fill_reason},
                        ),
                    )
                    continue
                self.event_store.append("fills", make_event(FillEvent, "FILL", symbol, "paper", self.event_store.next_seq("fills"), self.legacy_fill_payload(fill), idempotency_key=fill.fill_id))
                state.fills_all.append(fill)
                accepted_fills.append(fill)

            if not accepted_fills:
                continue

            fill_notional = sum(f.notional for f in accepted_fills)
            fees = sum(f.fee + f.slippage_cost for f in accepted_fills)
            state.funding_paid_pct += abs(bar.funding_rate) * 100
            side = 1 if adjusted.side == "buy" else -1
            ret = side * (bar.mark_price / prev_bar.mark_price - 1)
            pnl = fill_notional * ret - fees - abs(bar.funding_rate) * fill_notional
            state.equity += pnl / max(self.settings.policy.base_risk_budget, 1.0)
            state.peak = max(state.peak, state.equity)
            state.exposure += fill_notional if adjusted.side == "buy" else -fill_notional
            self.risk.record_return((pnl / max(fill_notional, 1.0)) * 100)
            self._record_fills(
                accepted_fills=accepted_fills,
                state=state,
                bar=bar,
                fill_notional=fill_notional,
                pnl=pnl,
            )
            state.plans.append({"order_id": order_id, **asdict(adjusted)})
            state.trade_log.append({"order_id": order_id, "side": adjusted.side, "notional": fill_notional, "pnl": pnl, "why": adjusted.why})
            self.learning.record(
                LearningRecord(
                    symbol=symbol,
                    ts=bar.ts,
                    regime_label=regime_assessment.label,
                    confidence=fc.confidence,
                    uncertainty=max(0.0, 1.0 - fc.confidence),
                    intended_notional=adjusted.target_notional,
                    filled_notional=fill_notional,
                    expected_edge_bps=max(abs(fc.mu) * 10000.0, 0.0),
                    realized_pnl=pnl,
                    hold_seconds=0.0,
                    exit_reason="bar_close_mark_to_market",
                    metadata={
                        "order_id": order_id,
                        "risk_reason": decision.reason,
                        "execution_plan": asdict(plan),
                    },
                )
            )
            self.forensics.analyze_trade(
                context=TradeForensicsContext(
                    symbol=symbol,
                    ts=bar.ts,
                    venue="paper",
                    order_id=order_id,
                    side=adjusted.side,
                    regime_label=regime_assessment.label,
                    policy_confidence=fc.confidence,
                    policy_uncertainty=max(0.0, 1.0 - fc.confidence),
                    expected_edge_bps=max(abs(fc.mu) * 10000.0, 0.0),
                    unrealized_truth_source="paper_mark_to_market",
                    inventory_age=0.0 if inventory_state is None else float(inventory_state.weighted_age_seconds),
                    profitability_context=profitability_context,
                    capital_release_context=capital_release_context,
                    quantum_context={}
                    if quantum_state is None
                    else {
                        "dominant_state": quantum_state.scenario_tree.dominant_state,
                        "no_trade_probability": quantum_state.collapse_decision.no_trade_probability,
                        "execution_fragility_score": quantum_state.collapse_decision.execution_fragility_score,
                        "branch_disagreement_score": quantum_state.collapse_decision.branch_disagreement_score,
                        "scenario_drift_score": quantum_state.collapse_decision.scenario_drift_score,
                    },
                    edge_immunity_context={}
                    if edge_immunity_decision is None
                    else {
                        "action": edge_immunity_decision.action,
                        "reason": edge_immunity_decision.reason,
                        "fragility_index": edge_immunity_decision.report.fragility_index,
                        "wait_value_score": edge_immunity_decision.report.wait_value_score,
                    },
                    metadata={
                        "exit_reason": "bar_close_mark_to_market",
                        "risk_reason": decision.reason,
                        "hold_seconds": 0.0,
                        "event_intelligence": {}
                        if event_intelligence_report is None
                        else asdict(event_intelligence_report),
                        "synthetic_affect": {}
                        if synthetic_affect_state is None
                        else asdict(synthetic_affect_state),
                        "capital_sovereignty": {}
                        if capital_sovereignty_decision is None
                        else asdict(capital_sovereignty_decision),
                        "position_morph": {}
                        if position_morph_plan is None
                        else asdict(position_morph_plan),
                        "adaptive_exit": {}
                        if adaptive_exit_allocation is None
                        else asdict(adaptive_exit_allocation),
                        "execution_simulation": {}
                        if execution_simulation_report is None
                        else asdict(execution_simulation_report),
                        "decision_doctrine": {}
                        if not isinstance(evidence_decision.why, dict)
                        else dict(evidence_decision.why.get("decision_doctrine", {}) or {}),
                        "human_escalation": {}
                        if human_escalation_decision is None
                        else asdict(human_escalation_decision),
                        "mastermind": {}
                        if mastermind_advisory is None
                        else {
                            "provider": mastermind_advisory.provider,
                            "signal": mastermind_advisory.signal,
                            "confidence": mastermind_advisory.confidence,
                            "reason": mastermind_advisory.reason,
                            "decision": mastermind_advisory.decision,
                            "risk_level": mastermind_advisory.risk_level,
                            "veto": mastermind_advisory.veto,
                            "size_multiplier": mastermind_advisory.size_multiplier,
                            "execution_style_bias": mastermind_advisory.execution_style_bias,
                            "reasons": list(mastermind_advisory.reasons),
                        },
                    },
                ),
                fills=accepted_fills,
                filled_notional=fill_notional,
                realized_pnl=pnl,
                execution_plan=plan,
                execution_quality=execution_quality,
                additional_metadata={"portfolio_allocation": asdict(portfolio_allocation)},
            )
            self.ops_inc_submitted()
            state.strategy_perf = {k: v + pnl / 10000 for k, v in state.strategy_perf.items()}
            self.policy.update_allocator(state.strategy_perf)
        return state

    def _record_fills(self, *, accepted_fills: list[Any], state: PaperDecisionState, bar: Any, fill_notional: float, pnl: float) -> None:
        remaining = fill_notional
        for idx, fill in enumerate(accepted_fills):
            if idx == len(accepted_fills) - 1:
                pnl_share = pnl if remaining <= 0 else pnl * (fill.notional / max(fill_notional, 1.0))
            else:
                pnl_share = pnl * (fill.notional / max(fill_notional, 1.0))
            remaining -= fill.notional
            self.portfolio.record_fill(fill, realized_pnl=pnl_share, venue="paper")
            if self.inventory is not None:
                self.inventory.update_from_fill(fill, ts=bar.ts)

    def _handle_divergence(self, *, symbol: str, bar: Any, state: PaperDecisionState) -> bool:
        if not self.qa.divergence_breaker(bar, float(self.settings.risk.divergence_threshold_bps)):
            return False
        self.risk.state.kill_switch = True
        self.risk.state.safe_mode = True
        self.event_store.append("risk", make_event(RiskEvent, "DIVERGENCE_KILL", symbol, "paper", self.event_store.next_seq("risk"), {"divergence": True}))
        if abs(state.exposure) > 0:
            state.fills_all.append(self.execution.flatten_worst_case(symbol, state.exposure))
            state.exposure = 0.0
        return True

    def ops_inc_rejects(self) -> None:
        self.ops.inc_metric("orders_rejected_total")

    def ops_inc_submitted(self) -> None:
        self.ops.inc_metric("orders_submitted_total")
