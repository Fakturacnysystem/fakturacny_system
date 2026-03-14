from __future__ import annotations

from autonomous_investment_robot.services.universe_core import (
    DecisionFingerprint,
    MemoryEngine,
    OutcomeGrade,
    StrategyProposal,
    UniverseMind,
)


def _world_state() -> dict[str, object]:
    return {
        "current_world_state": "TREND_LOW_VOL_NORMAL_LIQUIDITY",
        "portfolio": {"drawdown_pct": 0.01},
    }


def _packet(memory: MemoryEngine, *, cycle_id: str, strategy: str = "microstructure_momentum", shield_mode: str = "normal"):
    packet = memory.build_packet(
        symbol="XBTUSD",
        venue="kraken_spot",
        world_state=_world_state(),
        mission={"mission": "momentum_extraction", "confidence": 0.82, "reason_codes": ["trend_confirmed"]},
        proposals=[
            {
                "strategy": strategy,
                "expected_value_bps": 12.0,
                "confidence": 0.80,
            }
        ],
        selected_strategy=strategy,
        selected_strategies=[strategy],
        parliament_mode="top_1",
        parliament_no_trade=False,
        parliament={"diagnostics": {"best_score": 12.0}, "reasons": ["selected_best"]},
        execution_plan={
            "target_notional_quote": 120.0,
            "actionable": True,
            "order_type": "limit",
            "side": "buy",
            "maker_taker": "maker",
            "urgency": "normal",
        },
        shield={
            "mode": shield_mode,
            "shield_mode": shield_mode,
            "approved": True,
            "reason_codes": ["normal"],
            "escalation_reason_codes": ["normal"],
            "strategy_health_summary": {"strategy_health_score": 0.8},
        },
        ops_snapshot={"rollout_stage": "paper"},
        meta_intelligence={
            "regime_cluster": "trend_quality",
            "risk_scale": 1.0,
            "strategy_weights": [{"strategy": strategy, "total_weight": 1.0}],
        },
        cycle_id=cycle_id,
    )
    return packet


def _seed_world(mind: UniverseMind, *, symbol: str = "XBTUSD") -> None:
    for event_type, payload in (
        (
            "MarketTickEvent",
            {"symbol": symbol, "venue": "kraken_spot", "mid": 100.0, "spread_bps": 6.0, "trend_bps": 52.0, "realized_vol": 0.008},
        ),
        (
            "BookSnapshotEvent",
            {"symbol": symbol, "venue": "kraken_spot", "spread_bps": 6.0, "depth_notional": 16_000.0},
        ),
        (
            "AccountSnapshotEvent",
            {"symbol": symbol, "venue": "kraken_spot", "equity_quote": 2_500.0, "free_quote": 2_000.0, "exposure_quote": 150.0, "drawdown_pct": 0.01},
        ),
        (
            "HealthEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "status": "OK",
                "latency_ms": 45.0,
                "health_score": 0.95,
                "rejection_ratio": 0.02,
                "stale_feed": False,
                "desync": False,
            },
        ),
        (
            "RiskEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "mode": "normal",
                "model_confidence": 0.84,
                "uncertainty_bps": 7.0,
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
                "volatility_regime": "LOW_VOL",
                "liquidity_regime": "DEEP",
                "expansion_state": "COMPRESSION",
                "panic": False,
            },
        ),
    ):
        mind.emit(event_type=event_type, source="test", partition_key=symbol, payload=payload)


def test_phase7_decision_memory_record_serialization(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packet = _packet(memory, cycle_id="c-1")
    record = memory.build_decision_memory_record(packet)
    roundtrip = record.from_mapping(record.to_dict())
    assert roundtrip.to_dict() == record.to_dict()


def test_phase7_stable_decision_fingerprint_generation(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packet = _packet(memory, cycle_id="fp-1")
    fp_a = DecisionFingerprint.from_packet(packet)
    fp_b = DecisionFingerprint.from_packet(packet)
    assert fp_a.to_dict() == fp_b.to_dict()


def test_phase7_outcome_grading_positive_case(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packet = _packet(memory, cycle_id="g-pos")
    graded = memory.grade(packet, realized_pnl_quote=3.2, realized_slippage_bps=1.2, realized_regime="TREND", fill_ratio=0.95)
    assert graded.evaluation["outcome_grade"] == OutcomeGrade.POSITIVE.value


def test_phase7_outcome_grading_neutral_case(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packet = _packet(memory, cycle_id="g-neu")
    graded = memory.grade(packet, realized_pnl_quote=0.0, realized_slippage_bps=1.0, realized_regime="RANGE", fill_ratio=0.90)
    assert graded.evaluation["outcome_grade"] == OutcomeGrade.NEUTRAL.value


def test_phase7_outcome_grading_negative_case(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packet = _packet(memory, cycle_id="g-neg")
    graded = memory.grade(packet, realized_pnl_quote=-1.0, realized_slippage_bps=2.5, realized_regime="TREND", fill_ratio=0.85)
    assert graded.evaluation["outcome_grade"] in {OutcomeGrade.NEGATIVE.value, OutcomeGrade.SEVERE_NEGATIVE.value}


def test_phase7_outcome_grading_severe_negative_case(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packet = _packet(memory, cycle_id="g-sev", shield_mode="hard_stop")
    graded = memory.grade(packet, realized_pnl_quote=-12.0, realized_slippage_bps=18.0, realized_regime="PANIC", fill_ratio=0.40)
    assert graded.evaluation["outcome_grade"] == OutcomeGrade.SEVERE_NEGATIVE.value


def test_phase7_shield_aware_grading_penalizes_escalated_modes(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    normal = memory.grade(_packet(memory, cycle_id="s-normal", shield_mode="normal"), realized_pnl_quote=1.0, realized_slippage_bps=2.0, realized_regime="TREND")
    defensive = memory.grade(_packet(memory, cycle_id="s-def", shield_mode="defensive"), realized_pnl_quote=1.0, realized_slippage_bps=2.0, realized_regime="TREND")
    assert float(normal.evaluation["risk_adjusted_score"]) > float(defensive.evaluation["risk_adjusted_score"])


def test_phase7_promotion_gate_requires_sufficient_evidence(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path), min_policy_samples=6)
    for idx in range(5):
        packet = _packet(memory, cycle_id=f"prom-{idx}")
        memory.record(packet)
        memory.grade(packet, realized_pnl_quote=2.0, realized_slippage_bps=1.0, realized_regime="TREND")
    pre = memory.learning_snapshot()
    assert pre.promotion_candidates_count == 0
    packet = _packet(memory, cycle_id="prom-5")
    memory.record(packet)
    memory.grade(packet, realized_pnl_quote=2.2, realized_slippage_bps=1.0, realized_regime="TREND")
    post = memory.learning_snapshot()
    assert post.promotion_candidates_count >= 1


def test_phase7_demotion_and_retirement_gates(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path), min_policy_samples=6)
    for idx in range(6):
        packet = _packet(memory, cycle_id=f"dem-{idx}", strategy="mean_reversion", shield_mode="defensive")
        memory.record(packet)
        memory.grade(packet, realized_pnl_quote=-2.5, realized_slippage_bps=8.0, realized_regime="RANGE")
    demotion_snapshot = memory.learning_snapshot()
    assert demotion_snapshot.demotion_candidates_count >= 1

    for idx in range(6):
        packet = _packet(memory, cycle_id=f"ret-{idx}", strategy="breakout_continuation", shield_mode="hard_stop")
        memory.record(packet)
        memory.grade(packet, realized_pnl_quote=-15.0, realized_slippage_bps=22.0, realized_regime="PANIC")
    retirement_snapshot = memory.learning_snapshot()
    assert retirement_snapshot.retirement_candidates_count >= 1


def test_phase7_bounded_memory_compaction(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path), max_records=20)
    for idx in range(60):
        packet = _packet(memory, cycle_id=f"cap-{idx}")
        memory.record(packet)
    records = memory.load_memory_records()
    snapshot = memory.learning_snapshot()
    assert len(records) <= 20
    assert snapshot.bounded_retention_health["within_limit"] is True


def test_phase7_deterministic_replay_grading_same_inputs(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packet = _packet(memory, cycle_id="det-1", shield_mode="cautious")
    graded_a = memory.grade(packet, realized_pnl_quote=1.3, realized_slippage_bps=2.0, realized_regime="TREND")
    graded_b = memory.grade(packet, realized_pnl_quote=1.3, realized_slippage_bps=2.0, realized_regime="TREND")
    assert graded_a.evaluation["outcome_grade"] == graded_b.evaluation["outcome_grade"]
    assert graded_a.evaluation["risk_adjusted_score"] == graded_b.evaluation["risk_adjusted_score"]


def test_phase7_universe_mind_integration_enriches_learning_summary(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind)
    result = mind.run_cycle(
        symbol="XBTUSD",
        venue="kraken_spot",
        proposals=[
            StrategyProposal(
                strategy="microstructure_momentum",
                instrument="XBTUSD",
                action="trade",
                side="buy",
                target_notional_quote=150.0,
                expected_value_bps=12.0,
                confidence=0.80,
                expected_hold_time_s=40.0,
                execution_sensitivity=0.6,
                slippage_risk_bps=1.4,
                regime_compatibility=0.9,
                risk_cost_bps=1.0,
            )
        ],
    )
    assert result.ops_snapshot is not None
    assert result.ops_snapshot.memory_records_written == 1
    assert isinstance(result.ops_snapshot.grading_state_summary, dict)
    assert "learning_summary" in result.decision_packet.evaluation
    learning_summary = result.decision_packet.evaluation.get("learning_summary", {})
    assert isinstance(learning_summary, dict)
    assert "bounded_retention_health" in learning_summary
    assert "memory_compaction_summary" in learning_summary
    assert "shield_aware_learning_summary" in learning_summary
    assert "errors" in learning_summary
    assert mind.memory.load_memory_records()


def test_phase7_fallback_when_memory_store_unavailable(tmp_path) -> None:
    class BrokenMemoryEngine(MemoryEngine):
        def record(self, packet):  # type: ignore[override]
            raise RuntimeError("store_down")

        def learning_snapshot(self):  # type: ignore[override]
            raise RuntimeError("snapshot_down")

    mind = UniverseMind(str(tmp_path), memory=BrokenMemoryEngine(str(tmp_path)))
    _seed_world(mind)
    result = mind.run_cycle(
        symbol="XBTUSD",
        venue="kraken_spot",
        proposals=[
            StrategyProposal(
                strategy="microstructure_momentum",
                instrument="XBTUSD",
                action="trade",
                side="buy",
                target_notional_quote=150.0,
                expected_value_bps=12.0,
                confidence=0.80,
                expected_hold_time_s=40.0,
                execution_sensitivity=0.6,
                slippage_risk_bps=1.4,
                regime_compatibility=0.9,
                risk_cost_bps=1.0,
            )
        ],
    )
    assert result.ops_snapshot is not None
    assert result.ops_snapshot.memory_records_written == 0
    assert result.ops_snapshot.bounded_retention_health.get("status") == "degraded"
    learning_summary = result.decision_packet.evaluation.get("learning_summary", {})
    assert isinstance(learning_summary, dict)
    assert "bounded_retention_health" in learning_summary
    assert "memory_compaction_summary" in learning_summary
    assert "shield_aware_learning_summary" in learning_summary
    assert "errors" in learning_summary
