from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from autonomous_investment_robot.config.settings import AllocatorSettings, ExecutionSettings, PolicySettings, RiskLimits, RobotSettings, StorageSettings, TCOSettings
from autonomous_investment_robot.core.contracts import RecoveryDecision
from autonomous_investment_robot.services.alpha_service.service import AlphaService
from autonomous_investment_robot.services.adaptive_exit_allocator.service import AdaptiveExitAllocator
from autonomous_investment_robot.services.capital_sovereignty_service.service import CapitalSovereigntyService
from autonomous_investment_robot.services.execution.service import Fill
from autonomous_investment_robot.services.execution.service import ExecutionService
from autonomous_investment_robot.services.execution_simulation_sandbox.service import ExecutionSimulationSandbox
from autonomous_investment_robot.services.event_intelligence_service.service import EventIntelligenceService
from autonomous_investment_robot.services.forensics_service.service import ForensicsService
from autonomous_investment_robot.services.feature_store.service import FeatureStoreService
from autonomous_investment_robot.services.health_service.service import HealthService
from autonomous_investment_robot.services.inventory_service.service import InventoryService
from autonomous_investment_robot.services.edge_immunity_service.service import EdgeImmunityService
from autonomous_investment_robot.services.live_runtime.coordination import (
    LiveControlCoordinator,
    LiveDecisionCoordinator,
    LiveMarketCoordinator,
    LiveRecoveryCoordinator,
    LiveReconciliationCoordinator,
)
from autonomous_investment_robot.services.mastermind.service import MastermindService
from autonomous_investment_robot.services.market_data_service.service import MarketDataService
from autonomous_investment_robot.services.market_integrity_service.service import MarketIntegrityService
from autonomous_investment_robot.services.models.service import ModelsService
from autonomous_investment_robot.services.human_escalation_layer.service import HumanEscalationLayer
from autonomous_investment_robot.services.observability_service.service import ObservabilityService
from autonomous_investment_robot.services.ops.service import OpsService
from autonomous_investment_robot.services.policy.service import PolicyService
from autonomous_investment_robot.services.portfolio_service.service import PortfolioService
from autonomous_investment_robot.services.position_morphing_service.service import PositionMorphingEngine
from autonomous_investment_robot.services.profitability_service.service import ProfitabilityService
from autonomous_investment_robot.services.quantum_state_service.service import QuantumStateService
from autonomous_investment_robot.services.regime_service.service import RegimeService
from autonomous_investment_robot.services.reporting_service.service import ReportingCoordinator
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService
from autonomous_investment_robot.services.shared_venue_limit_governor.service import SharedVenueLimitGovernor
from autonomous_investment_robot.services.synthetic_affect_service.service import SyntheticAffectEngine
from autonomous_investment_robot.services.venue_capability_registry.service import VenueCapabilityRegistry


def _limits() -> RiskLimits:
    return RiskLimits(
        max_daily_loss_pct=5.0,
        max_weekly_loss_pct=10.0,
        max_drawdown_pct=10.0,
        max_position_notional=1000.0,
        max_exposure_notional=2000.0,
        max_symbol_exposure_notional=1000.0,
        max_cluster_exposure_notional=1000.0,
        max_orders_per_min=10,
        leverage=0,
        max_spread_bps=20.0,
        min_depth_notional=100.0,
        stale_data_seconds=60.0,
        min_margin_buffer=2.0,
        max_funding_cost_per_day=1.0,
        max_oi_spike_pct=5.0,
        max_liquidation_spike=100000.0,
        divergence_threshold_bps=50.0,
        crowding_score_kill=50.0,
    )


def _settings(tmp_path) -> RobotSettings:
    return RobotSettings(
        storage=StorageSettings(run_dir=str(tmp_path)),
        provider_whitelist=["binance_um_perps"],
        risk=_limits(),
        policy=PolicySettings(confidence_threshold=0.0, base_risk_budget=100.0),
        allocator=AllocatorSettings(),
        execution=ExecutionSettings(mode="paper"),
        tco=TCOSettings(max_total_cost_bps=50.0, max_impact_bps=50.0),
    )


def _market_coordinator(tmp_path):
    settings = _settings(tmp_path)
    ops = OpsService(str(tmp_path))
    observability = ObservabilityService(str(tmp_path), ops)
    return (
        settings,
        LiveMarketCoordinator(
            features_service=FeatureStoreService(),
            market_data=MarketDataService(),
            models=ModelsService(regime_settings=settings.regime),
            regime_service=RegimeService(settings.regime),
            mastermind=MastermindService(),
            execution=ExecutionService(settings.execution),
            alpha=AlphaService(),
            portfolio=PortfolioService(),
            quantum_state_service=QuantumStateService(),
            edge_immunity_service=EdgeImmunityService(),
            observability=observability,
            settings=settings,
            ops=ops,
            market_integrity_service=MarketIntegrityService(),
            venue_capability_registry=VenueCapabilityRegistry(),
            shared_venue_limit_governor=SharedVenueLimitGovernor(),
            event_intelligence_service=EventIntelligenceService(),
        ),
    )


def test_live_market_coordinator_collects_context_and_journals(tmp_path):
    settings, coordinator = _market_coordinator(tmp_path)
    live = SimpleNamespace(
        connector=SimpleNamespace(book_ticker=lambda symbol: {"bidPrice": "130.0", "askPrice": "130.2", "bidQty": "5", "askQty": "5", "symbol": symbol}),
        market_integrity_evidence=lambda now_dt=None: {"ts": datetime.now(timezone.utc), "sequence_ok": False, "checksum_ok": True, "gap_count": 1, "checksum_mismatch_count": 0},
    )

    context = coordinator.collect(
        live=live,
        symbol="BTCUSDT",
        now_dt=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        prices=[100.0, 110.0, 120.0],
        base_budget=settings.policy.base_risk_budget,
        exposure_notional=0.0,
    )

    assert context.snapshot.mid > 0.0
    assert context.forecast.symbol == "BTCUSDT"
    assert context.alpha_signals
    assert context.quantum_state is not None
    assert context.edge_immunity_decision is not None
    assert context.provider_capability is not None
    assert context.market_integrity is not None
    assert context.venue_limit_decision is not None
    assert context.event_intelligence_report is not None
    assert context.advisory is not None
    assert (Path(settings.storage.run_dir) / "signal_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "mastermind_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "quantum_state_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "edge_immunity_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "market_integrity_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "market_integrity_evidence_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "provider_capability_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "venue_limit_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "event_intelligence_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "source_trust_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "freshness_novelty_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "asset_relevance_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "market_impact_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "priced_in_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "adversarial_narrative_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "data_provenance_journal.jsonl").exists()


def test_live_decision_coordinator_builds_intent_and_plan(tmp_path):
    settings, market_coordinator = _market_coordinator(tmp_path)
    ops = OpsService(str(tmp_path))
    observability = ObservabilityService(str(tmp_path), ops)
    market = market_coordinator.collect(
        live=SimpleNamespace(connector=SimpleNamespace(book_ticker=lambda symbol: {"bidPrice": "130.0", "askPrice": "130.2", "bidQty": "5", "askQty": "5", "symbol": symbol})),
        symbol="BTCUSDT",
        now_dt=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        prices=[100.0, 110.0, 120.0],
        base_budget=settings.policy.base_risk_budget,
        exposure_notional=0.0,
    )
    market = replace(
        market,
        forecast=replace(market.forecast, regime="RANGE", liquidity_regime="GOOD"),
        regime_assessment=replace(market.regime_assessment, label="trend", degradation_warning=None),
        quantum_state=SimpleNamespace(
            heuristic=True,
            scenario_tree=SimpleNamespace(dominant_state="bullish_continuation"),
            collapse_decision=SimpleNamespace(
                recommended_action="trade",
                side="sell",
                action_score=1.0,
                no_trade_probability=0.1,
                execution_fragility_score=0.2,
                uncertainty=0.2,
                size_multiplier=0.8,
                expected_move_bps=-15.0,
                reasons=["trade_supported"],
            ),
        ),
        edge_immunity_decision=SimpleNamespace(
            action="trade_smaller",
            reason="fragility_requires_smaller_size",
            report=SimpleNamespace(
                recommended_size_multiplier=0.75,
                edge_survival_ratio=0.8,
                fragility_index=0.3,
                self_impact_penalty_bps=1.0,
                reality_gap_score=0.2,
                wait_value_score=0.0,
                recommended_execution_style="unchanged",
                dominant_failure_modes=[],
            ),
        ),
        advisory=SimpleNamespace(
            provider="local",
            signal="bounded_support",
            confidence=0.8,
            reason="robust_enough_under_distortion",
            decision="CONTINUE",
            risk_level=20.0,
            veto=False,
            size_multiplier=1.0,
            execution_style_bias="unchanged",
            reasons=["mastermind_continue"],
            heuristic=True,
            raw={},
        ),
    )
    decision = LiveDecisionCoordinator(
        health=HealthService(),
        policy=PolicyService(settings.policy, settings.allocator, settings.tco),
        risk=RiskEngineService(settings.risk, safe_mode=False),
        execution=ExecutionService(settings.execution),
        profitability=ProfitabilityService(
            base_safety_buffer_bps=float(settings.policy.safety_buffer_bps),
            min_free_quote_reserve_pct=float(settings.policy.min_free_quote_reserve_pct),
        ),
        inventory=InventoryService(),
        reporting=ReportingCoordinator(observability=observability),
        capital_sovereignty=CapitalSovereigntyService(),
        position_morphing=PositionMorphingEngine(),
        adaptive_exit_allocator=AdaptiveExitAllocator(),
        synthetic_affect=SyntheticAffectEngine(),
        execution_simulation_sandbox=ExecutionSimulationSandbox(),
        human_escalation_layer=HumanEscalationLayer(),
        observability=observability,
        settings=settings,
    ).evaluate(
        symbol="BTCUSDT",
        market=market,
        exposure_notional=0.0,
        last_recon_ok=True,
        live=SimpleNamespace(rate_limits=SimpleNamespace(timestamps=[]), rejects=SimpleNamespace(timestamps=[])),
        drawdown_pct=0.0,
        daily_loss_pct=0.0,
        weekly_loss_pct=0.0,
        funding_paid_pct=0.0,
        legacy_policy_why=lambda why: why,
        legacy_risk_details=lambda details: details,
    )

    assert decision.health_snapshot.action == "continue"
    assert decision.meta_governor_decision is not None
    assert decision.policy_decision is not None
    assert decision.intent is not None
    assert decision.risk_decision is not None
    assert decision.risk_decision.allowed is True
    assert decision.adjusted_intent is not None
    assert decision.execution_plan is not None
    assert "decision_doctrine" in decision.adjusted_intent.why
    assert "global_execution_adjustments" in decision.execution_plan.reasons
    assert decision.synthetic_affect_state is not None
    assert decision.capital_sovereignty_decision is not None
    assert decision.position_morph_plan is not None
    assert decision.execution_simulation_report is not None
    assert "decision_doctrine" in decision.policy_decision.why
    assert (Path(settings.storage.run_dir) / "synthetic_affect_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "capital_sovereignty_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "position_morphing_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "execution_simulation_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "spre_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "shadow_rival_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "decision_doctrine_journal.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "decision_doctrine_summary.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "mastermind_summary.jsonl").exists()
    assert (Path(settings.storage.run_dir) / "capital_strategy_summary.jsonl").exists()


def test_live_decision_coordinator_blocks_trade_when_venue_constraints_zero_the_plan(tmp_path):
    settings, market_coordinator = _market_coordinator(tmp_path)
    settings.policy.base_risk_budget = 1.0
    ops = OpsService(str(tmp_path))
    observability = ObservabilityService(str(tmp_path), ops)
    market = market_coordinator.collect(
        live=SimpleNamespace(connector=SimpleNamespace(book_ticker=lambda symbol: {"bidPrice": "130.0", "askPrice": "130.2", "bidQty": "5", "askQty": "5", "symbol": symbol})),
        symbol="BTCUSDT",
        now_dt=datetime.now(timezone.utc),
        prices=[100.0, 110.0, 120.0],
        base_budget=settings.policy.base_risk_budget,
        exposure_notional=0.0,
    )
    market = replace(
        market,
        forecast=replace(market.forecast, regime="RANGE", liquidity_regime="GOOD"),
        regime_assessment=replace(market.regime_assessment, label="trend", degradation_warning=None),
        quantum_state=SimpleNamespace(
            heuristic=True,
            scenario_tree=SimpleNamespace(dominant_state="bullish_continuation"),
            collapse_decision=SimpleNamespace(
                recommended_action="trade",
                side="sell",
                action_score=1.0,
                no_trade_probability=0.1,
                execution_fragility_score=0.2,
                uncertainty=0.2,
                size_multiplier=0.8,
                expected_move_bps=-15.0,
                reasons=["trade_supported"],
            ),
        ),
        edge_immunity_decision=SimpleNamespace(
            action="trade_smaller",
            reason="fragility_requires_smaller_size",
            report=SimpleNamespace(
                recommended_size_multiplier=0.75,
                edge_survival_ratio=0.8,
                fragility_index=0.3,
                self_impact_penalty_bps=1.0,
                reality_gap_score=0.2,
                wait_value_score=0.0,
                recommended_execution_style="unchanged",
                dominant_failure_modes=[],
            ),
        ),
        advisory=SimpleNamespace(
            provider="local",
            signal="bounded_support",
            confidence=0.8,
            reason="robust_enough_under_distortion",
            decision="CONTINUE",
            risk_level=20.0,
            veto=False,
            size_multiplier=1.0,
            execution_style_bias="unchanged",
            reasons=["mastermind_continue"],
            heuristic=True,
            raw={},
        ),
    )
    decision = LiveDecisionCoordinator(
        health=HealthService(),
        policy=PolicyService(settings.policy, settings.allocator, settings.tco),
        risk=RiskEngineService(settings.risk, safe_mode=False),
        execution=ExecutionService(ExecutionSettings(mode="paper", provider_id="binance_um_perps")),
        observability=observability,
        settings=settings,
    ).evaluate(
        symbol="BTCUSDT",
        market=market,
        exposure_notional=0.0,
        last_recon_ok=True,
        live=SimpleNamespace(rate_limits=SimpleNamespace(timestamps=[]), rejects=SimpleNamespace(timestamps=[])),
        drawdown_pct=0.0,
        daily_loss_pct=0.0,
        weekly_loss_pct=0.0,
        funding_paid_pct=0.0,
        legacy_policy_why=lambda why: why,
        legacy_risk_details=lambda details: details,
    )

    assert decision.execution_plan is None
    assert decision.risk_decision is not None
    assert decision.risk_decision.reason == "venue_constraints_block_open"


def test_live_decision_coordinator_halts_before_policy_when_health_is_bad(tmp_path):
    settings, market_coordinator = _market_coordinator(tmp_path)
    base_market = market_coordinator.collect(
        live=SimpleNamespace(connector=SimpleNamespace(book_ticker=lambda symbol: {"bidPrice": "130.0", "askPrice": "130.2", "bidQty": "5", "askQty": "5", "symbol": symbol})),
        symbol="BTCUSDT",
        now_dt=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        prices=[100.0, 110.0, 120.0],
        base_budget=settings.policy.base_risk_budget,
        exposure_notional=0.0,
    )
    stressed_market = replace(
        base_market,
        execution_quality=replace(base_market.execution_quality, expected_fill_speed_ms=2000),
        regime_assessment=replace(base_market.regime_assessment, degradation_warning="exchange_health_bad"),
    )
    decision = LiveDecisionCoordinator(
        health=HealthService(),
        policy=PolicyService(settings.policy, settings.allocator, settings.tco),
        risk=RiskEngineService(settings.risk, safe_mode=False),
        execution=ExecutionService(settings.execution),
        observability=ObservabilityService(str(tmp_path), OpsService(str(tmp_path))),
        settings=settings,
    ).evaluate(
        symbol="BTCUSDT",
        market=stressed_market,
        exposure_notional=0.0,
        last_recon_ok=False,
        live=SimpleNamespace(rate_limits=SimpleNamespace(timestamps=[1, 2, 3, 4]), rejects=SimpleNamespace(timestamps=[1, 2, 3, 4])),
        drawdown_pct=0.0,
        daily_loss_pct=0.0,
        weekly_loss_pct=0.0,
        funding_paid_pct=0.0,
        legacy_policy_why=lambda why: why,
        legacy_risk_details=lambda details: details,
    )

    assert decision.health_snapshot.action == "halt_and_flatten"
    assert decision.policy_decision is None
    assert decision.execution_plan is None


def test_live_reconciliation_coordinator_enters_flatten_only_on_reconciliation_gap(tmp_path):
    ops = OpsService(str(tmp_path))
    observability = ObservabilityService(str(tmp_path), ops)
    forensics = ForensicsService(str(tmp_path), observability)
    coordinator = LiveReconciliationCoordinator(
        live_state=SimpleNamespace(
            reconcile_state=lambda live, symbol, internal_exposure, market_health=None: SimpleNamespace(
                ok=False,
                code="live_fill_truth_unavailable",
                action=SimpleNamespace(value="flatten_only"),
                details={"truth_confidence": {"fill_truth_confidence": {"level": "unavailable"}}},
                to_dict=lambda: {"code": "live_fill_truth_unavailable", "details": {"truth_confidence": {"fill_truth_confidence": {"level": "unavailable"}}}},
            )
        ),
        ops=ops,
        settings=_settings(tmp_path),
        observability=observability,
        forensics=forensics,
    )
    live = SimpleNamespace(enter_flatten_only=lambda reason: setattr(live, "reason", reason))

    result = coordinator.apply(live=live, symbol="BTCUSDT", exposure_notional=10.0)

    assert result.ok is False
    assert getattr(live, "reason") == "reconciliation:live_fill_truth_unavailable"
    assert (Path(tmp_path) / "reconciliation_journal.jsonl").exists()
    assert (Path(tmp_path) / "truth_confidence_journal.jsonl").exists()
    assert (Path(tmp_path) / "loss_autopsy.jsonl").exists()


def test_live_control_coordinator_flattens_only_on_meta_governor(tmp_path):
    ops = OpsService(str(tmp_path))
    observability = ObservabilityService(str(tmp_path), ops)
    coordinator = LiveControlCoordinator(
        ops=ops,
        incidents=SimpleNamespace(evaluate=lambda metrics: None),
        incident_responder=SimpleNamespace(execute=lambda *args, **kwargs: None),
        observability=observability,
    )
    live = SimpleNamespace(enter_flatten_only=lambda reason: setattr(live, "reason", reason))
    decision = SimpleNamespace(action="force_flatten_only", size_multiplier=0.0, forced_risk_mode="flatten-only", reasons=["truth_gap"])

    result = coordinator.apply_meta_governor(
        live=live,
        meta_governor=decision,
        mode="live",
        steps=1,
        exposure_notional=0.0,
    )

    assert result.continue_loop is True
    assert getattr(live, "reason") == "meta_governor"
    assert (Path(tmp_path) / "control_journal.jsonl").exists()


def test_live_recovery_coordinator_writes_recovery_and_truth_journals(tmp_path):
    ops = OpsService(str(tmp_path))
    observability = ObservabilityService(str(tmp_path), ops)
    forensics = ForensicsService(str(tmp_path), observability)
    coordinator = LiveRecoveryCoordinator(
        live_state=SimpleNamespace(
            rehydrate_state=lambda live, symbol: SimpleNamespace(
                confidence="degraded",
                details={"truth_confidence": {"fill_truth_confidence": {"level": "proxy"}}},
            ),
            recover_inflight_state=lambda live, symbol, restart_confidence, safe_mode_requested: RecoveryDecision(
                symbol=symbol,
                ts=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                outcome="warm_restart",
                action="flatten_only",
                confidence="degraded",
                recovered_orders=1,
                orphan_orders=0,
                reasons=["rehydrated"],
            ),
        ),
        settings=_settings(tmp_path),
        observability=observability,
        forensics=forensics,
    )

    state = coordinator.boot_state(live=SimpleNamespace(connector=SimpleNamespace(provider_id="binance_um_perps")), symbol="BTCUSDT")

    assert state.confidence == "degraded"
    assert (Path(tmp_path) / "recovery_journal.jsonl").exists()
    assert (Path(tmp_path) / "truth_confidence_journal.jsonl").exists()
    assert (Path(tmp_path) / "loss_autopsy.jsonl").exists()


def test_live_decision_coordinator_can_prioritize_capital_release_exit(tmp_path):
    settings, market_coordinator = _market_coordinator(tmp_path)
    ops = OpsService(str(tmp_path))
    observability = ObservabilityService(str(tmp_path), ops)
    inventory = InventoryService()
    inventory.update_from_fill(
        Fill("paper", "o1", "f1", "BTCUSDT", "buy", 100.0, 0.5, 0.5, 10, "filled"),
        ts=datetime.now(timezone.utc) - timedelta(hours=24),
    )
    market = market_coordinator.collect(
        live=SimpleNamespace(connector=SimpleNamespace(book_ticker=lambda symbol: {"bidPrice": "130.0", "askPrice": "130.2", "bidQty": "5", "askQty": "5", "symbol": symbol})),
        symbol="BTCUSDT",
        now_dt=datetime.now(timezone.utc),
        prices=[100.0, 110.0, 120.0],
        base_budget=settings.policy.base_risk_budget,
        exposure_notional=100.0,
    )
    decision = LiveDecisionCoordinator(
        health=HealthService(),
        policy=PolicyService(settings.policy, settings.allocator, settings.tco),
        risk=RiskEngineService(settings.risk, safe_mode=False),
        execution=ExecutionService(settings.execution),
        observability=observability,
        settings=settings,
        profitability=ProfitabilityService(base_safety_buffer_bps=settings.policy.safety_buffer_bps, min_free_quote_reserve_pct=settings.policy.min_free_quote_reserve_pct),
        inventory=inventory,
        reporting=ReportingCoordinator(observability=observability),
    ).evaluate(
        symbol="BTCUSDT",
        market=market,
        exposure_notional=100.0,
        last_recon_ok=True,
        live=SimpleNamespace(rate_limits=SimpleNamespace(timestamps=[]), rejects=SimpleNamespace(timestamps=[])),
        drawdown_pct=0.0,
        daily_loss_pct=0.0,
        weekly_loss_pct=0.0,
        funding_paid_pct=0.0,
        legacy_policy_why=lambda why: why,
        legacy_risk_details=lambda details: details,
        reconciliation_report=SimpleNamespace(
            details={
                "exchange_balance": 100.0,
                "local_cash_delta": 0.0,
                "local_unrealized_pnl": -10.0,
                "truth_confidence": {
                    "fill_truth_confidence": {"level": "authoritative"},
                    "fee_truth_confidence": {"level": "authoritative"},
                    "realized_pnl_confidence": {"level": "authoritative"},
                    "balance_truth_confidence": {"level": "authoritative"},
                    "exposure_truth_confidence": {"level": "authoritative"},
                    "market_data_truth_confidence": {"level": "authoritative"},
                    "unrealized_pnl_confidence": {"level": "authoritative"},
                },
            }
        ),
    )
    assert decision.adjusted_intent is not None
    assert decision.execution_plan is not None
    assert decision.adjusted_intent.side == "sell"
    assert decision.execution_plan.reduce_only is True
