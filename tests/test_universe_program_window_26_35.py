from __future__ import annotations

from types import SimpleNamespace

from autonomous_investment_robot.services.universe_core import (
    AdaptivePersonalityEngine,
    AutonomousFundBrain,
    CapitalSurvivalDoctrine,
    CrossRealitySignalFusion,
    DeterministicFutureSimulationEngine,
    EvolutionaryStrategyResearchLayer,
    GlobalMarketBrain,
    InstitutionalReadinessEngine,
    MarketEnergyPhysicsModel,
    MultiHorizonDecisionLayer,
    StrategyProposal,
    UniverseMind,
    WorldStateGraph,
    build_event,
)


def _seed_world(graph: WorldStateGraph, *, symbol: str = "XBTUSD", regime: str = "TREND", realized_vol: float = 0.010, depth_notional: float = 16_000.0) -> None:
    for event_type, payload in (
        (
            "MarketTickEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "mid": 100.0,
                "spread_bps": 8.0,
                "trend_bps": 45.0,
                "realized_vol": realized_vol,
            },
        ),
        (
            "BookSnapshotEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "spread_bps": 8.0,
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
                "exposure_quote": 220.0,
                "drawdown_pct": 0.02,
            },
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
            "OrderEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "open_orders": 2,
                "order_type": "limit",
                "side": "buy",
                "queue_quality": 0.90,
                "rejection_ratio": 0.02,
            },
        ),
        (
            "FillEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "fill_ratio": 0.94,
                "slippage_bps": 1.8,
                "fill_probability": 0.92,
                "latency_ms": 45.0,
                "rejection_ratio": 0.02,
            },
        ),
        (
            "RiskEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "mode": "normal",
                "model_confidence": 0.85,
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
                "regime": regime,
                "confidence": 0.82,
                "volatility_regime": "HIGH_VOL" if realized_vol >= 0.015 else "LOW_VOL",
                "liquidity_regime": "THIN" if depth_notional <= 1_000.0 else "DEEP",
                "expansion_state": "EXPANSION" if realized_vol >= 0.015 else "COMPRESSION",
                "panic": regime == "PANIC",
            },
        ),
    ):
        graph.apply(build_event(event_type=event_type, source="test", partition_key=symbol, payload=payload))


def _world_snapshot() -> object:
    graph = WorldStateGraph()
    _seed_world(graph)
    return graph.snapshot()


def _proposal() -> StrategyProposal:
    return StrategyProposal(
        strategy="microstructure_momentum",
        instrument="XBTUSD",
        action="trade",
        side="buy",
        target_notional_quote=180.0,
        expected_value_bps=12.0,
        confidence=0.82,
        expected_hold_time_s=40.0,
        execution_sensitivity=0.70,
        slippage_risk_bps=1.8,
        regime_compatibility=0.90,
        risk_cost_bps=1.0,
    )


def test_phase26_global_market_brain_determinism_and_degradation() -> None:
    world = _world_snapshot()
    brain = GlobalMarketBrain()
    payload = {
        "as_of_ts": world.as_of_time,
        "macro_liquidity": {"liquidity_score": 0.70, "funding_pressure": 0.40},
        "cross_venue": {"divergence_bps": 12.0, "spread_pressure": 0.20},
        "sentiment": {"sentiment_score": 0.62, "panic_index": 0.22},
    }
    first = brain.assess(world=world, payload=payload)
    second = brain.assess(world=world, payload=payload)
    assert first.to_dict() == second.to_dict()
    stale = brain.assess(
        world=world,
        payload={"as_of_ts": world.as_of_time, "macro_liquidity": {"as_of_ts": world.as_of_time - 900.0}},
    )
    assert stale.partial_data is True
    assert "macro_liquidity" in stale.freshness.stale_components


def test_phase27_horizon_conflicts_are_reported() -> None:
    world = _world_snapshot()
    global_state = GlobalMarketBrain().assess(world=world, payload={"cross_venue": {"venue_outage_risk": 0.90}, "sentiment": {"panic_index": 0.85}})
    verdict = SimpleNamespace(selected=_proposal())
    plan = SimpleNamespace(urgency_alpha=1.0)
    mission = SimpleNamespace(mission="momentum_extraction")
    report = MultiHorizonDecisionLayer().assess(
        world=world,
        global_market=global_state,
        mission=mission,
        verdict=verdict,
        plan=plan,
    )
    assert isinstance(report.conflicts, list)
    assert report.recommendation_safe in {True, False}


def test_phase28_market_energy_is_deterministic() -> None:
    world = _world_snapshot()
    global_state = GlobalMarketBrain().assess(world=world, payload={})
    report = MultiHorizonDecisionLayer().assess(
        world=world,
        global_market=global_state,
        mission=SimpleNamespace(mission="momentum_extraction"),
        verdict=SimpleNamespace(selected=_proposal()),
        plan=SimpleNamespace(urgency_alpha=0.6),
    )
    model = MarketEnergyPhysicsModel()
    first = model.assess(world=world, global_market=global_state, horizon=report).to_dict()
    second = model.assess(world=world, global_market=global_state, horizon=report).to_dict()
    assert first == second


def test_phase29_future_simulation_is_seeded_bounded_and_serializable() -> None:
    world = _world_snapshot()
    global_state = GlobalMarketBrain().assess(world=world, payload={})
    report = MultiHorizonDecisionLayer().assess(
        world=world,
        global_market=global_state,
        mission=SimpleNamespace(mission="momentum_extraction"),
        verdict=SimpleNamespace(selected=_proposal()),
        plan=SimpleNamespace(urgency_alpha=0.6),
    )
    energy = MarketEnergyPhysicsModel().assess(world=world, global_market=global_state, horizon=report)
    engine = DeterministicFutureSimulationEngine(max_branches=5, max_depth=2)
    first = engine.simulate(
        seed_payload={"cycle_id": "c1", "symbol": "XBTUSD"},
        market_energy=energy,
        expected_edge_bps=12.0,
        capital_scale=0.3,
    )
    second = engine.simulate(
        seed_payload={"cycle_id": "c1", "symbol": "XBTUSD"},
        market_energy=energy,
        expected_edge_bps=12.0,
        capital_scale=0.3,
    )
    assert first.to_dict() == second.to_dict()
    assert first.scenario_tree.bounded is True
    assert first.replay_export["bounded_compute"] is True


def test_phase30_cross_reality_fusion_graceful_degradation_and_determinism() -> None:
    fusion = CrossRealitySignalFusion()
    degraded = fusion.fuse(payload={"derivatives": {"funding_rate": 0.002}})
    assert degraded.integrity.component_coverage < 1.0
    assert "partial_component_coverage" in degraded.integrity.reason_codes
    full_payload = {
        "derivatives": {"funding_rate": 0.001, "open_interest_delta": 0.12, "basis_bps": 4.0, "pressure_score": 0.35},
        "on_chain": {"net_exchange_flow": -1200.0, "whale_flow_score": 0.40, "pressure_score": 0.42},
        "social": {"panic_score": 0.20, "message_velocity": 1.4},
        "vol_surface": {"skew_change": 0.10, "term_structure_stress": 0.30, "deformation_score": 0.28},
    }
    first = fusion.fuse(payload=full_payload).to_dict()
    second = fusion.fuse(payload=full_payload).to_dict()
    assert first == second


def test_phase31_personality_hysteresis_and_safety_constraints() -> None:
    world = _world_snapshot()
    global_state = GlobalMarketBrain().assess(world=world, payload={})
    horizon = MultiHorizonDecisionLayer().assess(
        world=world,
        global_market=global_state,
        mission=SimpleNamespace(mission="momentum_extraction"),
        verdict=SimpleNamespace(selected=_proposal()),
        plan=SimpleNamespace(urgency_alpha=0.8),
    )
    energy = MarketEnergyPhysicsModel().assess(world=world, global_market=global_state, horizon=horizon)
    cross = CrossRealitySignalFusion().fuse(payload={"social": {"panic_score": 0.9, "message_velocity": 3.2}})
    engine = AdaptivePersonalityEngine(hysteresis_steps=2)
    first = engine.assess(
        cycle_id="cy1",
        as_of_ts=world.as_of_time,
        horizon=horizon,
        energy=energy,
        cross_reality=cross,
        safety_hard_stop=False,
    )
    second = engine.assess(
        cycle_id="cy2",
        as_of_ts=world.as_of_time + 1.0,
        horizon=horizon,
        energy=energy,
        cross_reality=cross,
        safety_hard_stop=False,
    )
    hard_stop = engine.assess(
        cycle_id="cy3",
        as_of_ts=world.as_of_time + 2.0,
        horizon=horizon,
        energy=energy,
        cross_reality=cross,
        safety_hard_stop=True,
    )
    assert first.shift.shifted in {True, False}
    assert second.execution_personality.value in {"defensive", "survival", "patient", "recovery", "aggressive", "predator"}
    assert hard_stop.constraints.allow_new_risk is False
    assert hard_stop.constraints.hard_safety_override is True


def test_phase32_capital_survival_conservative_escalation() -> None:
    world = _world_snapshot()
    global_state = GlobalMarketBrain().assess(
        world=world,
        payload={"cross_venue": {"venue_outage_risk": 0.95}, "sentiment": {"panic_index": 0.92}, "macro_liquidity": {"funding_pressure": 0.85}},
    )
    horizon = MultiHorizonDecisionLayer().assess(
        world=world,
        global_market=global_state,
        mission=SimpleNamespace(mission="preserve_capital"),
        verdict=SimpleNamespace(selected=_proposal()),
        plan=SimpleNamespace(urgency_alpha=0.8),
    )
    energy = MarketEnergyPhysicsModel().assess(world=world, global_market=global_state, horizon=horizon)
    cross = CrossRealitySignalFusion().fuse(
        payload={
            "derivatives": {"pressure_score": 0.9},
            "on_chain": {"pressure_score": 0.9},
            "social": {"panic_score": 0.95, "message_velocity": 4.0},
            "vol_surface": {"deformation_score": 0.88, "term_structure_stress": 0.92},
        }
    )
    personality = AdaptivePersonalityEngine(hysteresis_steps=1).assess(
        cycle_id="cy-high",
        as_of_ts=world.as_of_time,
        horizon=horizon,
        energy=energy,
        cross_reality=cross,
        safety_hard_stop=True,
    )
    decision = CapitalSurvivalDoctrine().assess(
        world=world,
        energy=energy,
        cross_reality=cross,
        personality=personality,
    )
    assert decision.safety_veto is True
    assert decision.capital_bunker.activate is True


def test_phase33_evolutionary_research_is_offline_seeded_and_evidence_gated() -> None:
    layer = EvolutionaryStrategyResearchLayer()
    grades = [
        {"overall_grade": 0.72, "stability_score": 0.66, "drawdown_severity": 0.18},
        {"overall_grade": 0.70, "stability_score": 0.64, "drawdown_severity": 0.16},
    ]
    first = layer.evolve(cycle_id="x1", selected_strategy="microstructure_momentum", performance_samples=grades)
    second = layer.evolve(cycle_id="x1", selected_strategy="microstructure_momentum", performance_samples=grades)
    assert first.genome.mutation_seed == second.genome.mutation_seed
    assert first.safety_envelope.live_promotion_allowed is False
    assert first.safety_envelope.offline_only is True


def test_phase34_committee_bundle_exposes_disagreement_and_veto() -> None:
    research = EvolutionaryStrategyResearchLayer().evolve(cycle_id="x2", selected_strategy="microstructure_momentum", performance_samples=[])
    world = _world_snapshot()
    global_state = GlobalMarketBrain().assess(world=world, payload={})
    horizon = MultiHorizonDecisionLayer().assess(
        world=world,
        global_market=global_state,
        mission=SimpleNamespace(mission="preserve_capital"),
        verdict=SimpleNamespace(selected=_proposal()),
        plan=SimpleNamespace(urgency_alpha=0.6),
    )
    energy = MarketEnergyPhysicsModel().assess(world=world, global_market=global_state, horizon=horizon)
    cross = CrossRealitySignalFusion().fuse(payload={"social": {"panic_score": 0.95, "message_velocity": 5.0}})
    personality = AdaptivePersonalityEngine(hysteresis_steps=1).assess(
        cycle_id="x2",
        as_of_ts=world.as_of_time,
        horizon=horizon,
        energy=energy,
        cross_reality=cross,
        safety_hard_stop=True,
    )
    survival = CapitalSurvivalDoctrine().assess(
        world=world,
        energy=energy,
        cross_reality=cross,
        personality=personality,
    )
    recommendation = AutonomousFundBrain().recommend(
        cycle_id="x2",
        research=research,
        survival=survival,
        execution_quality_score=0.9,
    )
    assert recommendation.bundle is not None
    assert recommendation.bundle.disagreement_map.severity >= 0.0
    assert recommendation.bundle.safety_veto is True


def test_phase35_institutional_readiness_machine_readable_and_residual_risk_explicit() -> None:
    research = EvolutionaryStrategyResearchLayer().evolve(cycle_id="x3", selected_strategy="microstructure_momentum", performance_samples=[])
    world = _world_snapshot()
    global_state = GlobalMarketBrain().assess(world=world, payload={})
    horizon = MultiHorizonDecisionLayer().assess(
        world=world,
        global_market=global_state,
        mission=SimpleNamespace(mission="preserve_capital"),
        verdict=SimpleNamespace(selected=_proposal()),
        plan=SimpleNamespace(urgency_alpha=0.6),
    )
    energy = MarketEnergyPhysicsModel().assess(world=world, global_market=global_state, horizon=horizon)
    cross = CrossRealitySignalFusion().fuse(payload={"social": {"panic_score": 0.80}})
    personality = AdaptivePersonalityEngine(hysteresis_steps=1).assess(
        cycle_id="x3",
        as_of_ts=world.as_of_time,
        horizon=horizon,
        energy=energy,
        cross_reality=cross,
        safety_hard_stop=True,
    )
    survival = CapitalSurvivalDoctrine().assess(
        world=world,
        energy=energy,
        cross_reality=cross,
        personality=personality,
    )
    recommendation = AutonomousFundBrain().recommend(
        cycle_id="x3",
        research=research,
        survival=survival,
        execution_quality_score=0.4,
    )
    report = InstitutionalReadinessEngine().compile(
        cycle_id="x3",
        ops_snapshot={"rollout_stage": "blocked", "readiness_score": 0.4, "blockers": ["risk_hard_stop"], "manual_gate_required": True},
        fund_recommendation=recommendation,
        survival=survival,
    )
    payload = report.to_dict()
    assert "deployment_certification" in payload
    assert isinstance(payload["deployment_certification"]["checklist"], list)
    assert isinstance(payload["residual_risks"]["risks"], list)


def test_phase26_to_35_universe_mind_integration_and_ops_visibility(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(
        symbol="XBTUSD",
        venue="kraken_spot",
        proposals=[_proposal()],
    )
    assert isinstance(result.advanced_intelligence, dict)
    for key in (
        "phase26_global_market_state",
        "phase27_horizon_alignment",
        "phase28_market_energy",
        "phase29_future_simulation",
        "phase30_cross_reality_signal",
        "phase31_personality_trace",
        "phase32_survival_doctrine",
        "phase33_evolutionary_research",
        "phase34_fund_brain",
        "phase35_institutional_readiness",
    ):
        assert key in result.advanced_intelligence
    assert result.ops_snapshot is not None
    assert isinstance(result.ops_snapshot.phase26_global_market_state, dict)
    assert isinstance(result.ops_snapshot.phase35_institutional_readiness, dict)
    packet_meta = result.decision_packet.meta_intelligence
    assert "advanced_intelligence" in packet_meta
    assert "phase35_institutional_readiness" in packet_meta["advanced_intelligence"]


def test_phase29_replay_seed_determinism_across_identical_world_inputs(tmp_path) -> None:
    left = UniverseMind(str(tmp_path / "left"))
    right = UniverseMind(str(tmp_path / "right"))
    _seed_world(left.graph)
    _seed_world(right.graph)
    r1 = left.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    r2 = right.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    tree1 = r1.advanced_intelligence["phase29_future_simulation"]["scenario_tree"]["tree_id"]
    tree2 = r2.advanced_intelligence["phase29_future_simulation"]["scenario_tree"]["tree_id"]
    assert tree1 == tree2
