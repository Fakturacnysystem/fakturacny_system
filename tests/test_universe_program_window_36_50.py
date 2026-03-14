from __future__ import annotations

from autonomous_investment_robot.services.universe_core import (
    CausalTwinBridge,
    CapitalConstraintCompiler,
    CommitteeEscalationProtocol,
    CrossRealityIntegrityGuard,
    DeterministicIntelligenceLedger,
    ExecutionPersonality,
    GlobalMarketCalibrationEngine,
    EvidenceVaultIndexBuilder,
    InstitutionalGateCompiler,
    MacroMicroDecisionBridge,
    LiveCanaryEnvelopeCompiler,
    PersonalityConstraints,
    PersonalityShiftDecision,
    PersonalityStabilityGovernor,
    PersonalityTrace,
    Phase50CertificationCompiler,
    ReplayDistributedBridge,
    RiskPersonality,
    ScenarioPortfolioNettingEngine,
    StrategyProposal,
    UniverseMind,
    WorldStateGraph,
    build_event,
)


def _seed_world(graph: WorldStateGraph, *, symbol: str = "XBTUSD") -> None:
    for event_type, payload in (
        (
            "MarketTickEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "mid": 100.0,
                "spread_bps": 8.0,
                "trend_bps": 45.0,
                "realized_vol": 0.010,
            },
        ),
        (
            "BookSnapshotEvent",
            {
                "symbol": symbol,
                "venue": "kraken_spot",
                "spread_bps": 8.0,
                "depth_notional": 16_000.0,
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
                "regime": "TREND",
                "confidence": 0.82,
                "volatility_regime": "LOW_VOL",
                "liquidity_regime": "DEEP",
                "expansion_state": "COMPRESSION",
                "panic": False,
            },
        ),
    ):
        graph.apply(build_event(event_type=event_type, source="test", partition_key=symbol, payload=payload))


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


def _proposal_with_notional(notional: float) -> StrategyProposal:
    base = _proposal().to_dict()
    base["target_notional_quote"] = float(notional)
    return StrategyProposal(**base)


def test_phase36_intelligence_ledger_deterministic_across_identical_world_inputs(tmp_path) -> None:
    left = UniverseMind(str(tmp_path / "left"))
    right = UniverseMind(str(tmp_path / "right"))
    _seed_world(left.graph)
    _seed_world(right.graph)
    r1 = left.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    r2 = right.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    ledger1 = r1.advanced_intelligence["phase36_intelligence_ledger"]
    ledger2 = r2.advanced_intelligence["phase36_intelligence_ledger"]
    assert ledger1["ledger_id"] == ledger2["ledger_id"]
    assert ledger1["world_fingerprint"] == ledger2["world_fingerprint"]
    assert ledger1["phase_hash_chain"] == ledger2["phase_hash_chain"]
    assert ledger1["bounded_compute"] is True


def test_phase36_intelligence_ledger_tracks_veto_lineage() -> None:
    graph = WorldStateGraph()
    _seed_world(graph)
    world = graph.snapshot()
    payload = {
        "phase32_survival_doctrine": {
            "safety_veto": True,
            "reason_codes": ["existential_level:extreme", "safety_veto_active"],
        },
        "phase34_fund_brain": {
            "bundle": {
                "safety_veto": True,
            },
        },
        "phase35_institutional_readiness": {
            "deployment_certification": {
                "rollout_stage": "blocked",
            }
        },
    }
    left = DeterministicIntelligenceLedger().compile(cycle_id="a", world=world, advanced_intelligence=payload).to_dict()
    right = DeterministicIntelligenceLedger().compile(cycle_id="b", world=world, advanced_intelligence=payload).to_dict()
    assert left["ledger_id"] == right["ledger_id"]
    assert "phase32_safety_veto" in left["veto_chain"]
    assert "phase34_committee_veto" in left["veto_chain"]
    assert "phase35_rollout_blocked" in left["veto_chain"]


def test_phase36_intelligence_ledger_visible_in_packet_meta(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase36_intelligence_ledger" in result.advanced_intelligence
    packet_meta = result.decision_packet.meta_intelligence
    assert "advanced_intelligence" in packet_meta
    assert "phase36_intelligence_ledger" in packet_meta["advanced_intelligence"]


def test_phase37_portfolio_netting_deterministic_and_capped(tmp_path) -> None:
    left = UniverseMind(str(tmp_path / "left"))
    right = UniverseMind(str(tmp_path / "right"))
    _seed_world(left.graph)
    _seed_world(right.graph)
    proposal = _proposal_with_notional(6_000.0)
    r1 = left.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[proposal])
    r2 = right.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[proposal])
    n1 = r1.advanced_intelligence["phase37_portfolio_netting"]
    n2 = r2.advanced_intelligence["phase37_portfolio_netting"]
    assert n1["envelope_id"] == n2["envelope_id"]
    assert n1["deterministic"] is True
    assert n1["bounded_compute"] is True
    assert n1["capped_exposure_quote"] <= n1["risk_cap_quote"] + 1e-9


def test_phase37_portfolio_netting_fail_closed_and_meta_visibility(tmp_path) -> None:
    graph = WorldStateGraph()
    _seed_world(graph)
    world = graph.snapshot()
    envelope = ScenarioPortfolioNettingEngine().net(
        world=world,
        primary_symbol="XBTUSD",
        primary_plan_notional_quote=250.0,
        primary_simulation={},
    ).to_dict()
    assert envelope["fail_closed"] is True
    assert envelope["capped_exposure_quote"] == 0.0
    assert "portfolio_netting_fail_closed" in envelope["escalation_reason_codes"]
    capped = ScenarioPortfolioNettingEngine().net(
        world=world,
        primary_symbol="XBTUSD",
        primary_plan_notional_quote=6_000.0,
        primary_simulation={
            "pnl_envelope": {"expected": 5.0, "worst_case": -50.0, "best_case": 15.0},
            "black_swan": {"severity": 0.8},
            "confidence": {"overall": 0.9},
        },
    ).to_dict()
    assert capped["capped_exposure_quote"] <= capped["risk_cap_quote"] + 1e-9
    assert "portfolio_netting_cap_applied" in capped["escalation_reason_codes"]

    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase37_portfolio_netting" in result.advanced_intelligence
    packet_meta = result.decision_packet.meta_intelligence
    assert "advanced_intelligence" in packet_meta
    assert "phase37_portfolio_netting" in packet_meta["advanced_intelligence"]


def test_phase38_capital_constraints_deterministic_and_safety_veto_hard_clamp() -> None:
    graph = WorldStateGraph()
    _seed_world(graph)
    world = graph.snapshot()
    netting = ScenarioPortfolioNettingEngine().net(
        world=world,
        primary_symbol="XBTUSD",
        primary_plan_notional_quote=500.0,
        primary_simulation={
            "pnl_envelope": {"expected": 5.0, "worst_case": -40.0, "best_case": 16.0},
            "black_swan": {"severity": 0.2},
            "confidence": {"overall": 0.8},
        },
    ).to_dict()
    compiler = CapitalConstraintCompiler()
    left = compiler.compile(
        world=world,
        plan={"target_notional_quote": 300.0},
        shield={"kill_switch": False, "hard_stop_forced": False},
        survival_doctrine={"safety_veto": True, "recommendation_mode": "survival"},
        netting_envelope=netting,
    ).to_dict()
    right = compiler.compile(
        world=world,
        plan={"target_notional_quote": 300.0},
        shield={"kill_switch": False, "hard_stop_forced": False},
        survival_doctrine={"safety_veto": True, "recommendation_mode": "survival"},
        netting_envelope=netting,
    ).to_dict()
    assert left["contract_id"] == right["contract_id"]
    assert left["hard_clamp"] is True
    assert left["max_total_exposure_quote"] == 0.0
    assert left["max_new_trade_notional_quote"] == 0.0
    assert left["allow_new_risk"] is False


def test_phase38_capital_constraints_visible_in_universe_mind_meta(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(
        symbol="XBTUSD",
        venue="kraken_spot",
        proposals=[_proposal_with_notional(6_000.0)],
    )
    assert "phase38_capital_constraints" in result.advanced_intelligence
    payload = result.advanced_intelligence["phase38_capital_constraints"]
    assert payload["deterministic"] is True
    assert isinstance(payload["limits"], dict)
    packet_meta = result.decision_packet.meta_intelligence
    assert "advanced_intelligence" in packet_meta
    assert "phase38_capital_constraints" in packet_meta["advanced_intelligence"]


def test_phase39_global_market_calibration_deterministic_and_stale_degrades_confidence() -> None:
    engine = GlobalMarketCalibrationEngine()
    payload = {
        "market_stress": 0.6,
        "risk_on_score": 0.5,
        "partial_data": True,
        "confidence": {"overall": 0.88},
        "freshness": {"max_age_s": 420.0, "stale_components": ["macro_liquidity", "sentiment"]},
    }
    left = engine.calibrate(global_market_state=payload).to_dict()
    right = engine.calibrate(global_market_state=payload).to_dict()
    assert left == right
    assert left["calibrated_confidence"] <= left["input_confidence"] + 1e-9
    assert "stale_input_confidence_degraded" in left["reason_codes"]


def test_phase39_global_market_calibration_visible_in_ops_payload(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase39_global_market_calibration" in result.advanced_intelligence
    payload = result.advanced_intelligence["phase39_global_market_calibration"]
    assert payload["deterministic"] is True
    assert result.ops_snapshot is not None
    assert "phase39_global_market_calibration" in result.ops_snapshot.advanced_intelligence


def test_phase40_cross_reality_integrity_guard_flags_low_coverage_deterministically() -> None:
    guard = CrossRealityIntegrityGuard()
    payload = {
        "confidence": 0.20,
        "integrity": {
            "component_coverage": 0.30,
            "normalization_drift": 0.80,
            "missing_components": ["derivatives", "vol_surface"],
        },
    }
    left = guard.assess(cross_reality_signal=payload).to_dict()
    right = guard.assess(cross_reality_signal=payload).to_dict()
    assert left == right
    assert left["fail_closed"] is True
    assert "low_component_coverage" in left["escalation_reason_codes"]


def test_phase40_cross_reality_integrity_visible_and_consumed_by_survival(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase40_cross_reality_integrity" in result.advanced_intelligence
    integrity = result.advanced_intelligence["phase40_cross_reality_integrity"]
    assert isinstance(integrity["escalation_reason_codes"], list)
    survival = result.advanced_intelligence["phase32_survival_doctrine"]
    assert any(str(code).startswith("integrity:") for code in survival.get("reason_codes", []))


def _trace(
    *,
    cycle_id: str,
    previous_execution: ExecutionPersonality,
    previous_risk: RiskPersonality,
    next_execution: ExecutionPersonality,
    next_risk: RiskPersonality,
    shifted: bool,
    hard_safety_override: bool = False,
) -> PersonalityTrace:
    return PersonalityTrace(
        cycle_id=cycle_id,
        execution_personality=next_execution,
        risk_personality=next_risk,
        shift=PersonalityShiftDecision(
            previous_execution=previous_execution,
            previous_risk=previous_risk,
            next_execution=next_execution,
            next_risk=next_risk,
            shifted=shifted,
            hysteresis_hold_steps=0,
            reason_codes=("test",),
        ),
        constraints=PersonalityConstraints(
            max_size_scale=0.8,
            risk_budget_scale=0.7,
            allow_new_risk=True,
            hard_safety_override=hard_safety_override,
            reason_codes=("test",),
        ),
        as_of_ts=1.0,
    )


def test_phase41_personality_transition_budget_deterministic_and_enforced() -> None:
    governor = PersonalityStabilityGovernor(window_size=4, max_transitions=1)
    t1 = _trace(
        cycle_id="1",
        previous_execution=ExecutionPersonality.PATIENT,
        previous_risk=RiskPersonality.PATIENT,
        next_execution=ExecutionPersonality.AGGRESSIVE,
        next_risk=RiskPersonality.AGGRESSIVE,
        shifted=True,
    )
    _, b1, v1 = governor.enforce(trace=t1, safety_hard_stop=False)
    assert v1 is None
    assert b1.transitions_used == 1

    t2 = _trace(
        cycle_id="2",
        previous_execution=ExecutionPersonality.AGGRESSIVE,
        previous_risk=RiskPersonality.AGGRESSIVE,
        next_execution=ExecutionPersonality.DEFENSIVE,
        next_risk=RiskPersonality.DEFENSIVE,
        shifted=True,
    )
    constrained, b2, v2 = governor.enforce(trace=t2, safety_hard_stop=False)
    assert v2 is not None
    assert v2.violation_code == "phase41_transition_budget_exceeded"
    assert constrained.execution_personality == ExecutionPersonality.AGGRESSIVE
    assert constrained.risk_personality == RiskPersonality.AGGRESSIVE
    assert b2.transitions_remaining == 0


def test_phase41_hard_safety_override_keeps_survival_and_no_violation() -> None:
    governor = PersonalityStabilityGovernor(window_size=4, max_transitions=1)
    survival = _trace(
        cycle_id="hard",
        previous_execution=ExecutionPersonality.SURVIVAL,
        previous_risk=RiskPersonality.SURVIVAL,
        next_execution=ExecutionPersonality.SURVIVAL,
        next_risk=RiskPersonality.SURVIVAL,
        shifted=False,
        hard_safety_override=True,
    )
    result, budget, violation = governor.enforce(trace=survival, safety_hard_stop=True)
    assert violation is None
    assert result.execution_personality == ExecutionPersonality.SURVIVAL
    assert result.risk_personality == RiskPersonality.SURVIVAL
    assert "hard_safety_override" in budget.reason_codes


def test_phase41_personality_stability_visible_in_universe_mind(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase41_personality_stability" in result.advanced_intelligence
    payload = result.advanced_intelligence["phase41_personality_stability"]
    assert payload["deterministic"] is True
    assert isinstance(payload["budget"], dict)


def test_phase42_committee_escalation_bundle_deterministic_and_safety_veto_propagates() -> None:
    protocol = CommitteeEscalationProtocol()
    fund = {
        "bundle": {
            "safety_veto": True,
            "disagreement_map": {"severity": 0.8},
            "research_vote": {"committee": "research", "vote": "approve", "confidence": 0.8},
            "risk_vote": {"committee": "risk", "vote": "veto", "confidence": 0.9},
        }
    }
    survival = {"safety_veto": True}
    left = protocol.compile(cycle_id="x", fund_recommendation=fund, survival_doctrine=survival).to_dict()
    right = protocol.compile(cycle_id="x", fund_recommendation=fund, survival_doctrine=survival).to_dict()
    assert left == right
    assert left["safety_veto"] is True
    assert "safety_veto_propagated" in left["reason_codes"]
    assert left["veto_bundle"]["machine_readable"] is True


def test_phase42_committee_escalation_visible_in_ops_snapshot(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase42_committee_escalation" in result.advanced_intelligence
    payload = result.advanced_intelligence["phase42_committee_escalation"]
    assert payload["deterministic"] is True
    assert result.ops_snapshot is not None
    assert any(str(note).startswith("phase42_escalation_level=") for note in result.ops_snapshot.notes)


def test_phase43_institutional_gate_fail_closed_and_machine_readable_blockers() -> None:
    compiler = InstitutionalGateCompiler()
    left = compiler.compile(
        cycle_id="x",
        institutional_readiness={
            "approved": True,
            "deployment_certification": {"stage": "paper_ready"},
        },
        committee_escalation={"safety_veto": False},
        manual_gate_override={"live_go": False, "confirmation_file_exists": False},
    ).to_dict()
    right = compiler.compile(
        cycle_id="x",
        institutional_readiness={
            "approved": True,
            "deployment_certification": {"stage": "paper_ready"},
        },
        committee_escalation={"safety_veto": False},
        manual_gate_override={"live_go": False, "confirmation_file_exists": False},
    ).to_dict()
    assert left == right
    assert left["gate_open"] is False
    assert left["resolved_stage"] == "blocked"
    assert any(row["blocker_id"] == "manual_live_gate" for row in left["blockers"])
    fail_closed = compiler.compile(
        cycle_id="x2",
        institutional_readiness={},
        committee_escalation={},
        manual_gate_override={"live_go": True, "confirmation_file_exists": True},
    ).to_dict()
    assert fail_closed["fail_closed"] is True
    assert "missing_required_evidence" in fail_closed["reason_codes"]


def test_phase43_institutional_gate_visible_in_universe_mind(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase43_institutional_gate" in result.advanced_intelligence
    payload = result.advanced_intelligence["phase43_institutional_gate"]
    assert payload["deterministic"] is True
    assert isinstance(payload["blockers"], list)


def test_phase44_macro_micro_bridge_deterministic_and_contracts_on_macro_stress() -> None:
    bridge = MacroMicroDecisionBridge()
    payload = {
        "global_market_state": {"market_stress": 0.85, "confidence": {"overall": 0.9}},
        "calibration_state": {"calibrated_confidence": 0.35},
        "capital_constraints": {"hard_clamp": False},
        "execution_intelligence": {"quality_estimate": {"expected_net_edge_bps": 1.0}},
    }
    left = bridge.bridge(**payload).to_dict()
    right = bridge.bridge(**payload).to_dict()
    assert left == right
    assert left["contraction"]["size_scale"] < 1.0
    assert left["contraction"]["risk_scale"] < 1.0
    assert left["contraction"]["urgency_cap"] in {"low", "medium"}


def test_phase44_macro_micro_bridge_visible_in_universe_mind(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase44_macro_micro_bridge" in result.advanced_intelligence
    payload = result.advanced_intelligence["phase44_macro_micro_bridge"]
    assert payload["deterministic"] is True
    assert isinstance(payload["contraction"], dict)


def test_phase45_future_simulation_ensemble_deterministic_and_bounded(tmp_path) -> None:
    left = UniverseMind(str(tmp_path / "left"))
    right = UniverseMind(str(tmp_path / "right"))
    _seed_world(left.graph)
    _seed_world(right.graph)
    r1 = left.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    r2 = right.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    e1 = r1.advanced_intelligence["phase45_future_simulation_ensemble"]
    e2 = r2.advanced_intelligence["phase45_future_simulation_ensemble"]
    assert e1["ensemble_id"] == e2["ensemble_id"]
    assert e1["deterministic"] is True
    assert e1["bounded_compute"] is True
    assert len(e1["trees"]) <= int(e1["tree_limit"])
    assert all(int(row.get("branch_count", 0)) <= int(e1["branch_limit"]) for row in e1["trees"])


def test_phase45_future_simulation_ensemble_replay_export_visible(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    payload = result.advanced_intelligence["phase45_future_simulation_ensemble"]
    assert payload["replay_export"]["schema"] == "phase45_future_simulation_ensemble_v1"
    assert payload["replay_export"]["bounded_compute"] is True


def test_phase46_causal_twin_alignment_deterministic_and_stale_fallback() -> None:
    bridge = CausalTwinBridge(max_twin_age_s=60.0)
    simulation = {
        "trees": [{"tree_id": "a", "branch_count": 5}],
        "aggregate_pnl_envelope": {"expected": 5.0, "worst_case": -20.0, "best_case": 15.0},
        "confidence": {"overall_confidence": 0.7},
    }
    twin = {
        "as_of_ts": 1.0,
        "stale": False,
        "confidence": 0.8,
        "trend_bps": 40.0,
        "order_flow_pressure": 0.4,
        "spread_bps": 10.0,
        "vol": 0.01,
        "liquidity_pressure": 0.2,
        "multimodal_score": 0.1,
        "macro_risk_on": 0.3,
        "sentiment_score": 0.2,
    }
    first = bridge.align(simulation_ensemble=simulation, twin_state=twin).to_dict()
    second = bridge.align(simulation_ensemble=simulation, twin_state=twin).to_dict()
    assert first == second
    stale = bridge.align(simulation_ensemble=simulation, twin_state={"stale": True}).to_dict()
    assert stale["conservative_fallback"] is True
    assert "conservative_fallback_stale_twin" in stale["reason_codes"]


def test_phase46_causal_twin_alignment_visible_in_universe_mind(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase46_causal_twin_alignment" in result.advanced_intelligence
    payload = result.advanced_intelligence["phase46_causal_twin_alignment"]
    assert payload["deterministic"] is True
    assert isinstance(payload["divergence_signal"], dict)


def test_phase47_replay_distributed_bridge_deterministic_and_partial_failure_explicit() -> None:
    bridge = ReplayDistributedBridge(max_shards=4, timeout_s=1.0)
    payload = {
        "ensemble_id": "ens-1",
        "trees": [{"tree_id": "a"}, {"tree_id": "b"}],
        "tree_limit": 3,
    }
    health = {"backend": "redis_streams"}
    left = bridge.compile(
        run_id="run-1",
        symbols=["XBTUSD", "ETHUSD"],
        ensemble_payload=payload,
        compute_health=health,
        failed_symbols=[],
    ).to_dict()
    right = bridge.compile(
        run_id="run-1",
        symbols=["XBTUSD", "ETHUSD"],
        ensemble_payload=payload,
        compute_health=health,
        failed_symbols=[],
    ).to_dict()
    assert left == right
    failed = bridge.compile(
        run_id="run-1",
        symbols=["XBTUSD", "ETHUSD"],
        ensemble_payload=payload,
        compute_health={"backend": "local"},
        failed_symbols=["ETHUSD"],
    ).to_dict()
    assert failed["partial_failure"] is True
    assert "partial_shard_failure" in failed["reason_codes"]


def test_phase47_replay_distributed_bridge_visible_in_universe_mind(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase47_replay_distributed_bridge" in result.advanced_intelligence
    payload = result.advanced_intelligence["phase47_replay_distributed_bridge"]
    assert payload["deterministic"] is True
    assert isinstance(payload["shards"], list)


def test_phase48_evidence_index_deterministic_and_missing_artifacts_explicit() -> None:
    builder = EvidenceVaultIndexBuilder()
    left = builder.build(
        packet={"cycle_id": "c1"},
        ops_snapshot={},
        advanced_intelligence={},
    ).to_dict()
    right = builder.build(
        packet={"cycle_id": "c1"},
        ops_snapshot={},
        advanced_intelligence={},
    ).to_dict()
    assert left == right
    assert left["ready"] is False
    assert "missing_required_evidence_links" in left["reason_codes"]
    assert "phase36_ledger" in left["missing_required_artifacts"]


def test_phase48_evidence_index_visible_in_universe_mind(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase48_evidence_vault_index" in result.advanced_intelligence
    payload = result.advanced_intelligence["phase48_evidence_vault_index"]
    assert payload["deterministic"] is True
    assert isinstance(payload["pointers"], list)


def test_phase49_canary_envelope_deterministic_and_manual_gate_lock_blocks() -> None:
    compiler = LiveCanaryEnvelopeCompiler()
    left = compiler.compile(
        rollout_stage="paper_ready",
        manual_gate_required=True,
        manual_gate_present=False,
        safety_veto=False,
        evidence_ready=True,
        deployment_gate_open=True,
    ).to_dict()
    right = compiler.compile(
        rollout_stage="paper_ready",
        manual_gate_required=True,
        manual_gate_present=False,
        safety_veto=False,
        evidence_ready=True,
        deployment_gate_open=True,
    ).to_dict()
    assert left == right
    assert left["canary_allowed"] is False
    assert left["manual_gate_lock"] is True
    assert "manual_gate_lock_active" in left["reason_codes"]


def test_phase49_canary_envelope_visible_in_ops_and_meta(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase49_live_canary_envelope" in result.advanced_intelligence
    payload = result.advanced_intelligence["phase49_live_canary_envelope"]
    assert payload["deterministic"] is True
    assert result.ops_snapshot is not None
    assert "phase49_canary_envelope" in result.ops_snapshot.governance_observability


def test_phase50_certification_deterministic_and_residual_risk_explicit() -> None:
    compiler = Phase50CertificationCompiler()
    inputs = {
        "advanced_intelligence": {
            "phase35_institutional_readiness": {"approved": True, "report_id": "r1"},
            "phase49_live_canary_envelope": {"canary_allowed": True, "envelope_id": "e1"},
            "phase48_evidence_vault_index": {"ready": True, "index_id": "i1"},
            "phase43_institutional_gate": {"gate_open": True},
        },
        "ops_snapshot": {
            "rollout_stage": "paper_ready",
            "rollout_governance": {"rollback_readiness": {"rollback_ready": True, "dry_run_validated": True}},
        },
        "completed_phases": list(range(36, 51)),
    }
    left = compiler.compile(**inputs).to_dict()
    right = compiler.compile(**inputs).to_dict()
    assert left == right
    assert left["recommended_next_phase"] is None
    assert "rows" in left["residual_risk_truth_table"]
    assert left["residual_risk_truth_table"]["unresolved_count"] == 0


def test_phase50_certification_visible_in_universe_mind(tmp_path) -> None:
    mind = UniverseMind(str(tmp_path))
    _seed_world(mind.graph)
    result = mind.run_cycle(symbol="XBTUSD", venue="kraken_spot", proposals=[_proposal()])
    assert "phase50_certification" in result.advanced_intelligence
    payload = result.advanced_intelligence["phase50_certification"]
    assert payload["deterministic"] is True
    assert isinstance(payload["residual_risk_truth_table"], dict)
