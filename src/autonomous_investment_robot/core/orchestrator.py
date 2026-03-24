from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import time

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings, UNSPECIFIED
from autonomous_investment_robot.core.contracts import LearningRecord
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
from autonomous_investment_robot.services.observability_facade.service import ObservabilityFacade
from autonomous_investment_robot.services.observability_service.service import ObservabilityService
from autonomous_investment_robot.services.operator_summary.service import OperatorSummaryCoordinator
from autonomous_investment_robot.services.oms.service import ManagedOrder, OMSService
from autonomous_investment_robot.services.ops.service import OpsService
from autonomous_investment_robot.services.paper_runtime.coordination import PaperRuntimeCoordinator
from autonomous_investment_robot.services.policy.service import OrderIntent, PolicyService
from autonomous_investment_robot.services.portfolio_service.service import PortfolioService
from autonomous_investment_robot.services.position_morphing_service.service import PositionMorphingEngine
from autonomous_investment_robot.services.inventory_service.service import InventoryService
from autonomous_investment_robot.services.profitability_service.service import ProfitabilityService
from autonomous_investment_robot.services.quantum_state_service.service import QuantumStateService
from autonomous_investment_robot.services.raw_store.service import RawStoreService
from autonomous_investment_robot.services.reconciliation.service import ReconciliationService
from autonomous_investment_robot.services.regime_service.service import RegimeService
from autonomous_investment_robot.services.replay_reporting.service import ReplayReportingCoordinator
from autonomous_investment_robot.services.reporting_service.service import ReportingCoordinator
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

    def _serialize_payload(self, payload: object) -> object:
        if payload is None:
            return None
        try:
            return json.loads(json.dumps(payload, sort_keys=True, default=lambda value: asdict(value) if hasattr(value, "__dataclass_fields__") else getattr(value, "__dict__", str(value))))
        except Exception:
            return str(payload)

    def _jsonl_count(self, name: str) -> int:
        path = Path(self.settings.storage.run_dir) / f"{name}.jsonl"
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

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
        artifact_index = {
            "run_dir": self.settings.storage.run_dir,
            "step": step,
            "files": sorted(path.name for path in Path(self.settings.storage.run_dir).glob("*.json*")),
        }
        self._write_json_artifact("live_capability_matrix.json", capability_matrix)
        self._write_json_artifact("live_activated_capabilities.json", activated)
        self._write_json_artifact("live_still_gated_capabilities.json", still_gated)
        self._write_json_artifact("live_doctrine_blocked_capabilities.json", doctrine_blocked)
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
        }
        return self.operator_summary.emit(summary=summary)

    def _emit_readonly_analysis(self, *, live: object, symbol: str) -> dict[str, object]:
        if not self.settings.kraken_spot_full_analysis_enabled():
            return {}
        now_dt = datetime.now(timezone.utc)
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
            "files": sorted(path.name for path in Path(self.settings.storage.run_dir).glob("*.json*")),
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
        }
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
                else:
                    self.ops.audit_event("book_error", {"symbol": symbol, "error": message})
                    self.ops.inc_metric("book_errors_total")
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
                meta_control.stop_result.setdefault("operator_summary_path", latest_operator_summary_path)
                return meta_control.stop_result
            if meta_control.continue_loop:
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
                self.ops.inc_metric("orders_rejected_total")
                self.ops.audit_event(
                    "heartbeat",
                    {
                        "symbol": symbol,
                        "mid": mid,
                        "spread_bps": spread_bps,
                        "equity": equity,
                        "reason": policy_decision.no_trade.reason if policy_decision.no_trade is not None else "no_trade",
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
            result = self.execution.execute_live(adjusted)
            self.ops.audit_event(
                "live_exec",
                {"status": result.status, "reason": result.reason, "symbol": adjusted.symbol, "side": adjusted.side, "notional": adjusted.target_notional},
            )
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
                if not ledger_result.fill_truth_ok:
                    self.ops.inc_metric("live_fill_truth_gap_total")
            elif result.status in {"rejected", "blocked", "killed"}:
                self.ops.inc_metric("orders_rejected_total")

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
            ok_preflight, reason_preflight = live.preflight()
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
            else:
                boot_state = self.live_recovery.boot_state(live=live, symbol=symbol)
                confidence, confidence_details = boot_state.confidence, boot_state.details
                recovery_decision = boot_state.recovery_decision
                exchange_state = self.live_state.exchange_state(live, symbol)
                exchange_balance_total = exchange_state.balance_total
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
            ordering_allowed = bool(
                ok_preflight
                and confidence != "insufficient"
                and recovery_decision.action not in {"degrade", "flatten_only", "halt", "halt_and_flatten"}
                and mode != ExecutionMode.LIVE_READONLY
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
            )
            if not ok_preflight:
                self.ops.inc_metric("auth_errors_total")
                inc = self.incidents.evaluate(self.ops.metrics)
                if inc is not None:
                    self.notifier.notify(inc.action, inc.reason)
                return {"status": "blocked", "reason": reason_preflight, "operator_summary_path": operator_summary_path}
            if confidence == "insufficient":
                if hasattr(live, "enter_flatten_only"):
                    live.enter_flatten_only("restart_state_confidence_insufficient")
                return {
                    "status": "blocked",
                    "reason": "restart_state_confidence_insufficient",
                    "details": confidence_details,
                    "operator_summary_path": operator_summary_path,
                }
            if recovery_decision.action in {"halt", "halt_and_flatten"}:
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
            result = self._live_loop(live, symbol=symbol, mode=mode)
            result.setdefault("operator_summary_path", operator_summary_path)
            return result

        return self.paper_runtime.run(symbol=symbol)
