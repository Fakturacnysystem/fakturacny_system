from __future__ import annotations

from autonomous_investment_robot.services.universe_core import (
    AdaptiveActivationGate,
    MemoryEngine,
    PromotionDecision,
    PromotionLadderEngine,
    PromotionStage,
    ReplayLadderEngine,
    ReplayRetentionPolicy,
    StrategyProposal,
    StrategyReplayGrade,
    UniverseMind,
)


def _world_state(*, regime: str = "TREND", liquidity: str = "DEEP", volatility: str = "LOW_VOL", drawdown_pct: float = 0.01) -> dict[str, object]:
    return {
        "market_state": {
            "regime": regime,
            "liquidity_regime": liquidity,
            "volatility_regime": volatility,
            "spread_bps": 6.0,
            "depth_notional": 20_000.0,
        },
        "portfolio_state": {
            "drawdown_pct": drawdown_pct,
            "unrealized_pnl_quote": 0.4,
            "equity_quote": 2_500.0,
            "concentration_score": 0.20,
        },
    }


def _packet(
    memory: MemoryEngine,
    *,
    cycle_id: str,
    strategy: str = "microstructure_momentum",
    mission: str = "momentum_extraction",
    pnl: float = 1.0,
    slippage: float = 1.2,
    regime: str = "TREND",
    liquidity: str = "DEEP",
    volatility: str = "LOW_VOL",
    drawdown_pct: float = 0.01,
    shield_mode: str = "normal",
):
    packet = memory.build_packet(
        symbol="XBTUSD",
        venue="kraken_spot",
        world_state=_world_state(regime=regime, liquidity=liquidity, volatility=volatility, drawdown_pct=drawdown_pct),
        mission={"mission": mission, "confidence": 0.82, "reason_codes": ["test"]},
        proposals=[
            {
                "strategy": strategy,
                "expected_value_bps": 12.0,
                "confidence": 0.8,
                "expected_hold_time_s": 45.0,
            }
        ],
        selected_strategy=strategy,
        selected_strategies=[strategy],
        parliament_mode="top_1",
        parliament_no_trade=False,
        parliament={"diagnostics": {"best_score": 12.0}, "selected_top": [{"strategy": strategy, "expected_value_bps": 12.0, "confidence": 0.8}]},
        execution_plan={
            "target_notional_quote": 180.0,
            "actionable": True,
            "order_type": "limit",
            "side": "buy",
            "maker_taker": "maker",
            "urgency_tier": "normal",
        },
        shield={
            "mode": shield_mode,
            "shield_mode": shield_mode,
            "approved": True,
            "reason_codes": [shield_mode],
            "escalation_reason_codes": [shield_mode],
        },
        ops_snapshot={"rollout_stage": "paper"},
        meta_intelligence={"strategy_weights": [{"strategy": strategy, "total_weight": 1.0}]},
        cycle_id=cycle_id,
    )
    memory.record(packet)
    return memory.grade(
        packet,
        realized_pnl_quote=pnl,
        realized_slippage_bps=slippage,
        realized_regime=regime,
        fill_ratio=0.94,
    )


def _seed_world(mind: UniverseMind, *, symbol: str = "XBTUSD") -> None:
    for event_type, payload in (
        ("MarketTickEvent", {"symbol": symbol, "venue": "kraken_spot", "mid": 100.0, "spread_bps": 6.0, "trend_bps": 52.0, "realized_vol": 0.008}),
        ("BookSnapshotEvent", {"symbol": symbol, "venue": "kraken_spot", "spread_bps": 6.0, "depth_notional": 16_000.0}),
        ("AccountSnapshotEvent", {"symbol": symbol, "venue": "kraken_spot", "equity_quote": 2_500.0, "free_quote": 2_000.0, "exposure_quote": 150.0, "drawdown_pct": 0.01}),
        ("HealthEvent", {"symbol": symbol, "venue": "kraken_spot", "status": "OK", "latency_ms": 45.0, "health_score": 0.95, "rejection_ratio": 0.02, "stale_feed": False, "desync": False}),
        ("RiskEvent", {"symbol": symbol, "venue": "kraken_spot", "mode": "normal", "model_confidence": 0.84, "uncertainty_bps": 7.0, "observe_only": False, "hard_stop": False}),
        ("RegimeEvent", {"symbol": symbol, "venue": "kraken_spot", "regime": "TREND", "confidence": 0.82, "volatility_regime": "LOW_VOL", "liquidity_regime": "DEEP", "expansion_state": "COMPRESSION", "panic": False}),
    ):
        mind.emit(event_type=event_type, source="test", partition_key=symbol, payload=payload)


def _proposal(symbol: str = "XBTUSD") -> list[StrategyProposal]:
    return [
        StrategyProposal(
            strategy="microstructure_momentum",
            instrument=symbol,
            action="trade",
            side="buy",
            target_notional_quote=160.0,
            expected_value_bps=12.0,
            confidence=0.80,
            expected_hold_time_s=45.0,
            execution_sensitivity=0.65,
            slippage_risk_bps=1.5,
            regime_compatibility=0.90,
            risk_cost_bps=1.0,
        )
    ]


def test_phase8_deterministic_replay_trace(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packets = [_packet(memory, cycle_id=f"det-{idx}", pnl=1.5 + idx * 0.1) for idx in range(4)]
    engine = ReplayLadderEngine(max_batch_packets=50)
    first = engine.run_batch(packets=packets, mission_filter="momentum_extraction", capital_scale=0.2)
    second = engine.run_batch(packets=packets, mission_filter="momentum_extraction", capital_scale=0.2)
    assert first.batch_id == second.batch_id
    assert first.reproducibility_metadata == second.reproducibility_metadata
    assert [row.to_dict() for row in first.traces] == [row.to_dict() for row in second.traces]
    assert [row.to_dict() for row in first.strategy_grades] == [row.to_dict() for row in second.strategy_grades]


def test_phase8_deterministic_replay_session_support(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packets = [_packet(memory, cycle_id=f"sess-{idx}", pnl=1.0 + idx * 0.1) for idx in range(10)]
    engine = ReplayLadderEngine(max_batch_packets=50)
    first = engine.run_session(packets=packets, mission_filter="momentum_extraction", capital_scale=0.25)
    second = engine.run_session(packets=packets, mission_filter="momentum_extraction", capital_scale=0.25)
    assert first.session_id == second.session_id
    assert first.batch_status["batch_id"] == second.batch_status["batch_id"]
    assert first.walk_forward == second.walk_forward
    assert first.comparative_counterfactual == second.comparative_counterfactual


def test_phase8_decision_reconstruction_and_inferred_markers(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packet = _packet(memory, cycle_id="recon-1", pnl=1.1)
    raw = packet.to_dict()
    raw["mission"] = {}
    raw["execution_plan"] = {"target_notional_quote": 0.0}
    reconstructed = ReplayLadderEngine().reconstruct_decisions([memory.build_packet(
        symbol=raw["symbol"],
        venue=raw["venue"],
        world_state=raw["world_state"],
        mission=raw["mission"],
        proposals=raw["proposals"],
        selected_strategy=raw["selected_strategy"],
        selected_strategies=raw["selected_strategies"],
        parliament=raw["parliament"],
        execution_plan=raw["execution_plan"],
        shield=raw["shield"],
        ops_snapshot=raw["ops_snapshot"],
        meta_intelligence=raw["meta_intelligence"],
        cycle_id=raw["cycle_id"] + "-x",
    )])
    assert reconstructed
    assert any(marker.startswith("inferred:") for marker in reconstructed[0].inferred_markers)


def test_phase8_counterfactual_comparative_evaluation_has_inferred_markers(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packets = [_packet(memory, cycle_id=f"cf-{idx}", pnl=1.4) for idx in range(6)]
    engine = ReplayLadderEngine(max_batch_packets=50)
    comparative = engine.compare_counterfactual(
        packets=packets,
        mission_filter="momentum_extraction",
        baseline_capital_scale=0.30,
        counterfactual_capital_scale=0.12,
        counterfactual_constraints={"scenario": "lower_capital"},
    )
    assert comparative.deltas["overall_grade_delta"] <= 1.0
    assert any(marker.startswith("inferred:") for marker in comparative.inferred_markers)


def test_phase8_walk_forward_holdout_evaluation_support(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packets = [_packet(memory, cycle_id=f"wf-{idx}", pnl=1.0 + ((idx % 3) * 0.2)) for idx in range(24)]
    engine = ReplayLadderEngine(max_batch_packets=80)
    walk = engine.run_walk_forward_holdout(
        packets=packets,
        mission_filter="momentum_extraction",
        holdout_ratio=0.25,
        walk_forward_window=8,
        walk_forward_step=4,
    )
    assert walk.session_id
    assert isinstance(walk.walk_forward_batches, list)
    assert walk.walk_forward_batches
    assert walk.holdout_overall_grade >= 0.0


def test_phase8_grade_stability_scoring(tmp_path) -> None:
    stable_memory = MemoryEngine(str(tmp_path / "stable"))
    volatile_memory = MemoryEngine(str(tmp_path / "volatile"))
    stable_packets = [_packet(stable_memory, cycle_id=f"s-{idx}", pnl=1.2 + (0.02 * idx)) for idx in range(8)]
    volatile_packets = [_packet(volatile_memory, cycle_id=f"v-{idx}", pnl=(8.0 if idx % 2 == 0 else -7.5)) for idx in range(8)]
    engine = ReplayLadderEngine(max_batch_packets=50)
    stable_grade = engine.run_batch(packets=stable_packets).strategy_grades[0]
    volatile_grade = engine.run_batch(packets=volatile_packets).strategy_grades[0]
    assert stable_grade.stability_score > volatile_grade.stability_score
    assert stable_grade.overall_grade > volatile_grade.overall_grade


def test_phase8_promotion_hysteresis() -> None:
    ladder = PromotionLadderEngine(min_replay_evidence=4, promote_hysteresis=3, demote_hysteresis=2)
    fingerprint = "strategy-a"
    low_history = [
        StrategyReplayGrade(
            stability_score=0.8,
            risk_adjusted_return=0.5,
            drawdown_severity=0.1,
            volatility_of_edge=0.2,
            capital_efficiency=0.4,
            regime_consistency=0.8,
            shield_penalty_score=0.1,
            determinism_score=1.0,
            overall_grade=0.72,
            strategy_fingerprint=fingerprint,
            sample_count=2,
            regime_diversity_count=2,
        ),
        StrategyReplayGrade(
            stability_score=0.8,
            risk_adjusted_return=0.5,
            drawdown_severity=0.1,
            volatility_of_edge=0.2,
            capital_efficiency=0.4,
            regime_consistency=0.8,
            shield_penalty_score=0.1,
            determinism_score=1.0,
            overall_grade=0.71,
            strategy_fingerprint=fingerprint,
            sample_count=2,
            regime_diversity_count=2,
        ),
    ]
    no_promotion = ladder.evaluate(
        latest_grades=[low_history[-1]],
        history={fingerprint: low_history[:1]},
        previous_decisions={},
    )[0]
    assert no_promotion.next_stage_candidate == PromotionStage.SANDBOX_SHADOW

    promotion = ladder.evaluate(
        latest_grades=[low_history[-1]],
        history={fingerprint: low_history},
        previous_decisions={},
    )[0]
    assert promotion.next_stage_candidate == PromotionStage.SHADOW_LIVE


def test_phase8_quarantine_trigger_logic() -> None:
    ladder = PromotionLadderEngine(min_replay_evidence=2, promote_hysteresis=1)
    fingerprint = "quarantine-me"
    decision = ladder.evaluate(
        latest_grades=[
            StrategyReplayGrade(
                stability_score=0.9,
                risk_adjusted_return=0.4,
                drawdown_severity=0.1,
                volatility_of_edge=0.1,
                capital_efficiency=0.3,
                regime_consistency=0.8,
                shield_penalty_score=0.1,
                determinism_score=1.0,
                overall_grade=0.7,
                strategy_fingerprint=fingerprint,
                sample_count=2,
                regime_diversity_count=2,
            )
        ],
        history={},
        previous_decisions={},
        inconsistent_fingerprints=[fingerprint],
    )[0]
    assert decision.next_stage_candidate == PromotionStage.QUARANTINE
    assert decision.quarantine_recommendation is True


def test_phase8_capital_ramp_logic(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path / "gate"))
    _seed_world(mind)
    world = mind.get_world_state()
    gate = AdaptiveActivationGate()
    decisions = [
        PromotionDecision(
            strategy_fingerprint="micro",
            current_stage=PromotionStage.MICRO_CAPITAL_LIVE,
            next_stage_candidate=PromotionStage.MICRO_CAPITAL_LIVE,
            promotion_confidence=0.65,
            capital_scaling_factor=0.30,
            required_observation_window=8,
            safety_override_flag=False,
        ),
        PromotionDecision(
            strategy_fingerprint="core",
            current_stage=PromotionStage.CORE_LIVE,
            next_stage_candidate=PromotionStage.CORE_LIVE,
            promotion_confidence=0.85,
            capital_scaling_factor=0.65,
            required_observation_window=8,
            safety_override_flag=False,
        ),
    ]
    gates = {row.strategy_fingerprint: row for row in gate.apply(decisions=decisions, world=world, replay_live_divergence=0.10)}
    assert gates["core"].capital_scaling_factor > gates["micro"].capital_scaling_factor
    kill_switch = gate.apply(decisions=decisions, world=world, replay_live_divergence=1.20)
    assert all(not row.allowed for row in kill_switch)
    assert all(row.resolved_stage == PromotionStage.SANDBOX_SHADOW for row in kill_switch)


def test_phase8_memory_persistence_correctness(tmp_path) -> None:
    memory = MemoryEngine(str(tmp_path))
    packets = [_packet(memory, cycle_id=f"mem-{idx}", pnl=1.0 + (idx * 0.1)) for idx in range(6)]
    batch = ReplayLadderEngine(max_batch_packets=50).run_batch(packets=packets)
    memory.persist_replay_batch_status(batch.to_dict())
    memory.persist_replay_grades(
        batch_id=batch.batch_id,
        grades=[row.to_dict() for row in batch.strategy_grades],
        reproducibility_metadata=batch.reproducibility_metadata,
    )
    ladder_state = {
        "decisions": [
            {
                "strategy_fingerprint": batch.strategy_grades[0].strategy_fingerprint,
                "current_stage": "sandbox_shadow",
                "next_stage_candidate": "shadow_live",
                "promotion_confidence": 0.66,
                "capital_scaling_factor": 0.10,
                "required_observation_window": 8,
                "safety_override_flag": False,
                "promotion_reason_codes": ["test"],
                "demotion_reason_codes": [],
            }
        ],
        "top_strategy_candidates": [{"strategy_fingerprint": batch.strategy_grades[0].strategy_fingerprint}],
        "quarantine_strategy_list": [],
        "promotion_readiness_score": 0.66,
    }
    memory.persist_promotion_ladder_state(ladder_state)
    latest = memory.latest_replay_batch_status()
    history, inconsistent = memory.load_replay_grade_history()
    lookup = memory.replay_fingerprint_lookup(batch.strategy_grades[0].strategy_fingerprint)
    assert latest["batch_id"] == batch.batch_id
    assert inconsistent == []
    assert batch.strategy_grades[0].strategy_fingerprint in history
    assert "latest_replay_grade" in lookup
    assert lookup.get("latest_stage") == "shadow_live"


def test_phase8_ops_snapshot_enrichment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("UNIVERSE_REPLAY_PROMOTION_ENABLED", "1")
    mind = UniverseMind(str(tmp_path / "ops"))
    _seed_world(mind)
    first = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=_proposal())
    mind.grade_cycle(first.decision_packet, realized_pnl_quote=2.0, realized_slippage_bps=1.2, realized_regime="TREND", fill_ratio=0.95)
    second = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=_proposal())
    assert second.ops_snapshot is not None
    assert isinstance(second.ops_snapshot.replay_batch_status, dict)
    assert isinstance(second.ops_snapshot.promotion_ladder_state, dict)
    assert isinstance(second.ops_snapshot.top_strategy_candidates, list)
    assert isinstance(second.ops_snapshot.quarantine_strategy_list, list)
    assert second.ops_snapshot.promotion_readiness_score >= 0.0


def test_phase8_universe_mind_run_cycle_integration(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("UNIVERSE_REPLAY_PROMOTION_ENABLED", "1")
    mind = UniverseMind(str(tmp_path / "integration"))
    _seed_world(mind)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=_proposal())
    assert result.ops_snapshot is not None
    assert "replay_batch_status" in result.decision_packet.evaluation.get("learning_summary", {})
    assert "promotion_ladder_state" in result.decision_packet.evaluation.get("learning_summary", {})
    assert result.ops_snapshot.replay_backlog_depth >= 0
