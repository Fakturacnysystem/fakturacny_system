from __future__ import annotations

from autonomous_investment_robot.services.autonomous_decision.engine import DecisionContext
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.replay.events import MarketEvent, make_event
from autonomous_investment_robot.services.universe_core import (
    CrossAssetAllocator,
    EventFabric,
    MemoryEngine,
    MissionEngine,
    ResearchReplayLab,
    ShieldDecision,
    StrategyProposal,
    UniverseAllocationInput,
    UniverseMind,
    UniverseOpsService,
    WorldStateReadAdapter,
    WorldStateGraph,
    WorldStateStore,
    build_event,
    strategy_proposals_from_intent,
)


def _decision_context() -> DecisionContext:
    return DecisionContext(
        symbol="XBTUSD",
        now_ts=1_700_000_000.0,
        bid=100.0,
        ask=100.06,
        mid=100.03,
        spread_bps=6.0,
        depth_notional=20_000.0,
        features={
            "ret_1": 0.002,
            "ret_3": 0.006,
            "realized_vol": 0.008,
            "spread_proxy": 0.0006,
            "depth_notional": 20_000.0,
            "orderbook_imbalance": 0.42,
            "flow_imbalance": 0.38,
        },
        market_watch={
            "trend_30s_bps": 12.0,
            "trend_2m_bps": 58.0,
            "trend_10m_bps": 96.0,
            "realized_vol_2m": 0.008,
            "realized_vol_10m": 0.009,
            "confidence": 0.82,
        },
        forecast_mu=14.0,
        forecast_sigma=7.0,
        forecast_confidence=0.84,
        position_notional_quote=0.0,
        signed_exposure_notional_quote=0.0,
        avg_entry_price=0.0,
        position_age_s=0.0,
        current_profit_bps=0.0,
        drawdown_pct=0.01,
        quote_free=2_500.0,
        max_exposure_notional=5_000.0,
        order_cadence_s=5.0,
        last_submission_ts=1_699_999_000.0,
        fee_bps=10.0,
        slippage_bps=1.2,
        latency_ms=45.0,
        market_class="crypto_spot",
        guards_mode="strict",
        modeled_cost_floor_bps=30.0,
        sell_min_profit_bps=30.0,
        sell_target_profit_bps=60.0,
    )


def _intent() -> OrderIntent:
    return OrderIntent(
        symbol="XBTUSD",
        side="buy",
        target_notional=300.0,
        why={
            "components": [
                {
                    "strategy": "microstructure_momentum",
                    "signal_side": "buy",
                    "signal_notional": 240.0,
                    "final_edge_bps": 18.0,
                    "confidence": 0.82,
                    "cost_total_bps": 4.0,
                    "execution_sensitivity": 0.85,
                    "slippage_risk_bps": 1.8,
                    "regime_fit": 0.95,
                    "reason_codes": ["flow_up", "trend_confirmed"],
                },
                {
                    "strategy": "mean_reversion",
                    "signal_side": "buy",
                    "signal_notional": 180.0,
                    "final_edge_bps": 10.0,
                    "confidence": 0.78,
                    "cost_total_bps": 2.0,
                    "execution_sensitivity": 0.30,
                    "slippage_risk_bps": 1.0,
                    "regime_fit": 0.20,
                    "reason_codes": ["range_snapback"],
                },
            ]
        },
    )


def _healthy_world_snapshot():
    graph = WorldStateGraph()
    ctx = _decision_context()
    for event_type, payload in (
        (
            "MarketTickEvent",
            {"symbol": ctx.symbol, "venue": "kraken_spot", "mid": ctx.mid, "spread_bps": ctx.spread_bps, "trend_bps": ctx.market_watch["trend_2m_bps"], "realized_vol": ctx.features["realized_vol"]},
        ),
        (
            "BookSnapshotEvent",
            {"symbol": ctx.symbol, "venue": "kraken_spot", "spread_bps": ctx.spread_bps, "depth_notional": ctx.depth_notional},
        ),
        (
            "AccountSnapshotEvent",
            {"symbol": ctx.symbol, "venue": "kraken_spot", "equity_quote": ctx.quote_free, "free_quote": ctx.quote_free, "exposure_quote": 0.0, "drawdown_pct": ctx.drawdown_pct},
        ),
        (
            "HealthEvent",
            {"symbol": ctx.symbol, "venue": "kraken_spot", "status": "OK", "latency_ms": ctx.latency_ms, "health_score": 0.95, "rejection_ratio": 0.0, "stale_feed": False, "desync": False},
        ),
        (
            "RiskEvent",
            {"symbol": ctx.symbol, "venue": "kraken_spot", "model_confidence": ctx.forecast_confidence, "uncertainty_bps": ctx.forecast_sigma, "mode": "normal", "observe_only": False, "hard_stop": False},
        ),
        (
            "RegimeEvent",
            {"symbol": ctx.symbol, "venue": "kraken_spot", "regime": "TREND", "confidence": ctx.forecast_confidence, "volatility_regime": "LOW_VOL", "liquidity_regime": "DEEP", "expansion_state": "COMPRESSION", "panic": False},
        ),
    ):
        graph.apply(build_event(event_type=event_type, source="test", partition_key=ctx.symbol, payload=payload))
    return graph.snapshot()


def test_event_fabric_deduplicates_and_projects_world_state(tmp_path) -> None:
    fabric = EventFabric(str(tmp_path))
    first = fabric.emit(
        event_type="MarketTickEvent",
        source="test",
        partition_key="XBTUSD",
        payload={"symbol": "XBTUSD", "venue": "kraken_spot", "mid": 100.0, "spread_bps": 6.0, "trend_bps": 32.0, "realized_vol": 0.009},
        idempotency_key="tick-1",
    )
    second = fabric.emit(
        event_type="MarketTickEvent",
        source="test",
        partition_key="XBTUSD",
        payload={"symbol": "XBTUSD", "venue": "kraken_spot", "mid": 100.0, "spread_bps": 6.0, "trend_bps": 32.0, "realized_vol": 0.009},
        idempotency_key="tick-1",
    )
    regime = fabric.emit(
        event_type="RegimeEvent",
        source="test",
        partition_key="XBTUSD",
        payload={"symbol": "XBTUSD", "venue": "kraken_spot", "regime": "TREND", "confidence": 0.80, "volatility_regime": "LOW_VOL", "liquidity_regime": "DEEP", "expansion_state": "EXPANSION"},
    )
    assert first is not None
    assert second is None
    assert regime is not None

    graph = WorldStateGraph()
    graph.apply_all(fabric.replay())
    snap = graph.snapshot()
    assert len(fabric.replay()) == 2
    assert snap.market_state.regime == "TREND"
    assert snap.market_state.last_mid == 100.0
    assert snap.current_world_state.startswith("TREND")
    assert snap.confidence_score > 0.40


def test_world_state_read_adapter_snapshot_exposes_freshness_and_graph_state() -> None:
    adapter = WorldStateReadAdapter()
    snapshot = _healthy_world_snapshot()
    view = adapter.from_snapshot(snapshot, symbol="XBTUSD", max_age_s=30.0)
    payload = view.to_dict()
    assert payload["world_state_available"] is True
    assert payload["graph_available"] is True
    assert "market_state" in payload["freshness_s"]
    assert isinstance(payload["stale_domains"], list)


def test_world_state_read_adapter_runtime_observation_degrades_when_unhealthy() -> None:
    adapter = WorldStateReadAdapter()
    view = adapter.from_runtime_observation(
        symbol="XBTUSD",
        as_of_time=1_700_000_000.0,
        market_data_stale_s=90.0,
        ws_healthy=False,
        drawdown_pct=0.2,
        regime="PANIC",
        market_class="crypto_spot",
        max_age_s=30.0,
    )
    payload = view.to_dict()
    assert payload["world_state_available"] is False
    assert payload["graph_available"] is False
    assert payload["safe_to_trade"] is False
    assert "market_state" in payload["stale_critical_domains"]


def test_unified_event_envelope_contains_phase1_contract_fields() -> None:
    event = build_event(
        event_type="MarketTickEvent",
        source="unit_test",
        partition_key="XBTUSD",
        payload={"symbol": "XBTUSD", "venue": "kraken_spot", "mid": 100.0},
        correlation_id="corr-1",
        causation_id="cause-1",
        priority=3,
        producer="tester",
        tags={"suite": "phase1"},
    )
    payload = event.to_dict()
    required = {
        "event_id",
        "event_type",
        "event_domain",
        "schema_version",
        "source",
        "subject",
        "partition_key",
        "event_time",
        "observed_time",
        "processed_time",
        "correlation_id",
        "causation_id",
        "sequence_no",
        "priority",
        "is_replay",
        "is_snapshot",
        "is_synthetic",
        "producer",
        "trace_id",
        "tags",
        "payload",
    }
    assert required.issubset(payload.keys())
    assert payload["event_domain"] == "market"
    assert payload["schema_version"] == "v1"


def test_event_fabric_rejects_unknown_schema_and_records_dead_letter(tmp_path) -> None:
    fabric = EventFabric(str(tmp_path))
    rejected = fabric.emit(
        event_type="UnknownEventType",
        source="test",
        partition_key="XBTUSD",
        payload={"symbol": "XBTUSD", "venue": "kraken_spot"},
    )
    assert rejected is None
    metrics = fabric.metrics_snapshot()
    assert metrics["schema_reject_total"] >= 1
    dead_letter = tmp_path / "universe_event_dead_letter.jsonl"
    assert dead_letter.exists()
    text = dead_letter.read_text(encoding="utf-8")
    assert "schema_reject" in text


def test_event_fabric_wildcard_routing_handler_isolation_and_metrics(tmp_path) -> None:
    fabric = EventFabric(str(tmp_path))
    delivered: list[str] = []

    def ok_handler(event) -> None:
        delivered.append(event.event_type)

    def failing_handler(event) -> None:
        raise RuntimeError(f"boom:{event.event_type}")

    fabric.subscribe("market.*", ok_handler)
    fabric.subscribe("market.*", failing_handler)
    emitted = fabric.emit(
        event_type="MarketTickEvent",
        source="test",
        partition_key="XBTUSD",
        payload={"symbol": "XBTUSD", "venue": "kraken_spot", "mid": 100.0},
    )
    assert emitted is not None
    assert delivered == ["MarketTickEvent"]
    metrics = fabric.metrics_snapshot()
    assert metrics["handler_calls"] == 2
    assert metrics["handler_failures"] == 1
    assert metrics["dead_letter_total"] >= 1


def test_event_fabric_projection_seed_and_correlation_reconstruction(tmp_path) -> None:
    fabric = EventFabric(str(tmp_path))
    corr = "corr-123"
    for event_type, payload in (
        ("MarketTickEvent", {"symbol": "XBTUSD", "venue": "kraken_spot", "mid": 101.0}),
        ("RiskEvent", {"symbol": "XBTUSD", "venue": "kraken_spot", "mode": "normal"}),
        ("HealthEvent", {"symbol": "XBTUSD", "venue": "kraken_spot", "status": "OK"}),
    ):
        emitted = fabric.emit(
            event_type=event_type,
            source="test",
            partition_key="XBTUSD",
            payload=payload,
            correlation_id=corr,
        )
        assert emitted is not None

    traced = fabric.trace_correlation(corr)
    assert len(traced) == 3
    projection = fabric.projection_snapshot()
    assert "XBTUSD" in projection["market"]
    assert "XBTUSD" in projection["risk"]
    assert "XBTUSD" in projection["health"]


def test_event_fabric_ingests_legacy_replay_events_with_deterministic_dedup(tmp_path) -> None:
    fabric = EventFabric(str(tmp_path))
    legacy = make_event(
        MarketEvent,
        "MarketEvent",
        "XBTUSD",
        "kraken_spot",
        7,
        {"mid": 101.5, "spread_bps": 6.2, "realized_vol": 0.009},
    )
    first = fabric.ingest_legacy_event(legacy, source="legacy_replay")
    second = fabric.ingest_legacy_event(legacy, source="legacy_replay")
    assert first is not None
    assert second is None
    assert first.event_type == "MarketTickEvent"
    assert first.payload["symbol"] == "XBTUSD"
    assert first.payload["venue"] == "kraken_spot"
    assert len(fabric.replay()) == 1


def test_event_fabric_ingests_legacy_intent_mapping_as_strategy_proposal(tmp_path) -> None:
    fabric = EventFabric(str(tmp_path))
    events = fabric.ingest_legacy_events(
        [
            {
                "event_type": "OrderIntentEvent",
                "symbol": "XBTUSD",
                "venue": "kraken_spot",
                "seq": 3,
                "payload": {
                    "signal_side": "buy",
                    "target_notional": 42.0,
                },
            }
        ],
        source="legacy_replay",
    )
    assert len(events) == 1
    assert events[0].event_type == "StrategyProposalEvent"
    assert events[0].payload["strategy"] == "legacy_intent"
    assert events[0].payload["side"] == "buy"
    assert events[0].payload["target_notional_quote"] == 42.0


def test_event_fabric_legacy_adapter_rejects_unreadable_payload_with_dead_letter(tmp_path) -> None:
    fabric = EventFabric(str(tmp_path))
    rejected = fabric.ingest_legacy_event(42, source="legacy_replay")
    assert rejected is None
    metrics = fabric.metrics_snapshot()
    assert metrics["rejected_total"] >= 1
    dead_letter = tmp_path / "universe_event_dead_letter.jsonl"
    assert dead_letter.exists()
    text = dead_letter.read_text(encoding="utf-8")
    assert "legacy_adapter_reject" in text


def test_strategy_proposals_from_intent_prefers_serialized_contract_payload() -> None:
    intent = OrderIntent(
        symbol="XBTUSD",
        side="buy",
        target_notional=99.0,
        why={
            "strategy_proposals": [
                {
                    "strategy": "serialized_momentum",
                    "instrument": "XBTUSD",
                    "action": "trade",
                    "side": "buy",
                    "target_notional_quote": 12.5,
                    "expected_value_bps": 9.0,
                    "confidence": 0.77,
                    "expected_hold_time_s": 30.0,
                    "execution_sensitivity": 0.5,
                    "slippage_risk_bps": 1.0,
                    "regime_compatibility": 0.9,
                    "risk_cost_bps": 1.5,
                    "source": "legacy_policy_adapter",
                }
            ],
            "components": [
                {
                    "strategy": "component_should_not_override_serialized",
                    "signal_side": "sell",
                    "signal_notional": 20.0,
                }
            ],
        },
    )
    rows_a = strategy_proposals_from_intent(intent, mission="momentum_extraction")
    rows_b = strategy_proposals_from_intent(intent, mission="momentum_extraction")

    payload_a = [row.to_dict() for row in rows_a]
    payload_b = [row.to_dict() for row in rows_b]
    assert payload_a == payload_b
    assert payload_a[0]["strategy"] == "serialized_momentum"
    assert payload_a[0]["source"] == "legacy_policy_adapter"
    assert payload_a[0]["target_notional_quote"] == 12.5
    assert any(row["strategy"] == "no_trade_guardian" for row in payload_a)


def test_universe_mind_cycle_from_context_and_intent_generates_plan(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    mind.ingest_decision_context(_decision_context(), venue="kraken_spot")
    result = mind.run_cycle_from_intent(
        _intent(),
        venue="kraken_spot",
        cross_asset_inputs=[
            UniverseAllocationInput(
                universe_id="crypto_spot",
                market_class="crypto_spot",
                edge_score=0.85,
                regime_fit=0.90,
                execution_quality=0.88,
                telemetry_health=0.95,
            ),
            UniverseAllocationInput(
                universe_id="fx_majors",
                market_class="fx",
                edge_score=0.45,
                regime_fit=0.70,
                execution_quality=0.82,
                telemetry_health=0.90,
            ),
        ],
    )
    assert result.mission.mission == "momentum_extraction"
    assert result.parliament.no_trade is False
    assert result.parliament.selected.strategy == "microstructure_momentum"
    assert result.execution_plan.actionable is True
    assert result.execution_plan.maker_taker == "taker"
    assert result.shield.approved is True
    assert result.decision_packet.selected_strategy == "microstructure_momentum"
    assert {event.event_type for event in result.published_events} >= {"MissionEvent", "StrategyProposalEvent", "ExecutionPlanEvent", "RiskEvent"}
    assert len(result.allocations) == 2
    assert abs(sum(row.weight for row in result.allocations) - 1.0) < 1e-9
    assert max(result.allocations, key=lambda row: row.weight).universe_id == "crypto_spot"
    assert result.world_state.strategy_state.last_mission == "momentum_extraction"
    assert result.world_state.strategy_state.selected_strategy_summary["strategy"] == "microstructure_momentum"
    assert result.ops_snapshot is not None
    assert result.ops_snapshot.world_state_available is True
    assert result.ops_snapshot.primary_symbol_state["symbol"] == "XBTUSD"


def test_universe_mind_shield_blocks_on_stale_feed_and_stress(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    symbol = "XBTUSD"
    mind.emit(
        event_type="MarketTickEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "mid": 99.5, "spread_bps": 55.0, "trend_bps": -40.0, "realized_vol": 0.035},
    )
    mind.emit(
        event_type="BookSnapshotEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "spread_bps": 55.0, "depth_notional": 500.0},
    )
    mind.emit(
        event_type="AccountSnapshotEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "equity_quote": 800.0, "free_quote": 120.0, "exposure_quote": 650.0, "drawdown_pct": 0.14},
    )
    mind.emit(
        event_type="HealthEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "status": "WARN", "latency_ms": 900.0, "health_score": 0.15, "rejection_ratio": 0.45, "stale_feed": True, "desync": True},
    )
    mind.emit(
        event_type="RiskEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "model_confidence": 0.20, "uncertainty_bps": 180.0, "mode": "defensive", "observe_only": True, "hard_stop": False},
    )
    mind.emit(
        event_type="RegimeEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "regime": "PANIC", "confidence": 0.30, "volatility_regime": "HIGH_VOL", "liquidity_regime": "THIN", "expansion_state": "EXPANSION", "panic": True},
    )
    result = mind.run_cycle(
        symbol=symbol,
        venue="kraken_spot",
        proposals=[
            StrategyProposal(
                strategy="microstructure_momentum",
                instrument=symbol,
                action="trade",
                side="buy",
                target_notional_quote=150.0,
                expected_value_bps=14.0,
                confidence=0.75,
                expected_hold_time_s=45.0,
                execution_sensitivity=0.90,
                slippage_risk_bps=5.0,
                regime_compatibility=0.80,
                risk_cost_bps=3.0,
                reason_codes=["attempt_buy"],
            )
        ],
    )
    assert result.mission.mission == "observation_only"
    assert result.shield.approved is False
    assert result.shield.mode == "observe_only"
    assert result.execution_plan.actionable is False
    assert result.decision_packet.execution_plan["order_type"] == "none"


def test_memory_research_and_ops_promote_only_to_limited_live(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    world_state = _healthy_world_snapshot().to_dict()
    packets = []
    for idx in range(12):
        packet = memory.build_packet(
            symbol="XBTUSD",
            venue="kraken_spot",
            world_state=world_state,
            mission={"mission": "momentum_extraction", "confidence": 0.82},
            proposals=[{"strategy": "microstructure_momentum", "expected_value_bps": 12.0}],
            selected_strategy="microstructure_momentum",
            parliament={"selected": {"strategy": "microstructure_momentum"}},
            execution_plan={"target_notional_quote": 120.0},
            shield={"mode": "normal", "approved": True},
            ops_snapshot={"rollout_stage": "paper"},
            cycle_id=f"cycle-{idx}",
        )
        memory.record(packet)
        packets.append(
            memory.grade(
                packet,
                realized_pnl_quote=8.0 if idx < 10 else 2.0,
                realized_slippage_bps=2.0,
                realized_regime="TREND",
                fill_ratio=0.92,
            )
        )

    graded = memory.load(graded=True)
    summary = memory.aggregate_performance(graded)
    assert summary["total_records"] == 12
    assert summary["win_rate"] == 1.0

    research = ResearchReplayLab().assess(graded)
    assert research.current_stage == "limited_live"
    assert research.next_stage == "scaled_live"
    assert research.ready_to_promote is True

    allocations = CrossAssetAllocator().allocate(
        [
            UniverseAllocationInput("crypto_spot", "crypto_spot", 0.80, 0.90, 0.85, 0.95),
            UniverseAllocationInput("index_futures", "futures", 0.50, 0.70, 0.80, 0.90),
        ]
    )
    ops = UniverseOpsService().assess(
        world=_healthy_world_snapshot(),
        shield=ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=["normal"], kill_switch=False),
        research=research,
        allocations=allocations,
    )
    assert ops.rollout_stage == "blocked"
    assert ops.manual_gate_required is True
    assert ops.rollout_governance["decision"]["candidate_stage"] == "limited_live_ready"
    assert ops.readiness_score > 0.70
    assert ops.world_state_available is True
    assert ops.world_state_summary["market"]["regime"] == "TREND"
    assert ops.primary_symbol_state["symbol"] == "XBTUSD"


def test_world_state_store_builds_domains_and_symbol_queries() -> None:
    ctx = _decision_context()
    store = WorldStateStore()
    store.apply_market_update(
        symbol=ctx.symbol,
        venue="kraken_spot",
        payload={"mid": ctx.mid, "spread_bps": ctx.spread_bps, "trend_bps": ctx.market_watch["trend_2m_bps"], "realized_vol": ctx.features["realized_vol"]},
        ts=100.0,
    )
    store.apply_market_update(
        symbol=ctx.symbol,
        venue="kraken_spot",
        event_type="BookSnapshotEvent",
        payload={"spread_bps": ctx.spread_bps, "depth_notional": ctx.depth_notional, "levels": 10},
        ts=101.0,
    )
    store.apply_account_update(
        symbol=ctx.symbol,
        venue="kraken_spot",
        payload={"equity_quote": ctx.quote_free, "free_quote": ctx.quote_free, "exposure_quote": 120.0, "position_notional_quote": 120.0, "drawdown_pct": ctx.drawdown_pct},
        ts=102.0,
    )
    store.apply_execution_update(
        symbol=ctx.symbol,
        venue="kraken_spot",
        event_type="OrderEvent",
        payload={"open_orders": 2, "order_type": "post_only", "side": "buy", "queue_quality": 0.88, "rejection_ratio": 0.10},
        ts=103.0,
    )
    store.apply_execution_update(
        symbol=ctx.symbol,
        venue="kraken_spot",
        event_type="FillEvent",
        payload={"fill_ratio": 0.92, "slippage_bps": 1.4, "fill_probability": 0.90, "latency_ms": 45.0},
        ts=104.0,
    )
    store.apply_risk_update(
        symbol=ctx.symbol,
        venue="kraken_spot",
        payload={"mode": "normal", "model_confidence": ctx.forecast_confidence, "uncertainty_bps": ctx.forecast_sigma, "hard_stop": False, "observe_only": False},
        ts=105.0,
    )
    store.apply_telemetry_update(
        symbol=ctx.symbol,
        venue="kraken_spot",
        payload={"status": "OK", "health_score": 0.96, "latency_ms": 42.0, "stale_feed": False, "desync": False},
        ts=106.0,
    )
    store.apply_strategy_update(
        symbol=ctx.symbol,
        venue="kraken_spot",
        event_type="MissionEvent",
        payload={"mission": "momentum_extraction", "rationale": ["trend_confirmed"]},
        ts=107.0,
    )

    world = store.get_world_state()
    symbol_state = store.get_symbol_state(ctx.symbol)

    assert world.market_state.primary_symbol == ctx.symbol
    assert world.venue_state.primary_venue == "kraken_spot"
    assert world.asset_state.primary_symbol == ctx.symbol
    assert world.portfolio_state.positions[ctx.symbol].position_notional_quote == 120.0
    assert world.execution_state.open_orders_total == 2
    assert world.risk_state.mode == "normal"
    assert world.infra_state.health_status == "OK"
    assert world.strategy_state.last_mission == "momentum_extraction"
    assert symbol_state.market is not None
    assert symbol_state.market.depth_notional == ctx.depth_notional
    assert symbol_state.execution is not None
    assert symbol_state.execution.fill_ratio == 0.92
    assert symbol_state.asset is not None
    assert symbol_state.asset.allow_trade is True


def test_world_state_partial_updates_do_not_corrupt_unrelated_domains() -> None:
    graph = WorldStateGraph()
    graph.apply(
        build_event(
            event_type="MarketTickEvent",
            source="test",
            partition_key="XBTUSD",
            payload={"symbol": "XBTUSD", "venue": "kraken_spot", "mid": 101.0, "spread_bps": 7.0, "trend_bps": 22.0, "realized_vol": 0.007},
            ts=10.0,
        )
    )
    graph.apply(
        build_event(
            event_type="AccountSnapshotEvent",
            source="test",
            partition_key="XBTUSD",
            payload={"symbol": "XBTUSD", "venue": "kraken_spot", "equity_quote": 2_000.0, "free_quote": 1_700.0, "exposure_quote": 150.0, "drawdown_pct": 0.02},
            ts=11.0,
        )
    )
    before = graph.snapshot()

    graph.apply(
        build_event(
            event_type="RiskEvent",
            source="test",
            partition_key="XBTUSD",
            payload={"symbol": "XBTUSD", "venue": "kraken_spot", "mode": "defensive", "model_confidence": 0.55, "uncertainty_bps": 20.0, "observe_only": True, "hard_stop": False},
            ts=12.0,
        )
    )
    after = graph.snapshot()

    assert after.market_state.last_mid == before.market_state.last_mid
    assert after.portfolio_state.free_quote == before.portfolio_state.free_quote
    assert after.risk_state.mode == "defensive"
    assert after.asset_state.assets["XBTUSD"].allow_trade is False


def test_world_state_freshness_and_serialization_export() -> None:
    store = WorldStateStore()
    store.apply_market_update(
        symbol="XBTUSD",
        venue="kraken_spot",
        payload={"mid": 100.0, "spread_bps": 5.0, "trend_bps": 18.0, "realized_vol": 0.004},
        ts=100.0,
    )
    store.apply_account_update(
        symbol="XBTUSD",
        venue="kraken_spot",
        payload={"equity_quote": 1_500.0, "free_quote": 1_250.0, "exposure_quote": 100.0, "drawdown_pct": 0.01},
        ts=110.0,
    )

    world = store.get_world_state()
    payload = world.to_dict()
    summary = store.export_summary()

    assert world.as_of_time == 110.0
    assert summary["world_state_as_of"] == 110.0
    assert summary["freshness_s"]["market_state"] == 10.0
    assert payload["asset_state"]["assets"]["XBTUSD"]["symbol"] == "XBTUSD"
    assert payload["summary"]["portfolio"]["free_quote"] == 1_250.0
    assert payload["metadata"]["version"].startswith("world_state_graph:")


def test_world_state_stale_domain_detection_and_safe_to_trade_gate() -> None:
    store = WorldStateStore()
    store.apply_market_update(
        symbol="XBTUSD",
        venue="kraken_spot",
        payload={"mid": 100.0, "spread_bps": 5.0, "trend_bps": 18.0, "realized_vol": 0.004},
        ts=100.0,
    )
    store.apply_account_update(
        symbol="XBTUSD",
        venue="kraken_spot",
        payload={"equity_quote": 1_500.0, "free_quote": 1_250.0, "exposure_quote": 100.0, "drawdown_pct": 0.01},
        ts=160.0,
    )
    store.apply_risk_update(
        symbol="XBTUSD",
        venue="kraken_spot",
        payload={"mode": "normal", "model_confidence": 0.8, "uncertainty_bps": 10.0, "observe_only": False, "hard_stop": False},
        ts=160.0,
    )
    store.apply_telemetry_update(
        symbol="XBTUSD",
        venue="kraken_spot",
        payload={"status": "OK", "health_score": 0.95, "latency_ms": 35.0, "stale_feed": False, "desync": False},
        ts=160.0,
    )
    world = store.get_world_state()
    stale = world.stale_domains(max_age_s=30.0)
    assert "market_state" in stale
    assert world.safe_to_trade(max_age_s=30.0) is False


def test_universe_mind_projection_failure_degrades_safely(tmp_path) -> None:
    class BrokenProjectionGraph(WorldStateGraph):
        def apply(self, event) -> None:  # type: ignore[override]
            raise RuntimeError("projection_broken")

    mind = UniverseMind(str(tmp_path), graph=BrokenProjectionGraph())
    emitted = mind.emit(
        event_type="MarketTickEvent",
        source="test",
        partition_key="XBTUSD",
        payload={"symbol": "XBTUSD", "venue": "kraken_spot", "mid": 100.0, "spread_bps": 5.0, "trend_bps": 20.0, "realized_vol": 0.005},
    )
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot")

    assert emitted is not None
    assert result.world_state.metadata.graph_available is False
    assert "projection_failed" in result.world_state.metadata.last_error
    assert result.execution_plan.actionable is False


def test_mission_contract_serialization_contains_policy_and_transition_fields() -> None:
    world = _healthy_world_snapshot()
    engine = MissionEngine()
    decision = engine.choose(world, previous_mission="low_risk_accumulation")
    payload = decision.to_dict()

    assert payload["mission"] == "momentum_extraction"
    assert payload["mission_type"] == "momentum_extraction"
    assert isinstance(payload["reason_codes"], list)
    assert isinstance(payload["allowed_strategy_families"], list)
    assert "execution_posture_hint" in payload
    assert "shield_posture_hint" in payload
    assert "transition_summary" in payload
    assert payload["transition_summary"]["changed"] is True
    assert payload["expected_duration"] == payload["duration_hint_s"]
    assert payload["aggressiveness_hint"] == payload["aggressiveness_tier"]
    assert payload["no_trade_preference"] == payload["no_trade_preferred"]
    assert payload["fallback_flag"] == payload["is_conservative_fallback"]


def test_mission_engine_selects_inventory_unwind_when_inventory_pressure_dominates() -> None:
    world = _healthy_world_snapshot()
    world.market_state.regime = "RANGE"
    world.portfolio_state.exposure_ratio = 0.82
    world.portfolio_state.inventory_pressure = 0.91

    decision = MissionEngine().choose(world, previous_mission="momentum_extraction")

    assert decision.mission == "inventory_unwind"
    assert "inventory_pressure" in decision.reason_codes


def test_mission_engine_falls_back_conservatively_on_internal_error() -> None:
    class BrokenMissionEngine(MissionEngine):
        def build_context(self, world):  # type: ignore[override]
            raise RuntimeError("boom")

    decision = BrokenMissionEngine().choose(_healthy_world_snapshot(), previous_mission="momentum_extraction")
    payload = decision.to_dict()

    assert decision.mission == "observation_only"
    assert decision.is_conservative_fallback is True
    assert "mission_engine_failure" in payload["reason_codes"]


def test_mission_engine_selects_observation_only_on_low_confidence() -> None:
    world = _healthy_world_snapshot()
    world.risk_state.model_confidence = 0.05
    world.infra_state.system_health_stress = 0.0
    world.execution_state.execution_stress = 0.05
    world.portfolio_state.own_account_stress = 0.15

    decision = MissionEngine().choose(world, previous_mission="momentum_extraction")

    assert decision.mission == "observation_only"
    assert "confidence_soft" in decision.reason_codes


def test_universe_mind_packet_and_ops_include_mission_diagnostics(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    mind.ingest_decision_context(_decision_context(), venue="kraken_spot")
    result = mind.run_cycle_from_intent(_intent(), venue="kraken_spot")

    mission_payload = result.decision_packet.mission
    assert mission_payload["mission"] == result.mission.mission
    assert "allowed_strategy_families" in mission_payload
    assert "execution_posture_hint" in mission_payload
    assert result.ops_snapshot is not None
    assert result.ops_snapshot.mission_selected == result.mission.mission
    assert result.ops_snapshot.execution_posture_hint == result.mission.execution_posture_hint


def test_mission_policy_reduces_buy_aggression_in_preserve_capital_mode(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    symbol = "XBTUSD"
    mind.emit(
        event_type="MarketTickEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "mid": 100.0, "spread_bps": 9.0, "trend_bps": 4.0, "realized_vol": 0.006},
    )
    mind.emit(
        event_type="BookSnapshotEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "spread_bps": 9.0, "depth_notional": 10_000.0},
    )
    mind.emit(
        event_type="AccountSnapshotEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "equity_quote": 1_000.0, "free_quote": 80.0, "exposure_quote": 620.0, "drawdown_pct": 0.03},
    )
    mind.emit(
        event_type="HealthEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "status": "OK", "latency_ms": 55.0, "health_score": 0.95, "rejection_ratio": 0.02, "stale_feed": False, "desync": False},
    )
    mind.emit(
        event_type="RiskEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "model_confidence": 0.55, "uncertainty_bps": 20.0, "mode": "normal", "observe_only": False, "hard_stop": False},
    )
    mind.emit(
        event_type="RegimeEvent",
        source="test",
        partition_key=symbol,
        payload={"symbol": symbol, "venue": "kraken_spot", "regime": "RANGE", "confidence": 0.60, "volatility_regime": "LOW_VOL", "liquidity_regime": "NORMAL", "expansion_state": "COMPRESSION", "panic": False},
    )

    result = mind.run_cycle(
        symbol=symbol,
        venue="kraken_spot",
        proposals=[
            StrategyProposal(
                strategy="microstructure_momentum",
                instrument=symbol,
                action="trade",
                side="buy",
                target_notional_quote=180.0,
                expected_value_bps=20.0,
                confidence=0.82,
                expected_hold_time_s=45.0,
                execution_sensitivity=0.70,
                slippage_risk_bps=2.0,
                regime_compatibility=0.40,
                risk_cost_bps=4.0,
                reason_codes=["candidate_buy"],
            )
        ],
    )

    assert result.mission.mission == "preserve_capital"
    buy_rows = [row for row in result.decision_packet.proposals if row.get("strategy") == "microstructure_momentum"]
    assert buy_rows
    buy_row = buy_rows[0]
    assert float(buy_row.get("mission_compatibility", 1.0)) <= 0.10
    assert "mission_blocks_new_risk_buy" in buy_row.get("reason_codes", [])
