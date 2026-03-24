from __future__ import annotations

from typing import Any, Callable

from autonomous_investment_robot.services.paper_runtime.accounting import PaperAccountingCoordinator
from autonomous_investment_robot.services.paper_runtime.decision import PaperDecisionCoordinator
from autonomous_investment_robot.services.paper_runtime.metrics import MetricsCoordinator
from autonomous_investment_robot.services.paper_runtime.replay import ReplayCoordinator


class PaperRuntimeCoordinator:
    def __init__(
        self,
        *,
        settings: Any,
        ingestion: Any,
        qa: Any,
        market_data: Any,
        raw: Any,
        event_store: Any,
        features: Any,
        models: Any,
        regime_service: Any,
        alpha: Any,
        policy: Any,
        risk: Any,
        execution: Any,
        oms: Any,
        portfolio: Any,
        recon: Any,
        ops: Any,
        learning: Any,
        forensics: Any,
        observability: Any,
        inventory: Any | None,
        profitability: Any | None,
        reporting: Any | None,
        harmony_resolver: Any | None,
        market_integrity_service: Any | None,
        venue_capability_registry: Any | None,
        market_watch_service: Any | None,
        replay_reporting: Any | None,
        operator_summary: Any | None,
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
        incidents: Any,
        notifier: Any,
        mlops: Any,
        legacy_risk_details: Callable[[dict[str, Any]], dict[str, Any]],
        legacy_fill_payload: Callable[[Any], dict[str, Any]],
    ) -> None:
        self.settings = settings
        self.ingestion = ingestion
        self.qa = qa
        self.market_data = market_data
        self.raw = raw
        self.event_store = event_store
        self.features = features
        self.models = models
        self.regime_service = regime_service
        self.alpha = alpha
        self.policy = policy
        self.risk = risk
        self.execution = execution
        self.oms = oms
        self.portfolio = portfolio
        self.recon = recon
        self.ops = ops
        self.learning = learning
        self.forensics = forensics
        self.observability = observability
        self.inventory = inventory
        self.profitability = profitability
        self.reporting = reporting
        self.harmony_resolver = harmony_resolver
        self.market_integrity_service = market_integrity_service
        self.venue_capability_registry = venue_capability_registry
        self.market_watch_service = market_watch_service
        self.replay_reporting = replay_reporting
        self.operator_summary = operator_summary
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
        self.incidents = incidents
        self.notifier = notifier
        self.mlops = mlops
        self.legacy_risk_details = legacy_risk_details
        self.legacy_fill_payload = legacy_fill_payload
        self.replay = ReplayCoordinator(raw=self.raw, portfolio=self.portfolio, legacy_fill_payload=self.legacy_fill_payload)
        self.metrics = MetricsCoordinator(ops=self.ops, risk=self.risk, settings=self.settings)
        self.decision = PaperDecisionCoordinator(
            settings=self.settings,
            ingestion=self.ingestion,
            qa=self.qa,
            market_data_service=self.market_data,
            features=self.features,
            event_store=self.event_store,
            alpha=self.alpha,
            models=self.models,
            regime_service=self.regime_service,
            policy=self.policy,
            risk=self.risk,
            execution=self.execution,
            oms=self.oms,
            portfolio=self.portfolio,
            inventory=self.inventory,
            profitability=self.profitability,
            learning=self.learning,
            forensics=self.forensics,
            observability=self.observability,
            ops=self.ops,
            reporting=self.reporting,
            harmony_resolver=self.harmony_resolver,
            market_integrity_service=self.market_integrity_service,
            venue_capability_registry=self.venue_capability_registry,
            market_watch_service=self.market_watch_service,
            quantum_state_service=self.quantum_state_service,
            edge_immunity_service=self.edge_immunity_service,
            event_intelligence_service=self.event_intelligence_service,
            synthetic_affect_service=self.synthetic_affect_service,
            capital_sovereignty_service=self.capital_sovereignty_service,
            position_morphing_service=self.position_morphing_service,
            adaptive_exit_allocator=self.adaptive_exit_allocator,
            execution_simulation_sandbox=self.execution_simulation_sandbox,
            human_escalation_layer=self.human_escalation_layer,
            mastermind_service=self.mastermind_service,
            metrics=self.metrics,
            legacy_risk_details=self.legacy_risk_details,
            legacy_fill_payload=self.legacy_fill_payload,
        )
        self.accounting = PaperAccountingCoordinator(
            recon=self.recon,
            risk=self.risk,
            execution=self.execution,
            event_store=self.event_store,
            observability=self.observability,
            ops=self.ops,
            policy=self.policy,
            incidents=self.incidents,
            notifier=self.notifier,
            mlops=self.mlops,
            replay=self.replay,
        )

    def _validate_inputs(self, symbol: str) -> tuple[bool, dict[str, Any]]:
        if len(self.settings.universe) > 1:
            if not self.settings.fixtures.symbol_files:
                return False, {"status": "blocked", "reason": "missing_symbol_fixtures"}
            for sym in self.settings.universe:
                if sym not in self.settings.fixtures.symbol_files:
                    return False, {"status": "blocked", "reason": f"missing_fixture_for_{sym}"}

        source = str(getattr(self.settings.replay, "source", "fixtures") or "fixtures")
        if source == "recordings":
            run_id = self.ingestion.resolve_recording_run_id(self.settings.storage.run_dir)
            if run_id is None:
                return False, {"status": "blocked", "reason": "recordings_missing"}
            recording_health = self.ingestion.recordings_health(self.settings.storage.run_dir, run_id)
            bars = self.ingestion.replay_recordings(self.settings.storage.run_dir, run_id, symbol, source=source)
            if not bars:
                return False, {"status": "blocked", "reason": "recordings_empty"}
            ok, issues = self.qa.validate_replay(bars)
            if not ok:
                return False, {"status": "blocked", "reason": ",".join(issues)}
            return True, {"bars": bars, "fvs": self.features.build_from_bars(bars), "source": source, "recording_health": recording_health, "run_id": run_id}

        bars = self.ingestion.replay_csv(symbol, self.settings.fixtures.ohlcv_csv)
        ok, issues = self.qa.validate_replay(bars)
        if not ok:
            return False, {"status": "blocked", "reason": ",".join(issues)}
        return True, {"bars": bars, "fvs": self.features.build_from_bars(bars), "source": source, "recording_health": None, "run_id": None}

    def run(self, *, symbol: str) -> dict[str, Any]:
        ok, payload = self._validate_inputs(symbol)
        if not ok:
            return payload

        bars = payload["bars"]
        fvs = payload["fvs"]
        state = self.decision.run(symbol=symbol, bars=bars, fvs=fvs, input_context=payload)
        result = self.accounting.finalize_run(
            symbol=symbol,
            equity=state.equity,
            peak=state.peak,
            exposure=state.exposure,
            funding_paid_pct=state.funding_paid_pct,
            fills_all=state.fills_all,
            plans=state.plans,
            trade_log=state.trade_log,
            fvs=fvs,
        )
        analysis = getattr(self.decision, "last_analysis_bundle", {}) or {}
        if analysis:
            if self.replay_reporting is not None and analysis.get("emit_replay_bundle", False):
                paths = self.replay_reporting.emit(
                    summary=analysis.get("replay_summary", {}),
                    capability_matrix=analysis.get("capability_matrix", []),
                    activated=analysis.get("activated_capabilities", {}),
                    still_gated=analysis.get("still_gated_capabilities", {}),
                    doctrine_blocked=analysis.get("doctrine_blocked_capabilities", {}),
                    artifact_index=analysis.get("artifact_index", {}),
                )
                result["replay_bundle"] = paths
            if self.operator_summary is not None and analysis.get("emit_operator_bundle", False):
                result["operator_summary_path"] = self.operator_summary.emit(summary=analysis.get("operator_summary", {}))
        return result
