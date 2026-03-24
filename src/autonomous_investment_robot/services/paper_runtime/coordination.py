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
            qa=self.qa,
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

        bars = self.ingestion.replay_csv(symbol, self.settings.fixtures.ohlcv_csv)
        ok, issues = self.qa.validate_replay(bars)
        if not ok:
            return False, {"status": "blocked", "reason": ",".join(issues)}
        return True, {"bars": bars, "fvs": self.features.build_from_bars(bars)}

    def run(self, *, symbol: str) -> dict[str, Any]:
        ok, payload = self._validate_inputs(symbol)
        if not ok:
            return payload

        bars = payload["bars"]
        fvs = payload["fvs"]
        state = self.decision.run(symbol=symbol, bars=bars, fvs=fvs)
        return self.accounting.finalize_run(
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
