import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from autonomous_investment_robot.config.settings import (
    DoctrineSettings,
    ExecutionSettings,
    HarmonySettings,
    LiveUnlockSettings,
    MarketWatchSettings,
    RiskLimits,
    RobotSettings,
    SafetySettings,
    StorageSettings,
    TCOSettings,
)
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator
from autonomous_investment_robot.main import run_with_config
from autonomous_investment_robot.services.paper_runtime import MetricsCoordinator, PaperDecisionCoordinator


def test_paper_run_emits_observability_journals():
    result = run_with_config("config.perps_intraday.paper.yaml")
    assert result["status"] == "ok"
    run_dir = Path("runs/perps_intraday")
    assert (run_dir / "config_manifest.jsonl").exists()
    assert (run_dir / "signal_journal.jsonl").exists()
    assert (run_dir / "policy_journal.jsonl").exists()
    assert (run_dir / "execution_journal.jsonl").exists()
    assert (run_dir / "quantum_state_journal.jsonl").exists()
    assert (run_dir / "edge_immunity_journal.jsonl").exists()
    assert (run_dir / "event_intelligence_journal.jsonl").exists()
    assert (run_dir / "mastermind_journal.jsonl").exists()
    assert (run_dir / "decision_doctrine_journal.jsonl").exists()
    assert (run_dir / "decision_doctrine_summary.jsonl").exists()
    assert (run_dir / "mastermind_summary.jsonl").exists()
    assert (run_dir / "source_trust_journal.jsonl").exists()
    assert (run_dir / "freshness_novelty_journal.jsonl").exists()
    assert (run_dir / "asset_relevance_journal.jsonl").exists()
    assert (run_dir / "market_impact_journal.jsonl").exists()
    assert (run_dir / "priced_in_journal.jsonl").exists()
    assert (run_dir / "adversarial_narrative_journal.jsonl").exists()
    assert (run_dir / "data_provenance_journal.jsonl").exists()
    assert (run_dir / "learning_records.jsonl").exists()
    assert (run_dir / "pnl_attribution.jsonl").exists()
    assert (run_dir / "post_trade_summary.jsonl").exists()


def test_orchestrator_wires_live_runtime_observability():
    settings = RobotSettings.from_file("config.perps_intraday.paper.yaml")
    orchestrator = RobotOrchestrator(settings)

    assert orchestrator.live_ledger.observability is orchestrator.observability
    assert orchestrator.live_recovery.observability is orchestrator.observability
    assert orchestrator.live_reconciliation.observability is orchestrator.observability
    assert orchestrator.live_control.observability is orchestrator.observability
    assert orchestrator.live_market.market_integrity_service is orchestrator.market_integrity
    assert orchestrator.live_market.venue_capability_registry is orchestrator.venue_capabilities
    assert orchestrator.live_market.shared_venue_limit_governor is orchestrator.shared_venue_limits


def test_orchestrator_wires_paper_runtime_coordinator():
    settings = RobotSettings.from_file("config.perps_intraday.paper.yaml")
    orchestrator = RobotOrchestrator(settings)

    assert orchestrator.paper_runtime.event_store is orchestrator.event_store
    assert orchestrator.paper_runtime.observability is orchestrator.observability
    assert orchestrator.paper_runtime.oms is orchestrator.oms
    assert isinstance(orchestrator.paper_runtime.decision, PaperDecisionCoordinator)
    assert isinstance(orchestrator.paper_runtime.metrics, MetricsCoordinator)


def test_orchestrator_emits_provider_capability_journal():
    result = run_with_config("config.perps_intraday.paper.yaml")
    assert result["status"] == "ok"
    run_dir = Path("runs/perps_intraday")
    assert (run_dir / "provider_capability_journal.jsonl").exists()


def test_paper_runtime_coordinator_preserves_golden_checksums():
    settings = RobotSettings.from_file("config.perps_intraday.paper.yaml")
    orchestrator = RobotOrchestrator(settings)

    result = orchestrator.paper_runtime.run(symbol=settings.universe[0])
    fixture = json.loads(Path("tests/fixtures/replay/golden_checksums_perps_intraday.json").read_text(encoding="utf-8"))

    assert result["status"] == "ok"
    assert result["orders_checksum"] == fixture["orders_checksum"]
    assert result["fills_checksum"] == fixture["fills_checksum"]
    assert result["equity_checksum"] == fixture["equity_checksum"]


def test_live_readonly_boot_skips_signed_recovery_without_credentials(monkeypatch, tmp_path):
    from autonomous_investment_robot.core import orchestrator as orchestrator_module

    class FakeLiveKraken:
        def __init__(self, settings, run_id, connector):  # noqa: ARG002
            self.connector = SimpleNamespace(provider_id="kraken_derivatives", has_credentials=False)

        def preflight(self):
            return True, "readonly"

    monkeypatch.setattr(orchestrator_module, "LiveKrakenService", FakeLiveKraken)
    monkeypatch.setattr(orchestrator_module, "KrakenDerivativesConnector", lambda settings: object())
    settings = RobotSettings(
        storage=StorageSettings(run_dir=str(tmp_path)),
        provider_whitelist=["kraken_derivatives"],
        universe=["PI_XBTUSD"],
        execution=ExecutionSettings(mode="live_readonly", provider_id="kraken_derivatives"),
        risk=RiskLimits(
            max_daily_loss_pct=1.0,
            max_weekly_loss_pct=2.0,
            max_drawdown_pct=2.0,
            max_position_notional=10.0,
            max_exposure_notional=10.0,
            max_symbol_exposure_notional=10.0,
            max_cluster_exposure_notional=10.0,
            max_orders_per_min=5,
            leverage=0,
            max_spread_bps=10.0,
            min_depth_notional=10.0,
            stale_data_seconds=10.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=1.0,
            max_liquidation_spike=1.0,
            divergence_threshold_bps=10.0,
            crowding_score_kill=10.0,
        ),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )

    result = RobotOrchestrator(settings).boot()

    assert result["status"] == "ok"
    assert result["mode"] == "live_readonly"
    assert result["reason"] == "live_preflight_passed"
    truth_log = (Path(settings.storage.run_dir) / "events_truth.jsonl").read_text(encoding="utf-8")
    assert "readonly_without_credentials" in truth_log


def test_readonly_analysis_emits_performance_artifacts(tmp_path):
    @dataclass
    class StubMarketIntegrity:
        action: str = "continue"
        score: float = 0.99
        reasons: list[str] = None  # type: ignore[assignment]

        def __post_init__(self):
            if self.reasons is None:
                self.reasons = []

    @dataclass
    class StubProviderCapability:
        user_stream_confidence: str = "rest_history_only"
        lifecycle_completeness: str = "partial_without_snapshot"
        fee_truth_confidence: str = "partial_exchange_history"
        metadata: dict = None  # type: ignore[assignment]

        def __post_init__(self):
            if self.metadata is None:
                self.metadata = {}

    @dataclass
    class StubMarketWatch:
        action: str = "continue"
        score: float = 0.8
        spread_score: float = 1.0
        liquidity_score: float = 1.0
        reasons: list[str] = None  # type: ignore[assignment]
        metadata: dict = None  # type: ignore[assignment]

        def __post_init__(self):
            if self.reasons is None:
                self.reasons = []
            if self.metadata is None:
                self.metadata = {}

    settings = RobotSettings.from_file("config.kraken_spot.readonly_analysis.yaml")
    settings.storage = StorageSettings(run_dir=str(tmp_path))
    orchestrator = RobotOrchestrator(settings)
    orchestrator._last_live_preflight_ok = True
    orchestrator.live_market.collect = lambda **kwargs: SimpleNamespace(
        market_integrity=StubMarketIntegrity(),
        provider_capability=StubProviderCapability(),
        market_watch=StubMarketWatch(),
        event_intelligence_report=SimpleNamespace(partial=True),
        execution_quality=SimpleNamespace(fill_probability=0.0),
        forecast=SimpleNamespace(symbol="BTC/USD", regime="RANGE", liquidity_regime="GOOD"),
    )
    orchestrator.live_decision.evaluate = lambda **kwargs: SimpleNamespace(
        policy_decision=SimpleNamespace(why={"decision_doctrine": {"action": "continue"}}, no_trade=None),
        capital_sovereignty_decision=None,
        position_morph_plan=None,
        adaptive_exit_allocation=None,
        human_escalation_decision=None,
    )
    orchestrator._decision_collapse_trace = lambda **kwargs: SimpleNamespace(
        trade_path_state="blocked_by_decision",
        reason_chain=["readonly:analysis"],
    )
    orchestrator._serialize_payload = lambda payload: {"ranked_blockers": [{"stage": "policy", "reason": "runtime_ordering_blocked"}]}
    orchestrator._decision_explainability = lambda **kwargs: {"action_state": "no_trade", "trade_path_state": "blocked_by_decision"}
    orchestrator._performance_architecture_artifacts = lambda **kwargs: {
        "capital_envelope_summary": {"deployable_capital": 0.0},
        "performance_target_translation": {"target_monthly_return_pct": 30.0},
        "performance_gap_report": {"gaps": {"capital_utilization_gap_pct": 50.0}},
        "pair_ranking_report": {"active_symbols": ["BTC/USD"]},
        "regime_snapshot": {"label": "mean_reversion"},
        "playbook_candidate_log": {"candidates": []},
        "opportunity_auction_report": {"ranked_candidates": []},
        "allocator_decisions": {"recommended_notional": 0.0},
        "expectancy_engine_report": {"net_expectancy_bps": 0.0},
        "experiment_registry": {"experiments": []},
        "dead_capital_pressure_report": {"dead_capital_pressure": 0.0},
        "cost_model_diagnostics": {"maker_probability": 0.5},
        "private_stream_health": {"status": "degraded"},
        "live_degradation_detector_report": {"status": "degraded"},
        "self_throttling_state_report": {"active": True},
        "selected_candidate": {},
    }

    result = orchestrator._emit_readonly_analysis(live=object(), symbol="BTC/USD")

    assert Path(result["operator_summary_path"]).exists()
    assert (tmp_path / "capital_envelope_summary.json").exists()
    assert (tmp_path / "pair_ranking_report.json").exists()
    assert (tmp_path / "expectancy_engine_report.json").exists()
    assert (tmp_path / "private_stream_health.json").exists()
    operator_summary = json.loads(Path(result["operator_summary_path"]).read_text(encoding="utf-8"))
    assert operator_summary["performance_architecture"]["capital_envelope"]["deployable_capital"] == 0.0
    assert operator_summary["performance_architecture"]["market_universe"]["active_symbols"] == ["BTC/USD"]
    assert operator_summary["performance_architecture"]["execution_alpha"]["private_stream_health"]["status"] == "degraded"


def test_live_runtime_summary_emits_decision_collapse_trace_and_trade_path_health(tmp_path):
    settings = RobotSettings(
        storage=StorageSettings(run_dir=str(tmp_path)),
        provider_whitelist=["kraken_spot"],
        universe=["BTCUSDT"],
        canary_mode=True,
        execution=ExecutionSettings(mode="paper", provider_id="kraken_spot"),
        risk=RiskLimits(
            max_daily_loss_pct=1.0,
            max_weekly_loss_pct=2.0,
            max_drawdown_pct=2.0,
            max_position_notional=10.0,
            max_exposure_notional=10.0,
            max_symbol_exposure_notional=10.0,
            max_cluster_exposure_notional=10.0,
            max_orders_per_min=5,
            leverage=0,
            max_spread_bps=10.0,
            min_depth_notional=10.0,
            stale_data_seconds=10.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=1.0,
            max_liquidation_spike=1.0,
            divergence_threshold_bps=10.0,
            crowding_score_kill=10.0,
        ),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    orchestrator = RobotOrchestrator(settings)
    orchestrator._last_live_preflight_ok = True
    orchestrator._last_live_ordering_allowed = True
    orchestrator._last_live_blocking_reasons = []
    market = SimpleNamespace(
        forecast=SimpleNamespace(symbol="BTCUSDT", regime="RANGE", liquidity_regime="GOOD"),
        market_integrity=SimpleNamespace(action="continue", score=0.94, reasons=[]),
        market_watch=SimpleNamespace(
            action="degrade",
            score=0.82,
            spread_score=1.0,
            liquidity_score=1.0,
            reasons=["regime_watch:dead_market"],
            metadata={
                "spread_bps": 0.03,
                "depth_notional": 240000.0,
                "regime_score_table": {
                    "spread_health": 1.0,
                    "liquidity_health": 1.0,
                    "book_liveliness_health": 0.88,
                    "dead_market_candidate": 1.0,
                    "healthy_microstructure_override": 1.0,
                },
                "dead_market_reasoning": {
                    "candidate": True,
                    "healthy_microstructure": True,
                    "book_liveliness_score": 0.88,
                    "seconds_since_distinct_book_change": 1.4,
                    "book_repeat_count": 1,
                    "public_market_data_connected": True,
                    "dead_market_reason": "healthy_microstructure_overrides_low_energy",
                },
            },
        ),
        edge_immunity_decision=SimpleNamespace(
            action="trade_now",
            reason="edge_survives_costs",
            report=SimpleNamespace(
                base_expected_edge_bps=13.0,
                stressed_expected_edge_bps=9.5,
                edge_survival_ratio=0.79,
                fragility_index=0.18,
                wait_value_score=0.12,
                dominant_failure_modes=[],
                metadata={"wait_dominance": {"trade_now_score": 0.81, "wait_score_bps": 0.12, "wait_dominant": False}},
            ),
        ),
        quantum_state=SimpleNamespace(
            collapse_decision=SimpleNamespace(
                recommended_action="wait",
                action_score=2.4,
                no_trade_probability=0.33,
                execution_fragility_score=0.22,
                uncertainty=0.54,
                branch_disagreement_score=0.58,
                scenario_drift_score=0.49,
                reasons=["branch_disagreement_high"],
                metadata={"thresholds": {"branch_disagreement_high": False, "scenario_drift_high": False}},
            ),
            collapse_context=SimpleNamespace(
                top_states={"primary": "bullish_continuation"},
                uncertainty_decomposition={
                    "epistemic_uncertainty": 0.42,
                    "policy_disagreement": 0.58,
                    "execution_fragility": 0.22,
                    "observability_uncertainty": 0.15,
                    "negative_evidence_mass": 0.29,
                },
            ),
            scenario_tree=SimpleNamespace(
                branches=[SimpleNamespace(label="bullish_continuation", probability=0.55, expected_move_bps=12.0)],
                probability_field=SimpleNamespace(confidence_decomposition={"signal": 0.72, "regime": 0.66}),
            ),
        ),
        provider_capability=SimpleNamespace(
            user_stream_confidence="rest_history_only",
            lifecycle_completeness="partial_without_snapshot",
            fee_truth_confidence="partial_exchange_history",
            metadata={
                "capability_evidence": {
                    "partial": True,
                    "lifecycle_snapshot_count": 0,
                    "freshness_seconds": 2.0,
                    "single_process_lifecycle_equivalent": False,
                    "reasons": ["lifecycle_snapshot_absent", "user_stream_not_connected"],
                    "classifications": {
                        "execution_blocker": [],
                        "promotion_blocker": ["lifecycle_snapshot_absent", "user_stream_not_connected"],
                        "confidence_haircut": [],
                        "informational_only": [],
                    },
                }
            },
        ),
        event_intelligence_report=SimpleNamespace(partial=True),
        execution_quality=SimpleNamespace(),
    )
    decision_ctx = SimpleNamespace(
        health_snapshot=SimpleNamespace(action="continue"),
        meta_governor_decision=SimpleNamespace(action="continue", reasons=[], size_multiplier=1.0),
        policy_decision=SimpleNamespace(
            symbol="BTCUSDT",
            trade_allowed=False,
            side=None,
            no_trade=SimpleNamespace(reason="doctrine_wait", reasons=["doctrine_wait"]),
            why={
                "spre": {
                    "dominant_action": "wait",
                    "internal_action": "wait",
                    "chosen_survival_ratio": 0.76,
                    "action_gap_bps": 1.6,
                    "ambiguity_penalty": 0.42,
                    "no_trade_quality": 1.4,
                    "reasons": ["spre_wait"],
                    "action_scores": {"trade": 3.1, "wait": 4.2, "no_trade": 1.4},
                },
                "mastermind": {
                    "decision": "WAIT",
                    "signal": "wait_dominates",
                    "reason": "uncertainty_requires_wait",
                    "confidence": 0.47,
                    "risk_level": 58.0,
                    "size_multiplier": 0.0,
                    "veto": False,
                    "reasons": ["mastermind_wait"],
                    "raw": {
                        "risk_components": {"market_toxicity": 0.18, "provider_penalty": 0.12, "decision_uncertainty": 0.38},
                        "observability_components": {"provider_penalty": 0.18},
                        "uncertainty_components": {"quantum_uncertainty": 0.38, "forecast_confidence_gap": 0.24},
                        "veto_chain": ["uncertainty_wait"],
                    },
                },
                "decision_doctrine": {
                    "recommended_action": "wait",
                    "size_multiplier": 0.0,
                    "uncertainty_pressure": 0.54,
                    "partial_truth_penalty": 0.22,
                    "truth_strength": 0.84,
                    "survival_score": 0.62,
                    "robustness_score": 0.61,
                    "reasons": ["doctrine_mastermind_caution_wait"],
                    "metadata": {"uncertainty_components": {"quantum_uncertainty": 0.38, "market_ambiguity": 0.04}},
                },
            },
        ),
        risk_decision=SimpleNamespace(allowed=True, reason="", details={}),
        adjusted_intent=None,
        execution_plan=None,
        synthetic_affect_state=None,
        capital_sovereignty_decision=None,
        position_morph_plan=None,
        adaptive_exit_allocation=None,
        execution_simulation_report=None,
        human_escalation_decision=None,
    )

    summary_path = orchestrator._emit_live_runtime_summary(
        symbol="BTCUSDT",
        mode=settings.execution_mode_enum(),
        market=market,
        decision_ctx=decision_ctx,
        step=3,
    )

    trace_latest = json.loads((Path(settings.storage.run_dir) / "decision_collapse_trace_latest.json").read_text(encoding="utf-8"))
    explainability = json.loads((Path(settings.storage.run_dir) / "decision_explainability.json").read_text(encoding="utf-8"))
    health_summary = json.loads((Path(settings.storage.run_dir) / "health_summary.json").read_text(encoding="utf-8"))
    operator_summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))

    assert trace_latest["trade_path_state"] == "blocked_by_decision"
    assert trace_latest["ranked_blockers"]
    assert (Path(settings.storage.run_dir) / "decision_collapse_trace.jsonl").exists()
    assert explainability["collapse_stage"] == explainability["ranked_blockers"][0]["stage"]
    assert health_summary["infra_ok"] is True
    assert health_summary["trade_path_state"] == "blocked_by_decision"
    assert health_summary["top_blockers"]
    assert operator_summary["current_blocker_chain"]
    assert operator_summary["decision_collapse_trace"]["frame_id"] == trace_latest["frame_id"]


def test_live_runtime_summary_uses_current_truth_gate_over_boot_blockers(tmp_path):
    settings = RobotSettings(
        storage=StorageSettings(run_dir=str(tmp_path)),
        provider_whitelist=["kraken_spot"],
        universe=["ETH/EUR"],
        canary_mode=True,
        execution=ExecutionSettings(mode="paper", provider_id="kraken_spot"),
        risk=RiskLimits(
            max_daily_loss_pct=1.0,
            max_weekly_loss_pct=2.0,
            max_drawdown_pct=2.0,
            max_position_notional=10.0,
            max_exposure_notional=10.0,
            max_symbol_exposure_notional=10.0,
            max_cluster_exposure_notional=10.0,
            max_orders_per_min=5,
            leverage=0,
            max_spread_bps=10.0,
            min_depth_notional=10.0,
            stale_data_seconds=10.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=1.0,
            max_liquidation_spike=1.0,
            divergence_threshold_bps=10.0,
            crowding_score_kill=10.0,
        ),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    orchestrator = RobotOrchestrator(settings)
    orchestrator._last_live_preflight_ok = True
    orchestrator._last_live_ordering_allowed = False
    orchestrator._last_live_blocking_reasons = [
        "truth_confidence:degrade:fill_proxy",
        "truth_confidence:degrade:fee_proxy",
        "truth_confidence:degrade:realized_pnl_proxy",
    ]
    market = SimpleNamespace(
        forecast=SimpleNamespace(symbol="ETH/EUR", regime="RANGE", liquidity_regime="GOOD"),
        market_integrity=SimpleNamespace(action="continue", score=1.0, reasons=[]),
        market_watch=SimpleNamespace(action="continue", score=1.0, spread_score=1.0, liquidity_score=1.0, reasons=[], metadata={}),
        edge_immunity_decision=SimpleNamespace(
            action="trade_now",
            reason="edge_survives_counterfactuals",
            report=SimpleNamespace(
                base_expected_edge_bps=12.0,
                stressed_expected_edge_bps=10.0,
                edge_survival_ratio=0.83,
                fragility_index=0.19,
                wait_value_score=0.1,
                dominant_failure_modes=[],
                metadata={"wait_dominance": {"trade_now_score": 0.8, "wait_score_bps": 0.12, "wait_dominant": False}},
            ),
        ),
        quantum_state=SimpleNamespace(
            collapse_decision=SimpleNamespace(
                recommended_action="probe",
                action_score=1.2,
                no_trade_probability=0.2,
                execution_fragility_score=0.18,
                uncertainty=0.31,
                branch_disagreement_score=0.25,
                scenario_drift_score=0.21,
                reasons=[],
                metadata={"thresholds": {"branch_disagreement_high": False, "scenario_drift_high": False}},
            ),
            collapse_context=SimpleNamespace(
                top_states={"primary": "range_probe"},
                uncertainty_decomposition={
                    "epistemic_uncertainty": 0.22,
                    "policy_disagreement": 0.25,
                    "execution_fragility": 0.18,
                    "observability_uncertainty": 0.0,
                    "negative_evidence_mass": 0.12,
                },
            ),
            scenario_tree=SimpleNamespace(
                branches=[SimpleNamespace(label="range_probe", probability=0.55, expected_move_bps=14.0)],
                probability_field=SimpleNamespace(confidence_decomposition={"signal": 0.72, "regime": 0.66}),
            ),
        ),
        provider_capability=SimpleNamespace(
            user_stream_confidence="user_stream_plus_rest_repair",
            lifecycle_completeness="strong_without_replace",
            fee_truth_confidence="spot_trade_history_authoritative",
            metadata={"capability_evidence": {"partial": False, "lifecycle_snapshot_count": 0, "freshness_seconds": 0.0, "single_process_lifecycle_equivalent": False, "reasons": ["lifecycle_proof_incomplete"], "classifications": {"execution_blocker": [], "promotion_blocker": ["lifecycle_proof_incomplete"], "confidence_haircut": [], "informational_only": []}}},
        ),
        event_intelligence_report=SimpleNamespace(partial=True),
        execution_quality=SimpleNamespace(),
    )
    decision_ctx = SimpleNamespace(
        health_snapshot=SimpleNamespace(action="continue"),
        meta_governor_decision=SimpleNamespace(action="continue", reasons=[], size_multiplier=1.0),
        policy_decision=SimpleNamespace(
            symbol="ETH/EUR",
            trade_allowed=False,
            side=None,
            no_trade=SimpleNamespace(reason="no_edge_after_costs", reasons=["no_edge_after_costs"]),
            why={
                "truth_context": {
                    "reconciliation_ok": True,
                    "snapshot": {
                        "overall_action": "continue",
                        "reasons": [],
                    },
                },
                "spre": {
                    "dominant_action": "no_trade",
                    "internal_action": "no_trade",
                    "chosen_survival_ratio": 0.76,
                    "action_gap_bps": 1.6,
                    "ambiguity_penalty": 0.12,
                    "no_trade_quality": 1.4,
                    "reasons": ["no_trade_quality_dominant"],
                    "action_scores": {"trade": 2.1, "wait": 2.2, "no_trade": 2.3},
                },
                "mastermind": {
                    "decision": "CONTINUE",
                    "signal": "hold_for_better_edge",
                    "reason": "mastermind_continue",
                    "confidence": 0.72,
                    "risk_level": 23.0,
                    "size_multiplier": 0.7,
                    "veto": False,
                    "reasons": ["mastermind_continue"],
                    "raw": {
                        "risk_components": {"decision_uncertainty": 0.18},
                        "observability_components": {},
                        "uncertainty_components": {"quantum_uncertainty": 0.21},
                        "veto_chain": [],
                    },
                },
                "decision_doctrine": {
                    "recommended_action": "no_trade",
                    "size_multiplier": 0.0,
                    "uncertainty_pressure": 0.31,
                    "partial_truth_penalty": 0.0,
                    "truth_strength": 1.0,
                    "survival_score": 0.82,
                    "robustness_score": 0.81,
                    "reasons": ["doctrine_round_trip_not_positive"],
                    "metadata": {"uncertainty_components": {"quantum_uncertainty": 0.21}},
                },
            },
        ),
        risk_decision=SimpleNamespace(allowed=True, reason="", details={}),
        adjusted_intent=None,
        execution_plan=None,
        synthetic_affect_state=None,
        capital_sovereignty_decision=None,
        position_morph_plan=None,
        adaptive_exit_allocation=None,
        execution_simulation_report=None,
        human_escalation_decision=None,
    )

    orchestrator._emit_live_runtime_summary(
        symbol="ETH/EUR",
        mode=settings.execution_mode_enum(),
        market=market,
        decision_ctx=decision_ctx,
        step=2,
    )

    health_summary = json.loads((Path(settings.storage.run_dir) / "health_summary.json").read_text(encoding="utf-8"))

    assert health_summary["ordering_allowed"] is True
    assert health_summary["blocking_reasons"] == []
    assert health_summary["trade_path_state"] == "blocked_by_decision"
    assert health_summary["top_blockers"][0]["code"] != "truth_confidence:degrade:fill_proxy"


def test_live_runtime_summary_surfaces_affordability_veto_as_top_blocker(tmp_path):
    settings = RobotSettings(
        storage=StorageSettings(run_dir=str(tmp_path)),
        provider_whitelist=["kraken_spot"],
        universe=["BTC/USD"],
        canary_mode=True,
        execution=ExecutionSettings(mode="paper", provider_id="kraken_spot"),
        risk=RiskLimits(
            max_daily_loss_pct=1.0,
            max_weekly_loss_pct=2.0,
            max_drawdown_pct=2.0,
            max_position_notional=10.0,
            max_exposure_notional=10.0,
            max_symbol_exposure_notional=10.0,
            max_cluster_exposure_notional=10.0,
            max_orders_per_min=5,
            leverage=0,
            max_spread_bps=10.0,
            min_depth_notional=10.0,
            stale_data_seconds=10.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=1.0,
            max_liquidation_spike=1.0,
            divergence_threshold_bps=10.0,
            crowding_score_kill=10.0,
        ),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    orchestrator = RobotOrchestrator(settings)
    orchestrator._last_live_preflight_ok = True
    orchestrator._last_live_ordering_allowed = True
    orchestrator._last_live_blocking_reasons = []
    market = SimpleNamespace(
        forecast=SimpleNamespace(symbol="BTC/USD", regime="RANGE", liquidity_regime="GOOD"),
        market_integrity=SimpleNamespace(action="continue", score=0.98, reasons=[]),
        market_watch=SimpleNamespace(action="continue", score=1.0, spread_score=1.0, liquidity_score=1.0, reasons=[], metadata={}),
        edge_immunity_decision=SimpleNamespace(
            action="trade_now",
            reason="edge_survives_counterfactuals",
            report=SimpleNamespace(
                base_expected_edge_bps=12.0,
                stressed_expected_edge_bps=10.0,
                edge_survival_ratio=0.83,
                fragility_index=0.19,
                wait_value_score=0.1,
                dominant_failure_modes=[],
                metadata={"wait_dominance": {"trade_now_score": 0.8, "wait_score_bps": 0.12, "wait_dominant": False}},
            ),
        ),
        quantum_state=SimpleNamespace(
            collapse_decision=SimpleNamespace(
                recommended_action="wait",
                action_score=2.0,
                no_trade_probability=0.21,
                execution_fragility_score=0.18,
                uncertainty=0.42,
                branch_disagreement_score=0.31,
                scenario_drift_score=0.28,
                reasons=["scenario_drift_high"],
                metadata={"thresholds": {"scenario_drift_high": False}},
            ),
            collapse_context=SimpleNamespace(
                top_states={"primary": "bullish_continuation"},
                uncertainty_decomposition={
                    "epistemic_uncertainty": 0.22,
                    "policy_disagreement": 0.31,
                    "execution_fragility": 0.18,
                    "observability_uncertainty": 0.0,
                    "negative_evidence_mass": 0.17,
                },
            ),
            scenario_tree=SimpleNamespace(
                branches=[SimpleNamespace(label="bullish_continuation", probability=0.61, expected_move_bps=11.0)],
                probability_field=SimpleNamespace(confidence_decomposition={"signal": 0.74, "regime": 0.69}),
            ),
        ),
        provider_capability=SimpleNamespace(
            user_stream_confidence="user_stream_plus_rest_repair",
            lifecycle_completeness="strong_without_replace",
            metadata={
                "capability_evidence": {
                    "partial": False,
                    "lifecycle_snapshot_count": 1,
                    "freshness_seconds": 0.4,
                    "single_process_lifecycle_equivalent": False,
                    "reasons": ["lifecycle_proof_incomplete"],
                    "classifications": {
                        "execution_blocker": [],
                        "promotion_blocker": ["lifecycle_proof_incomplete"],
                        "confidence_haircut": [],
                        "informational_only": ["lifecycle_proof_incomplete"],
                    },
                }
            },
        ),
        event_intelligence_report=SimpleNamespace(partial=True),
        execution_quality=SimpleNamespace(),
    )
    profitability = {
        "round_trip": {
            "action": "trade_smaller",
            "viable": True,
            "recommended_size_multiplier": 0.5,
            "reasons": ["free_quote_reserve_breached"],
        },
        "capital_release": {
            "action": "continue",
            "allowed": False,
            "pressure_score": 0.4,
            "metadata": {
                "reserve_state": {
                    "quote_asset": "USD",
                    "quote_free_balance": 0.0,
                    "quote_total_balance": 0.0,
                    "entry_buying_power_quote": 0.0,
                    "required_quote_with_fee_buffer": 0.13,
                    "reserve_floor_quote": 0.0,
                    "reserve_breached": True,
                    "reasons": ["free_quote_reserve_breached"],
                    "metadata": {"affordability_source": "quote_asset_balance"},
                }
            },
        },
    }
    decision_ctx = SimpleNamespace(
        health_snapshot=SimpleNamespace(action="continue"),
        meta_governor_decision=SimpleNamespace(action="continue", reasons=[], size_multiplier=1.0),
        policy_decision=SimpleNamespace(
            symbol="BTC/USD",
            trade_allowed=False,
            side=None,
            no_trade=SimpleNamespace(
                reason="spre_no_trade_dominance",
                reasons=["spre_no_trade_dominance", "decision_doctrine_probe"],
                metadata={
                    "profitability": profitability,
                    "capital_sovereignty": {"action": "probe_only", "reserve_pressure": 1.0, "probe_ratio": 0.08},
                    "human_escalation": {"action": "continue", "manual_review_required": False, "disagreement_score": 0.28},
                },
            ),
            why={
                "spre": {
                    "dominant_action": "no_trade",
                    "internal_action": "trade_now",
                    "chosen_survival_ratio": 1.0,
                    "action_gap_bps": 1.1,
                    "ambiguity_penalty": 0.2,
                    "no_trade_quality": 2.1,
                    "reasons": ["no_trade_quality_dominant"],
                    "action_scores": {"trade": 4.0, "wait": 3.6, "no_trade": 4.1},
                },
                "mastermind": {
                    "decision": "CONTINUE",
                    "signal": "bounded_support",
                    "reason": "local_survival_ok",
                    "confidence": 0.77,
                    "risk_level": 28.0,
                    "size_multiplier": 1.0,
                    "veto": False,
                    "reasons": ["mastermind_continue"],
                    "raw": {
                        "risk_components": {"decision_uncertainty": 0.28},
                        "observability_components": {"provider_penalty": 0.0},
                        "uncertainty_components": {"quantum_uncertainty": 0.38},
                        "veto_chain": [],
                    },
                },
                "decision_doctrine": {
                    "recommended_action": "probe",
                    "size_multiplier": 0.64,
                    "uncertainty_pressure": 0.42,
                    "partial_truth_penalty": 0.0,
                    "truth_strength": 1.0,
                    "survival_score": 0.85,
                    "robustness_score": 0.95,
                    "reasons": ["doctrine_probe_dominates"],
                    "metadata": {"uncertainty_components": {"quantum_uncertainty": 0.38}},
                },
                "profitability": profitability,
                "capital_sovereignty": {"action": "probe_only", "reserve_pressure": 1.0, "probe_ratio": 0.08},
                "human_escalation": {"action": "continue", "manual_review_required": False, "disagreement_score": 0.28},
            },
            profitability=profitability,
        ),
        risk_decision=SimpleNamespace(allowed=True, reason="", details={}),
        adjusted_intent=None,
        execution_plan=None,
        synthetic_affect_state=None,
        capital_sovereignty_decision=None,
        position_morph_plan=None,
        adaptive_exit_allocation=None,
        execution_simulation_report=None,
        human_escalation_decision=None,
    )

    summary_path = orchestrator._emit_live_runtime_summary(
        symbol="BTC/USD",
        mode=settings.execution_mode_enum(),
        market=market,
        decision_ctx=decision_ctx,
        step=8,
    )

    trace_latest = json.loads((Path(settings.storage.run_dir) / "decision_collapse_trace_latest.json").read_text(encoding="utf-8"))
    explainability = json.loads((Path(settings.storage.run_dir) / "decision_explainability.json").read_text(encoding="utf-8"))
    health_summary = json.loads((Path(settings.storage.run_dir) / "health_summary.json").read_text(encoding="utf-8"))
    operator_summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))

    assert trace_latest["ranked_blockers"][0]["code"] == "free_quote_reserve_breached"
    assert trace_latest["ranked_blockers"][0]["classification"] == "affordability_veto"
    assert trace_latest["ranked_blockers"][0]["metadata"]["quote_asset"] == "USD"
    assert "edge_survives_counterfactuals" not in [blocker["code"] for blocker in trace_latest["ranked_blockers"]]
    assert explainability["collapse_stage"] == "final_execution_gate"
    assert explainability["top_blocker_type"] == "affordability_veto"
    assert health_summary["top_blockers"][0]["code"] == "free_quote_reserve_breached"
    assert operator_summary["current_blocker_chain"][0]["code"] == "free_quote_reserve_breached"


def test_live_runtime_summary_uses_terminal_reject_truth_and_current_capability_evidence(tmp_path):
    settings = RobotSettings(
        storage=StorageSettings(run_dir=str(tmp_path)),
        provider_whitelist=["kraken_spot"],
        universe=["BTC/USD"],
        canary_mode=True,
        execution=ExecutionSettings(mode="paper", provider_id="kraken_spot"),
        risk=RiskLimits(
            max_daily_loss_pct=1.0,
            max_weekly_loss_pct=2.0,
            max_drawdown_pct=2.0,
            max_position_notional=10.0,
            max_exposure_notional=10.0,
            max_symbol_exposure_notional=10.0,
            max_cluster_exposure_notional=10.0,
            max_orders_per_min=5,
            leverage=0,
            max_spread_bps=10.0,
            min_depth_notional=10.0,
            stale_data_seconds=10.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=1.0,
            max_liquidation_spike=1.0,
            divergence_threshold_bps=10.0,
            crowding_score_kill=10.0,
        ),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    orchestrator = RobotOrchestrator(settings)
    orchestrator._last_live_preflight_ok = True
    orchestrator._last_live_ordering_allowed = True
    orchestrator._last_live_blocking_reasons = []
    market = SimpleNamespace(
        forecast=SimpleNamespace(symbol="BTC/USD", regime="RANGE", liquidity_regime="GOOD"),
        market_integrity=SimpleNamespace(action="continue", score=0.95, reasons=[]),
        market_watch=SimpleNamespace(action="continue", score=0.9, spread_score=1.0, liquidity_score=1.0, reasons=[], metadata={}),
        edge_immunity_decision=None,
        quantum_state=None,
        provider_capability=SimpleNamespace(
            user_stream_confidence="rest_history_only",
            lifecycle_completeness="partial_without_snapshot",
            metadata={
                "capability_evidence": {
                    "partial": True,
                    "lifecycle_snapshot_count": 0,
                    "freshness_seconds": 2.0,
                    "single_process_lifecycle_equivalent": False,
                    "reasons": ["lifecycle_snapshot_absent", "user_stream_not_connected"],
                    "classifications": {
                        "execution_blocker": [],
                        "promotion_blocker": ["lifecycle_snapshot_absent", "user_stream_not_connected"],
                        "confidence_haircut": [],
                        "informational_only": [],
                    },
                }
            },
        ),
        event_intelligence_report=SimpleNamespace(partial=False),
        execution_quality=SimpleNamespace(),
    )
    decision_ctx = SimpleNamespace(
        health_snapshot=SimpleNamespace(action="continue"),
        meta_governor_decision=SimpleNamespace(action="continue", reasons=[], size_multiplier=1.0),
        policy_decision=SimpleNamespace(symbol="BTC/USD", trade_allowed=True, why={}),
        risk_decision=SimpleNamespace(allowed=True, reason="", details={}),
        adjusted_intent=SimpleNamespace(symbol="BTC/USD", side="buy"),
        execution_plan=None,
        synthetic_affect_state=None,
        capital_sovereignty_decision=None,
        position_morph_plan=None,
        adaptive_exit_allocation=None,
        execution_simulation_report=None,
        human_escalation_decision=None,
    )
    execution_result = SimpleNamespace(
        status="rejected",
        reason='maker_reject:kraken {"error":["EOrder:Insufficient funds"]}',
        metadata={
            "lifecycle_proof": {
                "submitted": True,
                "exchange_acknowledged": False,
                "terminal_observed": True,
                "reconciliation_complete": False,
                "last_terminal_state": "REJECTED",
            },
            "capability_evidence": {
                "partial": True,
                "lifecycle_snapshot_count": 1,
                "freshness_seconds": 0.5,
                "single_process_lifecycle_equivalent": False,
                "reasons": ["user_stream_not_connected"],
                "classifications": {
                    "execution_blocker": [],
                    "promotion_blocker": ["user_stream_not_connected"],
                    "confidence_haircut": [],
                    "informational_only": [],
                },
            },
            "execution_blocker": {
                "code": 'maker_reject:kraken {"error":["EOrder:Insufficient funds"]}',
                "source": "exchange_submit_exception",
            },
        },
    )

    summary_path = orchestrator._emit_live_runtime_summary(
        symbol="BTC/USD",
        mode=settings.execution_mode_enum(),
        market=market,
        decision_ctx=decision_ctx,
        execution_result=execution_result,
        step=4,
    )

    trace_latest = json.loads((Path(settings.storage.run_dir) / "decision_collapse_trace_latest.json").read_text(encoding="utf-8"))
    health_summary = json.loads((Path(settings.storage.run_dir) / "health_summary.json").read_text(encoding="utf-8"))
    explainability = json.loads((Path(settings.storage.run_dir) / "decision_explainability.json").read_text(encoding="utf-8"))
    operator_summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    provider_stage = next(stage for stage in trace_latest["stages"] if stage["stage"] == "provider_capability")

    assert trace_latest["trade_path_state"] == "terminal_observed"
    assert health_summary["trade_path_state"] == "terminal_observed"
    assert explainability["collapse_stage"] == "final_execution_gate"
    assert explainability["top_blocker_type"] == "exchange_reject"
    assert provider_stage["normalized_inputs"]["lifecycle_snapshot_count"] == 1.0
    assert provider_stage["reasons"] == ["user_stream_not_connected"]
    assert operator_summary["current_blocker_chain"][0]["code"] == 'maker_reject:kraken {"error":["EOrder:Insufficient funds"]}'


def test_live_runtime_summary_rehydrates_execution_lifecycle_report_from_journals(tmp_path):
    settings = RobotSettings(
        storage=StorageSettings(run_dir=str(tmp_path)),
        provider_whitelist=["kraken_spot"],
        universe=["BTC/USD"],
        canary_mode=True,
        execution=ExecutionSettings(mode="paper", provider_id="kraken_spot"),
        risk=RiskLimits(
            max_daily_loss_pct=1.0,
            max_weekly_loss_pct=2.0,
            max_drawdown_pct=2.0,
            max_position_notional=10.0,
            max_exposure_notional=10.0,
            max_symbol_exposure_notional=10.0,
            max_cluster_exposure_notional=10.0,
            max_orders_per_min=5,
            leverage=0,
            max_spread_bps=10.0,
            min_depth_notional=10.0,
            stale_data_seconds=10.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=1.0,
            max_liquidation_spike=1.0,
            divergence_threshold_bps=10.0,
            crowding_score_kill=10.0,
        ),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    orchestrator = RobotOrchestrator(settings)
    orchestrator._last_live_preflight_ok = True
    orchestrator._last_live_ordering_allowed = True
    orchestrator._last_live_blocking_reasons = []
    orchestrator._append_jsonl_artifact(
        "lifecycle_evidence_journal.jsonl",
        {
            "type": "summary",
            "symbol": "BTC/USD",
            "provider_id": "kraken_spot",
            "result_status": "timeout",
            "gap_reasons": ["normalized_fill_missing"],
            "proof": {
                "requested": True,
                "submitted": True,
                "exchange_acknowledged": True,
                "terminal_observed": True,
                "last_terminal_state": "CANCELLED",
                "last_reason": "lifecycle_proof_timeout",
                "reconciliation_complete": False,
            },
        },
    )
    orchestrator._append_jsonl_artifact(
        "reconciliation_journal.jsonl",
        {
            "ok": False,
            "code": "live_fill_truth_unavailable",
            "action": "flatten_only",
            "details": {
                "failing_domains": ["fill_completeness"],
                "truth_confidence": {
                    "fill_truth_confidence": {"level": "unavailable"},
                },
            },
        },
    )
    market = SimpleNamespace(
        forecast=SimpleNamespace(symbol="BTC/USD", regime="RANGE", liquidity_regime="GOOD"),
        market_integrity=SimpleNamespace(action="continue", score=0.95, reasons=[]),
        market_watch=SimpleNamespace(action="continue", score=0.9, spread_score=1.0, liquidity_score=1.0, reasons=[], metadata={}),
        edge_immunity_decision=None,
        quantum_state=None,
        provider_capability=SimpleNamespace(
            user_stream_confidence="single_process_rest_repair",
            lifecycle_completeness="strong_without_replace",
            metadata={"capability_evidence": {"partial": False, "lifecycle_snapshot_count": 1, "freshness_seconds": 0.2, "classifications": {}}},
        ),
        event_intelligence_report=SimpleNamespace(partial=False),
        execution_quality=SimpleNamespace(fill_probability=0.0),
        regime_assessment=None,
        features={},
    )
    decision_ctx = SimpleNamespace(
        health_snapshot=SimpleNamespace(action="continue"),
        meta_governor_decision=SimpleNamespace(action="continue", reasons=[], size_multiplier=1.0),
        policy_decision=SimpleNamespace(symbol="BTC/USD", trade_allowed=True, why={"decision_doctrine": {"recommended_action": "continue", "reasons": []}}),
        risk_decision=SimpleNamespace(allowed=True, reason="", details={}, adjusted_notional=0.0),
        adjusted_intent=None,
        execution_plan=None,
        inventory_state=None,
        profitability_context=None,
        synthetic_affect_state=None,
        capital_sovereignty_decision=None,
        position_morph_plan=None,
        adaptive_exit_allocation=None,
        execution_simulation_report=None,
        human_escalation_decision=None,
    )

    orchestrator._emit_live_runtime_summary(
        symbol="BTC/USD",
        mode=settings.execution_mode_enum(),
        market=market,
        decision_ctx=decision_ctx,
        execution_result=None,
        step=5,
    )

    execution_lifecycle = json.loads((Path(settings.storage.run_dir) / "execution_lifecycle_report.json").read_text(encoding="utf-8"))

    assert execution_lifecycle["status"] == "timeout"
    assert execution_lifecycle["reason"] == "lifecycle_proof_timeout"
    assert execution_lifecycle["lifecycle_proof"]["terminal_observed"] is True
    assert execution_lifecycle["gap_reasons"] == ["normalized_fill_missing"]
    assert execution_lifecycle["reconciliation"]["code"] == "live_fill_truth_unavailable"
    assert execution_lifecycle["reconciliation"]["failing_domains"] == ["fill_completeness"]


def test_live_readiness_artifacts_overwrite_stale_execution_lifecycle_report(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    monkeypatch.setenv("TESTNET_VALIDATED", "true")
    settings = RobotSettings(
        storage=StorageSettings(run_dir=str(tmp_path)),
        provider_whitelist=["kraken_spot"],
        universe=["BTC/USD"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live", provider_id="kraken_spot"),
        safety=SafetySettings(
            live_unlock=LiveUnlockSettings(
                enable_live_trading=True,
                ack_i_understand_risks=True,
                require_testnet_passed=True,
            )
        ),
        doctrine=DoctrineSettings(
            target_provider="kraken_spot",
            product_target="spot",
            long_only=True,
            never_open_new_short_exposure=True,
            minimum_sell_net_profit_bps=120.0,
            enforce_cost_basis_sell_block=True,
            enforce_net_profit_sell_block=True,
            block_non_reduce_only_sells=True,
        ),
        harmony=HarmonySettings(enabled=True),
        market_watch=MarketWatchSettings(enabled=True),
        risk=RiskLimits(
            max_daily_loss_pct=1.0,
            max_weekly_loss_pct=2.0,
            max_drawdown_pct=2.0,
            max_position_notional=10.0,
            max_exposure_notional=10.0,
            max_symbol_exposure_notional=10.0,
            max_cluster_exposure_notional=10.0,
            max_orders_per_min=5,
            leverage=0,
            max_spread_bps=10.0,
            min_depth_notional=10.0,
            stale_data_seconds=10.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=1.0,
            max_liquidation_spike=1.0,
            divergence_threshold_bps=10.0,
            crowding_score_kill=10.0,
        ),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    orchestrator = RobotOrchestrator(settings)
    stale_path = Path(settings.storage.run_dir) / "execution_lifecycle_report.json"
    stale_path.write_text(json.dumps({"status": "timeout", "reason": "stale"}, indent=2), encoding="utf-8")

    orchestrator._emit_live_readiness_artifacts(
        symbol="BTC/USD",
        mode=settings.execution_mode_enum(),
        harmony_payload={},
        preflight_ok=True,
        preflight_reason="ok",
        confidence="degraded",
        confidence_details={},
        recovery_decision=SimpleNamespace(action="degrade"),
        ordering_allowed=False,
    )

    execution_lifecycle = json.loads(stale_path.read_text(encoding="utf-8"))

    assert execution_lifecycle["status"] is None
    assert execution_lifecycle["reason"] is None
    assert execution_lifecycle["trade_path_state"] == "not_attempted"
    assert execution_lifecycle["top_blockers"][0]["code"] == "restart_state:degraded"
