from __future__ import annotations

from autonomous_investment_robot.services.universe_core import (
    ExecutionIntelligence,
    MetaIntelligenceEngine,
    MissionDecision,
    MissionType,
    StrategyParliament,
    StrategyProposal,
    UniverseMind,
    UniverseShield,
    WorldStateGraph,
    build_event,
)


def _world(
    *,
    symbol: str = "XBTUSD",
    execution_stress: float = 0.10,
    slippage_bps: float = 1.0,
    infra_stress: float = 0.10,
    drawdown_pct: float = 0.01,
    account_stress: float = 0.10,
    regime_confidence: float = 0.82,
    model_confidence: float = 0.84,
    risk_mode: str = "normal",
    risk_observe_only: bool = False,
    risk_hard_stop: bool = False,
    stale_feed: bool = False,
    desync: bool = False,
    world_state_available: bool = True,
) -> object:
    graph = WorldStateGraph()
    for event_type, payload in (
        (
            "MarketTickEvent",
            {"symbol": symbol, "venue": "kraken_spot", "mid": 100.0, "spread_bps": 6.0, "trend_bps": 48.0, "realized_vol": 0.008},
        ),
        (
            "BookSnapshotEvent",
            {"symbol": symbol, "venue": "kraken_spot", "spread_bps": 6.0, "depth_notional": 20_000.0},
        ),
        (
            "AccountSnapshotEvent",
            {"symbol": symbol, "venue": "kraken_spot", "equity_quote": 2_500.0, "free_quote": 2_000.0, "exposure_quote": 200.0, "drawdown_pct": drawdown_pct},
        ),
        (
            "HealthEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "status": "OK",
                "latency_ms": 40.0,
                "health_score": 0.95,
                "rejection_ratio": 0.02,
                "stale_feed": stale_feed,
                "desync": desync,
            },
        ),
        (
            "OrderEvent",
            {"symbol": symbol, "venue": "kraken_spot", "open_orders": 2, "order_type": "limit", "side": "buy", "queue_quality": 0.92, "rejection_ratio": 0.02},
        ),
        (
            "FillEvent",
            {"symbol": symbol, "venue": "kraken_spot", "fill_ratio": 0.95, "slippage_bps": slippage_bps, "fill_probability": 0.94, "latency_ms": 35.0, "rejection_ratio": 0.02},
        ),
        (
            "RiskEvent",
            {"symbol": symbol, "venue": "kraken_spot", "mode": risk_mode, "model_confidence": model_confidence, "uncertainty_bps": 6.0, "observe_only": risk_observe_only, "hard_stop": risk_hard_stop},
        ),
        (
            "RegimeEvent",
            {"symbol": symbol, "venue": "kraken_spot", "regime": "TREND", "confidence": regime_confidence, "volatility_regime": "LOW_VOL", "liquidity_regime": "DEEP", "expansion_state": "COMPRESSION", "panic": False},
        ),
    ):
        graph.apply(build_event(event_type=event_type, source="test", partition_key=symbol, payload=payload))
    snap = graph.snapshot()
    snap.execution_state.execution_stress = execution_stress
    snap.execution_state.slippage_bps = slippage_bps
    snap.infra_state.system_health_stress = infra_stress
    snap.infra_state.health_score = max(0.0, min(1.0, 1.0 - infra_stress))
    snap.infra_state.stale_feed = stale_feed
    snap.infra_state.desync = desync
    snap.portfolio_state.drawdown_pct = drawdown_pct
    snap.portfolio_state.own_account_stress = account_stress
    snap.market_state.regime_confidence = regime_confidence
    snap.risk_state.model_confidence = model_confidence
    snap.risk_state.observe_only = risk_observe_only
    snap.risk_state.hard_stop = risk_hard_stop
    snap.risk_state.mode = risk_mode
    snap.metadata.graph_available = world_state_available
    return snap


def _mission(*, no_trade_preferred: bool = False, allow_new_risk: bool = True, confidence: float = 0.82) -> MissionDecision:
    return MissionDecision(
        mission_type=MissionType.MOMENTUM_EXTRACTION,
        confidence=confidence,
        reason_codes=("trend_confirmed",),
        no_trade_preferred=no_trade_preferred,
        allow_new_risk=allow_new_risk,
    )


def _meta(
    *,
    regime_cluster: str = "trend_quality",
    regime_confidence: float = 0.82,
    exploration_budget: float = 0.20,
    exploitation_budget: float = 0.80,
    risk_scale: float = 1.0,
) -> dict[str, object]:
    return {
        "regime_cluster": regime_cluster,
        "regime_confidence": regime_confidence,
        "exploration_budget": exploration_budget,
        "exploitation_budget": exploitation_budget,
        "risk_scale": risk_scale,
        "strategy_weights": [
            {
                "strategy": "microstructure_momentum",
                "total_weight": 1.10,
                "adaptive_weight": 1.05,
                "exploration_weight": exploration_budget,
                "exploitation_weight": exploitation_budget,
            }
        ],
    }


def _decision_inputs(world, *, symbol: str = "XBTUSD"):
    mission = _mission()
    proposals = [
        StrategyProposal(
            strategy="microstructure_momentum",
            instrument=symbol,
            action="trade",
            side="buy",
            target_notional_quote=180.0,
            expected_value_bps=14.0,
            confidence=0.82,
            expected_hold_time_s=45.0,
            execution_sensitivity=0.60,
            slippage_risk_bps=1.6,
            regime_compatibility=0.90,
            risk_cost_bps=1.0,
        ),
        StrategyProposal(
            strategy="mean_reversion",
            instrument=symbol,
            action="trade",
            side="sell",
            target_notional_quote=120.0,
            expected_value_bps=10.0,
            confidence=0.74,
            expected_hold_time_s=55.0,
            execution_sensitivity=0.35,
            slippage_risk_bps=1.2,
            regime_compatibility=0.80,
            risk_cost_bps=1.2,
        ),
    ]
    verdict = StrategyParliament(min_score=0.0).judge(proposals, world=world, mission=mission, selection_mode="top_n", top_n=2, score_floor=0.0)
    plan = ExecutionIntelligence().build_plan(verdict.selected, world=world, mission=mission)
    return mission, verdict, plan


def _seed_mind(mind: UniverseMind, *, symbol: str = "XBTUSD") -> None:
    for event_type, payload in (
        ("MarketTickEvent", {"symbol": symbol, "venue": "kraken_spot", "mid": 100.0, "spread_bps": 6.0, "trend_bps": 52.0, "realized_vol": 0.008}),
        ("BookSnapshotEvent", {"symbol": symbol, "venue": "kraken_spot", "spread_bps": 6.0, "depth_notional": 16_000.0}),
        ("AccountSnapshotEvent", {"symbol": symbol, "venue": "kraken_spot", "equity_quote": 2_500.0, "free_quote": 2_000.0, "exposure_quote": 150.0, "drawdown_pct": 0.01}),
        ("HealthEvent", {"symbol": symbol, "venue": "kraken_spot", "status": "OK", "latency_ms": 45.0, "health_score": 0.95, "rejection_ratio": 0.02, "stale_feed": False, "desync": False}),
        ("RiskEvent", {"symbol": symbol, "venue": "kraken_spot", "mode": "normal", "model_confidence": 0.84, "uncertainty_bps": 7.0, "observe_only": False, "hard_stop": False}),
        ("RegimeEvent", {"symbol": symbol, "venue": "kraken_spot", "regime": "TREND", "confidence": 0.82, "volatility_regime": "LOW_VOL", "liquidity_regime": "DEEP", "expansion_state": "COMPRESSION", "panic": False}),
    ):
        mind.emit(event_type=event_type, source="test", partition_key=symbol, payload=payload)


def _single_proposal(symbol: str = "XBTUSD") -> list[StrategyProposal]:
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


def test_shield_escalates_normal_to_cautious() -> None:
    shield = UniverseShield()
    world = _world()
    mission, verdict, plan = _decision_inputs(world)
    first = shield.assess(world=world, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(), cycle_id="c1")
    assert first.mode == "normal"

    degraded = _world(execution_stress=0.52, regime_confidence=0.50, slippage_bps=10.0)
    mission, verdict, plan = _decision_inputs(degraded)
    second = shield.assess(
        world=degraded,
        mission=mission,
        verdict=verdict,
        plan=plan,
        meta_diagnostics=_meta(regime_confidence=0.50, exploration_budget=0.48, exploitation_budget=0.52, risk_scale=0.78),
        cycle_id="c2",
    )
    assert second.previous_mode == "normal"
    assert second.mode == "cautious"
    assert "execution_stress_rising" in second.reason_codes or "meta_diagnostics_degraded" in second.reason_codes


def test_shield_escalates_cautious_to_defensive() -> None:
    shield = UniverseShield()
    world_a = _world(execution_stress=0.50)
    mission, verdict, plan = _decision_inputs(world_a)
    shield.assess(world=world_a, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(exploration_budget=0.46), cycle_id="c1")

    world_b = _world(execution_stress=0.74, infra_stress=0.66, drawdown_pct=0.09, account_stress=0.72, model_confidence=0.60)
    mission, verdict, plan = _decision_inputs(world_b)
    decision = shield.assess(world=world_b, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(risk_scale=0.70), cycle_id="c2")
    assert decision.previous_mode == "cautious"
    assert decision.mode == "defensive"
    assert "execution_infra_account_compound_stress" in decision.reason_codes


def test_shield_escalates_defensive_to_observe_only() -> None:
    shield = UniverseShield()
    world_a = _world(execution_stress=0.72, infra_stress=0.62, drawdown_pct=0.08, account_stress=0.70)
    mission, verdict, plan = _decision_inputs(world_a)
    shield.assess(world=world_a, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(risk_scale=0.70), cycle_id="c1")

    world_b = _world(execution_stress=0.58, model_confidence=0.18, regime_confidence=0.18)
    mission, verdict, plan = _decision_inputs(world_b)
    decision = shield.assess(
        world=world_b,
        mission=mission,
        verdict=verdict,
        plan=plan,
        meta_diagnostics=_meta(regime_confidence=0.18, exploration_budget=0.70, exploitation_budget=0.30, risk_scale=0.40),
        cycle_id="c2",
    )
    assert decision.previous_mode == "defensive"
    assert decision.mode == "observe_only"
    assert decision.no_trade_forced is True
    assert "confidence_collapse" in decision.reason_codes


def test_shield_escalates_observe_only_to_hard_stop_on_critical_failure() -> None:
    shield = UniverseShield()
    world_a = _world(model_confidence=0.20, regime_confidence=0.20, execution_stress=0.60)
    mission, verdict, plan = _decision_inputs(world_a)
    shield.assess(world=world_a, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(regime_confidence=0.20), cycle_id="c1")

    world_b = _world(
        execution_stress=0.95,
        slippage_bps=22.0,
        infra_stress=0.92,
        drawdown_pct=0.18,
        account_stress=0.94,
        regime_confidence=0.10,
        model_confidence=0.08,
        risk_hard_stop=True,
    )
    mission, verdict, plan = _decision_inputs(world_b)
    decision = shield.assess(world=world_b, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(regime_confidence=0.10, risk_scale=0.20), cycle_id="c2")
    assert decision.previous_mode == "observe_only"
    assert decision.mode == "hard_stop"
    assert decision.hard_stop_forced is True
    assert decision.kill_switch is True


def test_shield_hysteresis_prevents_flip_flop() -> None:
    shield = UniverseShield()
    stressed = _world(execution_stress=0.72, infra_stress=0.60, drawdown_pct=0.08, account_stress=0.70)
    mission, verdict, plan = _decision_inputs(stressed)
    first = shield.assess(world=stressed, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(risk_scale=0.72), cycle_id="c1")
    assert first.mode == "defensive"

    recovered = _world(execution_stress=0.12, infra_stress=0.08, drawdown_pct=0.01, account_stress=0.08, regime_confidence=0.85, model_confidence=0.86)
    mission, verdict, plan = _decision_inputs(recovered)
    second = shield.assess(world=recovered, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(regime_confidence=0.85, risk_scale=1.0), cycle_id="c2")
    assert second.mode == "defensive"
    assert "hysteresis_hold" in second.reason_codes


def test_shield_deescalates_only_after_sustained_recovery() -> None:
    shield = UniverseShield()
    stressed = _world(execution_stress=0.74, infra_stress=0.62, drawdown_pct=0.09, account_stress=0.72)
    mission, verdict, plan = _decision_inputs(stressed)
    first = shield.assess(world=stressed, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(risk_scale=0.70), cycle_id="c1")
    assert first.mode == "defensive"

    recovered = _world(execution_stress=0.10, infra_stress=0.05, drawdown_pct=0.01, account_stress=0.05, regime_confidence=0.88, model_confidence=0.90)
    mission, verdict, plan = _decision_inputs(recovered)
    second = shield.assess(world=recovered, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(regime_confidence=0.88, risk_scale=1.0), cycle_id="c2")
    third = shield.assess(world=recovered, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(regime_confidence=0.88, risk_scale=1.0), cycle_id="c3")
    fourth = shield.assess(world=recovered, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=_meta(regime_confidence=0.88, risk_scale=1.0), cycle_id="c4")
    assert second.mode == "defensive"
    assert third.mode == "defensive"
    assert fourth.mode == "cautious"
    assert fourth.recovery_eligibility["required_streak"] >= 3


def test_phase6_decision_packet_contains_shield_escalation_summary(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_mind(mind)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=_single_proposal())
    shield_payload = result.decision_packet.shield
    assert shield_payload["shield_mode"] == result.shield.mode
    assert "previous_shield_mode" in shield_payload
    assert "escalation_reason_codes" in shield_payload
    assert "hysteresis_state" in shield_payload
    assert "recovery_eligibility" in shield_payload


def test_phase6_ops_snapshot_enriched_with_shield_diagnostics(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_mind(mind)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=_single_proposal())
    assert result.ops_snapshot is not None
    assert result.ops_snapshot.shield_mode == result.shield.mode
    assert result.ops_snapshot.previous_shield_mode == result.shield.previous_mode
    assert isinstance(result.ops_snapshot.escalation_reason_codes, list)
    assert isinstance(result.ops_snapshot.hysteresis_state, dict)
    assert isinstance(result.ops_snapshot.recovery_eligibility, dict)


def test_phase6_memory_persists_shield_state(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_mind(mind)
    mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=_single_proposal())
    packets = mind.memory.load()
    assert packets
    shield_payload = packets[-1].shield
    assert "shield_mode" in shield_payload
    assert "escalation_inputs_summary" in shield_payload
    assert "meta_risk_summary" in shield_payload


def test_phase6_fallback_when_meta_diagnostics_unavailable(tmp_path) -> None:
    class BrokenMetaEngine(MetaIntelligenceEngine):
        def adapt_proposals(self, proposals, *, world, mission, cycle_id):  # type: ignore[override]
            raise RuntimeError("meta_down")

    mind = UniverseMind(str(tmp_path), meta=BrokenMetaEngine(str(tmp_path)))
    _seed_mind(mind)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=_single_proposal())
    assert result.shield.mode in {"normal", "cautious", "defensive", "observe_only", "hard_stop"}
    assert result.shield.meta_risk_summary.get("meta_available") is False
    assert result.decision_packet.meta_intelligence["notes"]


def test_phase6_shield_decisions_are_deterministic_for_same_inputs() -> None:
    world = _world(execution_stress=0.52, slippage_bps=8.0, regime_confidence=0.52, model_confidence=0.60)
    mission, verdict, plan = _decision_inputs(world)
    meta = _meta(regime_confidence=0.52, exploration_budget=0.46, exploitation_budget=0.54, risk_scale=0.78)
    first = UniverseShield().assess(world=world, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=meta, cycle_id="det-1")
    second = UniverseShield().assess(world=world, mission=mission, verdict=verdict, plan=plan, meta_diagnostics=meta, cycle_id="det-1")
    assert first.to_dict() == second.to_dict()
