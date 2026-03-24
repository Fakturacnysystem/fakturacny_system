from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
import time
from typing import Any

from autonomous_investment_robot.core.contracts import ExitIntent, MarketIntegrityEvidence
from autonomous_investment_robot.services.feature_store.service import FeatureVector
from autonomous_investment_robot.services.policy.service import OrderIntent


@dataclass(frozen=True)
class LiveMarketContext:
    now_dt: datetime
    book: dict[str, float]
    prices: list[float]
    snapshot: Any
    features: dict[str, float]
    market_health: Any
    forecast: Any
    regime_assessment: Any
    advisory: Any
    execution_quality: Any
    alpha_signals: list[Any]
    portfolio_allocation: Any
    market_stage_ms: float
    forecast_stage_ms: float
    quantum_stage_ms: float = 0.0
    edge_immunity_stage_ms: float = 0.0
    quantum_state: Any | None = None
    edge_immunity_decision: Any | None = None
    provider_capability: Any | None = None
    market_integrity: Any | None = None
    venue_limit_decision: Any | None = None
    event_intelligence_report: Any | None = None
    market_watch: Any | None = None


@dataclass(frozen=True)
class LiveDecisionContext:
    health_snapshot: Any
    meta_governor_decision: Any | None = None
    policy_decision: Any | None = None
    intent: OrderIntent | None = None
    risk_decision: Any | None = None
    adjusted_intent: OrderIntent | None = None
    execution_plan: Any | None = None
    reserve_state: Any | None = None
    inventory_state: Any | None = None
    profitability_context: Any | None = None
    exit_intent: Any | None = None
    synthetic_affect_state: Any | None = None
    capital_sovereignty_decision: Any | None = None
    position_morph_plan: Any | None = None
    adaptive_exit_allocation: Any | None = None
    execution_simulation_report: Any | None = None
    human_escalation_decision: Any | None = None
    health_stage_ms: float = 0.0
    risk_stage_ms: float = 0.0
    execution_stage_ms: float = 0.0


@dataclass(frozen=True)
class LiveBootState:
    confidence: str
    details: dict[str, Any]
    recovery_decision: Any


@dataclass(frozen=True)
class LiveReconciliationResult:
    ok: bool
    report: Any | None
    exposure_notional: float
    elapsed_ms: float


@dataclass(frozen=True)
class LiveControlResult:
    exposure_notional: float
    stop_result: dict[str, Any] | None = None
    continue_loop: bool = False


class LiveMarketCoordinator:
    def __init__(
        self,
        *,
        features_service: Any,
        market_data: Any,
        models: Any,
        regime_service: Any,
        mastermind: Any,
        execution: Any,
        alpha: Any,
        portfolio: Any,
        quantum_state_service: Any,
        edge_immunity_service: Any,
        observability: Any,
        settings: Any,
        ops: Any,
        market_integrity_service: Any | None = None,
        venue_capability_registry: Any | None = None,
        shared_venue_limit_governor: Any | None = None,
        event_intelligence_service: Any | None = None,
        market_watch_service: Any | None = None,
    ) -> None:
        self.features_service = features_service
        self.market_data = market_data
        self.models = models
        self.regime_service = regime_service
        self.mastermind = mastermind
        self.execution = execution
        self.alpha = alpha
        self.portfolio = portfolio
        self.quantum_state_service = quantum_state_service
        self.edge_immunity_service = edge_immunity_service
        self.observability = observability
        self.settings = settings
        self.ops = ops
        self.market_integrity_service = market_integrity_service
        self.venue_capability_registry = venue_capability_registry
        self.shared_venue_limit_governor = shared_venue_limit_governor
        self.event_intelligence_service = event_intelligence_service
        self.market_watch_service = market_watch_service

    def _route_truth_evidence(self, channel: str, payload: Any) -> None:
        route = getattr(self.observability, "route_truth_evidence", None)
        if callable(route):
            route(channel, payload)
        else:
            self.observability.journal(channel, payload)

    def _route_event_intelligence(self, *, symbol: str, ts: datetime, report: Any) -> None:
        self.observability.journal("event_intelligence_journal", report)
        self._route_truth_evidence(
            "source_trust_journal",
            {"symbol": symbol, "ts": ts, **asdict(getattr(report, "source_trust"))},
        )
        self._route_truth_evidence(
            "freshness_novelty_journal",
            {"symbol": symbol, "ts": ts, **asdict(getattr(report, "freshness_novelty"))},
        )
        self._route_truth_evidence(
            "asset_relevance_journal",
            {"symbol": symbol, "ts": ts, **asdict(getattr(report, "asset_relevance"))},
        )
        self._route_truth_evidence(
            "market_impact_journal",
            {"symbol": symbol, "ts": ts, **asdict(getattr(report, "market_impact"))},
        )
        self._route_truth_evidence(
            "priced_in_journal",
            {"symbol": symbol, "ts": ts, **asdict(getattr(report, "priced_in"))},
        )
        self._route_truth_evidence(
            "adversarial_narrative_journal",
            {"symbol": symbol, "ts": ts, **asdict(getattr(report, "adversarial"))},
        )
        self._route_truth_evidence(
            "data_provenance_journal",
            {"symbol": symbol, "ts": ts, **asdict(getattr(report, "provenance"))},
        )

    def _route_mastermind(self, payload: Any) -> None:
        route = getattr(self.observability, "route_mastermind", None)
        if callable(route):
            route(payload)
        else:
            self.observability.journal("mastermind_journal", payload)

    def _market_integrity_evidence(self, *, live: object, book_raw: dict[str, Any], now_dt: datetime, symbol: str, provider_id: str) -> MarketIntegrityEvidence:
        if hasattr(live, "capture_market_integrity_evidence"):
            try:
                live.capture_market_integrity_evidence(book_raw, now_dt)
            except Exception:
                pass
        payload: dict[str, Any] = {}
        if hasattr(live, "market_integrity_evidence"):
            try:
                payload = dict(live.market_integrity_evidence(now_dt=now_dt))
            except TypeError:
                payload = dict(live.market_integrity_evidence())
            except Exception:
                payload = {}
        feed_ts = payload.get("ts", book_raw.get("ts", book_raw.get("timestamp", book_raw.get("event_time", now_dt))))
        if isinstance(feed_ts, (int, float)):
            feed_dt = datetime.fromtimestamp(float(feed_ts), tz=now_dt.tzinfo)
        elif isinstance(feed_ts, str):
            try:
                feed_dt = datetime.fromisoformat(feed_ts)
            except Exception:
                feed_dt = now_dt
        else:
            feed_dt = feed_ts if isinstance(feed_ts, datetime) else now_dt
        if feed_dt.tzinfo is None:
            feed_dt = feed_dt.replace(tzinfo=now_dt.tzinfo)
        age_seconds = max(0.0, (now_dt - feed_dt).total_seconds())
        sequence_ok = bool(payload.get("sequence_ok", book_raw.get("sequence_ok", book_raw.get("sequenceOk", True))))
        checksum_ok = bool(payload.get("checksum_ok", book_raw.get("checksum_ok", book_raw.get("checksumOk", True))))
        gap_count = int(payload.get("gap_count", book_raw.get("gap_count", 0)) or 0)
        checksum_mismatch_count = int(payload.get("checksum_mismatch_count", book_raw.get("checksum_mismatch_count", 0)) or 0)
        evidence_confidence = "strong"
        reasons: list[str] = []
        if age_seconds > 30.0:
            evidence_confidence = "partial"
            reasons.append("feed_age_elevated")
        if not sequence_ok or gap_count > 0:
            evidence_confidence = "weak" if gap_count > 1 else "partial"
            reasons.append("sequence_gap_evidence")
        if not checksum_ok or checksum_mismatch_count > 0:
            evidence_confidence = "weak"
            reasons.append("checksum_gap_evidence")
        return MarketIntegrityEvidence(
            symbol=symbol,
            provider_id=provider_id,
            ts=now_dt,
            feed_age_seconds=age_seconds,
            sequence_ok=sequence_ok,
            checksum_ok=checksum_ok,
            gap_count=gap_count,
            checksum_mismatch_count=checksum_mismatch_count,
            evidence_confidence=evidence_confidence,
            reasons=reasons,
            partial=evidence_confidence != "strong",
            metadata=payload,
        )

    def collect(
        self,
        *,
        live: object,
        symbol: str,
        now_dt: datetime,
        prices: list[float],
        base_budget: float,
        exposure_notional: float,
    ) -> LiveMarketContext:
        book_raw = live.connector.book_ticker(symbol)  # type: ignore[attr-defined]
        bid = float(book_raw.get("bidPrice", 0.0))
        ask = float(book_raw.get("askPrice", 0.0))
        bid_qty = float(book_raw.get("bidQty", 0.0))
        ask_qty = float(book_raw.get("askQty", 0.0))
        if bid <= 0.0 or ask <= 0.0:
            raise ValueError(f"book_invalid:{bid}:{ask}")

        market_started = time.perf_counter()
        snapshot = self.market_data.build_live_snapshot(
            symbol,
            {"bidPrice": bid, "askPrice": ask, "bidQty": bid_qty, "askQty": ask_qty},
            recent_mids=prices,
            ts=now_dt,
        )
        updated_prices = list(prices) + [snapshot.mid]
        updated_prices = updated_prices[-8:]
        features = self.market_data.snapshot_features(snapshot, updated_prices)
        provider_id = str(getattr(getattr(live, "connector", None), "provider_id", getattr(self.execution.settings, "provider_id", "paper")))
        integrity_evidence = self._market_integrity_evidence(
            live=live,
            book_raw=book_raw,
            now_dt=now_dt,
            symbol=symbol,
            provider_id=provider_id,
        )
        market_health = self.market_data.assess_health(
            snapshot,
            stale_seconds=integrity_evidence.feed_age_seconds,
            stale_threshold_seconds=float(self.settings.risk.stale_data_seconds),
            min_depth_notional=float(self.settings.risk.min_depth_notional),
            max_spread_bps=float(self.settings.risk.max_spread_bps),
            sequence_ok=integrity_evidence.sequence_ok,
            checksum_ok=integrity_evidence.checksum_ok,
        )
        provider_capability = (
            self.venue_capability_registry.resolve(
                provider_id,
                connector=getattr(live, "connector", None),
                live=live,
                now=now_dt,
            )
            if self.venue_capability_registry is not None
            else self.execution.provider_capability_matrix()
        )
        capability_evidence = (
            self.venue_capability_registry.last_evidence(provider_id)
            if self.venue_capability_registry is not None
            else None
        )
        market_integrity = (
            self.market_integrity_service.assess(
                symbol=symbol,
                provider_id=provider_id,
                snapshot=snapshot,
                market_health=market_health,
                capability=provider_capability,
                integrity_evidence=integrity_evidence,
                capability_evidence=capability_evidence,
            )
            if self.market_integrity_service is not None
            else None
        )
        venue_limit_decision = (
            self.shared_venue_limit_governor.evaluate(
                symbol=symbol,
                provider_id=provider_id,
                market_integrity=market_integrity,
                capability=provider_capability,
            )
            if self.shared_venue_limit_governor is not None and market_integrity is not None
            else None
        )
        market_stage_ms = (time.perf_counter() - market_started) * 1000.0

        forecast_started = time.perf_counter()
        fv = FeatureVector(symbol=symbol, ts=now_dt, feature_version=self.features_service.feature_version, values=features)
        forecast = self.models.forecast(fv)
        regime_assessment = self.regime_service.assess(symbol, now_dt, features, forecast)
        preview_intent = OrderIntent(symbol=symbol, side="buy" if forecast.mu >= 0 else "sell", target_notional=base_budget, why={})
        execution_quality = self.execution.forecast_execution_quality(
            preview_intent,
            depth_notional=snapshot.depth_notional,
            spread_bps=snapshot.spread_bps,
            regime=forecast.regime,
            liquidity_regime=forecast.liquidity_regime,
        )
        alpha_signals = self.alpha.evaluate(symbol, now_dt, features, forecast, regime_assessment, execution_quality)
        portfolio_allocation = self.portfolio.recommend_allocation(
            symbol=symbol,
            ts=now_dt,
            base_budget=base_budget,
            expected_edge_bps=max(abs(forecast.mu) * 10000.0, 0.0),
            confidence=forecast.confidence,
            uncertainty=max(0.0, 1.0 - forecast.confidence),
            realized_vol=features.get("realized_vol", 0.0),
            depth_notional=snapshot.depth_notional,
            current_exposure=abs(exposure_notional),
            drawdown_pct=0.0,
            regime_fit=max(0.0, min(1.0, regime_assessment.confidence * regime_assessment.persistence)),
        )
        connector = getattr(live, "connector", None)
        raw_events = getattr(connector, "event_candidates", None)
        if raw_events is None:
            raw_events = getattr(connector, "events", None)
        if raw_events is None:
            raw_events = getattr(connector, "event_feed", None)
        event_intelligence_report = (
            self.event_intelligence_service.evaluate(
                symbol=symbol,
                ts=now_dt,
                features=features,
                forecast=forecast,
                events=raw_events,
            )
            if self.event_intelligence_service is not None
            else None
        )
        market_watch = (
            self.market_watch_service.evaluate(
                symbol=symbol,
                ts=now_dt,
                snapshot=snapshot,
                forecast=forecast,
                regime_assessment=regime_assessment,
                market_integrity=market_integrity,
            )
            if self.market_watch_service is not None
            else None
        )
        quantum_started = time.perf_counter()
        quantum_state = self.quantum_state_service.evaluate(
            symbol=symbol,
            ts=now_dt,
            features=features,
            forecast=forecast,
            regime_assessment=regime_assessment,
            alpha_signals=alpha_signals,
            execution_quality=execution_quality,
            portfolio_allocation=portfolio_allocation,
        )
        quantum_stage_ms = (time.perf_counter() - quantum_started) * 1000.0
        edge_started = time.perf_counter()
        edge_immunity_decision = self.edge_immunity_service.evaluate(
            symbol=symbol,
            ts=now_dt,
            features=features,
            forecast=forecast,
            regime_assessment=regime_assessment,
            execution_quality=execution_quality,
            portfolio_allocation=portfolio_allocation,
            quantum_state=quantum_state,
        )
        edge_immunity_stage_ms = (time.perf_counter() - edge_started) * 1000.0
        self.observability.journal("quantum_state_journal", quantum_state)
        self.observability.journal("edge_immunity_journal", edge_immunity_decision)
        self._route_truth_evidence("market_integrity_evidence_journal", integrity_evidence)
        if capability_evidence is not None:
            self._route_truth_evidence("provider_capability_journal", capability_evidence)
        if market_integrity is not None:
            self.observability.journal("market_integrity_journal", market_integrity)
        if venue_limit_decision is not None:
            self.observability.journal("venue_limit_journal", venue_limit_decision)
        if event_intelligence_report is not None:
            self._route_event_intelligence(symbol=symbol, ts=now_dt, report=event_intelligence_report)
        if market_watch is not None:
            self.observability.journal("market_watch_journal", market_watch)
        advisory = self.mastermind.advise(
            symbol,
            features,
            forecast.regime,
            forecast=forecast,
            regime_assessment=regime_assessment,
            execution_quality=execution_quality,
            portfolio_allocation=portfolio_allocation,
            market_integrity=market_integrity,
            provider_capability=provider_capability,
            event_intelligence_report=event_intelligence_report,
            quantum_state=quantum_state,
            edge_immunity_decision=edge_immunity_decision,
        )
        if advisory is not None:
            self._route_mastermind(
                {
                    "symbol": symbol,
                    "ts": now_dt,
                    "provider": advisory.provider,
                    "signal": advisory.signal,
                    "confidence": advisory.confidence,
                    "reason": advisory.reason,
                    "decision": advisory.decision,
                    "risk_level": advisory.risk_level,
                    "veto": advisory.veto,
                    "size_multiplier": advisory.size_multiplier,
                    "execution_style_bias": advisory.execution_style_bias,
                    "reasons": list(advisory.reasons),
                    "heuristic": advisory.heuristic,
                    "raw": dict(advisory.raw),
                }
            )
        self.observability.journal(
            "signal_journal",
            {
                "symbol": symbol,
                "ts": now_dt,
                "forecast": asdict(forecast),
                "regime": asdict(regime_assessment),
                "alpha_experts": [asdict(sig) for sig in alpha_signals],
                "market_health": asdict(market_health),
                "integrity_evidence": asdict(integrity_evidence),
                "capability_evidence": None if capability_evidence is None else asdict(capability_evidence),
                "provider_capability": None if provider_capability is None else asdict(provider_capability),
                "market_integrity": None if market_integrity is None else asdict(market_integrity),
                "venue_limit_decision": None if venue_limit_decision is None else asdict(venue_limit_decision),
                "event_intelligence": None if event_intelligence_report is None else asdict(event_intelligence_report),
                "market_watch": None if market_watch is None else asdict(market_watch),
                "portfolio_allocation": asdict(portfolio_allocation),
                "mastermind": None
                if advisory is None
                else {
                    "provider": advisory.provider,
                    "signal": advisory.signal,
                    "confidence": advisory.confidence,
                    "reason": advisory.reason,
                    "decision": advisory.decision,
                    "risk_level": advisory.risk_level,
                    "veto": advisory.veto,
                    "size_multiplier": advisory.size_multiplier,
                    "execution_style_bias": advisory.execution_style_bias,
                    "reasons": list(advisory.reasons),
                },
            },
        )
        forecast_stage_ms = (time.perf_counter() - forecast_started) * 1000.0
        return LiveMarketContext(
            now_dt=now_dt,
            book={"bid": bid, "ask": ask, "bid_qty": bid_qty, "ask_qty": ask_qty},
            prices=updated_prices,
            snapshot=snapshot,
            features=features,
            market_health=market_health,
            provider_capability=provider_capability,
            market_integrity=market_integrity,
            venue_limit_decision=venue_limit_decision,
            event_intelligence_report=event_intelligence_report,
            market_watch=market_watch,
            forecast=forecast,
            regime_assessment=regime_assessment,
            advisory=advisory,
            execution_quality=execution_quality,
            alpha_signals=alpha_signals,
            portfolio_allocation=portfolio_allocation,
            market_stage_ms=market_stage_ms,
            forecast_stage_ms=forecast_stage_ms,
            quantum_stage_ms=quantum_stage_ms,
            edge_immunity_stage_ms=edge_immunity_stage_ms,
            quantum_state=quantum_state,
            edge_immunity_decision=edge_immunity_decision,
        )


class LiveRecoveryCoordinator:
    def __init__(self, *, live_state: Any, settings: Any, observability: Any | None = None, forensics: Any | None = None) -> None:
        self.live_state = live_state
        self.settings = settings
        self.observability = observability
        self.forensics = forensics

    def boot_state(self, *, live: object, symbol: str) -> LiveBootState:
        rehydrated = self.live_state.rehydrate_state(live, symbol)
        recovery = self.live_state.recover_inflight_state(
            live,
            symbol,
            restart_confidence=rehydrated.confidence,
            safe_mode_requested=bool(self.settings.safe_mode_default),
        )
        if self.observability is not None:
            self.observability.journal("recovery_journal", recovery)
            truth_confidence = rehydrated.details.get("truth_confidence")
            if truth_confidence is not None:
                self.observability.journal("truth_confidence_journal", truth_confidence)
            unrealized_truth = rehydrated.details.get("exchange_unrealized_truth")
            if unrealized_truth is not None:
                self.observability.journal("unrealized_pnl_truth_journal", unrealized_truth)
        if self.forensics is not None and recovery.action != "continue":
            self.forensics.record_runtime_anomaly(
                symbol=symbol,
                ts=recovery.ts,
                venue=str(getattr(getattr(live, "connector", None), "provider_id", "live")),
                category="recovery",
                reason=recovery.outcome,
                truth_confidence=rehydrated.details.get("truth_confidence"),
                evidence={"details": rehydrated.details, "recovery": asdict(recovery)},
            )
        return LiveBootState(confidence=rehydrated.confidence, details=rehydrated.details, recovery_decision=recovery)


class LiveDecisionCoordinator:
    def __init__(
        self,
        *,
        health: Any,
        policy: Any,
        risk: Any,
        execution: Any,
        observability: Any,
        settings: Any,
        profitability: Any | None = None,
        inventory: Any | None = None,
        reporting: Any | None = None,
        capital_sovereignty: Any | None = None,
        position_morphing: Any | None = None,
        adaptive_exit_allocator: Any | None = None,
        synthetic_affect: Any | None = None,
        execution_simulation_sandbox: Any | None = None,
        human_escalation_layer: Any | None = None,
    ) -> None:
        self.health = health
        self.policy = policy
        self.risk = risk
        self.execution = execution
        self.profitability = profitability
        self.inventory = inventory
        self.reporting = reporting
        self.capital_sovereignty = capital_sovereignty
        self.position_morphing = position_morphing
        self.adaptive_exit_allocator = adaptive_exit_allocator
        self.synthetic_affect = synthetic_affect
        self.execution_simulation_sandbox = execution_simulation_sandbox
        self.human_escalation_layer = human_escalation_layer
        self.observability = observability
        self.settings = settings

    def _route(self, kind: str, payload: Any) -> None:
        route = getattr(self.observability, kind, None)
        if callable(route):
            route(payload)
        else:
            channel = {
                "route_execution_simulation": "execution_simulation_journal",
                "route_escalation": "human_escalation_journal",
                "route_spre": "spre_journal",
                "route_shadow": "shadow_rival_journal",
                "route_decision_doctrine": "decision_doctrine_journal",
                "route_mastermind": "mastermind_journal",
            }.get(kind, "journal")
            if channel == "journal":
                self.observability.journal(kind, payload)
            else:
                self.observability.journal(channel, payload)

    def evaluate(
        self,
        *,
        symbol: str,
        market: LiveMarketContext,
        exposure_notional: float,
        last_recon_ok: bool,
        live: object,
        drawdown_pct: float,
        daily_loss_pct: float,
        weekly_loss_pct: float,
        funding_paid_pct: float,
        legacy_policy_why: Any,
        legacy_risk_details: Any,
        reconciliation_report: Any | None = None,
    ) -> LiveDecisionContext:
        health_started = time.perf_counter()
        health_snapshot = self.health.evaluate(
            market_health=market.market_health,
            risk_mode=self.risk.state.risk_mode,
            reconciliation_ok=last_recon_ok,
            api_error_burst=len(getattr(getattr(live, "rate_limits", None), "timestamps", [])),
            order_reject_burst=len(getattr(getattr(live, "rejects", None), "timestamps", [])),
            abnormal_latency_ms=float(market.execution_quality.expected_fill_speed_ms),
            anomaly_pressure=1.0 if market.regime_assessment.degradation_warning else 0.0,
            market_integrity_status=market.market_integrity,
        )
        self.observability.journal("health_journal", health_snapshot)
        meta_governor = self.health.govern(
            symbol=symbol,
            health_snapshot=health_snapshot,
            rollout_stage=self.settings.rollout_stage().value,
            market_integrity_status=market.market_integrity,
            venue_limit_decision=market.venue_limit_decision,
        )
        self.observability.journal("meta_governor_journal", meta_governor)
        if getattr(meta_governor, "forced_risk_mode", None) and hasattr(self.risk, "_set_risk_mode"):
            self.risk._set_risk_mode(meta_governor.forced_risk_mode)
        health_stage_ms = (time.perf_counter() - health_started) * 1000.0
        if meta_governor.action in {"force_halt", "force_halt_and_flatten", "force_flatten_only", "disable_symbol"}:
            return LiveDecisionContext(
                health_snapshot=health_snapshot,
                meta_governor_decision=meta_governor,
                health_stage_ms=health_stage_ms,
            )

        preliminary_policy = self.policy.evaluate_decision(
            market.forecast,
            market.features,
            self.execution.settings.fee_bps,
            self.execution.settings.slippage_bps,
            regime_assessment=market.regime_assessment,
            execution_quality=market.execution_quality,
            portfolio_allocation=market.portfolio_allocation,
            quantum_state=market.quantum_state,
            edge_immunity_decision=market.edge_immunity_decision,
            truth_context=None if reconciliation_report is None else {"snapshot": getattr(reconciliation_report, "details", {}).get("truth_confidence"), "reconciliation_ok": last_recon_ok},
            market_integrity_status=market.market_integrity,
            provider_capability=market.provider_capability,
            mastermind_advisory=market.advisory,
            market_watch_report=market.market_watch,
        )
        reserve_state = None
        inventory_state = None
        profitability_context = None
        release_decision = None
        round_trip_report = None
        if self.inventory is not None and self.profitability is not None:
            details = {} if reconciliation_report is None else getattr(reconciliation_report, "details", {})
            reserve_state = self.inventory.reserve_state(
                ts=market.now_dt,
                exchange_balance=float(details.get("exchange_balance", 0.0) or 0.0),
                local_cash_delta=float(details.get("local_cash_delta", 0.0) or 0.0),
                gross_exposure_notional=abs(exposure_notional),
                minimum_reserve_pct=float(self.settings.policy.min_free_quote_reserve_pct),
                capital_floor=float(self.settings.policy.base_risk_budget),
            )
            truth_snapshot = details.get("truth_confidence")
            inventory_state = self.inventory.inventory_pressure(
                symbol=symbol,
                ts=market.now_dt,
                opportunity_cost_score=float(getattr(market.portfolio_allocation, "opportunity_cost_score", 0.0)),
                unrealized_pnl=float(details.get("local_unrealized_pnl", 0.0) or 0.0),
                truth_pressure=0.0 if truth_snapshot is None else 0.5 if "proxy" in json.dumps(truth_snapshot, sort_keys=True) else 0.0,
                execution_fragility=max(
                    float(getattr(market.execution_quality, "adverse_selection_risk", 0.0)),
                    float(getattr(getattr(market.edge_immunity_decision, "report", None), "fragility_index", 0.0) or 0.0),
                ),
            )
            floor, release_decision, round_trip_report = self.profitability.evaluate_open(
                symbol=symbol,
                ts=market.now_dt,
                target_notional=preliminary_policy.target_notional,
                expected_edge_bps=preliminary_policy.expected_edge_bps,
                fee_bps=float(self.execution.settings.fee_bps),
                slippage_bps=float(self.execution.settings.slippage_bps),
                spread_bps=float(market.snapshot.spread_bps),
                depth_notional=float(market.snapshot.depth_notional),
                execution_quality=market.execution_quality,
                inventory_state=inventory_state,
                reserve_state=reserve_state,
                truth_confidence=truth_snapshot,
                edge_immunity_decision=market.edge_immunity_decision,
            )
            profitability_context = {
                "profit_floor": asdict(floor),
                "capital_release": asdict(release_decision),
                "round_trip": asdict(round_trip_report),
            }
            if self.reporting is not None:
                self.reporting.report_profitability(
                    symbol=symbol,
                    profitability=profitability_context,
                    reserve_state=reserve_state,
                    inventory_state=inventory_state,
                )
        synthetic_affect_state = (
            self.synthetic_affect.evaluate(
                symbol=symbol,
                ts=market.now_dt,
                forecast=market.forecast,
                regime_assessment=market.regime_assessment,
                execution_quality=market.execution_quality,
                inventory_state=inventory_state,
                reserve_state=reserve_state,
                quantum_state=market.quantum_state,
                edge_immunity_decision=market.edge_immunity_decision,
                event_intelligence=market.event_intelligence_report,
            )
            if self.synthetic_affect is not None
            else None
        )
        if synthetic_affect_state is not None:
            self.observability.journal("synthetic_affect_journal", synthetic_affect_state)
        capital_sovereignty_decision = (
            self.capital_sovereignty.evaluate(
                symbol=symbol,
                ts=market.now_dt,
                reserve_state=reserve_state,
                inventory_state=inventory_state,
                portfolio_allocation=market.portfolio_allocation,
                round_trip=None if round_trip_report is None else asdict(round_trip_report),
                event_intelligence=market.event_intelligence_report,
                synthetic_affect=synthetic_affect_state,
                quantum_state=market.quantum_state,
                edge_immunity_decision=market.edge_immunity_decision,
            )
            if self.capital_sovereignty is not None
            else None
        )
        if capital_sovereignty_decision is not None:
            self.observability.journal("capital_sovereignty_journal", capital_sovereignty_decision)
        position_morph_plan = (
            self.position_morphing.evaluate(
                symbol=symbol,
                ts=market.now_dt,
                current_exposure=abs(exposure_notional),
                capital_sovereignty=capital_sovereignty_decision,
                synthetic_affect=synthetic_affect_state,
                quantum_state=market.quantum_state,
                edge_immunity_decision=market.edge_immunity_decision,
            )
            if self.position_morphing is not None and capital_sovereignty_decision is not None
            else None
        )
        if position_morph_plan is not None:
            self.observability.journal("position_morphing_journal", position_morph_plan)
        adaptive_exit_allocation = (
            self.adaptive_exit_allocator.evaluate(
                symbol=symbol,
                ts=market.now_dt,
                current_exposure=abs(exposure_notional),
                capital_release_decision=release_decision,
                position_morph_plan=position_morph_plan,
                synthetic_affect=synthetic_affect_state,
                event_intelligence=market.event_intelligence_report,
            )
            if self.adaptive_exit_allocator is not None and abs(exposure_notional) > 1e-9
            else None
        )
        if adaptive_exit_allocation is not None:
            self.observability.journal("adaptive_exit_journal", adaptive_exit_allocation)
        simulation_probe = OrderIntent(
            symbol=symbol,
            side=preliminary_policy.side or "buy",
            target_notional=float(getattr(preliminary_policy, "target_notional", 0.0) or 0.0),
            why={},
        )
        execution_simulation_report = (
            self.execution_simulation_sandbox.simulate(
                symbol=symbol,
                ts=market.now_dt,
                intent=simulation_probe,
                snapshot=market.snapshot,
                execution_quality=market.execution_quality,
                expected_edge_bps=float(getattr(preliminary_policy, "expected_edge_bps", 0.0) or 0.0),
                market_integrity=market.market_integrity,
                venue_limit_decision=market.venue_limit_decision,
                synthetic_affect=synthetic_affect_state,
            )
            if self.execution_simulation_sandbox is not None
            else None
        )
        if execution_simulation_report is not None:
            self._route("route_execution_simulation", execution_simulation_report)
        human_escalation_decision = (
            self.human_escalation_layer.evaluate(
                symbol=symbol,
                ts=market.now_dt,
                market_integrity=market.market_integrity,
                quantum_state=market.quantum_state,
                edge_immunity_decision=market.edge_immunity_decision,
                event_intelligence=market.event_intelligence_report,
                synthetic_affect=synthetic_affect_state,
                capital_sovereignty=capital_sovereignty_decision,
                execution_simulation=execution_simulation_report,
            )
            if self.human_escalation_layer is not None
            else None
        )
        if human_escalation_decision is not None:
            self._route("route_escalation", human_escalation_decision)
        if self.reporting is not None:
            self.reporting.report_capital_strategy(
                symbol=symbol,
                event_intelligence=market.event_intelligence_report,
                synthetic_affect=synthetic_affect_state,
                capital_sovereignty=capital_sovereignty_decision,
                position_morph=position_morph_plan,
                adaptive_exit=adaptive_exit_allocation,
            )
            if market.advisory is not None:
                self.reporting.report_mastermind(symbol=symbol, mastermind=market.advisory)
        policy_decision = self.policy.evaluate_decision(
            market.forecast,
            market.features,
            self.execution.settings.fee_bps,
            self.execution.settings.slippage_bps,
            regime_assessment=market.regime_assessment,
            execution_quality=market.execution_quality,
            portfolio_allocation=market.portfolio_allocation,
            quantum_state=market.quantum_state,
            edge_immunity_decision=market.edge_immunity_decision,
            profitability_context=profitability_context,
            inventory_context=None if inventory_state is None else asdict(inventory_state),
            event_intelligence_report=market.event_intelligence_report,
            synthetic_affect_state=synthetic_affect_state,
            capital_sovereignty_decision=capital_sovereignty_decision,
            position_morph_plan=position_morph_plan,
            adaptive_exit_allocation=adaptive_exit_allocation,
            execution_simulation_report=execution_simulation_report,
            human_escalation_decision=human_escalation_decision,
            truth_context=None if reconciliation_report is None else {"snapshot": getattr(reconciliation_report, "details", {}).get("truth_confidence"), "reconciliation_ok": last_recon_ok},
            market_integrity_status=market.market_integrity,
            provider_capability=market.provider_capability,
            mastermind_advisory=market.advisory,
            market_watch_report=market.market_watch,
        )
        self.observability.journal("policy_journal", policy_decision)
        spre_payload = getattr(policy_decision, "why", {}).get("spre") if isinstance(getattr(policy_decision, "why", None), dict) else None
        if spre_payload is not None:
            self._route("route_spre", {"symbol": symbol, "ts": market.now_dt, **dict(spre_payload)})
        shadow_payload = getattr(policy_decision, "why", {}).get("shadow_rival") if isinstance(getattr(policy_decision, "why", None), dict) else None
        if shadow_payload is not None:
            self._route("route_shadow", {"symbol": symbol, "ts": market.now_dt, **dict(shadow_payload)})
        doctrine_payload = getattr(policy_decision, "why", {}).get("decision_doctrine") if isinstance(getattr(policy_decision, "why", None), dict) else None
        if doctrine_payload is not None:
            self._route("route_decision_doctrine", {"symbol": symbol, "ts": market.now_dt, **dict(doctrine_payload)})
            if self.reporting is not None:
                self.reporting.report_decision_doctrine(
                    symbol=symbol,
                    decision_doctrine=doctrine_payload,
                    truth_context=(getattr(policy_decision, "why", {}) or {}).get("truth_context"),
                    market_integrity=(getattr(policy_decision, "why", {}) or {}).get("market_integrity"),
                    provider_capability=(getattr(policy_decision, "why", {}) or {}).get("provider_capability"),
                )
        if human_escalation_decision is not None and human_escalation_decision.action in {"manual_review", "flatten_only"}:
            no_trade_reason = "manual_review_required" if human_escalation_decision.action == "manual_review" else "human_escalation_flatten_only"
            blocked_policy = OrderIntent(symbol=symbol, side="sell", target_notional=abs(exposure_notional), why={"human_escalation": asdict(human_escalation_decision)})
            return LiveDecisionContext(
                health_snapshot=health_snapshot,
                meta_governor_decision=meta_governor,
                policy_decision=policy_decision,
                intent=blocked_policy if human_escalation_decision.action == "flatten_only" and abs(exposure_notional) > 1e-9 else None,
                reserve_state=reserve_state,
                inventory_state=inventory_state,
                profitability_context=profitability_context,
                synthetic_affect_state=synthetic_affect_state,
                capital_sovereignty_decision=capital_sovereignty_decision,
                position_morph_plan=position_morph_plan,
                adaptive_exit_allocation=adaptive_exit_allocation,
                execution_simulation_report=execution_simulation_report,
                human_escalation_decision=human_escalation_decision,
                health_stage_ms=health_stage_ms,
            )
        exit_intent = None
        if (
            self.profitability is not None
            and inventory_state is not None
            and reserve_state is not None
            and abs(exposure_notional) > 1e-9
        ):
            exit_release_decision, computed_exit_intent = self.profitability.evaluate_exit(
                symbol=symbol,
                ts=market.now_dt,
                inventory_state=inventory_state,
                reserve_state=reserve_state,
                current_exposure=exposure_notional,
            )
            if self.adaptive_exit_allocator is not None:
                adaptive_exit_allocation = self.adaptive_exit_allocator.evaluate(
                    symbol=symbol,
                    ts=market.now_dt,
                    current_exposure=abs(exposure_notional),
                    capital_release_decision=exit_release_decision,
                    position_morph_plan=position_morph_plan,
                    synthetic_affect=synthetic_affect_state,
                    event_intelligence=market.event_intelligence_report,
                )
                self.observability.journal("adaptive_exit_journal", adaptive_exit_allocation)
            if exit_release_decision.allowed:
                profitability_context = profitability_context or {}
                profitability_context["capital_release"] = asdict(exit_release_decision)
                exit_intent = computed_exit_intent
        if exit_intent is not None and adaptive_exit_allocation is not None and adaptive_exit_allocation.total_exit_notional > 0.0:
            exit_intent = ExitIntent(
                symbol=exit_intent.symbol,
                ts=exit_intent.ts,
                side=exit_intent.side,
                target_notional=max(float(exit_intent.target_notional), float(adaptive_exit_allocation.total_exit_notional)),
                reason=exit_intent.reason,
                reduce_only=exit_intent.reduce_only,
                execution_style=str(getattr(adaptive_exit_allocation, "execution_style", exit_intent.execution_style)),
                metadata={
                    **dict(getattr(exit_intent, "metadata", {}) or {}),
                    "adaptive_exit": asdict(adaptive_exit_allocation),
                },
            )
        if not policy_decision.trade_allowed or policy_decision.side is None:
            if exit_intent is None:
                return LiveDecisionContext(
                    health_snapshot=health_snapshot,
                    meta_governor_decision=meta_governor,
                    policy_decision=policy_decision,
                    reserve_state=reserve_state,
                    inventory_state=inventory_state,
                    profitability_context=profitability_context,
                    synthetic_affect_state=synthetic_affect_state,
                    capital_sovereignty_decision=capital_sovereignty_decision,
                    position_morph_plan=position_morph_plan,
                    adaptive_exit_allocation=adaptive_exit_allocation,
                    execution_simulation_report=execution_simulation_report,
                    human_escalation_decision=human_escalation_decision,
                    health_stage_ms=health_stage_ms,
                )
            intent = OrderIntent(
                exit_intent.symbol,
                exit_intent.side,
                exit_intent.target_notional,
                {
                    "capital_release": profitability_context.get("capital_release", {}) if isinstance(profitability_context, dict) else {},
                    "profitability": profitability_context.get("round_trip", {}) if isinstance(profitability_context, dict) else {},
                    "decision_doctrine": (getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}),
                    "market_integrity": (getattr(policy_decision, "why", {}) or {}).get("market_integrity", {}),
                    "execution_simulation": {}
                    if execution_simulation_report is None
                    else asdict(execution_simulation_report),
                    "human_escalation": {}
                    if human_escalation_decision is None
                    else asdict(human_escalation_decision),
                    "meta_governor": {
                        "action": getattr(meta_governor, "action", "continue"),
                        "size_multiplier": getattr(meta_governor, "size_multiplier", 1.0),
                        "forced_risk_mode": getattr(meta_governor, "forced_risk_mode", None),
                    },
                    "event_intelligence": {} if market.event_intelligence_report is None else asdict(market.event_intelligence_report),
                    "synthetic_affect": {} if synthetic_affect_state is None else asdict(synthetic_affect_state),
                    "capital_sovereignty": {} if capital_sovereignty_decision is None else asdict(capital_sovereignty_decision),
                    "position_morph": {} if position_morph_plan is None else asdict(position_morph_plan),
                    "adaptive_exit": {} if adaptive_exit_allocation is None else asdict(adaptive_exit_allocation),
                    "market_watch": {} if market.market_watch is None else asdict(market.market_watch),
                    "doctrine_target": {
                        "provider": str(getattr(self.settings.doctrine, "target_provider", "") or self.settings.execution.provider_id),
                        "product": str(getattr(self.settings.doctrine, "product_target", "") or "spot"),
                        "long_only": bool(getattr(self.settings.doctrine, "long_only", False)),
                        "minimum_sell_net_profit_bps": float(getattr(self.settings.doctrine, "minimum_sell_net_profit_bps", 120.0) or 120.0),
                        "enforce_cost_basis_sell_block": bool(getattr(self.settings.doctrine, "enforce_cost_basis_sell_block", False)),
                        "enforce_net_profit_sell_block": bool(getattr(self.settings.doctrine, "enforce_net_profit_sell_block", False)),
                        "block_non_reduce_only_sells": bool(getattr(self.settings.doctrine, "block_non_reduce_only_sells", False)),
                    },
                    "reduce_only": True,
                },
            )
            risk_started = time.perf_counter()
            risk_decision = self.risk.evaluate(
                intent=intent,
                current_exposure=abs(exposure_notional),
                drawdown_pct=drawdown_pct,
                daily_loss_pct=daily_loss_pct,
                data_lag_seconds=0.0,
                spread_bps=market.snapshot.spread_bps,
                depth_notional=market.snapshot.depth_notional,
                reconciliation_ok=last_recon_ok,
                funding_paid_pct=funding_paid_pct,
                oi_spike_pct=0.0,
                liquidation_spike=0.0,
                divergence_bps=0.0,
                margin_buffer=999.0,
                funding_rate_abs=0.0,
                weekly_loss_pct=weekly_loss_pct,
                symbol_exposure=abs(exposure_notional),
                cluster_exposure=abs(exposure_notional),
                market_regime=market.forecast.regime,
                liquidity_regime=market.forecast.liquidity_regime,
                balance_state_ok=last_recon_ok,
                api_error_burst=len(getattr(getattr(live, "rate_limits", None), "timestamps", [])),
                order_reject_burst=len(getattr(getattr(live, "rejects", None), "timestamps", [])),
                abnormal_latency_ms=float(market.execution_quality.expected_fill_speed_ms),
                is_reduce_only=True,
                free_quote_reserve_pct=None if reserve_state is None else reserve_state.free_quote_reserve_pct,
                inventory_staleness_score=None if inventory_state is None else inventory_state.stale_inventory_score,
                capital_release_pressure=None if profitability_context is None else float(profitability_context["capital_release"]["pressure_score"]),
                round_trip_edge_bps=None,
                doctrine_action=str((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("recommended_action", "continue")),
                doctrine_size_multiplier=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("size_multiplier", 1.0) or 1.0),
                doctrine_truth_strength=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("truth_strength", 1.0) or 1.0),
                doctrine_survival_score=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("survival_score", 1.0) or 1.0),
                doctrine_robustness_score=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("robustness_score", 1.0) or 1.0),
                doctrine_execution_survivability_score=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("execution_survivability_score", 1.0) or 1.0),
                doctrine_partial_truth_penalty=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("partial_truth_penalty", 0.0) or 0.0),
            )
            risk_stage_ms = (time.perf_counter() - risk_started) * 1000.0
            if not risk_decision.allowed:
                return LiveDecisionContext(
                    health_snapshot=health_snapshot,
                    meta_governor_decision=meta_governor,
                    policy_decision=policy_decision,
                    intent=intent,
                    risk_decision=risk_decision,
                    reserve_state=reserve_state,
                    inventory_state=inventory_state,
                    profitability_context=profitability_context,
                    exit_intent=exit_intent,
                    synthetic_affect_state=synthetic_affect_state,
                    capital_sovereignty_decision=capital_sovereignty_decision,
                    position_morph_plan=position_morph_plan,
                    adaptive_exit_allocation=adaptive_exit_allocation,
                    execution_simulation_report=execution_simulation_report,
                    human_escalation_decision=human_escalation_decision,
                    health_stage_ms=health_stage_ms,
                    risk_stage_ms=risk_stage_ms,
                )
            execution_started = time.perf_counter()
            execution_plan = self.execution.build_exit_plan(
                intent,
                depth_notional=market.snapshot.depth_notional,
                spread_bps=market.snapshot.spread_bps,
                regime=market.forecast.regime,
                liquidity_regime=market.forecast.liquidity_regime,
                execution_style=str(getattr(exit_intent, "execution_style", "passive_limit")),
            )
            if execution_plan.target_notional <= 0.0:
                risk_decision.allowed = False
                risk_decision.reason = "venue_constraints_block_exit"
                return LiveDecisionContext(
                    health_snapshot=health_snapshot,
                    meta_governor_decision=meta_governor,
                    policy_decision=policy_decision,
                    intent=intent,
                    risk_decision=risk_decision,
                    adjusted_intent=None,
                    execution_plan=None,
                    reserve_state=reserve_state,
                    inventory_state=inventory_state,
                    profitability_context=profitability_context,
                    exit_intent=exit_intent,
                    synthetic_affect_state=synthetic_affect_state,
                    capital_sovereignty_decision=capital_sovereignty_decision,
                    position_morph_plan=position_morph_plan,
                    adaptive_exit_allocation=adaptive_exit_allocation,
                    execution_simulation_report=execution_simulation_report,
                    human_escalation_decision=human_escalation_decision,
                    health_stage_ms=health_stage_ms,
                    risk_stage_ms=risk_stage_ms,
                    execution_stage_ms=(time.perf_counter() - execution_started) * 1000.0,
                )
            self.observability.journal("execution_journal", {"plan": asdict(execution_plan), "forecast": asdict(market.execution_quality), "capital_release": True})
            execution_stage_ms = (time.perf_counter() - execution_started) * 1000.0
            return LiveDecisionContext(
                health_snapshot=health_snapshot,
                meta_governor_decision=meta_governor,
                policy_decision=policy_decision,
                intent=intent,
                risk_decision=risk_decision,
                adjusted_intent=intent,
                execution_plan=execution_plan,
                reserve_state=reserve_state,
                inventory_state=inventory_state,
                profitability_context=profitability_context,
                exit_intent=exit_intent,
                synthetic_affect_state=synthetic_affect_state,
                capital_sovereignty_decision=capital_sovereignty_decision,
                position_morph_plan=position_morph_plan,
                adaptive_exit_allocation=adaptive_exit_allocation,
                execution_simulation_report=execution_simulation_report,
                human_escalation_decision=human_escalation_decision,
                health_stage_ms=health_stage_ms,
                risk_stage_ms=risk_stage_ms,
                execution_stage_ms=execution_stage_ms,
            )

        intent = OrderIntent(
            policy_decision.symbol,
            policy_decision.side,
            policy_decision.target_notional,
            legacy_policy_why(policy_decision.why),
        )
        risk_started = time.perf_counter()
        risk_decision = self.risk.evaluate(
            intent=intent,
            current_exposure=abs(exposure_notional),
            drawdown_pct=drawdown_pct,
            daily_loss_pct=daily_loss_pct,
            data_lag_seconds=0.0,
            spread_bps=market.snapshot.spread_bps,
            depth_notional=market.snapshot.depth_notional,
            reconciliation_ok=last_recon_ok,
            funding_paid_pct=funding_paid_pct,
            oi_spike_pct=0.0,
            liquidation_spike=0.0,
            divergence_bps=0.0,
            margin_buffer=999.0,
            funding_rate_abs=0.0,
            weekly_loss_pct=weekly_loss_pct,
            symbol_exposure=abs(exposure_notional),
            cluster_exposure=abs(exposure_notional),
            market_regime=market.forecast.regime,
            liquidity_regime=market.forecast.liquidity_regime,
            balance_state_ok=last_recon_ok,
            api_error_burst=len(getattr(getattr(live, "rate_limits", None), "timestamps", [])),
            order_reject_burst=len(getattr(getattr(live, "rejects", None), "timestamps", [])),
            abnormal_latency_ms=float(market.execution_quality.expected_fill_speed_ms),
            free_quote_reserve_pct=None if reserve_state is None else reserve_state.free_quote_reserve_pct,
            inventory_staleness_score=None if inventory_state is None else inventory_state.stale_inventory_score,
            capital_release_pressure=None if profitability_context is None else float(profitability_context["capital_release"]["pressure_score"]),
            round_trip_edge_bps=None if profitability_context is None else float(profitability_context["round_trip"]["net_edge_bps"]),
            doctrine_action=str((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("recommended_action", "continue")),
            doctrine_size_multiplier=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("size_multiplier", 1.0) or 1.0),
            doctrine_truth_strength=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("truth_strength", 1.0) or 1.0),
            doctrine_survival_score=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("survival_score", 1.0) or 1.0),
            doctrine_robustness_score=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("robustness_score", 1.0) or 1.0),
            doctrine_execution_survivability_score=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("execution_survivability_score", 1.0) or 1.0),
            doctrine_partial_truth_penalty=float((getattr(policy_decision, "why", {}) or {}).get("decision_doctrine", {}).get("partial_truth_penalty", 0.0) or 0.0),
        )
        risk_stage_ms = (time.perf_counter() - risk_started) * 1000.0
        if not risk_decision.allowed:
            return LiveDecisionContext(
                health_snapshot=health_snapshot,
                meta_governor_decision=meta_governor,
                policy_decision=policy_decision,
                intent=intent,
                risk_decision=risk_decision,
                reserve_state=reserve_state,
                inventory_state=inventory_state,
                profitability_context=profitability_context,
                exit_intent=exit_intent,
                synthetic_affect_state=synthetic_affect_state,
                capital_sovereignty_decision=capital_sovereignty_decision,
                position_morph_plan=position_morph_plan,
                adaptive_exit_allocation=adaptive_exit_allocation,
                execution_simulation_report=execution_simulation_report,
                human_escalation_decision=human_escalation_decision,
                health_stage_ms=health_stage_ms,
                risk_stage_ms=risk_stage_ms,
            )

        size_multiplier = float(getattr(meta_governor, "size_multiplier", 1.0))
        if str(getattr(self.settings.execution, "mode", "")) == "paper" and size_multiplier <= 0.0:
            # The live decision coordinator is exercised in paper-mode tests for compatibility.
            # Keep rollout caps authoritative for live modes, but do not zero paper test intents.
            size_multiplier = 1.0
        adjusted_intent = OrderIntent(
            intent.symbol,
            intent.side,
            max(0.0, risk_decision.adjusted_notional * size_multiplier),
            {
                **intent.why,
                "risk": {"decision_reason": risk_decision.reason, **legacy_risk_details(risk_decision.details)},
                "meta_governor": {
                    "action": getattr(meta_governor, "action", "continue"),
                    "size_multiplier": size_multiplier,
                    "forced_risk_mode": getattr(meta_governor, "forced_risk_mode", None),
                },
                "market_watch": {} if market.market_watch is None else asdict(market.market_watch),
                "doctrine_target": {
                    "provider": str(getattr(self.settings.doctrine, "target_provider", "") or self.settings.execution.provider_id),
                    "product": str(getattr(self.settings.doctrine, "product_target", "") or "spot"),
                    "long_only": bool(getattr(self.settings.doctrine, "long_only", False)),
                    "minimum_sell_net_profit_bps": float(getattr(self.settings.doctrine, "minimum_sell_net_profit_bps", 120.0) or 120.0),
                    "enforce_cost_basis_sell_block": bool(getattr(self.settings.doctrine, "enforce_cost_basis_sell_block", False)),
                    "enforce_net_profit_sell_block": bool(getattr(self.settings.doctrine, "enforce_net_profit_sell_block", False)),
                    "block_non_reduce_only_sells": bool(getattr(self.settings.doctrine, "block_non_reduce_only_sells", False)),
                },
                "reduce_only": False,
            },
        )
        execution_started = time.perf_counter()
        execution_plan = self.execution.build_execution_plan(
            adjusted_intent,
            depth_notional=market.snapshot.depth_notional,
            spread_bps=market.snapshot.spread_bps,
            regime=market.forecast.regime,
            liquidity_regime=market.forecast.liquidity_regime,
        )
        if execution_plan.target_notional <= 0.0:
            risk_decision.allowed = False
            risk_decision.reason = "venue_constraints_block_open"
            return LiveDecisionContext(
                health_snapshot=health_snapshot,
                meta_governor_decision=meta_governor,
                policy_decision=policy_decision,
                intent=intent,
                risk_decision=risk_decision,
                adjusted_intent=None,
                execution_plan=None,
                reserve_state=reserve_state,
                inventory_state=inventory_state,
                profitability_context=profitability_context,
                exit_intent=exit_intent,
                synthetic_affect_state=synthetic_affect_state,
                capital_sovereignty_decision=capital_sovereignty_decision,
                position_morph_plan=position_morph_plan,
                adaptive_exit_allocation=adaptive_exit_allocation,
                execution_simulation_report=execution_simulation_report,
                human_escalation_decision=human_escalation_decision,
                health_stage_ms=health_stage_ms,
                risk_stage_ms=risk_stage_ms,
                execution_stage_ms=(time.perf_counter() - execution_started) * 1000.0,
            )
        self.observability.journal("execution_journal", {"plan": asdict(execution_plan), "forecast": asdict(market.execution_quality)})
        execution_stage_ms = (time.perf_counter() - execution_started) * 1000.0
        return LiveDecisionContext(
            health_snapshot=health_snapshot,
            meta_governor_decision=meta_governor,
            policy_decision=policy_decision,
            intent=intent,
            risk_decision=risk_decision,
            adjusted_intent=adjusted_intent,
            execution_plan=execution_plan,
            reserve_state=reserve_state,
            inventory_state=inventory_state,
            profitability_context=profitability_context,
            exit_intent=exit_intent,
            synthetic_affect_state=synthetic_affect_state,
            capital_sovereignty_decision=capital_sovereignty_decision,
            position_morph_plan=position_morph_plan,
            adaptive_exit_allocation=adaptive_exit_allocation,
            execution_simulation_report=execution_simulation_report,
            human_escalation_decision=human_escalation_decision,
            health_stage_ms=health_stage_ms,
            risk_stage_ms=risk_stage_ms,
            execution_stage_ms=execution_stage_ms,
        )


class LiveReconciliationCoordinator:
    def __init__(self, *, live_state: Any, ops: Any, settings: Any, observability: Any | None = None, forensics: Any | None = None) -> None:
        self.live_state = live_state
        self.ops = ops
        self.settings = settings
        self.observability = observability
        self.forensics = forensics

    def apply(self, *, live: object, symbol: str, exposure_notional: float, market_health: Any | None = None) -> LiveReconciliationResult:
        started = time.perf_counter()
        updated_exposure = exposure_notional
        try:
            report = self.live_state.reconcile_state(live, symbol, abs(exposure_notional), market_health=market_health)
            if not report.ok:
                self.ops.inc_metric("reconciliation_mismatch_total")
                self.ops.audit_event("reconcile", report.to_dict())
                if report.action.value == "halt_and_flatten" and hasattr(live, "flatten_all_positions"):
                    closed, flat_reason = live.flatten_all_positions()
                    if closed:
                        updated_exposure = 0.0
                    self.ops.audit_event("flatten", {"reason": flat_reason, "closed": closed, "from": "reconciliation"})
                elif report.action.value == "flatten_only" and hasattr(live, "enter_flatten_only"):
                    live.enter_flatten_only(f"reconciliation:{report.code}")
                if report.action.value in {"halt", "halt_and_flatten"} and hasattr(live, "request_kill"):
                    live.request_kill(f"reconciliation:{report.code}")
            if self.observability is not None:
                self.observability.journal("reconciliation_journal", report.to_dict())
                truth_confidence = report.details.get("truth_confidence")
                if truth_confidence is not None:
                    self.observability.journal("truth_confidence_journal", truth_confidence)
                unrealized_truth = report.details.get("exchange_unrealized_truth")
                if unrealized_truth is not None:
                    self.observability.journal("unrealized_pnl_truth_journal", unrealized_truth)
            if self.forensics is not None and not report.ok:
                self.forensics.record_runtime_anomaly(
                    symbol=symbol,
                    ts=datetime.utcnow(),
                    venue=str(getattr(getattr(live, "connector", None), "provider_id", "live")),
                    category="reconciliation",
                    reason=report.code,
                    truth_confidence=report.details.get("truth_confidence"),
                    evidence=report.to_dict(),
                )
            return LiveReconciliationResult(
                ok=report.ok,
                report=report,
                exposure_notional=updated_exposure,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
        except Exception as exc:
            self.ops.audit_event("reconcile_error", {"error": str(exc)})
            return LiveReconciliationResult(
                ok=False,
                report=None,
                exposure_notional=updated_exposure,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )


class LiveControlCoordinator:
    def __init__(
        self,
        *,
        ops: Any,
        incidents: Any,
        incident_responder: Any,
        notifier: Any | None = None,
        observability: Any | None = None,
    ) -> None:
        self.ops = ops
        self.incidents = incidents
        self.incident_responder = incident_responder
        self.notifier = notifier
        self.observability = observability

    def check_kill_file(self, *, live: object, kill_path: str, mode: str, steps: int) -> dict[str, Any] | None:
        if not os.path.exists(kill_path):
            return None
        if hasattr(live, "request_kill"):
            live.request_kill("kill_file_detected")
        flattened = None
        if hasattr(live, "flatten_all_positions"):
            try:
                flattened = live.flatten_all_positions()
            except Exception as exc:  # pragma: no cover
                flattened = (False, f"flatten_error:{exc}")
        self.ops.audit_event("kill_file", {"path": kill_path, "flattened": flattened})
        if self.observability is not None:
            self.observability.journal(
                "control_journal",
                {
                    "control_surface": "kill_file",
                    "action": "force_halt_and_flatten" if flattened is not None else "force_halt",
                    "mode": mode,
                    "steps": steps,
                    "kill_path": kill_path,
                    "flattened": flattened,
                },
            )
        self.ops.export_prometheus()
        return {"status": "stopped", "mode": mode, "reason": "kill_file_detected", "steps": steps, "flattened": flattened}

    def apply_meta_governor(self, *, live: object, meta_governor: Any | None, mode: str, steps: int, exposure_notional: float) -> LiveControlResult:
        if meta_governor is None:
            return LiveControlResult(exposure_notional=exposure_notional)
        if self.observability is not None:
            self.observability.journal(
                "control_journal",
                {
                    "control_surface": "meta_governor",
                    "action": meta_governor.action,
                    "mode": mode,
                    "steps": steps,
                    "size_multiplier": meta_governor.size_multiplier,
                    "forced_risk_mode": meta_governor.forced_risk_mode,
                    "reasons": list(getattr(meta_governor, "reasons", [])),
                    "degradation_applied": meta_governor.action
                    in {"force_flatten_only", "force_halt", "force_halt_and_flatten", "force_degraded", "force_defensive", "disable_symbol"},
                },
            )
        self.ops.audit_event(
            "meta_governor",
            {
                "action": meta_governor.action,
                "size_multiplier": meta_governor.size_multiplier,
                "forced_risk_mode": meta_governor.forced_risk_mode,
                "reasons": meta_governor.reasons,
            },
        )
        if meta_governor.action == "force_halt_and_flatten" and hasattr(live, "flatten_all_positions"):
            closed, flat_reason = live.flatten_all_positions()
            updated_exposure = 0.0 if closed else exposure_notional
            self.ops.audit_event("flatten", {"reason": flat_reason, "closed": closed, "from": "meta_governor"})
            self.ops.export_prometheus()
            self.ops.export_dashboard_snapshot()
            return LiveControlResult(
                exposure_notional=updated_exposure,
                stop_result={"status": "stopped", "mode": mode, "reason": "meta_governor", "steps": steps},
            )
        if meta_governor.action == "force_halt":
            self.ops.export_prometheus()
            self.ops.export_dashboard_snapshot()
            return LiveControlResult(
                exposure_notional=exposure_notional,
                stop_result={"status": "stopped", "mode": mode, "reason": "meta_governor", "steps": steps},
            )
        if meta_governor.action == "force_flatten_only":
            if hasattr(live, "enter_flatten_only"):
                live.enter_flatten_only("meta_governor")
            self.ops.export_prometheus()
            self.ops.export_dashboard_snapshot()
            return LiveControlResult(exposure_notional=exposure_notional, continue_loop=True)
        if meta_governor.action == "disable_symbol":
            self.ops.export_prometheus()
            self.ops.export_dashboard_snapshot()
            return LiveControlResult(exposure_notional=exposure_notional, continue_loop=True)
        return LiveControlResult(exposure_notional=exposure_notional)

    def apply_incidents(self, *, live: object, exposure_notional: float, mode: str, steps: int, risk_engine: Any | None = None) -> LiveControlResult:
        incident = self.incidents.evaluate(self.ops.metrics)
        if incident is None:
            return LiveControlResult(exposure_notional=exposure_notional)
        response = self.incident_responder.execute(incident, risk_engine=risk_engine, live_service=live)
        self.ops.audit_event("incident", {"action": incident.action, "reason": incident.reason, "kill": response.kill, "flatten_requested": response.flatten_requested})
        if self.observability is not None:
            self.observability.journal(
                "control_journal",
                {
                    "control_surface": "incident_policy",
                    "action": incident.action,
                    "reason": incident.reason,
                    "kill": response.kill,
                    "flatten_requested": response.flatten_requested,
                    "mode": mode,
                    "steps": steps,
                },
            )
        if self.notifier is not None:
            self.notifier.notify(incident.action, incident.reason)
        updated_exposure = exposure_notional
        if response.flatten_requested and hasattr(live, "flatten_all_positions"):
            try:
                closed, flat_reason = live.flatten_all_positions()
                if closed:
                    updated_exposure = 0.0
                self.ops.audit_event("flatten", {"reason": flat_reason, "closed": closed, "from": f"incident:{incident.reason}"})
            except Exception as exc:
                self.ops.audit_event("flatten_error", {"from": f"incident:{incident.reason}", "error": str(exc)})
        if response.kill:
            self.ops.export_prometheus()
            return LiveControlResult(
                exposure_notional=updated_exposure,
                stop_result={"status": "stopped", "mode": mode, "reason": f"incident:{incident.reason}", "steps": steps},
            )
        return LiveControlResult(exposure_notional=updated_exposure)


class LiveMetricsCoordinator:
    def __init__(self, *, ops: Any, risk: Any) -> None:
        self.ops = ops
        self.risk = risk

    def record_loop_state(
        self,
        *,
        mid: float,
        spread_bps: float,
        depth_notional: float,
        equity: float,
        peak: float,
        exposure_notional: float,
        health_snapshot: Any,
    ) -> None:
        self.ops.set_metric("mid_price", mid)
        self.ops.set_metric("spread_bps", spread_bps)
        self.ops.set_metric("depth_notional", depth_notional)
        self.ops.set_metric("equity", equity)
        self.ops.set_metric("drawdown", max(0.0, (1.0 - (equity / max(peak, 1e-9))) * 100.0))
        self.ops.set_metric("exposure_notional", abs(exposure_notional))
        self.ops.set_metric("kill_switch_state", 1.0 if self.risk.state.kill_switch else 0.0)
        self.ops.set_metric("health_score", health_snapshot.health_score)
