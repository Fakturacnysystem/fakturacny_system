from __future__ import annotations

from autonomous_investment_robot.services.autonomous_decision.engine import DecisionContext
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.universe_core import (
    PARLIAMENT_MODE_TOP_N,
    DecisionPacket,
    ExplorationExploitationAllocator,
    MetaIntelligenceEngine,
    MetaPerformanceRecord,
    MetaRiskStabilizer,
    MissionDecision,
    MissionType,
    PersistentPerformanceMemory,
    RegimeClusterIntelligence,
    StrategyProposal,
    StrategyParliament,
    UniverseMind,
    WorldStateGraph,
    build_event,
)


def _world(
    *,
    symbol: str = "XBTUSD",
    regime: str = "TREND",
    volatility_regime: str = "LOW_VOL",
    liquidity_regime: str = "DEEP",
    expansion_state: str = "COMPRESSION",
    drawdown_pct: float = 0.01,
    depth_notional: float = 20_000.0,
    slippage_bps: float = 1.0,
    rejection_ratio: float = 0.02,
    latency_ms: float = 30.0,
) -> object:
    graph = WorldStateGraph()
    graph.apply(
        build_event(
            event_type="MarketTickEvent",
            source="test",
            partition_key=symbol,
            payload={
                "symbol": symbol,
                "venue": "kraken_spot",
                "mid": 100.0,
                "spread_bps": 8.0,
                "trend_bps": 45.0 if regime == "TREND" else 4.0,
                "realized_vol": 0.03 if volatility_regime == "HIGH_VOL" else 0.008,
            },
        )
    )
    graph.apply(
        build_event(
            event_type="BookSnapshotEvent",
            source="test",
            partition_key=symbol,
            payload={"symbol": symbol, "venue": "kraken_spot", "spread_bps": 8.0, "depth_notional": depth_notional},
        )
    )
    graph.apply(
        build_event(
            event_type="AccountSnapshotEvent",
            source="test",
            partition_key=symbol,
            payload={
                "symbol": symbol,
                "venue": "kraken_spot",
                "equity_quote": 2_000.0,
                "free_quote": 1_600.0,
                "exposure_quote": 200.0,
                "drawdown_pct": drawdown_pct,
            },
        )
    )
    graph.apply(
        build_event(
            event_type="HealthEvent",
            source="test",
            partition_key=symbol,
            payload={
                "symbol": symbol,
                "venue": "kraken_spot",
                "status": "OK",
                "latency_ms": latency_ms,
                "health_score": 0.95,
                "rejection_ratio": rejection_ratio,
                "stale_feed": False,
                "desync": False,
            },
        )
    )
    graph.apply(
        build_event(
            event_type="OrderEvent",
            source="test",
            partition_key=symbol,
            payload={
                "symbol": symbol,
                "venue": "kraken_spot",
                "open_orders": 2,
                "order_type": "limit",
                "side": "buy",
                "queue_quality": 0.90,
                "rejection_ratio": rejection_ratio,
            },
        )
    )
    graph.apply(
        build_event(
            event_type="FillEvent",
            source="test",
            partition_key=symbol,
            payload={
                "symbol": symbol,
                "venue": "kraken_spot",
                "fill_ratio": max(0.0, 1.0 - rejection_ratio),
                "slippage_bps": slippage_bps,
                "fill_probability": 0.90,
                "latency_ms": latency_ms,
                "rejection_ratio": rejection_ratio,
            },
        )
    )
    graph.apply(
        build_event(
            event_type="RiskEvent",
            source="test",
            partition_key=symbol,
            payload={
                "symbol": symbol,
                "venue": "kraken_spot",
                "mode": "normal",
                "model_confidence": 0.82,
                "uncertainty_bps": 8.0,
                "observe_only": False,
                "hard_stop": False,
            },
        )
    )
    graph.apply(
        build_event(
            event_type="RegimeEvent",
            source="test",
            partition_key=symbol,
            payload={
                "symbol": symbol,
                "venue": "kraken_spot",
                "regime": regime,
                "confidence": 0.80,
                "volatility_regime": volatility_regime,
                "liquidity_regime": liquidity_regime,
                "expansion_state": expansion_state,
                "panic": regime == "PANIC",
            },
        )
    )
    return graph.snapshot()


def _mission() -> MissionDecision:
    return MissionDecision(
        mission_type=MissionType.MOMENTUM_EXTRACTION,
        confidence=0.80,
        reason_codes=("trend_confirmed",),
        allow_new_risk=True,
    )


def test_regime_cluster_intelligence_classifies_core_states() -> None:
    classifier = RegimeClusterIntelligence()
    stress = classifier.classify(_world(regime="PANIC", volatility_regime="HIGH_VOL"))
    trend = classifier.classify(_world(regime="TREND", liquidity_regime="DEEP"))
    compressed = classifier.classify(_world(regime="RANGE", expansion_state="COMPRESSION"))
    assert stress == "stress"
    assert trend == "trend_quality"
    assert compressed == "range_compression"


def test_exploration_vs_exploitation_allocator_is_deterministic() -> None:
    allocator = ExplorationExploitationAllocator(base_exploration=0.30, min_samples=10)
    low_samples = allocator.budget(sample_count=1, strategy="a", regime_cluster="trend_quality", cycle_id="cycle-1")
    high_samples = allocator.budget(sample_count=20, strategy="a", regime_cluster="trend_quality", cycle_id="cycle-1")
    low_samples_repeat = allocator.budget(sample_count=1, strategy="a", regime_cluster="trend_quality", cycle_id="cycle-1")
    assert low_samples == low_samples_repeat
    assert low_samples[0] > high_samples[0]
    assert abs(low_samples[0] + low_samples[1] - 1.0) < 1e-9


def test_meta_risk_stabilizer_scales_down_under_stress() -> None:
    world = _world(
        regime="PANIC",
        volatility_regime="HIGH_VOL",
        liquidity_regime="THIN",
        drawdown_pct=0.12,
        depth_notional=500.0,
        rejection_ratio=0.40,
        slippage_bps=12.0,
        latency_ms=260.0,
    )
    decision = MissionDecision(
        mission_type=MissionType.PRESERVE_CAPITAL,
        confidence=0.9,
        reason_codes=("risk_off",),
        no_trade_preferred=True,
        allow_new_risk=False,
    )
    scale, notes = MetaRiskStabilizer().risk_scale(world=world, mission=decision)
    assert scale <= 0.40
    assert "high_volatility" in notes
    assert "thin_liquidity" in notes


def test_adaptive_strategy_weighting_uses_persistent_performance_memory(tmp_path) -> None:
    memory = PersistentPerformanceMemory(str(tmp_path), max_records=200)
    for idx in range(8):
        memory.record(
            MetaPerformanceRecord(
                cycle_id=f"win-{idx}",
                ts=1_700_000_000.0 + idx,
                strategy="microstructure_momentum",
                regime_cluster="trend_quality",
                realized_pnl_quote=4.0,
                realized_slippage_bps=1.0,
                grade="win",
            )
        )
        memory.record(
            MetaPerformanceRecord(
                cycle_id=f"loss-{idx}",
                ts=1_700_000_100.0 + idx,
                strategy="mean_reversion",
                regime_cluster="trend_quality",
                realized_pnl_quote=-2.0,
                realized_slippage_bps=4.0,
                grade="loss",
            )
        )
    engine = MetaIntelligenceEngine(str(tmp_path), performance_memory=memory)
    proposals = [
        StrategyProposal(
            strategy="microstructure_momentum",
            instrument="XBTUSD",
            action="trade",
            side="buy",
            target_notional_quote=100.0,
            expected_value_bps=10.0,
            confidence=0.8,
            expected_hold_time_s=40.0,
            execution_sensitivity=0.6,
            slippage_risk_bps=1.0,
            regime_compatibility=0.95,
            risk_cost_bps=1.0,
        ),
        StrategyProposal(
            strategy="mean_reversion",
            instrument="XBTUSD",
            action="trade",
            side="buy",
            target_notional_quote=100.0,
            expected_value_bps=10.0,
            confidence=0.8,
            expected_hold_time_s=40.0,
            execution_sensitivity=0.6,
            slippage_risk_bps=1.0,
            regime_compatibility=0.95,
            risk_cost_bps=1.0,
        ),
    ]
    adjusted_a, snapshot_a = engine.adapt_proposals(proposals, world=_world(), mission=_mission(), cycle_id="cycle-42")
    adjusted_b, snapshot_b = engine.adapt_proposals(proposals, world=_world(), mission=_mission(), cycle_id="cycle-42")
    per_strategy = {row.strategy: row for row in adjusted_a}
    assert per_strategy["microstructure_momentum"].expected_value_bps > per_strategy["mean_reversion"].expected_value_bps
    assert [row.to_dict() for row in adjusted_a] == [row.to_dict() for row in adjusted_b]
    assert snapshot_a.to_dict() == snapshot_b.to_dict()


def test_persistent_performance_memory_is_bounded(tmp_path) -> None:
    memory = PersistentPerformanceMemory(str(tmp_path), max_records=5)
    for idx in range(10):
        memory.record(
            MetaPerformanceRecord(
                cycle_id=f"cycle-{idx}",
                ts=float(idx),
                strategy="s",
                regime_cluster="neutral",
                realized_pnl_quote=1.0,
                realized_slippage_bps=1.0,
                grade="win",
            )
        )
    rows = memory.load()
    assert len(rows) == 5
    assert rows[0].cycle_id == "cycle-5"
    assert rows[-1].cycle_id == "cycle-9"


def test_universe_mind_integration_persists_meta_and_enriches_ops_snapshot(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    ctx = DecisionContext(
        symbol="XBTUSD",
        now_ts=1_700_000_000.0,
        bid=100.0,
        ask=100.05,
        mid=100.025,
        spread_bps=5.0,
        depth_notional=15_000.0,
        features={"realized_vol": 0.008, "depth_notional": 15_000.0},
        market_watch={"trend_2m_bps": 50.0},
        forecast_mu=12.0,
        forecast_sigma=6.0,
        forecast_confidence=0.84,
        position_notional_quote=0.0,
        signed_exposure_notional_quote=0.0,
        avg_entry_price=0.0,
        position_age_s=0.0,
        current_profit_bps=0.0,
        drawdown_pct=0.01,
        quote_free=2_000.0,
        max_exposure_notional=5_000.0,
        order_cadence_s=5.0,
        last_submission_ts=1_699_999_995.0,
        fee_bps=10.0,
        slippage_bps=1.0,
        latency_ms=40.0,
        market_class="crypto_spot",
        guards_mode="strict",
        modeled_cost_floor_bps=30.0,
        sell_min_profit_bps=30.0,
        sell_target_profit_bps=60.0,
    )
    intent = OrderIntent(
        symbol="XBTUSD",
        side="buy",
        target_notional=300.0,
        why={
            "components": [
                {
                    "strategy": "microstructure_momentum",
                    "signal_side": "buy",
                    "signal_notional": 220.0,
                    "final_edge_bps": 18.0,
                    "confidence": 0.82,
                    "cost_total_bps": 4.0,
                    "execution_sensitivity": 0.7,
                    "slippage_risk_bps": 1.8,
                    "regime_fit": 0.9,
                    "reason_codes": ["trend_confirmed"],
                }
            ]
        },
    )
    mind.ingest_decision_context(ctx, venue="kraken_spot")
    result = mind.run_cycle_from_intent(intent, venue="kraken_spot")
    assert result.meta_snapshot is not None
    assert result.decision_packet.meta_intelligence["regime_cluster"]
    assert result.ops_snapshot is not None
    assert result.ops_snapshot.meta_regime_cluster == result.decision_packet.meta_intelligence["regime_cluster"]
    graded = mind.grade_cycle(
        result.decision_packet,
        realized_pnl_quote=7.0,
        realized_slippage_bps=1.5,
        realized_regime="TREND",
        fill_ratio=0.9,
    )
    assert graded.evaluation["status"] == "graded"
    assert mind.meta.performance_memory.size() >= 1


def test_decision_packet_backward_compatibility_adapters() -> None:
    raw = {
        "cycle_id": "legacy-1",
        "ts": 1.0,
        "symbol": "XBTUSD",
        "venue": "kraken_spot",
        "world_state_fingerprint": "abc",
        "world_state": {},
        "mission": {"mission": "momentum_extraction"},
        "proposals": [],
        "selected_strategy": "microstructure_momentum",
        "parliament": {
            "selection_mode": "top_n",
            "selected_top": [{"strategy": "microstructure_momentum"}, {"strategy": "mean_reversion"}],
        },
        "execution_plan": {},
        "shield": {},
        "ops_snapshot": {},
        "meta": {"regime_cluster": "trend_quality"},
    }
    packet = DecisionPacket.from_mapping(raw)
    assert packet.parliament_mode == "top_n"
    assert packet.selected_strategies == ["microstructure_momentum", "mean_reversion"]
    assert packet.meta_intelligence["regime_cluster"] == "trend_quality"


def test_parliament_backward_compatible_top_n_mode_with_conflict_penalties() -> None:
    parliament = StrategyParliament(min_score=0.0)
    proposals = [
        StrategyProposal(
            strategy="microstructure_momentum",
            instrument="XBTUSD",
            action="trade",
            side="buy",
            target_notional_quote=120.0,
            expected_value_bps=16.0,
            confidence=0.85,
            expected_hold_time_s=45.0,
            execution_sensitivity=0.5,
            slippage_risk_bps=1.2,
            regime_compatibility=0.9,
            risk_cost_bps=1.0,
            correlation_group="trend_cluster",
        ),
        StrategyProposal(
            strategy="trend_breakout",
            instrument="XBTUSD",
            action="trade",
            side="buy",
            target_notional_quote=100.0,
            expected_value_bps=14.0,
            confidence=0.80,
            expected_hold_time_s=40.0,
            execution_sensitivity=0.5,
            slippage_risk_bps=1.3,
            regime_compatibility=0.9,
            risk_cost_bps=1.1,
            correlation_group="trend_cluster",
        ),
        StrategyProposal(
            strategy="mean_reversion",
            instrument="XBTUSD",
            action="trade",
            side="buy",
            target_notional_quote=80.0,
            expected_value_bps=9.0,
            confidence=0.72,
            expected_hold_time_s=60.0,
            execution_sensitivity=0.4,
            slippage_risk_bps=1.0,
            regime_compatibility=0.6,
            risk_cost_bps=1.0,
            correlation_group="",
        ),
    ]
    verdict = parliament.judge(
        proposals,
        world=_world(),
        mission=_mission(),
        selection_mode=PARLIAMENT_MODE_TOP_N,
        top_n=3,
        score_floor=0.0,
    )
    assert verdict.no_trade is False
    assert verdict.selection_mode == "top_n"
    assert len(verdict.selected_top) >= 2
    assert abs(sum(row.weight for row in verdict.allocations) - 1.0) < 1e-9
    trend_row = next(row for row in verdict.ranking if row.proposal.strategy == "microstructure_momentum")
    assert trend_row.diagnostics.get("correlation_penalty", 0.0) > 0.0
