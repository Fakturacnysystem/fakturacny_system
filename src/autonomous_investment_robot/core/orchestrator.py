from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import time

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings, RolloutStage, UNSPECIFIED
from autonomous_investment_robot.core.contracts import DecisionCollapseTrace, DecisionStageBlocker, DecisionStageTrace, LearningRecord
from autonomous_investment_robot.core.contracts import RecoveryDecision
from autonomous_investment_robot.core.truth_ownership import ownership_gaps, ownership_map, validate_ownership_map
from autonomous_investment_robot.connectors.cex.binance_um_perps import BinanceUMPerpsConnector
from autonomous_investment_robot.connectors.cex.kraken_derivatives import KrakenDerivativesConnector
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector
from autonomous_investment_robot.services.alpha_service.service import AlphaService
from autonomous_investment_robot.services.adaptive_exit_allocator.service import AdaptiveExitAllocator
from autonomous_investment_robot.services.capital_sovereignty_service.service import CapitalSovereigntyService
from autonomous_investment_robot.services.compliance.service import ComplianceService
from autonomous_investment_robot.services.data_ingestion.service import DataIngestionService
from autonomous_investment_robot.services.data_qa.service import DataQAService
from autonomous_investment_robot.services.event_store.service import EventStore
from autonomous_investment_robot.services.event_intelligence_service.service import EventIntelligenceService
from autonomous_investment_robot.services.edge_immunity_service.service import EdgeImmunityService
from autonomous_investment_robot.services.execution_simulation_sandbox.service import ExecutionSimulationSandbox
from autonomous_investment_robot.services.execution.service import ExecutionService
from autonomous_investment_robot.services.execution.live_binance_service import LiveBinanceService
from autonomous_investment_robot.services.execution.live_kraken_service import LiveKrakenService
from autonomous_investment_robot.services.execution.live_kraken_spot_service import LiveKrakenSpotService
from autonomous_investment_robot.services.feature_store.service import FeatureStoreService
from autonomous_investment_robot.services.feature_store.service import FeatureVector
from autonomous_investment_robot.services.forensics_service.service import ForensicsService
from autonomous_investment_robot.services.health_service.service import HealthService
from autonomous_investment_robot.services.harmony_config_resolver.service import HarmonyConfigResolver
from autonomous_investment_robot.services.human_escalation_layer.service import HumanEscalationLayer
from autonomous_investment_robot.services.incident.service import IncidentPolicy, IncidentResponder, Notifier
from autonomous_investment_robot.services.learning_service.service import LearningService
from autonomous_investment_robot.services.live_runtime.coordination import (
    LiveControlCoordinator,
    LiveDecisionCoordinator,
    LiveMarketCoordinator,
    LiveMetricsCoordinator,
    LiveReconciliationCoordinator,
    LiveRecoveryCoordinator,
)
from autonomous_investment_robot.services.live_runtime.service import LiveLedgerCoordinator, LiveStateCoordinator
from autonomous_investment_robot.services.mastermind.service import MastermindService
from autonomous_investment_robot.services.market_data_service.service import MarketDataService
from autonomous_investment_robot.services.market_integrity_service.service import MarketIntegrityService
from autonomous_investment_robot.services.market_watch_service.service import MarketWatchService
from autonomous_investment_robot.services.mlops.service import MLOpsService
from autonomous_investment_robot.services.models.service import ModelsService
from autonomous_investment_robot.services.calibration_service.service import CalibrationService
from autonomous_investment_robot.services.capital_envelope.service import CapitalEnvelopeService
from autonomous_investment_robot.services.cost_model.service import FillAwareCostModelService
from autonomous_investment_robot.services.observability_facade.service import ObservabilityFacade
from autonomous_investment_robot.services.observability_service.service import ObservabilityService
from autonomous_investment_robot.services.operator_summary.service import OperatorSummaryCoordinator
from autonomous_investment_robot.services.oms.service import ManagedOrder, OMSService
from autonomous_investment_robot.services.ops.service import OpsService
from autonomous_investment_robot.services.paper_runtime.coordination import PaperRuntimeCoordinator
from autonomous_investment_robot.services.policy.service import OrderIntent, PolicyService
from autonomous_investment_robot.services.policy.playbooks.service import PlaybookFrameworkService
from autonomous_investment_robot.services.portfolio_service.service import PortfolioService
from autonomous_investment_robot.services.portfolio_allocator.service import PortfolioAllocatorService
from autonomous_investment_robot.services.position_morphing_service.service import PositionMorphingEngine
from autonomous_investment_robot.services.inventory_service.service import InventoryService
from autonomous_investment_robot.services.profitability_service.service import ProfitabilityService
from autonomous_investment_robot.services.quantum_state_service.service import QuantumStateService
from autonomous_investment_robot.services.raw_store.service import RawStoreService
from autonomous_investment_robot.services.reconciliation.service import ReconciliationService
from autonomous_investment_robot.services.regime_service.service import RegimeService
from autonomous_investment_robot.services.replay_reporting.service import ReplayReportingCoordinator
from autonomous_investment_robot.services.reporting_service.service import ReportingCoordinator
from autonomous_investment_robot.services.runtime_metadata.service import RuntimeMetadataService
from autonomous_investment_robot.services.performance_target_translation.service import PerformanceTargetTranslationService
from autonomous_investment_robot.services.market_microstructure.service import MarketMicrostructureService
from autonomous_investment_robot.services.universe.service import MarketUniverseService
from autonomous_investment_robot.services.autonomous_decision.service import AutonomousDecisionService
from autonomous_investment_robot.services.expectancy_engine.service import ExpectancyEngineService
from autonomous_investment_robot.services.experiments.service import ExperimentsService
from autonomous_investment_robot.services.exit_intelligence.service import ExitIntelligenceService
from autonomous_investment_robot.services.shadow_rival_service.service import ShadowRivalService
from autonomous_investment_robot.services.shared_venue_limit_governor.service import SharedVenueLimitGovernor
from autonomous_investment_robot.services.spre_service.service import SPREEngine
from autonomous_investment_robot.services.synthetic_affect_service.service import SyntheticAffectEngine
from autonomous_investment_robot.services.venue_capability_registry.service import VenueCapabilityRegistry
from autonomous_investment_robot.services.replay.events import AccountEvent, ComplianceEvent, FillEvent, OrderEvent, OrderIntentEvent, PositionEvent, RiskEvent, TruthEvent, make_event, make_idempotency_key
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


class RobotOrchestrator:
    def __init__(self, settings: RobotSettings) -> None:
        self.settings = settings
        self.ingestion = DataIngestionService()
        self.qa = DataQAService()
        self.raw = RawStoreService(settings.storage.run_dir)
        self.event_store = EventStore(settings.storage.run_dir)
        self.features = FeatureStoreService()
        self.models = ModelsService(regime_settings=settings.regime)
        self.market_data = MarketDataService()
        self.market_integrity = MarketIntegrityService()
        self.market_watch = MarketWatchService(settings)
        self.regime_service = RegimeService(settings.regime)
        self.alpha = AlphaService()
        self.calibration = CalibrationService(settings.storage.run_dir)
        self.quantum_state = QuantumStateService(calibration_service=self.calibration)
        self.edge_immunity = EdgeImmunityService(calibration_service=self.calibration)
        self.event_intelligence = EventIntelligenceService()
        self.synthetic_affect = SyntheticAffectEngine()
        self.capital_sovereignty = CapitalSovereigntyService()
        self.position_morphing = PositionMorphingEngine()
        self.adaptive_exit_allocator = AdaptiveExitAllocator()
        self.execution_simulation = ExecutionSimulationSandbox()
        self.human_escalation = HumanEscalationLayer(
            settings.storage.run_dir,
            ack_ttl_minutes=int(settings.monitoring.manual_review_ack_ttl_minutes),
        )
        self.harmony = HarmonyConfigResolver(settings)
        self.runtime_metadata = RuntimeMetadataService(settings)
        self.performance_targets = PerformanceTargetTranslationService(settings)
        self.policy = PolicyService(
            settings.policy,
            settings.allocator,
            settings.tco,
            spre_engine=SPREEngine(calibration_service=self.calibration),
            shadow_rival_service=ShadowRivalService(calibration_service=self.calibration),
            long_only=bool(settings.doctrine.long_only),
            target_provider=str(settings.doctrine_target_provider()),
            product_target=str(settings.doctrine_product_target()),
        )
        self.risk = RiskEngineService(settings.risk, safe_mode=settings.safe_mode_default)
        self.execution = ExecutionService(settings.execution)
        self.portfolio = PortfolioService()
        self.inventory = InventoryService()
        self.profitability = ProfitabilityService(
            base_safety_buffer_bps=float(settings.policy.safety_buffer_bps),
            min_free_quote_reserve_pct=float(settings.policy.min_free_quote_reserve_pct),
        )
        self.capital_envelope = CapitalEnvelopeService(settings)
        self.market_microstructure = MarketMicrostructureService(settings)
        self.market_universe = MarketUniverseService(settings)
        self.playbook_framework = PlaybookFrameworkService(settings)
        self.autonomous_decision = AutonomousDecisionService(settings)
        self.cost_model = FillAwareCostModelService(settings)
        self.performance_allocator = PortfolioAllocatorService(settings)
        self.expectancy_engine = ExpectancyEngineService(settings)
        self.experiments = ExperimentsService(settings)
        self.exit_intelligence = ExitIntelligenceService(settings)
        self.venue_capabilities = VenueCapabilityRegistry()
        self.shared_venue_limits = SharedVenueLimitGovernor()
        self.recon = ReconciliationService()
        self.live_state = LiveStateCoordinator(self.event_store, self.portfolio, self.recon, self.inventory)
        self.compliance = ComplianceService(settings.provider_whitelist)
        self.oms = OMSService()
        self.ops = OpsService(settings.storage.run_dir)
        self.health = HealthService()
        self.learning = LearningService(settings.storage.run_dir)
        self.base_observability = ObservabilityService(settings.storage.run_dir, self.ops)
        self.observability = ObservabilityFacade(self.base_observability)
        self.reporting = ReportingCoordinator(observability=self.observability)
        self.replay_reporting = ReplayReportingCoordinator(settings.storage.run_dir, self.observability)
        self.operator_summary = OperatorSummaryCoordinator(settings.storage.run_dir, self.observability)
        self.forensics = ForensicsService(settings.storage.run_dir, self.observability)
        self.live_ledger = LiveLedgerCoordinator(self.event_store, self.portfolio, self.observability, self.forensics, self.inventory)
        self.incidents = IncidentPolicy()
        self.incident_responder = IncidentResponder()
        self.notifier = Notifier()
        self.mastermind = MastermindService()
        self.mlops = MLOpsService(settings.mlops.rollback_dd_threshold_pct, settings.mlops.drift_psi_threshold)
        self.live_market = LiveMarketCoordinator(
            features_service=self.features,
            market_data=self.market_data,
            models=self.models,
            regime_service=self.regime_service,
            mastermind=self.mastermind,
            execution=self.execution,
            alpha=self.alpha,
            portfolio=self.portfolio,
            quantum_state_service=self.quantum_state,
            edge_immunity_service=self.edge_immunity,
            observability=self.observability,
            settings=self.settings,
            ops=self.ops,
            market_integrity_service=self.market_integrity,
            venue_capability_registry=self.venue_capabilities,
            shared_venue_limit_governor=self.shared_venue_limits,
            event_intelligence_service=self.event_intelligence,
            market_watch_service=self.market_watch,
            data_ingestion_service=self.ingestion,
            reporting=self.reporting,
        )
        self.live_decision = LiveDecisionCoordinator(
            health=self.health,
            policy=self.policy,
            risk=self.risk,
            execution=self.execution,
            mastermind=self.mastermind,
            profitability=self.profitability,
            inventory=self.inventory,
            reporting=self.reporting,
            capital_sovereignty=self.capital_sovereignty,
            position_morphing=self.position_morphing,
            adaptive_exit_allocator=self.adaptive_exit_allocator,
            synthetic_affect=self.synthetic_affect,
            execution_simulation_sandbox=self.execution_simulation,
            human_escalation_layer=self.human_escalation,
            observability=self.observability,
            settings=self.settings,
        )
        self.live_recovery = LiveRecoveryCoordinator(
            live_state=self.live_state,
            settings=self.settings,
            observability=self.observability,
            forensics=self.forensics,
        )
        self.live_reconciliation = LiveReconciliationCoordinator(
            live_state=self.live_state,
            ops=self.ops,
            settings=self.settings,
            observability=self.observability,
            forensics=self.forensics,
        )
        self.live_control = LiveControlCoordinator(
            ops=self.ops,
            incidents=self.incidents,
            incident_responder=self.incident_responder,
            notifier=self.notifier,
            observability=self.observability,
        )
        self.live_metrics = LiveMetricsCoordinator(ops=self.ops, risk=self.risk)
        self.paper_runtime = PaperRuntimeCoordinator(
            settings=self.settings,
            ingestion=self.ingestion,
            qa=self.qa,
            market_data=self.market_data,
            raw=self.raw,
            event_store=self.event_store,
            features=self.features,
            models=self.models,
            regime_service=self.regime_service,
            alpha=self.alpha,
            policy=self.policy,
            risk=self.risk,
            execution=self.execution,
            oms=self.oms,
            portfolio=self.portfolio,
            recon=self.recon,
            ops=self.ops,
            learning=self.learning,
            forensics=self.forensics,
            observability=self.observability,
            inventory=self.inventory,
            profitability=self.profitability,
            reporting=self.reporting,
            harmony_resolver=self.harmony,
            market_integrity_service=self.market_integrity,
            venue_capability_registry=self.venue_capabilities,
            market_watch_service=self.market_watch,
            replay_reporting=self.replay_reporting,
            operator_summary=self.operator_summary,
            quantum_state_service=self.quantum_state,
            edge_immunity_service=self.edge_immunity,
            event_intelligence_service=self.event_intelligence,
            synthetic_affect_service=self.synthetic_affect,
            capital_sovereignty_service=self.capital_sovereignty,
            position_morphing_service=self.position_morphing,
            adaptive_exit_allocator=self.adaptive_exit_allocator,
            execution_simulation_sandbox=self.execution_simulation,
            human_escalation_layer=self.human_escalation,
            mastermind_service=self.mastermind,
            incidents=self.incidents,
            notifier=self.notifier,
            mlops=self.mlops,
            legacy_risk_details=self._legacy_risk_details,
            legacy_fill_payload=self._legacy_fill_payload,
        )
        self._live_runtime_diagnostics = self._fresh_live_runtime_diagnostics()
        self._last_live_preflight_ok = False
        self._last_live_ordering_allowed = False
        self._last_live_blocking_reasons: list[str] = []

    def _legacy_policy_why(self, why: dict) -> dict:
        keys = [
            "confidence",
            "regime",
            "liquidity_regime",
            "weights",
            "weights_net_after_costs",
            "veto_counts",
            "strategy_regime_cooldowns",
            "components",
            "decision_doctrine",
            "execution_simulation",
            "market_integrity",
            "provider_capability",
            "capital_sovereignty",
            "position_morph",
            "adaptive_exit",
            "synthetic_affect",
            "human_escalation",
            "event_intelligence",
            "mastermind",
        ]
        return {key: why[key] for key in keys if key in why}

    def _legacy_risk_details(self, details: dict) -> dict:
        keys = ["crowding_score", "crowding_level", "crowding_components", "funding_budget_utilization"]
        return {key: details[key] for key in keys if key in details}

    def _legacy_fill_payload(self, fill: object) -> dict:
        payload = asdict(fill)
        if not payload.get("metadata"):
            payload.pop("metadata", None)
        return payload

    def _missing_limits(self) -> bool:
        req = [
            self.settings.risk.max_daily_loss_pct,
            self.settings.risk.max_drawdown_pct,
            self.settings.risk.max_position_notional,
            self.settings.risk.max_exposure_notional,
            self.settings.risk.max_orders_per_min,
            self.settings.risk.leverage,
            self.settings.risk.max_spread_bps,
            self.settings.risk.min_depth_notional,
            self.settings.risk.stale_data_seconds,
            self.settings.risk.min_margin_buffer,
            self.settings.risk.max_funding_cost_per_day,
            self.settings.risk.max_oi_spike_pct,
            self.settings.risk.max_liquidation_spike,
            self.settings.risk.divergence_threshold_bps,
            self.settings.risk.crowding_score_kill,
            self.settings.tco.max_total_cost_bps,
            self.settings.tco.max_impact_bps,
        ]
        return any(v == UNSPECIFIED for v in req)

    def _maybe_warn_latency(self, metric_name: str, elapsed_ms: float, budget_ms: float) -> None:
        self.ops.set_metric(metric_name, elapsed_ms)
        if elapsed_ms > budget_ms:
            self.ops.inc_metric("latency_budget_breach_total")
            self.ops.audit_event("latency_budget_warning", {"metric": metric_name, "elapsed_ms": elapsed_ms, "budget_ms": budget_ms})

    def _exchange_exposure(self, live: object, symbol: str) -> tuple[float, int]:
        exchange = self.live_state.exchange_state(live, symbol)
        return exchange.exposure_notional, exchange.position_count

    def _rehydrate_live_state(self, live: object, symbol: str) -> tuple[str, dict]:
        result = self.live_state.rehydrate_state(live, symbol)
        return result.confidence, result.details

    def _recover_live_state(self, live: object, symbol: str, restart_confidence: str):
        return self.live_state.recover_inflight_state(
            live,
            symbol,
            restart_confidence=restart_confidence,
            safe_mode_requested=bool(self.settings.safe_mode_default),
        )

    def _kill_file_path(self) -> str:
        return os.path.join(self.settings.storage.run_dir, "KILL")

    def _pause_file_path(self) -> str:
        return os.path.join(self.settings.storage.run_dir, "PAUSE.json")

    def _pause_marker(self) -> dict[str, object] | None:
        path = Path(self._pause_file_path())
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        reason = str(payload.get("reason", "")).strip() or "operator_pause"
        requested_at = str(payload.get("requested_at", "")).strip()
        return {
            "pause_path": str(path),
            "reason": reason,
            "requested_at": requested_at,
        }

    def _doctrine_block_map(self) -> dict[str, list[str]]:
        return {
            "strategies": [
                "DeltaNeutralCarryStrategy",
                "BasisStrategy",
                "PairsStatArbStrategy",
                "CarryStrategy",
                "negative_directional_entries_from_trend_or_mean_reversion",
            ],
            "paths": [
                "derivatives_perps_configs",
                "derivatives_perps_launch_scripts",
                "derivative_live_services",
                "fresh_sell_entries_without_reduce_only_inventory",
            ],
            "provider_product_modes": [
                "binance_um_perps",
                "kraken_derivatives",
                "perps",
                "short_opening_modes",
            ],
        }

    def _write_json_artifact(self, name: str, payload: object) -> str:
        path = Path(self.settings.storage.run_dir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        return str(path)

    def _append_jsonl_artifact(self, name: str, payload: object) -> str:
        path = Path(self.settings.storage.run_dir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8") if not path.exists() else None
        serializable = self._serialize_payload(payload)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(serializable, sort_keys=True, default=str) + "\n")
        return str(path)

    def _serialize_payload(self, payload: object) -> object:
        if payload is None:
            return None
        try:
            return json.loads(json.dumps(payload, sort_keys=True, default=lambda value: asdict(value) if hasattr(value, "__dataclass_fields__") else getattr(value, "__dict__", str(value))))
        except Exception:
            return str(payload)

    def _read_json_artifact(self, name: str) -> object:
        path = Path(self.settings.storage.run_dir) / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _read_jsonl_artifact(self, name: str) -> list[dict[str, object]]:
        path = Path(self.settings.storage.run_dir) / name
        if not path.exists():
            return []
        rows: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    def _regime_architecture_reports(self, *, symbol: str, market: object) -> dict[str, object]:
        assessment = getattr(market, "regime_assessment", None)
        if assessment is None:
            return {
                "regime_snapshot": {},
                "regime_transition_log": {},
                "regime_pair_matrix": {},
                "regime_hysteresis_report": {},
                "regime_exit_family_report": {},
            }
        evidence = dict(getattr(assessment, "evidence", {}) or {})
        label = str(getattr(assessment, "label", "unavailable") or "unavailable")
        exit_family = str(evidence.get("regime_exit_family", "alpha_capture_exit") or "alpha_capture_exit")
        ts = datetime.now(timezone.utc).isoformat()
        return {
            "regime_snapshot": {
                "ts": ts,
                "symbol": symbol,
                "label": label,
                "confidence": float(getattr(assessment, "confidence", 0.0) or 0.0),
                "persistence": float(getattr(assessment, "persistence", 0.0) or 0.0),
                "transition_probability": float(getattr(assessment, "transition_probability", 0.0) or 0.0),
                "uncertainty": float(evidence.get("regime_uncertainty", 0.0) or 0.0),
                "evidence": evidence,
            },
            "regime_transition_log": {
                "ts": ts,
                "symbol": symbol,
                "previous_label": str(evidence.get("previous_label", "") or ""),
                "current_label": label,
                "transition_probability": float(getattr(assessment, "transition_probability", 0.0) or 0.0),
                "hysteresis_applied": bool(float(evidence.get("hysteresis_applied", 0.0) or 0.0) > 0.0),
            },
            "regime_pair_matrix": {
                "ts": ts,
                "pairs": {symbol: {"regime": label, "confidence": float(getattr(assessment, "confidence", 0.0) or 0.0)}},
            },
            "regime_hysteresis_report": {
                "ts": ts,
                "symbol": symbol,
                "previous_label": str(evidence.get("previous_label", "") or ""),
                "current_label": label,
                "hysteresis_applied": bool(float(evidence.get("hysteresis_applied", 0.0) or 0.0) > 0.0),
            },
            "regime_exit_family_report": {
                "ts": ts,
                "symbol": symbol,
                "preferred_exit_family": exit_family,
                "degradation_warning": str(getattr(assessment, "degradation_warning", "") or ""),
            },
        }

    def _performance_architecture_artifacts(
        self,
        *,
        symbol: str,
        market: object,
        decision_ctx: object,
        health_summary: dict[str, object],
        runtime_ordering_allowed: bool,
        execution_result: object | None = None,
    ) -> dict[str, object]:
        fills = self._read_jsonl_artifact("events_fills.jsonl")
        order_events = self._read_jsonl_artifact("events_orders.jsonl")
        trade_log_payload = self._read_json_artifact("trade_log.json")
        trade_log = trade_log_payload if isinstance(trade_log_payload, list) else []
        capital_bundle = self.capital_envelope.summarize(
            reserve_state=getattr(decision_ctx, "reserve_state", None),
            inventory_state=getattr(decision_ctx, "inventory_state", None),
            portfolio_allocation=getattr(market, "portfolio_allocation", None),
            execution_plan=getattr(decision_ctx, "execution_plan", None),
            execution_result=execution_result,
        )
        microstructure = self.market_microstructure.analyze(
            symbol=symbol,
            market=market,
            execution_result=execution_result,
        )
        expectancy_bundle = self.expectancy_engine.build(
            fills=fills,
            order_events=order_events,
            trade_log=trade_log if isinstance(trade_log, list) else [],
            ranked_candidates=[],
        )
        playbook_bundle = self.playbook_framework.evaluate(
            symbol=symbol,
            forecast=getattr(market, "forecast", None),
            regime_assessment=getattr(market, "regime_assessment", None),
            features=dict(getattr(market, "features", {}) or {}),
            execution_quality=getattr(market, "execution_quality", None),
            inventory_state=getattr(decision_ctx, "inventory_state", None),
            expectancy_report=dict(expectancy_bundle.get("report", {}) or {}),
        )
        decision_bundle = self.autonomous_decision.evaluate(
            candidates=list(playbook_bundle.get("candidates", []) or []),
            capital_envelope=dict(capital_bundle.get("capital_envelope_summary", {}) or {}),
            expectancy=dict(expectancy_bundle.get("report", {}) or {}),
            runtime_ordering_allowed=runtime_ordering_allowed,
        )
        expectancy_bundle = self.expectancy_engine.build(
            fills=fills,
            order_events=order_events,
            trade_log=trade_log if isinstance(trade_log, list) else [],
            ranked_candidates=list(dict(decision_bundle.get("decision_ranking_explainability", {}) or {}).get("ranked_candidates", []) or []),
        )
        universe_bundle = self.market_universe.evaluate(
            symbol=symbol,
            microstructure=microstructure,
            expectancy=dict(expectancy_bundle.get("report", {}) or {}),
            capital_envelope=dict(capital_bundle.get("capital_envelope_summary", {}) or {}),
            regime_label=str(getattr(getattr(market, "regime_assessment", None), "label", "") or ""),
            provider_capability=getattr(market, "provider_capability", None),
        )
        allocator_bundle = self.performance_allocator.allocate(
            capital_envelope=dict(capital_bundle.get("capital_envelope_summary", {}) or {}),
            expectancy=dict(expectancy_bundle.get("report", {}) or {}),
            selected_candidate=decision_bundle.get("selected_candidate") if isinstance(decision_bundle, dict) else None,
        )
        experiments_bundle = self.experiments.evaluate(
            playbook_candidates=list(playbook_bundle.get("candidates", []) or []),
            expectancy=dict(expectancy_bundle.get("report", {}) or {}),
            health_summary=health_summary,
        )
        performance_translation, performance_gap = self.performance_targets.translate(
            capital_envelope=dict(capital_bundle.get("capital_envelope_summary", {}) or {}),
            expectancy=dict(expectancy_bundle.get("report", {}) or {}),
            throughput=self._throughput_snapshot(),
        )
        cost_bundle = self.cost_model.analyze(
            market=market,
            execution_plan=getattr(decision_ctx, "execution_plan", None),
            execution_quality=getattr(market, "execution_quality", None),
            execution_result=execution_result,
        )
        exit_bundle = self.exit_intelligence.analyze(
            inventory_state=getattr(decision_ctx, "inventory_state", None),
            profitability_context=getattr(decision_ctx, "profitability_context", None),
            market=market,
            execution_result=execution_result,
        )
        regime_bundle = self._regime_architecture_reports(symbol=symbol, market=market)
        selected_candidate = decision_bundle.get("selected_candidate") if isinstance(decision_bundle, dict) else None
        provider_capability = self._serialize_payload(getattr(market, "provider_capability", None))
        private_stream_health = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "user_stream_confidence": None if not isinstance(provider_capability, dict) else provider_capability.get("user_stream_confidence"),
            "lifecycle_completeness": None if not isinstance(provider_capability, dict) else provider_capability.get("lifecycle_completeness"),
            "status": "healthy"
            if isinstance(provider_capability, dict) and str(provider_capability.get("user_stream_confidence", "")).startswith("authoritative")
            else "degraded",
        }
        execution_lifecycle_report = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "status": None if execution_result is None else str(getattr(execution_result, "status", "")),
            "reason": None if execution_result is None else str(getattr(execution_result, "reason", "")),
            "lifecycle_proof": {}
            if execution_result is None
            else dict((((getattr(execution_result, "metadata", {}) or {})).get("lifecycle_proof", {}) if isinstance(getattr(execution_result, "metadata", {}) or {}, dict) else {})),
        }
        order_reject_taxonomy = dict(health_summary.get("failure_taxonomy", {}) or {})
        maker_first_effectiveness = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "maker_probability": dict(cost_bundle.get("maker_taker_mix_report", {}) or {}).get("maker_probability"),
            "selected_execution_preference": None if not isinstance(selected_candidate, dict) else selected_candidate.get("execution_preference"),
        }
        selected_quality = 0.0 if not isinstance(selected_candidate, dict) else float(selected_candidate.get("quality_of_edge", 0.0) or 0.0)
        execution_quality_bucket_report = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "quality_bucket": "high" if selected_quality >= 0.75 else "medium" if selected_quality >= 0.50 else "low",
            "quality_of_edge": selected_quality,
            "fill_probability": None if getattr(market, "execution_quality", None) is None else float(getattr(market.execution_quality, "fill_probability", 0.0) or 0.0),
        }
        entry_timing_optimizer_report = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "selected_playbook": None if not isinstance(selected_candidate, dict) else selected_candidate.get("playbook"),
            "opportunity_decay": None if not isinstance(selected_candidate, dict) else selected_candidate.get("opportunity_decay"),
            "recommended_entry_style": None if not isinstance(selected_candidate, dict) else selected_candidate.get("execution_preference"),
        }
        cadence = max(1.0, float(self.harmony.resolve().get("order_cadence_s", 5.0) or 5.0))
        adaptive_cadence_report = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "base_order_cadence_s": cadence,
            "backlog_pressure": dict(decision_bundle.get("opportunity_backlog_report", {}) or {}).get("backlog_pressure"),
            "recommended_cadence_s": round(cadence * (1.25 if runtime_ordering_allowed else 2.0), 3),
        }
        live_degradation_score = max(
            float(dict(cost_bundle.get("live_degradation_delta_report", {}) or {}).get("live_degradation_delta", 0.0) or 0.0),
            1.0 if health_summary.get("blocking_reasons") else 0.0,
        )
        live_degradation_detector_report = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "live_degradation_score": live_degradation_score,
            "status": "degraded" if live_degradation_score >= float(self.settings.operator_kpis.live_degradation_warn) else "stable",
            "blocking_reasons": list(health_summary.get("blocking_reasons", []) or []),
        }
        self_throttling_state_report = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "active": not runtime_ordering_allowed or live_degradation_score >= float(self.settings.operator_kpis.live_degradation_warn),
            "reason": "runtime_blocked" if not runtime_ordering_allowed else "live_degradation" if live_degradation_score >= float(self.settings.operator_kpis.live_degradation_warn) else "none",
            "aggressiveness_scalar": dict(allocator_bundle.get("aggressiveness_scaler_report", {}) or {}).get("aggressiveness_scalar"),
        }
        dead_capital_bundle = {
            "capital_utilization_report": capital_bundle.get("capital_utilization_report", {}),
            "opportunity_miss_journal": decision_bundle.get("opportunity_miss_journal", {}),
            "no_trade_histogram": decision_bundle.get("no_trade_reason_histogram", {}),
            "deployment_efficiency_report": capital_bundle.get("deployment_efficiency_report", {}),
            "dead_capital_pressure_report": capital_bundle.get("dead_capital_pressure_report", {}),
        }
        return {
            **capital_bundle,
            "performance_target_translation": performance_translation,
            "performance_gap_report": performance_gap,
            **universe_bundle,
            **regime_bundle,
            **playbook_bundle,
            **decision_bundle,
            **exit_bundle,
            **cost_bundle,
            "private_stream_health": private_stream_health,
            "execution_lifecycle_report": execution_lifecycle_report,
            "order_reject_taxonomy": order_reject_taxonomy,
            "maker_first_effectiveness": maker_first_effectiveness,
            "execution_quality_bucket_report": execution_quality_bucket_report,
            "entry_timing_optimizer_report": entry_timing_optimizer_report,
            "adaptive_cadence_report": adaptive_cadence_report,
            "live_degradation_detector_report": live_degradation_detector_report,
            "self_throttling_state_report": self_throttling_state_report,
            **allocator_bundle,
            **{key: value for key, value in expectancy_bundle.items() if key != "report"},
            **experiments_bundle,
            **dead_capital_bundle,
        }

    def _jsonl_count(self, name: str) -> int:
        path = Path(self.settings.storage.run_dir) / f"{name}.jsonl"
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    def _fresh_live_runtime_diagnostics(self) -> dict[str, object]:
        return {
            "loop_steps": 0,
            "execution_attempts": 0,
            "orders_submitted": 0,
            "orders_rejected": 0,
            "orders_blocked": 0,
            "fills": 0,
            "deduped": 0,
            "no_intent": 0,
            "risk_rejected": 0,
            "meta_governor_blocks": 0,
            "reconciliation_blocks": 0,
            "surface_counts": {},
            "reason_counts": {},
            "failure_taxonomy": {},
        }

    def _failure_taxonomy_bucket(self, reason: str) -> str:
        normalized = str(reason or "").lower()
        if "stale" in normalized or "book_invalid" in normalized:
            return "stale_data"
        if "spread" in normalized:
            return "spread_explosion"
        if "reconciliation" in normalized:
            return "reconciliation_mismatch"
        if "daily_loss" in normalized:
            return "daily_loss"
        if "weekly_loss" in normalized:
            return "weekly_loss"
        if "invalid key" in normalized or "missing_credentials" in normalized or "auth" in normalized:
            return "invalid_auth"
        if "nonce" in normalized:
            return "invalid_nonce"
        if "permission" in normalized:
            return "permission_denied"
        if "insufficient_quote" in normalized or "reserve_breach" in normalized:
            return "insufficient_quote"
        if "no_trade" in normalized or "edge" in normalized or "round_trip_non_viable" in normalized:
            return "no_edge_after_costs"
        if "strategy" in normalized or "shadow_rival" in normalized or "spre" in normalized:
            return "strategy_gated"
        if "min_notional" in normalized or "below_min_notional" in normalized:
            return "exchange_min_notional_failure"
        if "dedupe" in normalized or "duplicate" in normalized:
            return "idempotency_duplicate_risk"
        if "rate_limit" in normalized:
            return "rate_limit_storm"
        return "other"

    def _record_live_reason(self, *, reason: str, surface: str) -> None:
        diagnostics = self._live_runtime_diagnostics
        surface_counts = diagnostics["surface_counts"]
        reason_counts = diagnostics["reason_counts"]
        failure_taxonomy = diagnostics["failure_taxonomy"]
        surface_counts[surface] = int(surface_counts.get(surface, 0)) + 1
        if reason:
            reason_counts[reason] = int(reason_counts.get(reason, 0)) + 1
            bucket = self._failure_taxonomy_bucket(reason)
            failure_taxonomy[bucket] = int(failure_taxonomy.get(bucket, 0)) + 1

    def _throughput_snapshot(self) -> dict[str, object]:
        diagnostics = self._live_runtime_diagnostics
        attempts = max(1, int(diagnostics["execution_attempts"]))
        submissions = int(diagnostics["orders_submitted"])
        fills = int(diagnostics["fills"])
        return {
            **diagnostics,
            "submission_efficiency": submissions / attempts,
            "fill_efficiency": fills / max(1, submissions),
        }

    def _trade_path_state(self, *, decision_ctx: object, execution_result: object | None = None) -> str:
        if execution_result is not None:
            metadata = getattr(execution_result, "metadata", {}) or {}
            proof = metadata.get("lifecycle_proof", {}) if isinstance(metadata, dict) else {}
            status = str(getattr(execution_result, "status", "") or "").lower()
            if isinstance(proof, dict):
                if bool(proof.get("reconciliation_complete", False)):
                    return "reconciled"
                if status in {"rejected", "timed_out", "timeout", "killed"}:
                    return "terminal_observed"
                if bool(proof.get("terminal_observed", False)):
                    return "terminal_observed"
                if status in {"accepted", "working"}:
                    return "acknowledged"
                if bool(proof.get("exchange_acknowledged", False)):
                    return "acknowledged"
                if status in {"submitted"}:
                    return "submitted"
                if bool(proof.get("submitted", False)):
                    return "submitted"
            if status in {"submitted"}:
                return "submitted"
            if status in {"accepted", "working"}:
                return "acknowledged"
            if "filled" in status or status in {"cancelled", "canceled", "rejected", "timed_out", "timeout", "killed"}:
                return "terminal_observed"
        if getattr(decision_ctx, "adjusted_intent", None) is not None:
            return "intent_created"
        if getattr(decision_ctx, "policy_decision", None) is not None:
            return "blocked_by_decision"
        return "not_attempted"

    def _decision_blocker(
        self,
        *,
        stage: str,
        code: str,
        classification: str,
        contribution: float,
        hard: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> DecisionStageBlocker:
        return DecisionStageBlocker(
            stage=stage,
            code=code,
            classification=classification,
            contribution=max(0.0, min(1.0, float(contribution))),
            hard=hard,
            metadata={} if metadata is None else dict(metadata),
        )

    def _blocker_priority(self, blocker: DecisionStageBlocker) -> tuple[int, int, float]:
        classification = str(blocker.classification or "")
        priority_map = {
            "exchange_reject": 8,
            "affordability_veto": 7,
            "execution_blocker": 6,
            "hard": 5,
            "decision_layer_veto": 4,
            "heuristic": 3,
            "soft": 2,
            "promotion_blocker": 1,
            "confidence_haircut": 0,
            "informational_only": -1,
        }
        return (
            priority_map.get(classification, 1),
            1 if bool(blocker.hard) else 0,
            float(blocker.contribution or 0.0),
        )

    def _dedupe_ranked_blockers(self, blockers: list[DecisionStageBlocker]) -> list[DecisionStageBlocker]:
        deduped: dict[tuple[str, str], DecisionStageBlocker] = {}
        for blocker in blockers:
            key = (str(blocker.stage or ""), str(blocker.code or ""))
            incumbent = deduped.get(key)
            if incumbent is None or self._blocker_priority(blocker) > self._blocker_priority(incumbent):
                deduped[key] = blocker
        return sorted(deduped.values(), key=self._blocker_priority, reverse=True)

    def _blocker_type(self, blocker: object | None) -> str | None:
        if blocker is None:
            return None
        if isinstance(blocker, DecisionStageBlocker):
            stage = str(blocker.stage or "")
            code = str(blocker.code or "")
            classification = str(blocker.classification or "")
            metadata = dict(blocker.metadata or {})
        elif isinstance(blocker, dict):
            stage = str(blocker.get("stage", "") or "")
            code = str(blocker.get("code", "") or "")
            classification = str(blocker.get("classification", "") or "")
            metadata = dict(blocker.get("metadata", {}) or {})
        else:
            return None
        explicit = str(metadata.get("blocker_type", "") or "").strip()
        if explicit:
            return explicit
        normalized = code.lower()
        if classification == "affordability_veto" or self._failure_taxonomy_bucket(code) == "insufficient_quote":
            return "affordability_veto"
        if classification == "exchange_reject" or "reject" in normalized or "insufficient funds" in normalized:
            return "exchange_reject"
        if stage == "provider_capability" or classification in {"promotion_blocker", "confidence_haircut", "informational_only"}:
            return "observability_gap"
        return "decision_layer_veto"

    def _policy_gate_trace(
        self,
        *,
        policy: object | None,
        decision_ctx: object,
        trade_path_state: str,
    ) -> tuple[DecisionStageTrace | None, list[DecisionStageBlocker]]:
        if policy is None or bool(getattr(policy, "trade_allowed", False)) or getattr(decision_ctx, "adjusted_intent", None) is not None:
            return None, []

        why = {} if not isinstance(getattr(policy, "why", None), dict) else dict(policy.why or {})
        no_trade = getattr(policy, "no_trade", None)
        no_trade_metadata = self._serialize_payload(getattr(no_trade, "metadata", None))
        if not why and isinstance(no_trade_metadata, dict):
            why = dict(no_trade_metadata)
        profitability = {}
        for candidate in (why.get("profitability"), getattr(policy, "profitability", None)):
            if isinstance(candidate, dict) and candidate:
                profitability = dict(candidate)
                break
        round_trip = dict(profitability.get("round_trip", {}) or {})
        capital_release = dict(profitability.get("capital_release", {}) or {})
        capital_release_meta = dict(capital_release.get("metadata", {}) or {})
        reserve_state = dict(capital_release_meta.get("reserve_state", {}) or {})
        capital_sovereignty = dict(why.get("capital_sovereignty", {}) or {})
        human_escalation = dict(why.get("human_escalation", {}) or {})

        blockers: list[DecisionStageBlocker] = []
        extracted_codes: set[str] = set()
        reasons: list[str] = []
        affordability_meta = {
            "blocker_type": "affordability_veto",
            "quote_asset": reserve_state.get("quote_asset"),
            "free_quote_balance": reserve_state.get("quote_free_balance", reserve_state.get("free_quote")),
            "quote_total_balance": reserve_state.get("quote_total_balance"),
            "entry_buying_power_quote": reserve_state.get("entry_buying_power_quote"),
            "required_quote_with_fee_buffer": reserve_state.get("required_quote_with_fee_buffer"),
            "reserve_floor_quote": reserve_state.get("reserve_floor_quote"),
            "reserve_breached": bool(reserve_state.get("reserve_breached", False)),
            "affordability_source": dict(reserve_state.get("metadata", {}) or {}).get("affordability_source"),
        }
        for code in list(reserve_state.get("reasons", []) or []):
            normalized = str(code or "").strip()
            if not normalized or normalized in extracted_codes:
                continue
            if self._failure_taxonomy_bucket(normalized) == "insufficient_quote":
                blockers.append(
                    self._decision_blocker(
                        stage="final_execution_gate",
                        code=normalized,
                        classification="affordability_veto",
                        contribution=1.0,
                        hard=True,
                        metadata=affordability_meta,
                    )
                )
                extracted_codes.add(normalized)
                reasons.append(normalized)
        for code in list(round_trip.get("reasons", []) or []):
            normalized = str(code or "").strip()
            if not normalized or normalized in extracted_codes:
                continue
            classification = "affordability_veto" if self._failure_taxonomy_bucket(normalized) == "insufficient_quote" else "soft"
            blockers.append(
                self._decision_blocker(
                    stage="final_execution_gate",
                    code=normalized,
                    classification=classification,
                    contribution=0.95 if classification == "affordability_veto" else 0.55,
                    hard=classification == "affordability_veto",
                    metadata=affordability_meta if classification == "affordability_veto" else {"blocker_type": "decision_layer_veto"},
                )
            )
            extracted_codes.add(normalized)
            reasons.append(normalized)

        sovereignty_action = str(capital_sovereignty.get("action", "") or "")
        if sovereignty_action in {"no_trade", "wait", "probe_only"}:
            sovereignty_reason = "capital_sovereignty_no_trade" if sovereignty_action == "no_trade" else "capital_sovereignty_probe_only" if sovereignty_action == "probe_only" else "capital_sovereignty_wait"
            if sovereignty_reason not in extracted_codes:
                blockers.append(
                    self._decision_blocker(
                        stage="final_execution_gate",
                        code=sovereignty_reason,
                        classification="decision_layer_veto" if sovereignty_action == "no_trade" else "soft",
                        contribution=0.85 if sovereignty_action == "no_trade" else 0.6,
                        hard=sovereignty_action == "no_trade",
                        metadata={
                            "blocker_type": "decision_layer_veto",
                            "action": sovereignty_action,
                            "reserve_pressure": capital_sovereignty.get("reserve_pressure"),
                            "probe_ratio": capital_sovereignty.get("probe_ratio"),
                        },
                    )
                )
                extracted_codes.add(sovereignty_reason)
                reasons.append(sovereignty_reason)

        escalation_action = str(human_escalation.get("action", "") or "")
        if escalation_action in {"manual_review", "flatten_only"}:
            escalation_reason = "human_escalation_manual_review" if escalation_action == "manual_review" else "human_escalation_flatten_only"
            if escalation_reason not in extracted_codes:
                blockers.append(
                    self._decision_blocker(
                        stage="final_execution_gate",
                        code=escalation_reason,
                        classification="decision_layer_veto",
                        contribution=0.9 if escalation_action == "flatten_only" else 0.75,
                        hard=True,
                        metadata={
                            "blocker_type": "decision_layer_veto",
                            "action": escalation_action,
                            "severity": human_escalation.get("severity"),
                            "disagreement_score": human_escalation.get("disagreement_score"),
                        },
                    )
                )
                extracted_codes.add(escalation_reason)
                reasons.append(escalation_reason)

        no_trade_reason = str(getattr(no_trade, "reason", "") or "")
        if no_trade_reason and no_trade_reason not in extracted_codes:
            blockers.append(
                self._decision_blocker(
                    stage="final_execution_gate",
                    code=no_trade_reason,
                    classification="decision_layer_veto",
                    contribution=0.5,
                    hard=False,
                    metadata={"blocker_type": "decision_layer_veto"},
                )
            )
            extracted_codes.add(no_trade_reason)
            reasons.append(no_trade_reason)

        if not blockers:
            return None, []

        return (
            DecisionStageTrace(
                stage="final_execution_gate",
                action=trade_path_state,
                raw_inputs={
                    "policy_no_trade_reason": no_trade_reason,
                    "round_trip_action": round_trip.get("action"),
                    "capital_release_action": capital_release.get("action"),
                    "capital_sovereignty_action": sovereignty_action,
                    "human_escalation_action": escalation_action,
                },
                normalized_inputs={
                    "trade_path_state": trade_path_state,
                    "quote_free_balance": reserve_state.get("quote_free_balance", reserve_state.get("free_quote")),
                    "quote_total_balance": reserve_state.get("quote_total_balance"),
                    "entry_buying_power_quote": reserve_state.get("entry_buying_power_quote"),
                    "reserve_floor_quote": reserve_state.get("reserve_floor_quote"),
                    "required_quote_with_fee_buffer": reserve_state.get("required_quote_with_fee_buffer"),
                },
                scores={
                    "round_trip_size_multiplier": float(round_trip.get("recommended_size_multiplier", 0.0) or 0.0),
                    "capital_release_pressure": float(capital_release.get("pressure_score", 0.0) or 0.0),
                    "capital_sovereignty_reserve_pressure": float(capital_sovereignty.get("reserve_pressure", 0.0) or 0.0),
                    "human_disagreement_score": float(human_escalation.get("disagreement_score", 0.0) or 0.0),
                },
                threshold_crossings={
                    "policy_trade_allowed": bool(getattr(policy, "trade_allowed", False)),
                    "reserve_breached": bool(reserve_state.get("reserve_breached", False)),
                    "manual_review_required": bool(human_escalation.get("manual_review_required", False)),
                    "round_trip_viable": bool(round_trip.get("viable", False)),
                },
                blockers=blockers,
                reasons=reasons,
                metadata={
                    "profitability": profitability,
                    "reserve_state": reserve_state,
                    "capital_sovereignty": capital_sovereignty,
                    "human_escalation": human_escalation,
                },
            ),
            blockers,
        )

    def _decision_collapse_trace(
        self,
        *,
        market: object,
        decision_ctx: object,
        execution_result: object | None,
        step: int,
    ) -> DecisionCollapseTrace:
        policy = getattr(decision_ctx, "policy_decision", None)
        why = {} if policy is None or not isinstance(getattr(policy, "why", None), dict) else dict(policy.why)
        market_watch = getattr(market, "market_watch", None)
        edge_immunity = getattr(market, "edge_immunity_decision", None)
        quantum_state = getattr(market, "quantum_state", None)
        provider_capability = getattr(market, "provider_capability", None)
        meta = getattr(decision_ctx, "meta_governor_decision", None)
        risk = getattr(decision_ctx, "risk_decision", None)
        trade_path_state = self._trade_path_state(decision_ctx=decision_ctx, execution_result=execution_result)
        final_decision = trade_path_state if execution_result is not None else str(
            getattr(
                execution_result,
                "status",
                getattr(
                    getattr(policy, "no_trade", None),
                    "reason",
                    getattr(meta, "action", "continue"),
                ),
            )
            or "continue"
        )

        stages: list[DecisionStageTrace] = []
        ranked_blockers: list[DecisionStageBlocker] = []

        if market_watch is not None:
            metadata = dict(getattr(market_watch, "metadata", {}) or {})
            reasons = list(getattr(market_watch, "reasons", []) or [])
            blockers = [
                self._decision_blocker(
                    stage="market_watch",
                    code=reason,
                    classification="hard" if str(getattr(market_watch, "action", "continue")) == "block_entries" else "soft",
                    contribution=max(0.0, 1.0 - float(getattr(market_watch, "score", 1.0) or 1.0)),
                    hard=str(getattr(market_watch, "action", "continue")) == "block_entries",
                )
                for reason in reasons
            ]
            stages.append(
                DecisionStageTrace(
                    stage="market_watch",
                    action=str(getattr(market_watch, "action", "continue")),
                    raw_inputs={
                        "spread_bps": metadata.get("spread_bps"),
                        "depth_notional": metadata.get("depth_notional"),
                        "dead_market_reasoning": metadata.get("dead_market_reasoning", {}),
                    },
                    normalized_inputs={
                        "spread_score": float(getattr(market_watch, "spread_score", 1.0) or 1.0),
                        "liquidity_score": float(getattr(market_watch, "liquidity_score", 1.0) or 1.0),
                    },
                    scores={str(k): float(v) for k, v in dict(metadata.get("regime_score_table", {}) or {}).items() if isinstance(v, (int, float))},
                    threshold_crossings={
                        "block_entries": str(getattr(market_watch, "action", "continue")) == "block_entries",
                        "degrade": str(getattr(market_watch, "action", "continue")) == "degrade",
                    },
                    clamp_sources=[],
                    veto_sources=reasons if str(getattr(market_watch, "action", "continue")) in {"block_entries", "degrade"} else [],
                    blockers=blockers,
                    reasons=reasons,
                    metadata=metadata,
                )
            )
            ranked_blockers.extend(blockers)

        if edge_immunity is not None:
            report = getattr(edge_immunity, "report", None)
            report_meta = {} if report is None else dict(getattr(report, "metadata", {}) or {})
            wait_meta = dict(report_meta.get("wait_dominance", {}) or {})
            edge_action = str(getattr(edge_immunity, "action", "trade_now"))
            blockers = [
                self._decision_blocker(
                    stage="edge_immunity",
                    code=str(reason),
                    classification="soft" if edge_action in {"wait", "trade_smaller"} else "hard",
                    contribution=float(getattr(report, "fragility_index", 0.0) or 0.0),
                    hard=edge_action == "no_trade",
                )
                for reason in [str(getattr(edge_immunity, "reason", "") or "")]
                if reason and edge_action in {"wait", "trade_smaller", "no_trade"}
            ]
            stages.append(
                DecisionStageTrace(
                    stage="edge_immunity",
                    action=edge_action,
                    raw_inputs={
                        "base_expected_edge_bps": None if report is None else float(getattr(report, "base_expected_edge_bps", 0.0) or 0.0),
                        "stressed_expected_edge_bps": None if report is None else float(getattr(report, "stressed_expected_edge_bps", 0.0) or 0.0),
                    },
                    normalized_inputs={
                        "edge_survival_ratio": None if report is None else float(getattr(report, "edge_survival_ratio", 0.0) or 0.0),
                        "fragility_index": None if report is None else float(getattr(report, "fragility_index", 0.0) or 0.0),
                        "wait_value_score": None if report is None else float(getattr(report, "wait_value_score", 0.0) or 0.0),
                    },
                    scores={
                        "trade_now_score": float(wait_meta.get("trade_now_score", 0.0) or 0.0),
                        "wait_score": float(wait_meta.get("wait_score_bps", 0.0) or 0.0),
                        "wait_value_score": None if report is None else float(getattr(report, "wait_value_score", 0.0) or 0.0),
                    },
                    threshold_crossings={
                        "wait_dominant": bool(wait_meta.get("wait_dominant", False)),
                        "fragility_high": False if report is None else float(getattr(report, "fragility_index", 0.0) or 0.0) >= 0.45,
                    },
                    blockers=blockers,
                    reasons=list(sorted(set([str(getattr(edge_immunity, "reason", "") or "")] + list(getattr(report, "dominant_failure_modes", []) if report is not None else [])))),
                    metadata=report_meta,
                )
            )
            ranked_blockers.extend(blockers)

        if quantum_state is not None:
            collapse = getattr(quantum_state, "collapse_decision", None)
            context = getattr(quantum_state, "collapse_context", None)
            collapse_meta = {} if collapse is None else dict(getattr(collapse, "metadata", {}) or {})
            blockers = [
                self._decision_blocker(
                    stage="quantum",
                    code=str(reason),
                    classification="hard" if str(getattr(collapse, "recommended_action", "wait")) == "no_trade" else "heuristic",
                    contribution=max(
                        float(getattr(collapse, "no_trade_probability", 0.0) or 0.0),
                        float(getattr(collapse, "uncertainty", 0.0) or 0.0) * 0.8,
                    ),
                    hard=str(getattr(collapse, "recommended_action", "wait")) == "no_trade",
                )
                for reason in list(getattr(collapse, "reasons", []) or [])
            ]
            stages.append(
                DecisionStageTrace(
                    stage="quantum",
                    action=str(getattr(collapse, "recommended_action", "wait")),
                    raw_inputs={
                        "scenario_branches": self._serialize_payload(getattr(getattr(quantum_state, "scenario_tree", None), "branches", [])),
                        "top_states": {} if context is None else dict(getattr(context, "top_states", {}) or {}),
                    },
                    normalized_inputs={} if context is None else dict(getattr(context, "uncertainty_decomposition", {}) or {}),
                    scores={
                        "action_score": None if collapse is None else float(getattr(collapse, "action_score", 0.0) or 0.0),
                        "no_trade_probability": None if collapse is None else float(getattr(collapse, "no_trade_probability", 0.0) or 0.0),
                        "execution_fragility_score": None if collapse is None else float(getattr(collapse, "execution_fragility_score", 0.0) or 0.0),
                        "uncertainty": None if collapse is None else float(getattr(collapse, "uncertainty", 0.0) or 0.0),
                        "branch_disagreement_score": None if collapse is None else float(getattr(collapse, "branch_disagreement_score", 0.0) or 0.0),
                        "scenario_drift_score": None if collapse is None else float(getattr(collapse, "scenario_drift_score", 0.0) or 0.0),
                    },
                    threshold_crossings={str(k): bool(v) for k, v in dict(collapse_meta.get("thresholds", {}) or {}).items()},
                    clamp_sources=["uncertainty_clipped"] if float(getattr(collapse, "uncertainty", 0.0) or 0.0) >= 0.999 else [],
                    veto_sources=list(getattr(collapse, "reasons", []) or []),
                    confidence_contributors={} if getattr(getattr(quantum_state, "scenario_tree", None), "probability_field", None) is None else dict(getattr(getattr(quantum_state, "scenario_tree", None).probability_field, "confidence_decomposition", {}) or {}),
                    uncertainty_contributors={} if context is None else dict(getattr(context, "uncertainty_decomposition", {}) or {}),
                    blockers=blockers,
                    reasons=list(getattr(collapse, "reasons", []) or []),
                    metadata=collapse_meta,
                )
            )
            ranked_blockers.extend(blockers)

        spre_payload = {} if not isinstance(why.get("spre"), dict) else dict(why.get("spre", {}) or {})
        if spre_payload:
            blockers = [
                self._decision_blocker(
                    stage="spre",
                    code=str(reason),
                    classification="soft" if str(spre_payload.get("dominant_action", "continue")) != "no_trade" else "heuristic",
                    contribution=min(1.0, float(spre_payload.get("no_trade_quality", 0.0) or 0.0) / 10.0),
                    hard=False,
                )
                for reason in list(spre_payload.get("reasons", []) or [])
            ]
            stages.append(
                DecisionStageTrace(
                    stage="spre",
                    action=str(spre_payload.get("dominant_action", "continue")),
                    raw_inputs={
                        "dominant_action": spre_payload.get("dominant_action"),
                        "internal_action": spre_payload.get("internal_action"),
                    },
                    normalized_inputs={
                        "chosen_survival_ratio": float(spre_payload.get("chosen_survival_ratio", 0.0) or 0.0),
                        "action_gap_bps": float(spre_payload.get("action_gap_bps", 0.0) or 0.0),
                        "ambiguity_penalty": float(spre_payload.get("ambiguity_penalty", 0.0) or 0.0),
                    },
                    scores={str(k): float(v) for k, v in dict(spre_payload.get("action_scores", {}) or {}).items()},
                    threshold_crossings={
                        "no_trade_dominant": str(spre_payload.get("dominant_action", "")) == "no_trade",
                        "wait_dominant": str(spre_payload.get("dominant_action", "")) == "wait",
                    },
                    blockers=blockers,
                    reasons=list(spre_payload.get("reasons", []) or []),
                    metadata=spre_payload,
                )
            )
            ranked_blockers.extend(blockers)

        mastermind_payload = {} if not isinstance(why.get("mastermind"), dict) else dict(why.get("mastermind", {}) or {})
        if mastermind_payload:
            raw = dict(mastermind_payload.get("raw", {}) or {})
            mastermind_action = str(mastermind_payload.get("decision", "continue")).lower()
            blockers = [
                self._decision_blocker(
                    stage="mastermind",
                    code=str(reason),
                    classification="hard" if mastermind_action == "no_trade" else "soft",
                    contribution=float(mastermind_payload.get("risk_level", 0.0) or 0.0) / 100.0,
                    hard=bool(mastermind_payload.get("veto", False)),
                )
                for reason in list(mastermind_payload.get("reasons", []) or [])
                if mastermind_action in {"no_trade", "wait", "trade_smaller"} or bool(mastermind_payload.get("veto", False))
            ]
            stages.append(
                DecisionStageTrace(
                    stage="mastermind",
                    action=mastermind_action,
                    raw_inputs={
                        "signal": mastermind_payload.get("signal"),
                        "reason": mastermind_payload.get("reason"),
                    },
                    normalized_inputs={
                        "confidence": float(mastermind_payload.get("confidence", 0.0) or 0.0),
                        "risk_level": float(mastermind_payload.get("risk_level", 0.0) or 0.0),
                        "size_multiplier": float(mastermind_payload.get("size_multiplier", 0.0) or 0.0),
                    },
                    scores={str(k): float(v) for k, v in dict(raw.get("risk_components", {}) or {}).items() if isinstance(v, (int, float))},
                    threshold_crossings={
                        "veto": bool(mastermind_payload.get("veto", False)),
                        "risk_level_100": float(mastermind_payload.get("risk_level", 0.0) or 0.0) >= 100.0,
                    },
                    veto_sources=list(raw.get("veto_chain", []) or []),
                    confidence_contributors={"confidence": float(mastermind_payload.get("confidence", 0.0) or 0.0)},
                    uncertainty_contributors={str(k): float(v) for k, v in dict(raw.get("uncertainty_components", {}) or {}).items() if isinstance(v, (int, float))},
                    blockers=blockers,
                    reasons=list(mastermind_payload.get("reasons", []) or []),
                    metadata={
                        "observability_components": raw.get("observability_components", {}),
                        "veto_chain": raw.get("veto_chain", []),
                    },
                )
            )
            ranked_blockers.extend(blockers)

        capability_payload = self._serialize_payload(provider_capability)
        if execution_result is not None:
            result_meta = getattr(execution_result, "metadata", {}) or {}
            capability_override = result_meta.get("capability_evidence", {}) if isinstance(result_meta, dict) else {}
            if isinstance(capability_payload, dict) and isinstance(capability_override, dict) and capability_override:
                meta = dict(capability_payload.get("metadata", {}) or {})
                meta["capability_evidence"] = capability_override
                capability_payload = {**capability_payload, "metadata": meta}
        if isinstance(capability_payload, dict):
            evidence = dict(capability_payload.get("metadata", {}).get("capability_evidence", {}) or {})
            classifications = dict(evidence.get("classifications", {}) or {})
            blockers = []
            for classification, reasons in classifications.items():
                for reason in list(reasons or []):
                    blockers.append(
                        self._decision_blocker(
                            stage="provider_capability",
                            code=str(reason),
                            classification=str(classification),
                            contribution=0.80 if classification == "execution_blocker" else 0.65 if classification == "promotion_blocker" else 0.40,
                            hard=classification == "execution_blocker",
                        )
                    )
            stages.append(
                DecisionStageTrace(
                    stage="provider_capability",
                    action="partial" if bool(evidence.get("partial", False)) or str(capability_payload.get("lifecycle_completeness", "")).startswith("partial") else "strong",
                    raw_inputs={
                        "user_stream_confidence": capability_payload.get("user_stream_confidence"),
                        "lifecycle_completeness": capability_payload.get("lifecycle_completeness"),
                    },
                    normalized_inputs={
                        "lifecycle_snapshot_count": float(evidence.get("lifecycle_snapshot_count", 0.0) or 0.0),
                        "freshness_seconds": float(evidence.get("freshness_seconds", 0.0) or 0.0),
                    },
                    scores={
                        "partial": 1.0 if bool(evidence.get("partial", False)) else 0.0,
                        "single_process_lifecycle_equivalent": 1.0 if bool(evidence.get("single_process_lifecycle_equivalent", False)) else 0.0,
                    },
                    threshold_crossings={
                        "lifecycle_missing": float(evidence.get("lifecycle_snapshot_count", 0.0) or 0.0) <= 0.0,
                        "partial": bool(evidence.get("partial", False)),
                    },
                    blockers=blockers,
                    reasons=list(evidence.get("reasons", []) or []),
                    metadata={"classifications": classifications},
                )
            )
            ranked_blockers.extend(blockers)

        doctrine_payload = {} if not isinstance(why.get("decision_doctrine"), dict) else dict(why.get("decision_doctrine", {}) or {})
        if doctrine_payload:
            doctrine_meta = dict(doctrine_payload.get("metadata", {}) or {})
            blockers = [
                self._decision_blocker(
                    stage="decision_doctrine",
                    code=str(reason),
                    classification="hard" if str(doctrine_payload.get("recommended_action", "continue")) == "no_trade" else "soft",
                    contribution=max(
                        float(doctrine_payload.get("uncertainty_pressure", 0.0) or 0.0),
                        float(doctrine_payload.get("partial_truth_penalty", 0.0) or 0.0),
                    ),
                    hard=str(doctrine_payload.get("recommended_action", "continue")) == "no_trade",
                )
                for reason in list(doctrine_payload.get("reasons", []) or [])
            ]
            stages.append(
                DecisionStageTrace(
                    stage="decision_doctrine",
                    action=str(doctrine_payload.get("recommended_action", "continue")),
                    raw_inputs={
                        "truth_strength": doctrine_payload.get("truth_strength"),
                        "survival_score": doctrine_payload.get("survival_score"),
                        "robustness_score": doctrine_payload.get("robustness_score"),
                    },
                    normalized_inputs={
                        "size_multiplier": float(doctrine_payload.get("size_multiplier", 0.0) or 0.0),
                        "uncertainty_pressure": float(doctrine_payload.get("uncertainty_pressure", 0.0) or 0.0),
                        "partial_truth_penalty": float(doctrine_payload.get("partial_truth_penalty", 0.0) or 0.0),
                    },
                    scores={str(k): float(v) for k, v in dict(doctrine_meta.get("uncertainty_components", {}) or {}).items() if isinstance(v, (int, float))},
                    threshold_crossings={
                        "no_trade": str(doctrine_payload.get("recommended_action", "continue")) == "no_trade",
                        "wait": str(doctrine_payload.get("recommended_action", "continue")) == "wait",
                        "probe": str(doctrine_payload.get("recommended_action", "continue")) == "probe",
                    },
                    blockers=blockers,
                    reasons=list(doctrine_payload.get("reasons", []) or []),
                    metadata=doctrine_meta,
                )
            )
            ranked_blockers.extend(blockers)

        policy_gate_stage, policy_gate_blockers = self._policy_gate_trace(
            policy=policy,
            decision_ctx=decision_ctx,
            trade_path_state=trade_path_state,
        )
        if policy_gate_stage is not None:
            stages.append(policy_gate_stage)
            ranked_blockers.extend(policy_gate_blockers)

        final_gate_reasons: list[str] = []
        final_gate_scores: dict[str, float] = {}
        if meta is not None and str(getattr(meta, "action", "continue")) != "continue":
            final_gate_reasons.extend(list(getattr(meta, "reasons", []) or []))
            final_gate_scores["meta_governor_size_multiplier"] = float(getattr(meta, "size_multiplier", 1.0) or 1.0)
        if risk is not None and not bool(getattr(risk, "allowed", True)):
            final_gate_reasons.append(str(getattr(risk, "reason", "risk_block") or "risk_block"))
        if execution_result is not None:
            final_gate_reasons.append(str(getattr(execution_result, "reason", getattr(execution_result, "status", "")) or "execution_result"))
        execution_blocker_meta = {}
        if execution_result is not None:
            result_meta = getattr(execution_result, "metadata", {}) or {}
            if isinstance(result_meta, dict) and isinstance(result_meta.get("execution_blocker"), dict):
                execution_blocker_meta = dict(result_meta.get("execution_blocker", {}) or {})
                execution_blocker_meta.setdefault("blocker_type", self._blocker_type({"stage": "final_execution_gate", "classification": "exchange_reject", "code": str(getattr(execution_result, "reason", getattr(execution_result, "status", "")) or "")}))
        if final_gate_reasons or trade_path_state != "blocked_by_decision":
            blockers = [
                self._decision_blocker(
                    stage="final_execution_gate",
                    code=reason,
                    classification="exchange_reject" if execution_result is not None and reason == str(getattr(execution_result, "reason", getattr(execution_result, "status", "")) or "") else "hard" if reason not in {"max_steps_reached"} else "soft",
                    contribution=1.0 if reason not in {"max_steps_reached"} else 0.25,
                    hard=reason not in {"max_steps_reached"},
                    metadata=execution_blocker_meta if execution_result is not None and reason == str(getattr(execution_result, "reason", getattr(execution_result, "status", "")) or "") else {"blocker_type": "decision_layer_veto" if reason not in {"max_steps_reached"} else "soft_execution_caution"},
                )
                for reason in final_gate_reasons
                if reason
            ]
            stages.append(
                DecisionStageTrace(
                    stage="final_execution_gate",
                    action=trade_path_state,
                    raw_inputs={
                        "meta_governor_action": None if meta is None else str(getattr(meta, "action", "continue")),
                        "risk_allowed": None if risk is None else bool(getattr(risk, "allowed", True)),
                        "execution_status": None if execution_result is None else str(getattr(execution_result, "status", "")),
                    },
                    normalized_inputs={"trade_path_state": trade_path_state},
                    scores=final_gate_scores,
                    threshold_crossings={
                        "adjusted_intent_present": getattr(decision_ctx, "adjusted_intent", None) is not None,
                        "execution_result_present": execution_result is not None,
                    },
                    blockers=blockers,
                    reasons=final_gate_reasons,
                    metadata=execution_blocker_meta,
                )
            )
            ranked_blockers.extend(blockers)

        ranked_blockers = self._dedupe_ranked_blockers(ranked_blockers)
        reason_chain = [f"{stage.stage}:{stage.action}:{'|'.join(stage.reasons[:3])}" for stage in stages if stage.reasons]
        return DecisionCollapseTrace(
            symbol=str(getattr(policy, "symbol", getattr(getattr(market, "forecast", None), "symbol", "")) or ""),
            ts=datetime.now(timezone.utc),
            frame_id=sha256(f"{step}|{trade_path_state}|{reason_chain}".encode("utf-8")).hexdigest()[:16],
            step=step,
            final_decision=str(final_decision),
            trade_path_state=trade_path_state,
            ranked_blockers=ranked_blockers,
            reason_chain=reason_chain,
            stages=stages,
            metadata={
                "policy_trade_allowed": False if policy is None else bool(getattr(policy, "trade_allowed", False)),
                "execution_result": None if execution_result is None else self._serialize_payload(execution_result),
            },
        )

    def _decision_explainability(
        self,
        *,
        market: object,
        decision_ctx: object,
        execution_result: object | None = None,
        trace: DecisionCollapseTrace | None = None,
    ) -> dict[str, object]:
        doctrine = {}
        if getattr(decision_ctx, "policy_decision", None) is not None and isinstance(
            getattr(decision_ctx.policy_decision, "why", None),
            dict,
        ):
            doctrine = dict(decision_ctx.policy_decision.why.get("decision_doctrine", {}) or {})
        if trace is not None:
            serialized_trace = self._serialize_payload(trace)
            ranked_blockers = [] if not isinstance(serialized_trace, dict) else list(serialized_trace.get("ranked_blockers", []) or [])
            top_blocker = None if not ranked_blockers else ranked_blockers[0]
            top_blocker_type = self._blocker_type(top_blocker)
            stage_actions = {}
            if isinstance(serialized_trace, dict):
                for stage in list(serialized_trace.get("stages", []) or []):
                    if isinstance(stage, dict) and stage.get("stage"):
                        stage_actions[str(stage["stage"])] = str(stage.get("action", ""))
            return {
                "action_state": trace.final_decision,
                "trade_path_state": trace.trade_path_state,
                "collapse_stage": None if top_blocker is None else str(top_blocker.get("stage", "")),
                "top_blocker_type": top_blocker_type,
                "reason_codes": [str(blocker.get("code", "")) for blocker in ranked_blockers if str(blocker.get("code", ""))],
                "ranked_blockers": ranked_blockers,
                "reason_chain": list(trace.reason_chain),
                "stage_actions": stage_actions,
                "operator_rationale": {
                    "forecast_regime": str(getattr(getattr(market, "forecast", None), "regime", "")),
                    "market_watch_action": None if getattr(market, "market_watch", None) is None else str(getattr(market.market_watch, "action", "continue")),
                    "market_integrity_action": None if getattr(market, "market_integrity", None) is None else str(getattr(market.market_integrity, "action", "continue")),
                    "doctrine_action": doctrine.get("recommended_action"),
                    "size_multiplier": doctrine.get("size_multiplier"),
                },
                "investor_rationale": {
                    "thesis": "buy_only_when_edge_survives_costs_and_truth_is_strong",
                    "capital_protection": "partial_observability_and_uncertainty_reduce_size_or_block_promotion_without_faking_toxicity",
                    "why_chosen_over_alternatives": {
                        "top_blocker": None if top_blocker is None else {**top_blocker, "blocker_type": top_blocker_type},
                        "trace_frame_id": trace.frame_id,
                    },
                },
            }
        policy = getattr(decision_ctx, "policy_decision", None)
        risk = getattr(decision_ctx, "risk_decision", None)
        meta = getattr(decision_ctx, "meta_governor_decision", None)
        action = "no_trade"
        if execution_result is not None:
            action = str(getattr(execution_result, "status", "executed") or "executed")
        elif getattr(decision_ctx, "adjusted_intent", None) is not None:
            action = f"intent:{getattr(getattr(decision_ctx, 'adjusted_intent', None), 'side', 'unknown')}"
        elif meta is not None and str(getattr(meta, "action", "continue")) != "continue":
            action = str(getattr(meta, "action", "continue"))
        elif policy is not None and not bool(getattr(policy, "trade_allowed", False)):
            action = str(getattr(getattr(policy, "no_trade", None), "reason", "no_trade") or "no_trade")
        reasons = []
        if meta is not None:
            reasons.extend(list(getattr(meta, "reasons", []) or []))
        if risk is not None:
            reasons.append(str(getattr(risk, "reason", "") or ""))
        if policy is not None and getattr(policy, "no_trade", None) is not None:
            reasons.extend(list(getattr(policy.no_trade, "reasons", []) or []))
        if doctrine:
            reasons.extend(list(doctrine.get("reasons", []) or []))
        reasons = [reason for reason in reasons if reason]
        alternatives = {
            "no_trade_reason": None if getattr(policy, "no_trade", None) is None else str(getattr(policy.no_trade, "reason", "") or ""),
            "meta_governor_action": None if meta is None else str(getattr(meta, "action", "continue")),
            "risk_reason": None if risk is None else str(getattr(risk, "reason", "")),
            "shadow_rival_action": doctrine.get("shadow_action"),
            "recommended_action": doctrine.get("recommended_action"),
        }
        return {
            "action_state": action,
            "reason_codes": sorted(set(reasons)),
            "operator_rationale": {
                "forecast_regime": str(getattr(getattr(market, "forecast", None), "regime", "")),
                "market_watch_action": None if getattr(market, "market_watch", None) is None else str(getattr(market.market_watch, "action", "continue")),
                "market_integrity_action": None if getattr(market, "market_integrity", None) is None else str(getattr(market.market_integrity, "action", "continue")),
                "doctrine_action": doctrine.get("recommended_action"),
                "size_multiplier": doctrine.get("size_multiplier"),
            },
            "investor_rationale": {
                "thesis": "buy_only_when_edge_survives_costs_and_truth_is_strong",
                "capital_protection": "reduce_or_block_under_truth_execution_or_market_weakness",
                "why_chosen_over_alternatives": alternatives,
            },
        }

    def _blocked_preflight_trace(
        self,
        *,
        symbol: str,
        preflight_ok: bool,
        preflight_reason: str,
        confidence: str,
        recovery_action: str,
        blocking_reasons: list[str],
    ) -> DecisionCollapseTrace:
        blockers: list[DecisionStageBlocker] = []
        for reason in blocking_reasons:
            normalized = str(reason).strip()
            if not normalized:
                continue
            classification = "hard"
            blocker_type = "decision_layer_veto"
            if normalized.startswith("truth_confidence:") or normalized.startswith("restart_state:"):
                classification = "promotion_blocker"
                blocker_type = "observability_gap"
            elif normalized.startswith("recovery:"):
                classification = "execution_blocker"
                blocker_type = "execution_blocker"
            blockers.append(
                self._decision_blocker(
                    stage="final_execution_gate",
                    code=normalized,
                    classification=classification,
                    contribution=1.0,
                    hard=True,
                    metadata={"blocker_type": blocker_type, "phase": "preflight"},
                )
            )
        blockers = self._dedupe_ranked_blockers(blockers)
        reason_chain = [
            "preflight:blocked_preflight:"
            + ("|".join(blocking_reasons) if blocking_reasons else (preflight_reason or "unknown"))
        ]
        return DecisionCollapseTrace(
            symbol=symbol,
            ts=datetime.now(timezone.utc),
            frame_id=sha256(
                f"preflight|{symbol}|{preflight_reason}|{confidence}|{recovery_action}|{blocking_reasons}".encode("utf-8")
            ).hexdigest()[:16],
            step=0,
            final_decision="blocked_preflight",
            trade_path_state="not_attempted",
            ranked_blockers=blockers,
            reason_chain=reason_chain,
            stages=[
                DecisionStageTrace(
                    stage="final_execution_gate",
                    action="blocked_preflight",
                    raw_inputs={
                        "preflight_ok": preflight_ok,
                        "preflight_reason": preflight_reason,
                        "restart_state_confidence": confidence,
                        "recovery_action": recovery_action,
                    },
                    normalized_inputs={"blocking_reason_count": float(len(blocking_reasons))},
                    threshold_crossings={"blocked_preflight": True},
                    blockers=blockers,
                    reasons=list(blocking_reasons),
                    metadata={"phase": "preflight"},
                )
            ],
            metadata={"preflight": True},
        )

    def _emit_live_readiness_artifacts(
        self,
        *,
        symbol: str,
        mode: ExecutionMode,
        harmony_payload: dict[str, object],
        preflight_ok: bool,
        preflight_reason: str,
        confidence: str,
        confidence_details: dict[str, object],
        recovery_decision: RecoveryDecision,
        ordering_allowed: bool,
    ) -> dict[str, str]:
        truth_confidence_action, truth_confidence_reasons = self._boot_truth_gate(confidence_details)
        blocking_reasons = self._live_blocking_reasons(
            preflight_ok=preflight_ok,
            preflight_reason=preflight_reason,
            confidence=confidence,
            recovery_action=recovery_decision.action,
            truth_confidence_reasons=truth_confidence_reasons,
        )
        safety_ready = bool(
            preflight_ok
            and ordering_allowed
            and confidence not in {"insufficient", "degraded"}
            and recovery_decision.action == "continue"
        )
        stage = self.settings.rollout_stage()
        rollout_profile = self.settings.rollout_profile()
        config_path = (
            "config.kraken_spot.tiny_live.yaml"
            if stage == RolloutStage.TINY_LIVE
            else "config.kraken_spot.live_profit.yaml"
            if stage == RolloutStage.NORMAL_LIVE
            else "config.kraken_spot.live.yaml"
        )
        safety_preflight = {
            "symbol": symbol,
            "runtime_mode": mode.value,
            "rollout_stage": stage.value,
            "provider_id": self.settings.execution.provider_id,
            "doctrine_launch_safe": bool(harmony_payload.get("live_gate_status", {}).get("doctrine_launch_safe", False)),
            "preflight_ok": preflight_ok,
            "preflight_reason": preflight_reason,
            "restart_state_confidence": confidence,
            "recovery_action": recovery_decision.action,
            "truth_confidence_action": truth_confidence_action,
            "ordering_allowed": ordering_allowed,
            "market_watch_enabled": bool(self.settings.market_watch.enabled),
            "harmony_enabled": bool(self.settings.harmony.enabled),
            "capital_protection": {
                "cost_basis_sell_block": bool(self.settings.doctrine.enforce_cost_basis_sell_block),
                "net_profit_sell_block": bool(self.settings.doctrine.enforce_net_profit_sell_block),
                "minimum_sell_net_profit_bps": float(self.settings.doctrine.minimum_sell_net_profit_bps),
            },
            "safety_ready": safety_ready,
            "blocking_reasons": [] if safety_ready else blocking_reasons,
            "details": confidence_details,
        }
        rollback_preflight = {
            "symbol": symbol,
            "rollout_stage": stage.value,
            "rollback_target": rollout_profile["rollback_target"],
            "paper_target_config": "config.kraken_spot.paper_full_analysis.yaml",
            "readonly_target_config": "config.kraken_spot.readonly_analysis.yaml",
            "kill_file": self._kill_file_path(),
            "flatten_command": f"python3 -m autonomous_investment_robot flatten --config {config_path}",
            "rollback_ready": True,
            "reasons": [],
        }
        tiny_live_readiness = {
            "symbol": symbol,
            "stage": stage.value,
            "ready": bool(stage.value == "tiny_live") and safety_ready,
            "purpose": rollout_profile["purpose"],
            "promotion_prerequisites": list(rollout_profile["promotion_prerequisites"]),
            "rollback_target": rollout_profile["rollback_target"],
            "blocking_reasons": [] if safety_ready else blocking_reasons,
        }
        tiny_live_envelope = {
            "symbol": symbol,
            "rollout_stage": stage.value,
            "base_risk_budget": float(self.settings.policy.base_risk_budget),
            "max_position_notional": float(self.settings.risk.max_position_notional),
            "max_exposure_notional": float(self.settings.risk.max_exposure_notional),
            "max_orders_per_min": int(self.settings.risk.max_orders_per_min),
            "max_spread_bps": float(self.settings.risk.max_spread_bps),
            "min_depth_notional": float(self.settings.risk.min_depth_notional),
            "maker_timeout_s": int(self.settings.execution.maker_timeout_s),
            "full_live_stage_required": bool(self.settings.live_gate_status().get("full_live_stage_required", False)),
            "double_unlock_required": True,
            "rollback_target": rollout_profile["rollback_target"],
            "aggression_envelope": rollout_profile["aggression_envelope"],
        }
        start_procedure = {
            "config": config_path,
            "required_env": ["ENABLE_LIVE_TRADING=true", "ACK_I_UNDERSTAND_RISKS=true", "KRAKEN_SPOT_API_KEY=...", "KRAKEN_SPOT_API_SECRET=..."],
            "optional_env": ["KRAKEN_SPOT_EVENT_FEED_PATH=/absolute/path/to/events.jsonl"],
            "readonly_validation": "bash scripts/run_kraken_spot_readonly_analysis.sh",
            "tiny_live_start": "bash scripts/run_kraken_spot_tiny_live.sh",
            "emergency_freeze": f"python3 -m autonomous_investment_robot flatten --config {config_path} --freeze-only --reason operator_freeze",
            "emergency_flatten": f"python3 -m autonomous_investment_robot flatten --config {config_path} --scope all --reason operator_flatten",
        }
        config_truth = self.runtime_metadata.config_truth_report(harmony_payload=harmony_payload)
        release_manifest = self.runtime_metadata.release_manifest()
        deployment_stamp = self.runtime_metadata.deployment_stamp()
        runtime_fingerprint = self.runtime_metadata.runtime_fingerprint()
        live_safety_summary = self.runtime_metadata.live_safety_summary(
            preflight_ok=preflight_ok,
            preflight_reason=preflight_reason,
            ordering_allowed=ordering_allowed,
            confidence=confidence,
            recovery_action=recovery_decision.action,
            blocking_reasons=blocking_reasons,
        )
        readiness_summary = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "runtime_mode": mode.value,
            "rollout_stage": stage.value,
            "provider_id": self.settings.execution.provider_id,
            "readiness_ready": bool(tiny_live_readiness["ready"] if stage == RolloutStage.TINY_LIVE else safety_ready),
            "preflight_ok": preflight_ok,
            "ordering_allowed": ordering_allowed,
            "restart_state_confidence": confidence,
            "recovery_action": recovery_decision.action,
            "truth_confidence_action": truth_confidence_action,
            "blocking_reasons": [] if safety_ready else blocking_reasons,
        }
        health_summary = self.runtime_metadata.health_summary(
            preflight_ok=preflight_ok,
            ordering_allowed=ordering_allowed,
            throughput=self._throughput_snapshot(),
            failure_taxonomy=dict(self._live_runtime_diagnostics.get("failure_taxonomy", {})),
            blocking_reasons=blocking_reasons,
        )
        blocked_trace = self._blocked_preflight_trace(
            symbol=symbol,
            preflight_ok=preflight_ok,
            preflight_reason=preflight_reason,
            confidence=confidence,
            recovery_action=recovery_decision.action,
            blocking_reasons=blocking_reasons,
        )
        blocked_trace_payload = self._serialize_payload(blocked_trace)
        top_blocker = None
        if isinstance(blocked_trace_payload, dict):
            ranked = list(blocked_trace_payload.get("ranked_blockers", []) or [])
            top_blocker = None if not ranked else ranked[0]
        blocked_explainability = {
            "action_state": "blocked_preflight",
            "trade_path_state": "not_attempted",
            "collapse_stage": None if top_blocker is None else str(top_blocker.get("stage", "")),
            "top_blocker_type": self._blocker_type(top_blocker),
            "reason_codes": sorted(blocking_reasons),
            "ranked_blockers": [] if not isinstance(blocked_trace_payload, dict) else list(blocked_trace_payload.get("ranked_blockers", []) or []),
            "reason_chain": list(blocked_trace.reason_chain),
            "stage_actions": {"final_execution_gate": "blocked_preflight"},
            "operator_rationale": {
                "forecast_regime": "",
                "market_watch_action": None,
                "market_integrity_action": None,
                "doctrine_action": "blocked",
                "size_multiplier": 0.0,
            },
            "investor_rationale": {
                "thesis": "capital_protection_blocks_until_truth_and_execution_preflight_are_verified",
                "capital_protection": "no_live_ordering_without_preflight_reconciliation_and_recovery_clearance",
                "why_chosen_over_alternatives": {
                    "no_trade_reason": preflight_reason,
                    "meta_governor_action": "blocked_preflight",
                    "risk_reason": confidence,
                    "shadow_rival_action": None,
                    "recommended_action": "blocked_preflight",
                },
            },
        }
        readiness_capital_bundle = self.capital_envelope.summarize()
        readiness_expectancy = self.expectancy_engine.build(
            fills=[],
            order_events=[],
            trade_log=[],
            ranked_candidates=[],
        )
        readiness_translation, readiness_gap_report = self.performance_targets.translate(
            capital_envelope=dict(readiness_capital_bundle.get("capital_envelope_summary", {}) or {}),
            expectancy=dict(readiness_expectancy.get("report", {}) or {}),
            throughput=self._throughput_snapshot(),
        )
        enhanced_harmony_report = {
            **harmony_payload,
            "performance_targets": self.settings.config_manifest().get("performance_targets", {}),
            "capital_envelope": self.settings.config_manifest().get("capital_envelope", {}),
            "market_universe": self.settings.config_manifest().get("market_universe", {}),
            "playbooks": self.settings.config_manifest().get("playbooks", {}),
            "expectancy": self.settings.config_manifest().get("expectancy", {}),
            "experiments": self.settings.config_manifest().get("experiments", {}),
            "operator_kpis": self.settings.config_manifest().get("operator_kpis", {}),
        }
        strategy_capability_matrix = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "playbooks": {
                "trend_follow_entry": {"live_enabled": True, "shadow_only": False, "exit_family": "trailing_profit_exit"},
                "mean_reversion_entry": {"live_enabled": True, "shadow_only": False, "exit_family": "alpha_capture_exit"},
                "breakout_continuation": {"live_enabled": True, "shadow_only": False, "exit_family": "trailing_profit_exit"},
                "volatility_expansion": {"live_enabled": True, "shadow_only": False, "exit_family": "regime_invalidation_exit"},
                "pullback_reentry": {"live_enabled": True, "shadow_only": False, "exit_family": "partial_take_profit_exit"},
                "inventory_unwind": {"live_enabled": False, "shadow_only": True, "exit_family": "forced_inventory_cleanup_exit"},
                "profit_capture_exit": {"live_enabled": False, "shadow_only": True, "exit_family": "alpha_capture_exit"},
            },
            "long_only": bool(self.settings.doctrine.long_only),
            "provider_target": self.settings.doctrine_target_provider(),
            "product_target": self.settings.doctrine_product_target(),
        }
        rollout_readiness_report = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "rollout_stage": stage.value,
            "ready": readiness_summary["readiness_ready"],
            "blocking_reasons": list(readiness_summary["blocking_reasons"]),
            "performance_gap": readiness_gap_report,
            "promotion_prerequisites": list(rollout_profile["promotion_prerequisites"]),
            "rollback_target": rollout_profile["rollback_target"],
        }
        operator_start_procedure = {
            **start_procedure,
            "target_translation": readiness_translation,
            "rollout_readiness": rollout_readiness_report,
        }
        artifact_index = {
            "run_dir": self.settings.storage.run_dir,
            "stage": stage.value,
            "files": [],
        }
        paths = {
            "safety_preflight_live_target": self._write_json_artifact("safety_preflight_live_target.json", safety_preflight),
            "rollback_preflight_liveprofit_paper": self._write_json_artifact("rollback_preflight_liveprofit_paper.json", rollback_preflight),
            "tiny_live_readiness_report": self._write_json_artifact("tiny_live_readiness_report.json", tiny_live_readiness),
            "tiny_live_envelope_summary": self._write_json_artifact("tiny_live_envelope_summary.json", tiny_live_envelope),
            "live_operator_start_procedure": self._write_json_artifact("live_operator_start_procedure.json", start_procedure),
            "operator_start_procedure": self._write_json_artifact("operator_start_procedure.json", operator_start_procedure),
            "config_truth_report": self._write_json_artifact("config_truth_report.json", config_truth),
            "enhanced_harmony_report": self._write_json_artifact("enhanced_harmony_report.json", enhanced_harmony_report),
            "strategy_capability_matrix": self._write_json_artifact("strategy_capability_matrix.json", strategy_capability_matrix),
            "rollout_readiness_report": self._write_json_artifact("rollout_readiness_report.json", rollout_readiness_report),
            "performance_target_translation": self._write_json_artifact("performance_target_translation.json", readiness_translation),
            "performance_gap_report": self._write_json_artifact("performance_gap_report.json", readiness_gap_report),
            "release_manifest": self._write_json_artifact("release_manifest.json", release_manifest),
            "deployment_stamp": self._write_json_artifact("deployment_stamp.json", deployment_stamp),
            "runtime_fingerprint": self._write_json_artifact("runtime_fingerprint.json", runtime_fingerprint),
            "readiness_summary": self._write_json_artifact("readiness_summary.json", readiness_summary),
            "live_safety_summary": self._write_json_artifact("live_safety_summary.json", live_safety_summary),
            "health_summary": self._write_json_artifact("health_summary.json", health_summary),
            "throughput_diagnostics": self._write_json_artifact("throughput_diagnostics.json", self._throughput_snapshot()),
            "failure_taxonomy": self._write_json_artifact(
                "failure_taxonomy.json",
                dict(self._live_runtime_diagnostics.get("failure_taxonomy", {})),
            ),
            "decision_collapse_trace_latest": self._write_json_artifact("decision_collapse_trace_latest.json", blocked_trace_payload),
            "decision_explainability": self._write_json_artifact("decision_explainability.json", blocked_explainability),
        }
        self._append_jsonl_artifact("decision_collapse_trace.jsonl", blocked_trace_payload)
        artifact_index["files"] = sorted(path.name for path in Path(self.settings.storage.run_dir).glob("*.json*"))
        paths["live_artifact_index"] = self._write_json_artifact("live_artifact_index.json", artifact_index)
        return paths

    @staticmethod
    def _dedupe_reasons(reasons: list[str]) -> list[str]:
        deduped: list[str] = []
        for reason in reasons:
            text = str(reason).strip()
            if text and text not in deduped:
                deduped.append(text)
        return deduped

    def _boot_truth_gate(self, confidence_details: dict[str, object]) -> tuple[str, list[str]]:
        truth_confidence = confidence_details.get("truth_confidence")
        if not isinstance(truth_confidence, dict) and "overall_action" in confidence_details:
            truth_confidence = confidence_details
        if not isinstance(truth_confidence, dict):
            return "continue", []
        action = str(truth_confidence.get("overall_action", "continue") or "continue")
        raw_reasons = truth_confidence.get("reasons", [])
        reasons: list[str] = []
        if isinstance(raw_reasons, list):
            reasons = [
                f"truth_confidence:{action}:{str(reason).strip()}"
                for reason in raw_reasons
                if str(reason).strip()
            ]
        if action != "continue" and not reasons:
            reasons = [f"truth_confidence:{action}"]
        return action, reasons

    def _live_blocking_reasons(
        self,
        *,
        preflight_ok: bool,
        preflight_reason: str,
        confidence: str,
        recovery_action: str,
        truth_confidence_reasons: list[str],
    ) -> list[str]:
        reasons: list[str] = []
        if not preflight_ok:
            reasons.append(preflight_reason)
        if confidence in {"insufficient", "degraded"}:
            reasons.append(f"restart_state:{confidence}")
        if recovery_action != "continue":
            reasons.append(f"recovery:{recovery_action}")
        reasons.extend(truth_confidence_reasons)
        return self._dedupe_reasons(reasons)

    def _live_capability_bundle(self, *, market: object, decision_ctx: object) -> tuple[list[dict[str, object]], dict[str, dict[str, object]], dict[str, dict[str, object]]]:
        event_report = getattr(market, "event_intelligence_report", None)
        event_partial = bool(getattr(event_report, "partial", True)) if event_report is not None else True
        event_feed_configured = bool(self.settings.kraken_spot_event_feed_path())
        capabilities: dict[str, dict[str, object]] = {
            "MarketIntegrityService": {"state": "implemented", "activation_state": "active" if getattr(market, "market_integrity", None) is not None else "gated", "kraken_spot_compatible": "yes", "exact_blocker": "" if getattr(market, "market_integrity", None) is not None else "market_integrity_missing", "exact_unlock_action_required": "" if getattr(market, "market_integrity", None) is not None else "wire_live_market_integrity", "doctrine_conflict": "no"},
            "VenueCapabilityRegistry": {"state": "implemented", "activation_state": "active" if getattr(market, "provider_capability", None) is not None else "gated", "kraken_spot_compatible": "yes", "exact_blocker": "" if getattr(market, "provider_capability", None) is not None else "provider_capability_missing", "exact_unlock_action_required": "" if getattr(market, "provider_capability", None) is not None else "wire_live_provider_capability", "doctrine_conflict": "no"},
            "HarmonyConfigResolver": {"state": "implemented", "activation_state": "active", "kraken_spot_compatible": "yes", "exact_blocker": "", "exact_unlock_action_required": "", "doctrine_conflict": "no"},
            "QuantumScenarioService": {"state": "implemented", "activation_state": "active" if getattr(market, "quantum_state", None) is not None else "gated", "kraken_spot_compatible": "yes", "exact_blocker": "" if getattr(market, "quantum_state", None) is not None else "quantum_state_missing", "exact_unlock_action_required": "" if getattr(market, "quantum_state", None) is not None else "evaluate_quantum_state", "doctrine_conflict": "no"},
            "SignalInterferenceEngine": {"state": "implemented", "activation_state": "active" if getattr(getattr(market, "quantum_state", None), "interference_report", None) is not None else "gated", "kraken_spot_compatible": "yes", "exact_blocker": "" if getattr(getattr(market, "quantum_state", None), "interference_report", None) is not None else "signal_interference_missing", "exact_unlock_action_required": "" if getattr(getattr(market, "quantum_state", None), "interference_report", None) is not None else "route_signal_interference", "doctrine_conflict": "no"},
            "EdgeImmunityService": {"state": "implemented", "activation_state": "active" if getattr(market, "edge_immunity_decision", None) is not None else "gated", "kraken_spot_compatible": "yes", "exact_blocker": "" if getattr(market, "edge_immunity_decision", None) is not None else "edge_immunity_missing", "exact_unlock_action_required": "" if getattr(market, "edge_immunity_decision", None) is not None else "evaluate_edge_immunity", "doctrine_conflict": "no"},
            "SPREEngine": {"state": "implemented", "activation_state": "active", "kraken_spot_compatible": "yes", "exact_blocker": "", "exact_unlock_action_required": "", "doctrine_conflict": "no"},
            "ShadowRivalService": {"state": "implemented", "activation_state": "active", "kraken_spot_compatible": "yes", "exact_blocker": "", "exact_unlock_action_required": "", "doctrine_conflict": "no"},
            "CapitalSovereigntyService": {"state": "implemented", "activation_state": "active" if getattr(decision_ctx, "capital_sovereignty_decision", None) is not None else "gated", "kraken_spot_compatible": "yes", "exact_blocker": "" if getattr(decision_ctx, "capital_sovereignty_decision", None) is not None else "capital_sovereignty_missing", "exact_unlock_action_required": "" if getattr(decision_ctx, "capital_sovereignty_decision", None) is not None else "evaluate_capital_sovereignty", "doctrine_conflict": "no"},
            "PositionMorphingEngine": {"state": "implemented", "activation_state": "active" if self.position_morphing is not None else "gated", "kraken_spot_compatible": "yes", "exact_blocker": "" if self.position_morphing is not None else "position_morphing_missing", "exact_unlock_action_required": "" if self.position_morphing is not None else "wire_position_morphing", "doctrine_conflict": "no"},
            "AdaptiveExitAllocator": {"state": "implemented", "activation_state": "active" if self.adaptive_exit_allocator is not None else "gated", "kraken_spot_compatible": "yes", "exact_blocker": "" if self.adaptive_exit_allocator is not None else "adaptive_exit_missing", "exact_unlock_action_required": "" if self.adaptive_exit_allocator is not None else "wire_adaptive_exit", "doctrine_conflict": "no"},
            "SyntheticAffectEngine": {"state": "implemented", "activation_state": "active" if getattr(decision_ctx, "synthetic_affect_state", None) is not None else "gated", "kraken_spot_compatible": "yes", "exact_blocker": "" if getattr(decision_ctx, "synthetic_affect_state", None) is not None else "synthetic_affect_missing", "exact_unlock_action_required": "" if getattr(decision_ctx, "synthetic_affect_state", None) is not None else "evaluate_synthetic_affect", "doctrine_conflict": "no"},
            "EventIntelligenceService": {"state": "implemented", "activation_state": "active_but_partial" if event_partial else "active", "kraken_spot_compatible": "yes", "exact_blocker": "no_live_event_evidence" if event_partial and not event_feed_configured else ("partial_live_event_evidence" if event_partial else ""), "exact_unlock_action_required": "provide_KRAKEN_SPOT_EVENT_FEED_PATH" if event_partial and not event_feed_configured else ("" if not event_partial else "improve_event_feed_quality"), "doctrine_conflict": "no"},
            "DataProvenanceLedger": {"state": "implemented", "activation_state": "active_but_partial" if event_partial else "active", "kraken_spot_compatible": "yes", "exact_blocker": "no_live_event_evidence" if event_partial and not event_feed_configured else ("partial_live_event_evidence" if event_partial else ""), "exact_unlock_action_required": "provide_KRAKEN_SPOT_EVENT_FEED_PATH" if event_partial and not event_feed_configured else ("" if not event_partial else "improve_event_feed_quality"), "doctrine_conflict": "no"},
            "ExecutionSimulationSandbox": {"state": "implemented", "activation_state": "active" if getattr(decision_ctx, "execution_simulation_report", None) is not None else "gated", "kraken_spot_compatible": "yes", "exact_blocker": "" if getattr(decision_ctx, "execution_simulation_report", None) is not None else "execution_simulation_missing", "exact_unlock_action_required": "" if getattr(decision_ctx, "execution_simulation_report", None) is not None else "evaluate_execution_simulation", "doctrine_conflict": "no"},
            "EpisodicTradeMemory": {"state": "implemented", "activation_state": "active", "kraken_spot_compatible": "yes", "exact_blocker": "", "exact_unlock_action_required": "", "doctrine_conflict": "no"},
            "AnalogTradeLookup": {"state": "implemented", "activation_state": "active", "kraken_spot_compatible": "yes", "exact_blocker": "", "exact_unlock_action_required": "", "doctrine_conflict": "no"},
            "CounterfactualEvaluator": {"state": "implemented", "activation_state": "active", "kraken_spot_compatible": "yes", "exact_blocker": "", "exact_unlock_action_required": "", "doctrine_conflict": "no"},
            "PnLAttributionService": {"state": "implemented", "activation_state": "active", "kraken_spot_compatible": "yes", "exact_blocker": "", "exact_unlock_action_required": "", "doctrine_conflict": "no"},
            "LossAutopsyService": {"state": "implemented", "activation_state": "active", "kraken_spot_compatible": "yes", "exact_blocker": "", "exact_unlock_action_required": "", "doctrine_conflict": "no"},
            "ObservabilityFacade": {"state": "implemented", "activation_state": "active", "kraken_spot_compatible": "yes", "exact_blocker": "", "exact_unlock_action_required": "", "doctrine_conflict": "no"},
            "HumanEscalationLayer": {"state": "implemented", "activation_state": "active" if self.human_escalation is not None else "gated", "kraken_spot_compatible": "yes", "exact_blocker": "" if self.human_escalation is not None else "human_escalation_missing", "exact_unlock_action_required": "" if self.human_escalation is not None else "wire_human_escalation", "doctrine_conflict": "no"},
            "OperatorSummaryCoordinator": {"state": "implemented", "activation_state": "active", "kraken_spot_compatible": "yes", "exact_blocker": "", "exact_unlock_action_required": "", "doctrine_conflict": "no"},
        }
        capability_matrix = [{"capability_name": name, **details} for name, details in sorted(capabilities.items())]
        activated = {name: details for name, details in capabilities.items() if str(details["activation_state"]).startswith("active")}
        still_gated = {name: details for name, details in capabilities.items() if not str(details["activation_state"]).startswith("active")}
        return capability_matrix, activated, still_gated

    def _emit_live_runtime_summary(
        self,
        *,
        symbol: str,
        mode: ExecutionMode,
        market: object,
        decision_ctx: object,
        execution_result: object | None = None,
        step: int,
    ) -> str:
        capability_matrix, activated, still_gated = self._live_capability_bundle(market=market, decision_ctx=decision_ctx)
        doctrine_blocked = self._doctrine_block_map()
        throughput = self._throughput_snapshot()
        trace = self._decision_collapse_trace(
            market=market,
            decision_ctx=decision_ctx,
            execution_result=execution_result,
            step=step,
        )
        trace_payload = self._serialize_payload(trace)
        explainability = self._decision_explainability(
            market=market,
            decision_ctx=decision_ctx,
            execution_result=execution_result,
            trace=trace,
        )
        runtime_ordering_allowed, runtime_blocking_reasons = self._runtime_ordering_gate_state(
            market=market,
            decision_ctx=decision_ctx,
        )
        health_summary = self.runtime_metadata.health_summary(
            preflight_ok=bool(self._last_live_preflight_ok),
            ordering_allowed=runtime_ordering_allowed,
            throughput=throughput,
            failure_taxonomy=throughput.get("failure_taxonomy", {}),
            blocking_reasons=runtime_blocking_reasons,
            infra_ok=bool(self._last_live_preflight_ok),
            trade_path_state=trace.trade_path_state,
            ranked_blockers=[]
            if not isinstance(trace_payload, dict)
            else list(trace_payload.get("ranked_blockers", []) or [])[:8],
            reason_chain=list(trace.reason_chain),
        )
        performance_artifacts = self._performance_architecture_artifacts(
            symbol=symbol,
            market=market,
            decision_ctx=decision_ctx,
            health_summary=health_summary,
            runtime_ordering_allowed=runtime_ordering_allowed,
            execution_result=execution_result,
        )
        health_summary["performance_gap"] = dict(
            (performance_artifacts.get("performance_gap_report") if isinstance(performance_artifacts.get("performance_gap_report"), dict) else {}) or {}
        ).get("gaps", {})
        artifact_index = {
            "run_dir": self.settings.storage.run_dir,
            "step": step,
            "files": sorted(path.name for path in Path(self.settings.storage.run_dir).glob("*.json*")),
        }
        self._write_json_artifact("live_capability_matrix.json", capability_matrix)
        self._write_json_artifact("live_activated_capabilities.json", activated)
        self._write_json_artifact("live_still_gated_capabilities.json", still_gated)
        self._write_json_artifact("live_doctrine_blocked_capabilities.json", doctrine_blocked)
        self._write_json_artifact("throughput_diagnostics.json", throughput)
        self._write_json_artifact("failure_taxonomy.json", throughput.get("failure_taxonomy", {}))
        self._append_jsonl_artifact("decision_collapse_trace.jsonl", trace_payload)
        self._write_json_artifact("decision_collapse_trace_latest.json", trace_payload)
        self._write_json_artifact("decision_explainability.json", explainability)
        self._write_json_artifact("health_summary.json", health_summary)
        for name, payload in performance_artifacts.items():
            if name == "selected_candidate":
                continue
            self._write_json_artifact(f"{name}.json", payload)
        artifact_index["files"] = sorted(path.name for path in Path(self.settings.storage.run_dir).glob("*.json*"))
        self._write_json_artifact("live_artifact_index.json", artifact_index)
        summary = {
            "symbol": symbol,
            "mode": mode.value,
            "provider_id": self.settings.execution.provider_id,
            "step": step,
            "rollout_stage": self.settings.rollout_stage().value,
            "harmony": self.harmony.resolve(),
            "live_gate_status": self.settings.live_gate_status(),
            "market_context": {
                "market_integrity": self._serialize_payload(getattr(market, "market_integrity", None)),
                "provider_capability": self._serialize_payload(getattr(market, "provider_capability", None)),
                "market_watch": self._serialize_payload(getattr(market, "market_watch", None)),
                "event_intelligence": self._serialize_payload(getattr(market, "event_intelligence_report", None)),
                "execution_quality": self._serialize_payload(getattr(market, "execution_quality", None)),
                "forecast": self._serialize_payload(getattr(market, "forecast", None)),
            },
            "decision": {
                "meta_governor": self._serialize_payload(getattr(decision_ctx, "meta_governor_decision", None)),
                "policy": self._serialize_payload(getattr(decision_ctx, "policy_decision", None)),
                "risk": self._serialize_payload(getattr(decision_ctx, "risk_decision", None)),
                "adjusted_intent": self._serialize_payload(getattr(decision_ctx, "adjusted_intent", None)),
                "execution_plan": self._serialize_payload(getattr(decision_ctx, "execution_plan", None)),
                "synthetic_affect": self._serialize_payload(getattr(decision_ctx, "synthetic_affect_state", None)),
                "capital_sovereignty": self._serialize_payload(getattr(decision_ctx, "capital_sovereignty_decision", None)),
                "position_morph": self._serialize_payload(getattr(decision_ctx, "position_morph_plan", None)),
                "adaptive_exit": self._serialize_payload(getattr(decision_ctx, "adaptive_exit_allocation", None)),
                "execution_simulation": self._serialize_payload(getattr(decision_ctx, "execution_simulation_report", None)),
                "human_escalation": self._serialize_payload(getattr(decision_ctx, "human_escalation_decision", None)),
            },
            "execution_result": self._serialize_payload(execution_result),
            "lifecycle_proof": {}
            if execution_result is None
            else dict(
                (
                    getattr(execution_result, "metadata", {}) or {}
                ).get("lifecycle_proof", {})
                if isinstance(getattr(execution_result, "metadata", {}) or {}, dict)
                else {}
            ),
            "forensics": {
                "pnl_attribution_records": self._jsonl_count("pnl_attribution"),
                "loss_autopsy_records": self._jsonl_count("loss_autopsy"),
                "analog_trade_lookup_records": self._jsonl_count("analog_trade_lookup"),
                "counterfactual_review_records": self._jsonl_count("counterfactual_review"),
                "calibration_profile_records": 1 if (Path(self.settings.storage.run_dir) / "calibration_profile.json").exists() else 0,
            },
            "activation": {
                "activated": sorted(activated.keys()),
                "still_gated": sorted(still_gated.keys()),
                "doctrine_blocked": doctrine_blocked,
            },
            "throughput": throughput,
            "failure_taxonomy": throughput.get("failure_taxonomy", {}),
            "trade_path_state": trace.trade_path_state,
            "current_blocker_chain": []
            if not isinstance(trace_payload, dict)
            else list(trace_payload.get("ranked_blockers", []) or [])[:8],
            "decision_collapse_trace": trace_payload,
            "explainability": explainability,
            "health_summary": health_summary,
            "performance_architecture": {
                "capital_envelope": performance_artifacts.get("capital_envelope_summary", {}),
                "target_translation": performance_artifacts.get("performance_target_translation", {}),
                "target_gap": performance_artifacts.get("performance_gap_report", {}),
                "market_universe": performance_artifacts.get("pair_ranking_report", {}),
                "regime": performance_artifacts.get("regime_snapshot", {}),
                "playbooks": performance_artifacts.get("playbook_candidate_log", {}),
                "opportunity_auction": performance_artifacts.get("opportunity_auction_report", {}),
                "allocator": performance_artifacts.get("allocator_decisions", {}),
                "expectancy": performance_artifacts.get("expectancy_engine_report", {}),
                "experiments": performance_artifacts.get("experiment_registry", {}),
                "dead_capital": performance_artifacts.get("dead_capital_pressure_report", {}),
                "execution_alpha": {
                    "cost_model": performance_artifacts.get("cost_model_diagnostics", {}),
                    "private_stream_health": performance_artifacts.get("private_stream_health", {}),
                    "live_degradation": performance_artifacts.get("live_degradation_detector_report", {}),
                    "self_throttling": performance_artifacts.get("self_throttling_state_report", {}),
                },
                "selected_candidate": performance_artifacts.get("selected_candidate", {}),
            },
            "rollout_profile": self.settings.rollout_profile(),
        }
        return self.operator_summary.emit(summary=summary)

    def _runtime_ordering_gate_state(
        self,
        *,
        market: object,
        decision_ctx: object,
    ) -> tuple[bool, list[str]]:
        if not bool(self._last_live_preflight_ok):
            return False, list(self._last_live_blocking_reasons)

        market_integrity = getattr(market, "market_integrity", None)
        market_integrity_action = "continue" if market_integrity is None else str(getattr(market_integrity, "action", "continue") or "continue")
        if market_integrity_action in {"degrade", "flatten_only", "halt", "halt_and_flatten"}:
            reasons = list(getattr(market_integrity, "reasons", []) or [])
            return False, reasons or [f"market_integrity:{market_integrity_action}"]

        truth_context = {}
        policy = getattr(decision_ctx, "policy_decision", None)
        why = getattr(policy, "why", {}) if policy is not None else {}
        if isinstance(why, dict):
            truth_context = dict(why.get("truth_context", {}) or {})
        if truth_context.get("reconciliation_ok") is False:
            return False, ["reconciliation_not_ok"]

        snapshot = truth_context.get("snapshot", truth_context.get("truth_confidence", truth_context))
        if isinstance(snapshot, dict):
            action = str(snapshot.get("overall_action", "continue") or "continue")
            if action in {"degrade", "flatten_only", "halt", "halt_and_flatten"}:
                reasons = [
                    f"truth_confidence:{action}:{str(reason).strip()}"
                    for reason in list(snapshot.get("reasons", []) or [])
                    if str(reason).strip()
                ]
                return False, reasons or [f"truth_confidence:{action}"]

        return True, []

    def _emit_readonly_analysis(self, *, live: object, symbol: str) -> dict[str, object]:
        if not self.settings.kraken_spot_full_analysis_enabled():
            return {}
        now_dt = datetime.now(timezone.utc)
        throughput = self._throughput_snapshot()
        market = self.live_market.collect(
            live=live,
            symbol=symbol,
            now_dt=now_dt,
            prices=[],
            base_budget=max(float(self.settings.policy.base_risk_budget), 1.0),
            exposure_notional=0.0,
        )
        decision_ctx = self.live_decision.evaluate(
            symbol=symbol,
            market=market,
            exposure_notional=0.0,
            last_recon_ok=True,
            live=live,
            drawdown_pct=0.0,
            daily_loss_pct=0.0,
            weekly_loss_pct=0.0,
            funding_paid_pct=0.0,
            legacy_policy_why=self._legacy_policy_why,
            legacy_risk_details=self._legacy_risk_details,
            reconciliation_report=None,
        )
        trace = self._decision_collapse_trace(
            market=market,
            decision_ctx=decision_ctx,
            execution_result=None,
            step=0,
        )
        trace_payload = self._serialize_payload(trace)
        explainability = self._decision_explainability(
            market=market,
            decision_ctx=decision_ctx,
            execution_result=None,
            trace=trace,
        )
        readonly_blocking_reasons = ["ordering_not_allowed_in_mode:live_readonly"]
        policy_decision = getattr(decision_ctx, "policy_decision", None)
        no_trade = None if policy_decision is None else getattr(policy_decision, "no_trade", None)
        no_trade_reason = "" if no_trade is None else str(getattr(no_trade, "reason", "") or "").strip()
        if no_trade_reason:
            readonly_blocking_reasons.append(no_trade_reason)
        health_summary = self.runtime_metadata.health_summary(
            preflight_ok=bool(self._last_live_preflight_ok),
            ordering_allowed=False,
            throughput=throughput,
            failure_taxonomy=throughput.get("failure_taxonomy", {}),
            blocking_reasons=self._dedupe_reasons(readonly_blocking_reasons),
            infra_ok=bool(self._last_live_preflight_ok),
            trade_path_state=trace.trade_path_state,
            ranked_blockers=[]
            if not isinstance(trace_payload, dict)
            else list(trace_payload.get("ranked_blockers", []) or [])[:8],
            reason_chain=list(trace.reason_chain),
        )
        performance_artifacts = self._performance_architecture_artifacts(
            symbol=symbol,
            market=market,
            decision_ctx=decision_ctx,
            health_summary=health_summary,
            runtime_ordering_allowed=False,
            execution_result=None,
        )
        health_summary["performance_gap"] = dict(
            (performance_artifacts.get("performance_gap_report") if isinstance(performance_artifacts.get("performance_gap_report"), dict) else {}) or {}
        ).get("gaps", {})
        capabilities = {
            "MarketIntegrityService": "active",
            "VenueCapabilityRegistry": "active",
            "HarmonyConfigResolver": "active",
            "QuantumScenarioService": "active",
            "SignalInterferenceEngine": "active",
            "EdgeImmunityService": "active",
            "SPREEngine": "active",
            "ShadowRivalService": "active",
            "CapitalSovereigntyService": "active",
            "PositionMorphingEngine": "active",
            "AdaptiveExitAllocator": "active",
            "SyntheticAffectEngine": "active",
            "ExecutionSimulationSandbox": "active",
            "ObservabilityFacade": "active",
            "HumanEscalationLayer": "active",
            "OperatorSummaryCoordinator": "active" if self.settings.kraken_spot_non_live.emit_operator_bundle else "gated",
            "ReplayReportingCoordinator": "active" if self.settings.kraken_spot_non_live.emit_replay_bundle else "gated",
            "EventIntelligenceService": "active_but_partial"
            if getattr(market.event_intelligence_report, "partial", True)
            else "active",
        }
        capability_matrix = [
            {
                "capability_name": name,
                "state": "implemented",
                "activation_state": status,
                "kraken_spot_compatible": "yes",
                "exact_blocker": "no_event_evidence" if name == "EventIntelligenceService" and status == "active_but_partial" else "",
                "exact_unlock_action_required": "provide_event_fixture_or_recording" if name == "EventIntelligenceService" and status == "active_but_partial" else "",
                "doctrine_conflict": "no",
            }
            for name, status in sorted(capabilities.items())
        ]
        activated = {row["capability_name"]: row for row in capability_matrix if str(row["activation_state"]).startswith("active")}
        still_gated = {row["capability_name"]: row for row in capability_matrix if not str(row["activation_state"]).startswith("active")}
        artifact_index = {
            "run_dir": self.settings.storage.run_dir,
            "profile": self.settings.kraken_spot_non_live.profile,
            "files": [],
        }
        replay_summary = {
            "symbol": symbol,
            "mode": self.settings.execution_mode_enum().value,
            "profile": self.settings.kraken_spot_non_live.profile,
            "provider_id": self.settings.execution.provider_id,
            "market_integrity": asdict(market.market_integrity) if market.market_integrity is not None else {},
            "provider_capability": asdict(market.provider_capability),
            "market_watch": asdict(market.market_watch) if market.market_watch is not None else {},
            "event_partial": bool(getattr(market.event_intelligence_report, "partial", True)),
        }
        operator_summary = {
            "symbol": symbol,
            "mode": self.settings.execution_mode_enum().value,
            "profile": self.settings.kraken_spot_non_live.profile,
            "harmony": self.harmony.resolve(),
            "decision_doctrine": {}
            if decision_ctx.policy_decision is None
            else dict(getattr(decision_ctx.policy_decision, "why", {}).get("decision_doctrine", {}) or {}),
            "capital_strategy": {
                "capital_sovereignty": None
                if decision_ctx.capital_sovereignty_decision is None
                else asdict(decision_ctx.capital_sovereignty_decision),
                "position_morph": None if decision_ctx.position_morph_plan is None else asdict(decision_ctx.position_morph_plan),
                "adaptive_exit": None if decision_ctx.adaptive_exit_allocation is None else asdict(decision_ctx.adaptive_exit_allocation),
            },
            "market_context": replay_summary,
            "human_escalation": None if decision_ctx.human_escalation_decision is None else asdict(decision_ctx.human_escalation_decision),
            "activation": {
                "activated": sorted(activated.keys()),
                "still_gated": sorted(still_gated.keys()),
                "doctrine_blocked": self._doctrine_block_map(),
            },
            "throughput": throughput,
            "decision_collapse_trace": trace_payload,
            "explainability": explainability,
            "health_summary": health_summary,
            "performance_architecture": {
                "capital_envelope": performance_artifacts.get("capital_envelope_summary", {}),
                "target_translation": performance_artifacts.get("performance_target_translation", {}),
                "target_gap": performance_artifacts.get("performance_gap_report", {}),
                "market_universe": performance_artifacts.get("pair_ranking_report", {}),
                "regime": performance_artifacts.get("regime_snapshot", {}),
                "playbooks": performance_artifacts.get("playbook_candidate_log", {}),
                "opportunity_auction": performance_artifacts.get("opportunity_auction_report", {}),
                "allocator": performance_artifacts.get("allocator_decisions", {}),
                "expectancy": performance_artifacts.get("expectancy_engine_report", {}),
                "experiments": performance_artifacts.get("experiment_registry", {}),
                "dead_capital": performance_artifacts.get("dead_capital_pressure_report", {}),
                "execution_alpha": {
                    "cost_model": performance_artifacts.get("cost_model_diagnostics", {}),
                    "private_stream_health": performance_artifacts.get("private_stream_health", {}),
                    "live_degradation": performance_artifacts.get("live_degradation_detector_report", {}),
                    "self_throttling": performance_artifacts.get("self_throttling_state_report", {}),
                },
                "selected_candidate": performance_artifacts.get("selected_candidate", {}),
            },
        }
        self._append_jsonl_artifact("decision_collapse_trace.jsonl", trace_payload)
        self._write_json_artifact("decision_collapse_trace_latest.json", trace_payload)
        self._write_json_artifact("decision_explainability.json", explainability)
        self._write_json_artifact("health_summary.json", health_summary)
        self._write_json_artifact("live_capability_matrix.json", capability_matrix)
        self._write_json_artifact("live_activated_capabilities.json", activated)
        self._write_json_artifact("live_still_gated_capabilities.json", still_gated)
        self._write_json_artifact("live_doctrine_blocked_capabilities.json", self._doctrine_block_map())
        self._write_json_artifact("throughput_diagnostics.json", throughput)
        self._write_json_artifact("failure_taxonomy.json", throughput.get("failure_taxonomy", {}))
        for name, payload in performance_artifacts.items():
            if name == "selected_candidate":
                continue
            self._write_json_artifact(f"{name}.json", payload)
        artifact_index["files"] = sorted(path.name for path in Path(self.settings.storage.run_dir).glob("*.json*"))
        self._write_json_artifact("live_artifact_index.json", artifact_index)
        result: dict[str, object] = {}
        if self.settings.kraken_spot_non_live.emit_replay_bundle:
            result["replay_bundle"] = self.replay_reporting.emit(
                summary=replay_summary,
                capability_matrix=capability_matrix,
                activated=activated,
                still_gated=still_gated,
                doctrine_blocked=self._doctrine_block_map(),
                artifact_index=artifact_index,
            )
        if self.settings.kraken_spot_non_live.emit_operator_bundle:
            result["operator_summary_path"] = self.operator_summary.emit(summary=operator_summary)
        return result

    def _emit_live_boot_summary(
        self,
        *,
        symbol: str,
        mode: ExecutionMode,
        harmony_payload: dict[str, object],
        preflight_ok: bool,
        preflight_reason: str,
        confidence: str,
        confidence_details: dict[str, object],
        recovery_decision: RecoveryDecision,
        ordering_allowed: bool,
        artifact_paths: dict[str, str] | None = None,
    ) -> str:
        summary = {
            "symbol": symbol,
            "mode": mode.value,
            "provider_id": self.settings.execution.provider_id,
            "doctrine": self.settings.config_manifest().get("doctrine", {}),
            "harmony": harmony_payload,
            "live_gate_status": self.settings.live_gate_status(),
            "preflight": {
                "ok": preflight_ok,
                "reason": preflight_reason,
            },
            "restart_state": {
                "confidence": confidence,
                "details": confidence_details,
                "recovery": asdict(recovery_decision),
            },
            "ordering_allowed": ordering_allowed,
            "capital_protection": {
                "cost_basis_sell_block": bool(self.settings.doctrine.enforce_cost_basis_sell_block),
                "net_profit_sell_block": bool(self.settings.doctrine.enforce_net_profit_sell_block),
                "minimum_sell_net_profit_bps": float(self.settings.doctrine.minimum_sell_net_profit_bps),
                "block_non_reduce_only_sells": bool(self.settings.doctrine.block_non_reduce_only_sells),
            },
            "provider_capability": asdict(self.execution.provider_capability_matrix()),
            "rollout_profile": self.settings.rollout_profile(),
            "artifact_paths": artifact_paths or {},
        }
        return self.operator_summary.emit(summary=summary)

    def _live_loop(self, live: object, symbol: str, mode: ExecutionMode) -> dict:
        harmony = self.harmony.resolve()
        poll_s = max(1.0, float(harmony.get("order_cadence_s", 5.0) or 5.0))
        max_steps = int(os.getenv("AUTONOMOUS_LIVE_LOOP_MAX_STEPS", "0") or "0")
        base_budget = max(float(self.settings.policy.base_risk_budget), 1.0)
        exposure_notional = 0.0
        equity = 1.0
        peak = 1.0
        funding_paid_pct = 0.0
        prices: list[float] = []
        last_mid = None
        steps = 0
        last_recon_ok = True
        latest_operator_summary_path = ""
        pause_active = False
        pause_reason = ""

        self.ops.audit_event(
            "live_loop_start",
            {
                "mode": mode.value,
                "symbol": symbol,
                "poll_s": poll_s,
                "max_steps": max_steps,
                "harmony_order_cadence_source": harmony.get("order_cadence_source"),
            },
        )
        while True:
            loop_started = time.perf_counter()
            steps += 1
            self._live_runtime_diagnostics["loop_steps"] = steps
            now_ts = time.time()
            now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
            stop_result = self.live_control.check_kill_file(
                live=live,
                kill_path=self._kill_file_path(),
                mode=mode.value,
                steps=steps,
            )
            if stop_result is not None:
                return stop_result

            pause_marker = self._pause_marker()
            if pause_marker is not None:
                marker_reason = str(pause_marker["reason"])
                if not pause_active or pause_reason != marker_reason:
                    payload = {
                        "control_surface": "pause_marker",
                        "action": "pause",
                        "mode": mode.value,
                        "steps": steps,
                        "pause_path": pause_marker["pause_path"],
                        "reason": marker_reason,
                        "requested_at": pause_marker["requested_at"],
                    }
                    self.ops.audit_event("operator_pause", payload)
                    self.observability.journal("control_journal", payload)
                pause_active = True
                pause_reason = marker_reason
                self._live_runtime_diagnostics["operator_pause_blocks"] = int(self._live_runtime_diagnostics.get("operator_pause_blocks", 0)) + 1
                self._record_live_reason(reason=f"operator_pause:{marker_reason}", surface="control")
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {
                        "status": "ok",
                        "mode": mode.value,
                        "reason": "max_steps_reached",
                        "steps": steps,
                        "operator_summary_path": latest_operator_summary_path,
                    }
                time.sleep(poll_s)
                continue
            if pause_active:
                payload = {
                    "control_surface": "pause_marker",
                    "action": "resume",
                    "mode": mode.value,
                    "steps": steps,
                    "pause_path": self._pause_file_path(),
                    "reason": pause_reason,
                }
                self.ops.audit_event("operator_resume", payload)
                self.observability.journal("control_journal", payload)
                pause_active = False
                pause_reason = ""

            try:
                market = self.live_market.collect(
                    live=live,
                    symbol=symbol,
                    now_dt=now_dt,
                    prices=prices,
                    base_budget=base_budget,
                    exposure_notional=exposure_notional,
                )
            except Exception as exc:
                message = str(exc)
                if message.startswith("book_invalid:"):
                    _, bid_raw, ask_raw = message.split(":", 2)
                    self.ops.audit_event("book_invalid", {"symbol": symbol, "bid": float(bid_raw), "ask": float(ask_raw)})
                    self.ops.inc_metric("book_invalid_total")
                    self._record_live_reason(reason="book_invalid", surface="market_data")
                else:
                    self.ops.audit_event("book_error", {"symbol": symbol, "error": message})
                    self.ops.inc_metric("book_errors_total")
                    self._record_live_reason(reason=message, surface="market_data")
                self.ops.export_prometheus()
                time.sleep(poll_s)
                continue

            prices = market.prices
            mid = market.snapshot.mid
            spread_bps = market.snapshot.spread_bps
            depth_notional = market.snapshot.depth_notional
            self._maybe_warn_latency("stage_market_snapshot_ms", market.market_stage_ms, 50.0)
            self._maybe_warn_latency("stage_forecast_regime_ms", market.forecast_stage_ms, 75.0)
            self._maybe_warn_latency("stage_quantum_state_ms", market.quantum_stage_ms, 60.0)
            self._maybe_warn_latency("stage_edge_immunity_ms", market.edge_immunity_stage_ms, 40.0)
            if market.advisory is not None and market.advisory.signal != "unavailable":
                self.ops.audit_event(
                    "advisory",
                    {
                        "provider": market.advisory.provider,
                        "signal": market.advisory.signal,
                        "confidence": market.advisory.confidence,
                        "reason": market.advisory.reason,
                    },
                )

            # Mark-to-market on estimated internal exposure.
            if last_mid is not None and abs(exposure_notional) > 1e-9:
                pnl = exposure_notional * ((mid / max(last_mid, 1e-9)) - 1.0)
                equity += pnl / base_budget
                self.risk.record_return((pnl / max(abs(exposure_notional), 1.0)) * 100.0)
                self.portfolio.mark_to_market(symbol, pnl)
            last_mid = mid
            peak = max(peak, equity)
            drawdown_pct = (equity / peak - 1.0) * 100.0
            daily_loss_pct = min(0.0, (equity - 1.0) * 100.0)
            weekly_loss_pct = daily_loss_pct

            if hasattr(live, "connector"):
                recon_result = self.live_reconciliation.apply(
                    live=live,
                    symbol=symbol,
                    exposure_notional=exposure_notional,
                    market_health=market.market_health,
                )
                last_recon_ok = recon_result.ok
                exposure_notional = recon_result.exposure_notional
                self._maybe_warn_latency("stage_reconciliation_ms", recon_result.elapsed_ms, self.settings.monitoring.reconciliation_lag_warn_ms)

            decision_ctx = self.live_decision.evaluate(
                symbol=symbol,
                market=market,
                exposure_notional=exposure_notional,
                last_recon_ok=last_recon_ok,
                live=live,
                drawdown_pct=drawdown_pct,
                daily_loss_pct=daily_loss_pct,
                weekly_loss_pct=weekly_loss_pct,
                funding_paid_pct=funding_paid_pct,
                legacy_policy_why=self._legacy_policy_why,
                legacy_risk_details=self._legacy_risk_details,
                reconciliation_report=recon_result.report if hasattr(live, "connector") else None,
            )
            latest_operator_summary_path = self._emit_live_runtime_summary(
                symbol=symbol,
                mode=mode,
                market=market,
                decision_ctx=decision_ctx,
                step=steps,
            )
            health_snapshot = decision_ctx.health_snapshot
            meta_governor = decision_ctx.meta_governor_decision
            meta_control = self.live_control.apply_meta_governor(
                live=live,
                meta_governor=meta_governor,
                mode=mode.value,
                steps=steps,
                exposure_notional=exposure_notional,
            )
            exposure_notional = meta_control.exposure_notional
            if meta_control.stop_result is not None:
                self._live_runtime_diagnostics["meta_governor_blocks"] = int(self._live_runtime_diagnostics["meta_governor_blocks"]) + 1
                meta_control.stop_result.setdefault("operator_summary_path", latest_operator_summary_path)
                return meta_control.stop_result
            if meta_control.continue_loop:
                self._live_runtime_diagnostics["meta_governor_blocks"] = int(self._live_runtime_diagnostics["meta_governor_blocks"]) + 1
                self._record_live_reason(reason=str(getattr(meta_governor, "action", "continue")), surface="meta_governor")
                if max_steps and steps >= max_steps:
                    return {
                        "status": "ok",
                        "mode": mode.value,
                        "reason": "max_steps_reached",
                        "steps": steps,
                        "operator_summary_path": latest_operator_summary_path,
                    }
                time.sleep(poll_s)
                continue
            if health_snapshot.action == "halt_and_flatten" and hasattr(live, "flatten_all_positions"):
                self._record_live_reason(reason="health_halt_and_flatten", surface="health")
                closed, flat_reason = live.flatten_all_positions()
                if closed:
                    exposure_notional = 0.0
                self.ops.audit_event("flatten", {"reason": flat_reason, "closed": closed, "from": "health_meta_governor"})
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                return {
                    "status": "stopped",
                    "mode": mode.value,
                    "reason": "health_meta_governor",
                    "steps": steps,
                    "operator_summary_path": latest_operator_summary_path,
                }
            if health_snapshot.action == "halt":
                self._record_live_reason(reason="health_halt", surface="health")
                self.ops.audit_event("health_halt", {"reasons": health_snapshot.reasons})
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {
                        "status": "ok",
                        "mode": mode.value,
                        "reason": "max_steps_reached",
                        "steps": steps,
                        "operator_summary_path": latest_operator_summary_path,
                    }
                time.sleep(poll_s)
                continue
            self._maybe_warn_latency("stage_policy_health_ms", decision_ctx.health_stage_ms, self.settings.monitoring.decision_latency_warn_ms)

            self.live_metrics.record_loop_state(
                mid=mid,
                spread_bps=spread_bps,
                depth_notional=depth_notional,
                equity=equity,
                peak=peak,
                exposure_notional=exposure_notional,
                health_snapshot=health_snapshot,
            )
            incident_control = self.live_control.apply_incidents(
                live=live,
                exposure_notional=exposure_notional,
                mode=mode.value,
                steps=steps,
                risk_engine=self.risk,
            )
            exposure_notional = incident_control.exposure_notional
            if incident_control.stop_result is not None:
                return incident_control.stop_result

            policy_decision = decision_ctx.policy_decision
            if policy_decision is None:
                self._live_runtime_diagnostics["no_intent"] = int(self._live_runtime_diagnostics["no_intent"]) + 1
                self._record_live_reason(reason="policy_decision_missing", surface="policy")
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {
                        "status": "ok",
                        "mode": mode.value,
                        "reason": "max_steps_reached",
                        "steps": steps,
                        "operator_summary_path": latest_operator_summary_path,
                    }
                time.sleep(poll_s)
                continue
            if (not policy_decision.trade_allowed or policy_decision.side is None) and decision_ctx.adjusted_intent is None:
                self._live_runtime_diagnostics["no_intent"] = int(self._live_runtime_diagnostics["no_intent"]) + 1
                self.ops.inc_metric("orders_rejected_total")
                no_trade_reason = policy_decision.no_trade.reason if policy_decision.no_trade is not None else "no_trade"
                self._record_live_reason(reason=no_trade_reason, surface="policy")
                self.ops.audit_event(
                    "heartbeat",
                    {
                        "symbol": symbol,
                        "mid": mid,
                        "spread_bps": spread_bps,
                        "equity": equity,
                        "reason": no_trade_reason,
                        "regime": market.forecast.regime,
                        "liq_regime": market.forecast.liquidity_regime,
                    },
                )
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {
                        "status": "ok",
                        "mode": mode.value,
                        "reason": "max_steps_reached",
                        "steps": steps,
                        "operator_summary_path": latest_operator_summary_path,
                    }
                time.sleep(poll_s)
                continue
            decision = decision_ctx.risk_decision
            if decision is None:
                self._live_runtime_diagnostics["risk_rejected"] = int(self._live_runtime_diagnostics["risk_rejected"]) + 1
                self._record_live_reason(reason="risk_decision_missing", surface="risk")
                self.ops.inc_metric("orders_rejected_total")
                self.ops.audit_event("risk_reject", {"reason": "risk_decision_missing", "details": {}})
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {
                        "status": "ok",
                        "mode": mode.value,
                        "reason": "max_steps_reached",
                        "steps": steps,
                        "operator_summary_path": latest_operator_summary_path,
                    }
                time.sleep(poll_s)
                continue
            self._maybe_warn_latency("stage_risk_ms", decision_ctx.risk_stage_ms, 50.0)
            self.ops.set_metric("crowding_score", float(decision.details.get("crowding_score", self.risk.state.last_crowding_score)))
            level = decision.details.get("crowding_level", self.risk.state.last_crowding_level)
            self.ops.set_metric("crowding_level", float({"none": 0, "medium": 1, "high": 2, "extreme": 3}.get(str(level), 0)))
            self.ops.set_metric("funding_budget_utilization", float(decision.details.get("funding_budget_utilization", 0.0)))
            self.ops.set_metric("risk_mode", float({"normal": 0, "cautious": 1, "degraded": 2, "defensive": 3, "flatten-only": 4, "kill-switch": 5}.get(self.risk.state.risk_mode, 0)))

            if not decision.allowed:
                self._live_runtime_diagnostics["risk_rejected"] = int(self._live_runtime_diagnostics["risk_rejected"]) + 1
                self._record_live_reason(reason=str(decision.reason), surface="risk")
                self.ops.inc_metric("orders_rejected_total")
                self.ops.audit_event("risk_reject", {"reason": decision.reason, "details": decision.details})
                if decision.flatten and hasattr(live, "flatten_all_positions"):
                    try:
                        closed, flat_reason = live.flatten_all_positions()
                        if closed:
                            exposure_notional = 0.0
                        self.ops.audit_event("flatten", {"reason": flat_reason, "closed": closed, "from": decision.reason})
                    except Exception as exc:
                        self.ops.audit_event("flatten_error", {"from": decision.reason, "error": str(exc)})
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {
                        "status": "ok",
                        "mode": mode.value,
                        "reason": "max_steps_reached",
                        "steps": steps,
                        "operator_summary_path": latest_operator_summary_path,
                    }
                time.sleep(poll_s)
                continue

            adjusted = decision_ctx.adjusted_intent
            plan = decision_ctx.execution_plan
            if adjusted is None or plan is None:
                self._live_runtime_diagnostics["orders_blocked"] = int(self._live_runtime_diagnostics["orders_blocked"]) + 1
                self._record_live_reason(reason="execution_plan_missing", surface="execution")
                self.ops.inc_metric("orders_rejected_total")
                self.ops.audit_event("risk_reject", {"reason": "execution_plan_missing", "details": decision.details})
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                if max_steps and steps >= max_steps:
                    return {
                        "status": "ok",
                        "mode": mode.value,
                        "reason": "max_steps_reached",
                        "steps": steps,
                        "operator_summary_path": latest_operator_summary_path,
                    }
                time.sleep(poll_s)
                continue
            self._maybe_warn_latency("stage_execution_planning_ms", decision_ctx.execution_stage_ms, 50.0)
            live_idem = make_idempotency_key(asdict(adjusted), provider_id := self.settings.execution.provider_id, steps)
            self.event_store.append(
                "orders",
                make_event(OrderIntentEvent, "ORDER_INTENT", symbol, provider_id, self.event_store.next_seq("orders"), asdict(adjusted), idempotency_key=live_idem),
            )
            self._live_runtime_diagnostics["execution_attempts"] = int(self._live_runtime_diagnostics["execution_attempts"]) + 1
            result = self.execution.execute_live(adjusted)
            self.ops.audit_event(
                "live_exec",
                {"status": result.status, "reason": result.reason, "symbol": adjusted.symbol, "side": adjusted.side, "notional": adjusted.target_notional},
            )
            if getattr(result, "reason", ""):
                self._record_live_reason(reason=str(result.reason), surface="execution")
            ledger_result = self.live_ledger.apply_execution_result(
                symbol=symbol,
                provider_id=provider_id,
                result=result,
                fallback_intent_notional=adjusted.target_notional,
                fallback_side=adjusted.side,
                current_exposure=exposure_notional,
                live=live,
            )
            latest_operator_summary_path = self._emit_live_runtime_summary(
                symbol=symbol,
                mode=mode,
                market=market,
                decision_ctx=decision_ctx,
                execution_result=result,
                step=steps,
            )
            if result.status in {"filled_maker", "filled_taker_fallback", "filled_marketable_limit"}:
                exposure_notional = ledger_result.exposure_notional
                self.ops.inc_metric("orders_submitted_total")
                self._live_runtime_diagnostics["orders_submitted"] = int(self._live_runtime_diagnostics["orders_submitted"]) + 1
                self._live_runtime_diagnostics["fills"] = int(self._live_runtime_diagnostics["fills"]) + 1
                if not ledger_result.fill_truth_ok:
                    self.ops.inc_metric("live_fill_truth_gap_total")
                    self._record_live_reason(reason="live_fill_truth_gap", surface="truth_confidence")
            elif result.status in {"rejected", "blocked", "killed"}:
                self.ops.inc_metric("orders_rejected_total")
                if result.status == "blocked":
                    self._live_runtime_diagnostics["orders_blocked"] = int(self._live_runtime_diagnostics["orders_blocked"]) + 1
                else:
                    self._live_runtime_diagnostics["orders_rejected"] = int(self._live_runtime_diagnostics["orders_rejected"]) + 1
            elif result.status == "deduped":
                self._live_runtime_diagnostics["deduped"] = int(self._live_runtime_diagnostics["deduped"]) + 1

            if getattr(live, "killed", False):
                self.ops.audit_event("live_killed", {"reason": getattr(live, "kill_reason", "")})
                self.ops.export_prometheus()
                self.ops.export_dashboard_snapshot()
                return {
                    "status": "stopped",
                    "mode": mode.value,
                    "reason": getattr(live, "kill_reason", "kill_switch_active"),
                    "steps": steps,
                    "operator_summary_path": latest_operator_summary_path,
                }

            self.ops.export_prometheus()
            self.ops.export_dashboard_snapshot()
            self._maybe_warn_latency("loop_duration_ms", (time.perf_counter() - loop_started) * 1000.0, self.settings.monitoring.loop_latency_warn_ms)
            if max_steps and steps >= max_steps:
                return {
                    "status": "ok",
                    "mode": mode.value,
                    "reason": "max_steps_reached",
                    "steps": steps,
                    "operator_summary_path": latest_operator_summary_path,
                }
            time.sleep(poll_s)

    def boot(self) -> dict:
        cfg_hash = self.ops.track_config(asdict(self.settings))
        config_manifest = self.settings.config_manifest()
        config_manifest["config_hash"] = cfg_hash
        self.raw.write_table("config_manifest", [config_manifest])
        self.observability.journal("config_manifest", config_manifest)
        harmony_paths = self.harmony.write_reports(self.settings.storage.run_dir)
        harmony_payload = self.harmony.resolve()
        harmony_payload["paths"] = harmony_paths
        self.raw.write_table("harmony_config", [harmony_payload])
        self.observability.journal("harmony_journal", harmony_payload)
        mode = self.settings.execution_mode_enum()
        if mode in {ExecutionMode.LIVE, ExecutionMode.LIVE_TESTNET} and not bool(
            harmony_payload.get("live_gate_status", {}).get("doctrine_launch_safe", False)
        ):
            return {
                "status": "blocked",
                "reason": "harmony_doctrine_launch_gate_failed",
                "details": harmony_payload.get("live_gate_status", {}),
            }
        capability_matrix = self.execution.provider_capability_matrix()
        self.raw.write_table("provider_capabilities", [asdict(capability_matrix)])
        self.observability.journal("provider_capability_journal", capability_matrix)
        symbol = self.settings.universe[0]
        mode = self.settings.execution_mode_enum()
        provider = "paper_sim_provider" if mode == ExecutionMode.PAPER else self.settings.execution.provider_id

        truth_rows = ownership_map(mode, self.settings.execution.provider_id)
        ownership_errors = validate_ownership_map(truth_rows)
        for row in truth_rows:
            self.event_store.append(
                "truth",
                make_event(
                    TruthEvent,
                    "TRUTH_OWNER_DECLARED",
                    symbol,
                    provider,
                    self.event_store.next_seq("truth"),
                    row.to_dict(),
                ),
            )
        if ownership_errors:
            self.event_store.append(
                "risk",
                make_event(
                    RiskEvent,
                    "TRUTH_OWNERSHIP_INVALID",
                    symbol,
                    provider,
                    self.event_store.next_seq("risk"),
                    {"errors": ownership_errors},
                ),
            )
            return {"status": "blocked", "reason": "truth_ownership_contract_invalid", "errors": ownership_errors}

        gaps = ownership_gaps(truth_rows)
        if gaps:
            self.event_store.append(
                "risk",
                make_event(
                    RiskEvent,
                    "TRUTH_OWNERSHIP_GAP",
                    symbol,
                    provider,
                    self.event_store.next_seq("risk"),
                    {"domains": gaps},
                ),
            )
        self.raw.write_table("truth_ownership", [row.to_dict() for row in truth_rows])

        c = self.compliance.check_provider_authorization(provider)
        self.event_store.append("compliance", make_event(ComplianceEvent, "COMPLIANCE_CHECK", symbol, provider, self.event_store.next_seq("compliance"), {"allowed": c.allowed, "reason": c.reason}))
        if not c.allowed:
            return {"status": "blocked", "reason": c.reason}
        if self._missing_limits():
            return {"status": "blocked", "reason": "missing_required_limits"}

        if mode != ExecutionMode.PAPER:
            if self.settings.execution.provider_id == "kraken_derivatives":
                live = LiveKrakenService(
                    settings=self.settings,
                    run_id=self.settings.storage.run_dir.replace("/", "_"),
                    connector=KrakenDerivativesConnector(self.settings.execution.kraken),
                )
            elif self.settings.execution.provider_id == "kraken_spot":
                live = LiveKrakenSpotService(
                    settings=self.settings,
                    run_id=self.settings.storage.run_dir.replace("/", "_"),
                    connector=KrakenSpotConnector(self.settings.execution.kraken_spot),
                )
            elif self.settings.execution.provider_id == "binance_um_perps":
                live = LiveBinanceService(
                    settings=self.settings,
                    run_id=self.settings.storage.run_dir.replace("/", "_"),
                    connector=BinanceUMPerpsConnector(self.settings.execution.binance),
                )
            else:
                return {"status": "blocked", "reason": f"unsupported_provider:{self.settings.execution.provider_id}"}
            self.execution.attach_live_service(live)
            try:
                ok_preflight, reason_preflight = live.preflight()
            except Exception as exc:
                ok_preflight, reason_preflight = False, str(exc)
            readonly_without_credentials = bool(
                mode == ExecutionMode.LIVE_READONLY
                and not bool(getattr(getattr(live, "connector", None), "has_credentials", False))
            )
            if readonly_without_credentials:
                confidence = "readonly"
                confidence_details = {
                    "confidence": "readonly",
                    "reason": "readonly_without_credentials",
                    "signed_boot_recovery_skipped": True,
                }
                recovery_decision = RecoveryDecision(
                    symbol=symbol,
                    ts=datetime.now(timezone.utc),
                    outcome="readonly_without_credentials",
                    action="continue",
                    confidence="readonly",
                    reasons=["signed_boot_recovery_skipped"],
                )
                exchange_balance_total = None
            elif ok_preflight:
                boot_state = self.live_recovery.boot_state(live=live, symbol=symbol)
                confidence, confidence_details = boot_state.confidence, boot_state.details
                recovery_decision = boot_state.recovery_decision
                exchange_state = self.live_state.exchange_state(live, symbol)
                exchange_balance_total = exchange_state.balance_total
            else:
                confidence = "insufficient"
                confidence_details = {
                    "confidence": "insufficient",
                    "reason": "preflight_failed",
                    "preflight_reason": reason_preflight,
                }
                recovery_decision = RecoveryDecision(
                    symbol=symbol,
                    ts=datetime.now(timezone.utc),
                    outcome="preflight_failed",
                    action="halt",
                    confidence="insufficient",
                    reasons=[reason_preflight],
                )
                exchange_balance_total = None
            self.event_store.append(
                "account",
                make_event(
                    AccountEvent,
                    "ACCOUNT_SNAPSHOT",
                    symbol,
                    provider,
                    self.event_store.next_seq("account"),
                    self.portfolio.account_row(
                        venue=provider,
                        exchange_balance=exchange_balance_total,
                        metadata={"source": "boot", "baseline_recorded_at_ms": int(time.time() * 1000)},
                    ),
                ),
            )
            if recovery_decision.action == "flatten_only" and hasattr(live, "enter_flatten_only"):
                live.enter_flatten_only(f"recovery:{recovery_decision.outcome}")
            elif recovery_decision.action == "degrade" and hasattr(live, "safe_mode"):
                live.safe_mode = True
            elif recovery_decision.action in {"halt", "halt_and_flatten"} and hasattr(live, "request_kill"):
                live.request_kill(f"recovery:{recovery_decision.outcome}")
            truth_confidence_action, truth_confidence_reasons = self._boot_truth_gate(confidence_details)
            if truth_confidence_action == "flatten_only" and hasattr(live, "enter_flatten_only"):
                live.enter_flatten_only("truth_confidence:flatten_only")
            elif truth_confidence_action == "degrade" and hasattr(live, "safe_mode"):
                live.safe_mode = True
            ordering_allowed = bool(
                ok_preflight
                and confidence != "insufficient"
                and recovery_decision.action not in {"degrade", "flatten_only", "halt", "halt_and_flatten"}
                and truth_confidence_action == "continue"
                and mode != ExecutionMode.LIVE_READONLY
            )
            self._last_live_preflight_ok = bool(ok_preflight)
            self._last_live_ordering_allowed = bool(ordering_allowed)
            self._last_live_blocking_reasons = [] if ordering_allowed else self._live_blocking_reasons(
                preflight_ok=ok_preflight,
                preflight_reason=reason_preflight,
                confidence=confidence,
                recovery_action=recovery_decision.action,
                truth_confidence_reasons=truth_confidence_reasons,
            )
            readiness_artifacts = self._emit_live_readiness_artifacts(
                symbol=symbol,
                mode=mode,
                harmony_payload=harmony_payload,
                preflight_ok=ok_preflight,
                preflight_reason=reason_preflight,
                confidence=confidence,
                confidence_details=confidence_details,
                recovery_decision=recovery_decision,
                ordering_allowed=ordering_allowed,
            )
            self.event_store.append(
                "truth",
                make_event(
                    TruthEvent,
                    "LIVE_GATE_STATUS",
                    symbol,
                    provider,
                    self.event_store.next_seq("truth"),
                    {
                        "rollout_stage": self.settings.rollout_stage().value,
                        "preflight_ok": ok_preflight,
                        "preflight_reason": reason_preflight,
                        "restart_state_confidence": confidence,
                        "recovery": asdict(recovery_decision),
                        "ordering_allowed": ordering_allowed,
                        "live_gate_status": self.settings.live_gate_status(),
                        "details": confidence_details,
                    },
                ),
            )
            self.recon.persist_report(
                self.settings.storage.run_dir,
                {
                    "mode": mode.value,
                    "preflight_ok": ok_preflight,
                    "reason": reason_preflight,
                    "restart_state_confidence": confidence,
                    "recovery": asdict(recovery_decision),
                    "details": confidence_details,
                },
            )
            operator_summary_path = self._emit_live_boot_summary(
                symbol=symbol,
                mode=mode,
                harmony_payload=harmony_payload,
                preflight_ok=ok_preflight,
                preflight_reason=reason_preflight,
                confidence=confidence,
                confidence_details=confidence_details,
                recovery_decision=recovery_decision,
                ordering_allowed=ordering_allowed,
                artifact_paths=readiness_artifacts,
            )
            if not ok_preflight:
                self._record_live_reason(reason=reason_preflight, surface="preflight")
                self.ops.inc_metric("auth_errors_total")
                inc = self.incidents.evaluate(self.ops.metrics)
                if inc is not None:
                    self.notifier.notify(inc.action, inc.reason)
                return {"status": "blocked", "reason": reason_preflight, "operator_summary_path": operator_summary_path}
            if confidence == "insufficient":
                self._record_live_reason(reason="restart_state_confidence_insufficient", surface="truth_confidence")
                if hasattr(live, "enter_flatten_only"):
                    live.enter_flatten_only("restart_state_confidence_insufficient")
                return {
                    "status": "blocked",
                    "reason": "restart_state_confidence_insufficient",
                    "details": confidence_details,
                    "operator_summary_path": operator_summary_path,
                }
            if truth_confidence_action != "continue":
                for reason in truth_confidence_reasons:
                    self._record_live_reason(reason=reason, surface="truth_confidence")
            if recovery_decision.action in {"halt", "halt_and_flatten"}:
                self._record_live_reason(reason=f"recovery:{recovery_decision.outcome}", surface="recovery")
                return {
                    "status": "blocked",
                    "reason": f"recovery:{recovery_decision.outcome}",
                    "details": asdict(recovery_decision),
                    "operator_summary_path": operator_summary_path,
                }
            if confidence == "degraded":
                self.event_store.append(
                    "risk",
                    make_event(
                        RiskEvent,
                        "RESTART_STATE_DEGRADED",
                        symbol,
                        provider,
                        self.event_store.next_seq("risk"),
                        confidence_details,
                    ),
                )
            if mode == ExecutionMode.LIVE_READONLY:
                result = {"status": "ok", "mode": mode.value, "reason": "live_preflight_passed"}
                result.update(self._emit_readonly_analysis(live=live, symbol=symbol))
                return result
            self._live_runtime_diagnostics = self._fresh_live_runtime_diagnostics()
            result = self._live_loop(live, symbol=symbol, mode=mode)
            result.setdefault("operator_summary_path", operator_summary_path)
            return result

        return self.paper_runtime.run(symbol=symbol)
