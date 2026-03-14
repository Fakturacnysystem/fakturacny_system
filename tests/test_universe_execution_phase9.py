from __future__ import annotations

from autonomous_investment_robot.services.universe_core import (
    ExecutionIntelligence,
    ExecutionIntelligenceEngine,
    MissionDecision,
    MissionType,
    StrategyProposal,
    UniverseMind,
)


def _seed_world(
    mind: UniverseMind,
    *,
    symbol: str = "XBTUSD",
    spread_bps: float = 6.0,
    depth_notional: float = 18_000.0,
    trend_bps: float = 52.0,
    realized_vol: float = 0.008,
    drawdown_pct: float = 0.01,
    rejection_ratio: float = 0.02,
    fill_probability: float = 0.94,
    slippage_bps: float = 1.4,
    latency_ms: float = 40.0,
    stale_feed: bool = False,
    desync: bool = False,
) -> None:
    for event_type, payload in (
        (
            "MarketTickEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "mid": 100.0,
                "spread_bps": spread_bps,
                "trend_bps": trend_bps,
                "realized_vol": realized_vol,
            },
        ),
        (
            "BookSnapshotEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "spread_bps": spread_bps,
                "depth_notional": depth_notional,
            },
        ),
        (
            "AccountSnapshotEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "equity_quote": 2_500.0,
                "free_quote": 2_000.0,
                "exposure_quote": 180.0,
                "drawdown_pct": drawdown_pct,
            },
        ),
        (
            "HealthEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "status": "OK",
                "latency_ms": latency_ms,
                "health_score": 0.95,
                "rejection_ratio": rejection_ratio,
                "stale_feed": stale_feed,
                "desync": desync,
            },
        ),
        (
            "OrderEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "open_orders": 2,
                "order_type": "limit",
                "side": "buy",
                "queue_quality": 0.90,
                "rejection_ratio": rejection_ratio,
            },
        ),
        (
            "FillEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "fill_ratio": 0.90,
                "slippage_bps": slippage_bps,
                "fill_probability": fill_probability,
                "latency_ms": latency_ms,
                "rejection_ratio": rejection_ratio,
            },
        ),
        (
            "RiskEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "mode": "normal",
                "model_confidence": 0.83,
                "uncertainty_bps": 6.0,
                "observe_only": False,
                "hard_stop": False,
            },
        ),
        (
            "RegimeEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "regime": "TREND",
                "confidence": 0.82,
                "volatility_regime": "HIGH_VOL" if realized_vol >= 0.015 else "LOW_VOL",
                "liquidity_regime": "THIN" if depth_notional < 1_200.0 else "DEEP",
                "expansion_state": "EXPANSION" if realized_vol >= 0.01 else "COMPRESSION",
                "panic": realized_vol >= 0.03,
            },
        ),
    ):
        mind.emit(event_type=event_type, source="test", partition_key=symbol, payload=payload)


def _proposal(
    *,
    symbol: str = "XBTUSD",
    strategy: str = "microstructure_momentum",
    side: str = "buy",
    edge_bps: float = 14.0,
    confidence: float = 0.82,
    target_notional_quote: float = 180.0,
    execution_sensitivity: float = 0.70,
    slippage_risk_bps: float = 1.6,
) -> StrategyProposal:
    return StrategyProposal(
        strategy=strategy,
        instrument=symbol,
        action="trade",
        side=side,
        target_notional_quote=target_notional_quote,
        expected_value_bps=edge_bps,
        confidence=confidence,
        expected_hold_time_s=45.0,
        execution_sensitivity=execution_sensitivity,
        slippage_risk_bps=slippage_risk_bps,
        regime_compatibility=0.92,
        risk_cost_bps=1.0,
    )


def _build_envelope(
    mind: UniverseMind,
    *,
    proposal: StrategyProposal,
    mission_override: MissionDecision | None = None,
):
    world = mind.get_world_state()
    mission = mission_override or mind.mission_engine.choose(world, previous_mission=world.strategy_state.last_mission)
    if mission.no_trade_preferred or mission.size_scale <= 0.05:
        mission = MissionDecision(
            mission_type=MissionType.MOMENTUM_EXTRACTION,
            confidence=0.70,
            reason_codes=("phase9_test_override",),
            allow_new_risk=True,
            no_trade_preferred=False,
            size_scale=1.0,
        )
    baseline = ExecutionIntelligence().build_plan(proposal, world=world, mission=mission)
    return ExecutionIntelligenceEngine().evaluate(
        proposal=proposal,
        baseline_plan=baseline,
        world=world,
        mission=mission,
        learning_summary={},
    )


def test_phase9_thin_book_wide_spread_depth_drop_stresses_execution(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(
        mind,
        spread_bps=48.0,
        depth_notional=620.0,
        realized_vol=0.020,
        rejection_ratio=0.35,
        fill_probability=0.40,
        slippage_bps=12.0,
        latency_ms=220.0,
    )
    world = mind.get_world_state()
    world.execution_state.execution_stress = 0.72
    world.market_state.depth_notional = 620.0
    envelope = _build_envelope(mind, proposal=_proposal(target_notional_quote=220.0))
    assert envelope.order_book_shape.thin_book is True
    assert envelope.order_book_shape.wide_spread is True
    assert envelope.order_book_shape.sudden_depth_drop is True
    assert envelope.stress_index.score >= 0.60
    assert envelope.slicer.slice_count >= 2


def test_phase9_microstructure_burst_and_toxicity_detection(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(
        mind,
        spread_bps=26.0,
        depth_notional=900.0,
        trend_bps=180.0,
        realized_vol=0.030,
        rejection_ratio=0.40,
        fill_probability=0.35,
        slippage_bps=14.0,
    )
    envelope = _build_envelope(mind, proposal=_proposal(target_notional_quote=260.0, edge_bps=22.0))
    assert envelope.stress_index.micro_vol_burst >= 0.80
    assert envelope.stress_index.toxicity >= 0.45
    assert envelope.matching_engine_anomaly.anomaly_flag is True


def test_phase9_abort_when_execution_risk_exceeds_edge(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(
        mind,
        spread_bps=40.0,
        depth_notional=700.0,
        realized_vol=0.022,
        rejection_ratio=0.45,
        fill_probability=0.35,
        slippage_bps=15.0,
        latency_ms=260.0,
        stale_feed=False,
        desync=False,
    )
    envelope = _build_envelope(mind, proposal=_proposal(edge_bps=2.0, target_notional_quote=250.0, execution_sensitivity=0.95))
    assert envelope.abort_decision.should_abort is True
    assert envelope.plan.actionable is False
    assert any(
        code in set(envelope.abort_decision.reason_codes)
        for code in (
            "no_net_edge_after_costs",
            "fill_risk_exceeds_alpha_edge",
            "exchange_health_degraded",
            "systemic_venue_risk",
        )
    )


def test_phase9_deterministic_for_same_inputs(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind)
    proposal = _proposal()
    first = _build_envelope(mind, proposal=proposal).to_dict()
    second = _build_envelope(mind, proposal=proposal).to_dict()
    assert first == second


def test_phase9_universe_mind_integration_enriches_packet_ops_and_memory(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert result.execution_intelligence is not None
    exec_meta = result.decision_packet.execution_plan.get("meta", {}).get("execution_intelligence", {})
    assert isinstance(exec_meta, dict)
    assert result.ops_snapshot is not None
    assert result.ops_snapshot.execution_personality_mode != ""
    assert result.ops_snapshot.execution_stress_index >= 0.0
    assert result.ops_snapshot.execution_expected_total_cost_bps >= 0.0
    assert result.ops_snapshot.execution_advisory_severity in {"normal", "elevated", "high", "critical", ""}
    assert result.ops_snapshot.execution_survival_protocol != ""
    learning = mind.memory.learning_snapshot().to_dict()
    feedback = learning.get("execution_feedback_summary", {})
    assert isinstance(feedback, dict)
    assert int(feedback.get("sample_count", 0)) >= 1


def test_phase9_execution_plan_contains_bridge_contract_fields(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind, spread_bps=30.0, depth_notional=800.0, realized_vol=0.020, rejection_ratio=0.40, fill_probability=0.35, slippage_bps=12.0)
    envelope = _build_envelope(mind, proposal=_proposal(edge_bps=5.0, target_notional_quote=220.0, execution_sensitivity=0.90))
    payload = envelope.plan.to_dict()
    meta = payload.get("meta", {})
    assert isinstance(meta, dict)
    execution_advisory = meta.get("execution_advisory", {})
    assert isinstance(execution_advisory, dict)
    assert execution_advisory.get("severity") in {"normal", "elevated", "high", "critical"}
    execution_intelligence = meta.get("execution_intelligence", {})
    assert isinstance(execution_intelligence, dict)
    abort = execution_intelligence.get("abort", {})
    assert isinstance(abort, dict)
    assert isinstance(abort.get("should_abort", False), bool)
    assert isinstance(abort.get("reason_codes", []), list)
    assert "expected_net_edge_bps" in payload


def test_phase9_feedback_penalizes_execution_sensitive_strategies(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    seed_packet = mind.memory.build_packet(
        symbol="XBTUSD",
        venue="kraken_spot",
        world_state={"current_world_state": "TREND_LOW_VOL_NORMAL_LIQUIDITY"},
        mission={"mission": "momentum_extraction", "confidence": 0.80},
        proposals=[{"strategy": "seed", "expected_value_bps": 5.0, "confidence": 0.5}],
        selected_strategy="seed",
        selected_strategies=["seed"],
        parliament_mode="top_1",
        parliament_no_trade=False,
        parliament={"diagnostics": {"best_score": 5.0}},
        execution_plan={
            "actionable": True,
            "side": "buy",
            "order_type": "limit",
            "target_notional_quote": 20.0,
            "maker_taker": "maker",
            "urgency_tier": "normal",
            "execution_quality_estimate": {"expected_fill_quality": 0.2, "expected_total_cost_bps": 20.0},
            "meta": {
                "execution_feedback_metrics": {
                    "fill_quality_score": 0.2,
                    "timing_error_score": 0.9,
                    "realized_vs_expected_slippage": 14.0,
                    "opportunity_decay_metric": 0.85,
                }
            },
        },
        shield={"mode": "normal", "shield_mode": "normal", "approved": True},
        ops_snapshot={"rollout_stage": "paper"},
        meta_intelligence={},
        cycle_id="phase9-seed",
    )
    mind.memory.record(seed_packet)
    _seed_world(mind)
    high_sens = _proposal(strategy="aggressive_momentum", execution_sensitivity=0.95, edge_bps=14.0)
    low_sens = _proposal(strategy="calm_momentum", execution_sensitivity=0.15, edge_bps=14.0)
    result = mind.run_cycle(
        symbol="XBTUSD",
        venue="kraken_spot",
        proposals=[high_sens, low_sens],
        parliament_mode="top_1",
        parliament_score_floor=0.0,
    )
    assert result.decision_packet.selected_strategy == "calm_momentum"
    rejected = [row for row in result.decision_packet.proposals if row.get("strategy") == "aggressive_momentum"]
    assert rejected
    assert "phase9_execution_feedback_penalty" in rejected[0].get("reason_codes", [])


def test_phase9_burst_volatility_sequence_downgrades_aggression(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    proposal = _proposal(target_notional_quote=220.0, edge_bps=20.0)
    envelopes = []
    for realized_vol in (0.008, 0.014, 0.022, 0.032):
        _seed_world(
            mind,
            spread_bps=8.0 + (realized_vol * 600.0),
            depth_notional=12_000.0 - (realized_vol * 200_000.0),
            trend_bps=70.0,
            realized_vol=realized_vol,
            rejection_ratio=0.02 + (realized_vol * 8.0),
            fill_probability=max(0.30, 0.95 - realized_vol * 12.0),
            slippage_bps=1.0 + realized_vol * 200.0,
            latency_ms=40.0 + realized_vol * 3_000.0,
        )
        envelopes.append(_build_envelope(mind, proposal=proposal))
    assert envelopes[0].stress_index.score <= envelopes[-1].stress_index.score
    assert envelopes[-1].mode in {"STEALTH_PASSIVE", "BALANCED_ALPHA", "PANIC_EXIT"}
    assert envelopes[-1].slicer.slice_interval_s >= envelopes[0].slicer.slice_interval_s


def test_phase9_spoof_like_depth_oscillation_heuristic_flags_instability(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(
        mind,
        spread_bps=34.0,
        depth_notional=850.0,
        trend_bps=25.0,
        realized_vol=0.020,
        rejection_ratio=0.28,
        fill_probability=0.28,
        slippage_bps=9.5,
        latency_ms=140.0,
    )
    envelope = _build_envelope(mind, proposal=_proposal(target_notional_quote=240.0, edge_bps=16.0))
    assert envelope.spoofing_heuristic.oscillation_score >= 0.50
    assert envelope.spoofing_heuristic.spoof_like_flag is True
    advisory = envelope.advisory_escalation
    assert isinstance(advisory, dict)
    assert "spoof_like_depth_oscillation" in advisory.get("reason_codes", [])


def test_phase9_unhealthy_exchange_state_raises_advisory_and_abort(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(
        mind,
        spread_bps=42.0,
        depth_notional=760.0,
        trend_bps=55.0,
        realized_vol=0.026,
        rejection_ratio=0.52,
        fill_probability=0.24,
        slippage_bps=14.0,
        latency_ms=360.0,
        stale_feed=True,
        desync=True,
    )
    envelope = _build_envelope(mind, proposal=_proposal(target_notional_quote=260.0, edge_bps=4.0))
    assert envelope.api_health.degraded is True
    assert envelope.advisory_escalation.get("severity") in {"high", "critical"}
    assert envelope.abort_decision.should_abort is True
    assert any(
        code in set(envelope.abort_decision.reason_codes)
        for code in ("exchange_health_degraded", "systemic_venue_risk", "fill_risk_exceeds_alpha_edge")
    )


def test_phase9_execution_personality_mode_transitions_cover_all_modes(tmp_path) -> None:
    def _mode_from_setup(**kwargs):
        mind = UniverseMind(str(tmp_path / kwargs.pop("case_id")))
        _seed_world(mind, **kwargs.pop("seed"))
        proposal = _proposal(**kwargs.pop("proposal"))
        envelope = _build_envelope(mind, proposal=proposal, mission_override=kwargs.pop("mission"))
        return envelope.mode.value

    aggressive = _mode_from_setup(
        case_id="aggressive",
        seed={"spread_bps": 4.0, "depth_notional": 24_000.0, "realized_vol": 0.006, "rejection_ratio": 0.01, "fill_probability": 0.97},
        proposal={"side": "buy", "edge_bps": 24.0, "target_notional_quote": 150.0},
        mission=MissionDecision(mission_type=MissionType.MOMENTUM_EXTRACTION, confidence=0.80),
    )
    sniper = _mode_from_setup(
        case_id="sniper",
        seed={"spread_bps": 5.0, "depth_notional": 30_000.0, "realized_vol": 0.010, "rejection_ratio": 0.03, "fill_probability": 0.95},
        proposal={"strategy": "spread_capture_maker", "edge_bps": 9.0, "target_notional_quote": 120.0, "execution_sensitivity": 0.30},
        mission=MissionDecision(mission_type=MissionType.SPREAD_CAPTURE, confidence=0.75, execution_posture_hint="maker_first", aggressiveness_tier="low_medium"),
    )
    balanced = _mode_from_setup(
        case_id="balanced",
        seed={"spread_bps": 13.0, "depth_notional": 7_000.0, "realized_vol": 0.012, "rejection_ratio": 0.08, "fill_probability": 0.84},
        proposal={"edge_bps": 12.0, "target_notional_quote": 180.0},
        mission=MissionDecision(mission_type=MissionType.MEAN_REVERSION_HARVEST, confidence=0.72),
    )
    stealth = _mode_from_setup(
        case_id="stealth",
        seed={"spread_bps": 28.0, "depth_notional": 1_100.0, "realized_vol": 0.022, "rejection_ratio": 0.33, "fill_probability": 0.48, "slippage_bps": 10.0},
        proposal={"edge_bps": 18.0, "target_notional_quote": 210.0},
        mission=MissionDecision(mission_type=MissionType.LOW_RISK_ACCUMULATION, confidence=0.70, shield_posture_hint="cautious"),
    )
    panic = _mode_from_setup(
        case_id="panic",
        seed={"spread_bps": 18.0, "depth_notional": 3_500.0, "realized_vol": 0.016, "drawdown_pct": 0.09, "rejection_ratio": 0.15, "fill_probability": 0.70},
        proposal={"side": "sell", "edge_bps": 10.0, "target_notional_quote": 220.0, "strategy": "inventory_unwind_fast"},
        mission=MissionDecision(
            mission_type=MissionType.RISK_OFF_DEFENSE,
            confidence=0.85,
            execution_posture_hint="risk_off",
            shield_posture_hint="hard_defensive",
            allow_new_risk=False,
        ),
    )
    seen = {aggressive, sniper, balanced, stealth, panic}
    assert seen == {"AGGRESSIVE_CAPTURE", "LIQUIDITY_SNIPER", "BALANCED_ALPHA", "STEALTH_PASSIVE", "PANIC_EXIT"}


def test_phase9_crisis_survival_doctrine_selects_panic_cliff_and_freeze_paths(tmp_path) -> None:
    panic_mind = UniverseMind(str(tmp_path / "panic"))
    _seed_world(
        panic_mind,
        spread_bps=20.0,
        depth_notional=4_500.0,
        drawdown_pct=0.10,
        realized_vol=0.017,
        rejection_ratio=0.14,
        fill_probability=0.76,
    )
    panic_env = _build_envelope(
        panic_mind,
        proposal=_proposal(side="sell", strategy="inventory_unwind_fast", target_notional_quote=220.0),
        mission_override=MissionDecision(
            mission_type=MissionType.RISK_OFF_DEFENSE,
            confidence=0.88,
            execution_posture_hint="risk_off",
            shield_posture_hint="hard_defensive",
            allow_new_risk=False,
        ),
    )
    assert panic_env.survival_doctrine.protocol == "PanicFlattenProtocol"
    assert panic_env.survival_doctrine.bounded_execution_loss_quote >= 0.0

    cliff_mind = UniverseMind(str(tmp_path / "cliff"))
    _seed_world(
        cliff_mind,
        spread_bps=30.0,
        depth_notional=680.0,
        realized_vol=0.020,
        rejection_ratio=0.26,
        fill_probability=0.42,
        slippage_bps=11.0,
    )
    cliff_env = _build_envelope(cliff_mind, proposal=_proposal(target_notional_quote=260.0, edge_bps=18.0))
    assert cliff_env.survival_doctrine.protocol == "LiquidityCrashExitStrategy"

    freeze_mind = UniverseMind(str(tmp_path / "freeze"))
    _seed_world(
        freeze_mind,
        spread_bps=24.0,
        depth_notional=900.0,
        realized_vol=0.018,
        rejection_ratio=0.30,
        fill_probability=0.45,
        stale_feed=True,
        desync=True,
    )
    freeze_env = _build_envelope(freeze_mind, proposal=_proposal(target_notional_quote=180.0, edge_bps=15.0))
    assert freeze_env.survival_doctrine.protocol == "FrozenOrderRecoveryRoutine"


def test_phase9_deterministic_replay_equivalence_for_execution_scores(tmp_path) -> None:
    original = UniverseMind(str(tmp_path / "a"))
    _seed_world(original, spread_bps=12.0, depth_notional=7_500.0, realized_vol=0.011, rejection_ratio=0.08, fill_probability=0.88)
    proposal = _proposal(target_notional_quote=160.0, edge_bps=13.0)
    first = _build_envelope(original, proposal=proposal).to_dict()
    replay_events = original.replay()

    replayed = UniverseMind(str(tmp_path / "b"))
    replayed.graph.apply_all(replay_events)
    second = _build_envelope(replayed, proposal=proposal).to_dict()
    assert first == second
