from __future__ import annotations

import json

from autonomous_investment_robot.services.universe_core import (
    PromotionState,
    ShieldDecision,
    UniverseOpsService,
    WorldStateGraph,
    build_event,
)


def _healthy_world():
    graph = WorldStateGraph()
    symbol = "XBTUSD"
    events = (
        (
            "MarketTickEvent",
            {"symbol": symbol, "venue": "kraken_spot", "mid": 100.0, "spread_bps": 6.0, "trend_bps": 20.0, "realized_vol": 0.01},
        ),
        (
            "BookSnapshotEvent",
            {"symbol": symbol, "venue": "kraken_spot", "spread_bps": 6.0, "depth_notional": 25_000.0},
        ),
        (
            "AccountSnapshotEvent",
            {"symbol": symbol, "venue": "kraken_spot", "equity_quote": 5_000.0, "free_quote": 4_000.0, "exposure_quote": 250.0, "drawdown_pct": 0.01},
        ),
        (
            "HealthEvent",
            {"symbol": symbol, "venue": "kraken_spot", "status": "OK", "latency_ms": 50.0, "health_score": 0.95, "stale_feed": False, "desync": False},
        ),
        (
            "RiskEvent",
            {"symbol": symbol, "venue": "kraken_spot", "mode": "normal", "model_confidence": 0.80, "uncertainty_bps": 20.0, "hard_stop": False, "observe_only": False},
        ),
        (
            "RegimeEvent",
            {"symbol": symbol, "venue": "kraken_spot", "regime": "TREND", "confidence": 0.80, "volatility_regime": "LOW_VOL", "liquidity_regime": "DEEP", "expansion_state": "COMPRESSION"},
        ),
    )
    for idx, (event_type, payload) in enumerate(events):
        graph.apply(
            build_event(
                event_type=event_type,
                source="test",
                partition_key=symbol,
                payload=payload,
                ts=100.0 + float(idx),
            )
        )
    return graph.snapshot()


def _base_learning_summary() -> dict[str, object]:
    return {
        "promotion_readiness_score": 0.82,
        "walk_forward_holdout_grade": 0.74,
        "counterfactual_overall_grade_delta": 0.08,
        "memory_grading_drift": 0.06,
        "replay_batch_status": {
            "enabled": True,
            "failed": False,
            "batch_id": "batch-phase10",
            "reproducibility_metadata": {"replay_session_id": "session-phase10"},
        },
        "top_strategy_candidates": [
            {
                "strategy_fingerprint": "fp-micro-1",
                "current_stage": "paper",
                "next_stage_candidate": "limited_live",
            }
        ],
        "quarantine_strategy_list": [],
        "promotion_ladder_state": {
            "activation_gates": [
                {
                    "strategy_fingerprint": "fp-micro-1",
                    "allowed": True,
                    "resolved_stage": "limited_live",
                    "capital_scaling_factor": 0.25,
                    "per_strategy_exposure_ceiling": 0.10,
                    "risk_multiplier": 0.50,
                    "kill_switch": False,
                    "reason_codes": [],
                }
            ]
        },
    }


def _base_execution_intel() -> dict[str, object]:
    return {
        "mode": "balanced_alpha",
        "stress_index": {"score": 0.20},
        "abort_decision": {"should_abort": False, "reason_codes": []},
        "advisory_escalation": {"severity": "none", "severity_score": 0.0, "reason_codes": []},
        "quality_estimate": {"expected_total_cost_bps": 2.5, "expected_net_edge_bps": 8.0, "execution_quality_score": 0.82},
    }


def test_phase10_blocked_candidate_cannot_be_approved() -> None:
    learning = _base_learning_summary()
    learning["top_strategy_candidates"] = [
        {
            "strategy_fingerprint": "fp-micro-1",
            "current_stage": "paper",
            "next_stage_candidate": "quarantine",
        }
    ]
    ops = UniverseOpsService().assess(
        world=_healthy_world(),
        shield=ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=[], kill_switch=False),
        research=PromotionState(current_stage="paper_mode", next_stage="limited_live", ready_to_promote=True, score=0.80),
        learning_summary=learning,
        execution_intelligence=_base_execution_intel(),
    )
    decision = ops.rollout_governance["decision"]
    assert decision["candidate_stage"] == "blocked"
    assert decision["approved"] is False
    assert decision["blocked"] is True
    assert "candidate_stage_blocked" in decision["reason_codes"]
    assert ops.manual_gate_required is False
    assert ops.production_readiness["blocked"] is True
    assert ops.production_readiness["stage"] == "blocked"


def test_phase10_requires_manual_gate_for_limited_live_promotion() -> None:
    ops = UniverseOpsService().assess(
        world=_healthy_world(),
        shield=ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=[], kill_switch=False),
        research=PromotionState(current_stage="paper_mode", next_stage="limited_live", ready_to_promote=True, score=0.80),
        learning_summary=_base_learning_summary(),
        execution_intelligence=_base_execution_intel(),
    )
    decision = ops.rollout_governance["decision"]
    assert decision["candidate_stage"] == "limited_live_ready"
    assert decision["approved"] is False
    assert decision["operator_approval_required"] is True
    assert decision["operator_approval_present"] is False
    assert "manual_live_gate_required" in decision["reason_codes"]
    assert ops.rollout_stage == "blocked"
    assert ops.manual_gate_required is True
    assert ops.production_readiness["replay_ready"] is True
    assert ops.production_readiness["shadow_ready"] is True
    assert ops.production_readiness["paper_ready"] is True
    assert ops.production_readiness["limited_live_ready"] is False
    assert ops.production_readiness["manual_gate_satisfied"] is False


def test_phase10_can_promote_with_operator_approval_and_deterministic_artifact() -> None:
    learning = _base_learning_summary()
    learning["rollback_dry_run_validated"] = True
    learning["manual_live_env_gate"] = {
        "live_go": True,
        "confirmation_file_exists": True,
        "confirmation_file": "ops/live_operator_confirmation.txt",
    }
    learning["config_drift_check_passed"] = True
    learning["distributed_audit_stream_ready"] = True
    learning["operator_approval_artifact"] = {
        "artifact_id": "approval-1",
        "stage": "limited_live",
        "approved": True,
        "approver": "operator_a",
        "approval_ts": 1_700_000_000.0,
        "reason_codes": ["manual_gate_ok"],
        "metadata": {"ticket": "OPS-42"},
    }

    service = UniverseOpsService()
    world = _healthy_world()
    shield = ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=[], kill_switch=False)
    research = PromotionState(current_stage="paper_mode", next_stage="limited_live", ready_to_promote=True, score=0.80)
    execution_intel = _base_execution_intel()

    first = service.assess(
        world=world,
        shield=shield,
        research=research,
        learning_summary=learning,
        execution_intelligence=execution_intel,
    )
    second = service.assess(
        world=world,
        shield=shield,
        research=research,
        learning_summary=learning,
        execution_intelligence=execution_intel,
    )

    decision = first.rollout_governance["decision"]
    assert decision["candidate_stage"] == "limited_live_ready"
    assert decision["resolved_stage"] == "limited_live_ready"
    assert decision["approved"] is True
    assert decision["blocked"] is False
    assert first.rollout_stage == "limited_live_ready"
    assert first.manual_gate_required is False

    readiness = first.production_readiness
    assert readiness["limited_live_ready"] is True
    assert readiness["scaled_live_candidate_ready"] is False
    assert readiness["rollback_dry_run_validated"] is True
    assert readiness["manual_gate_satisfied"] is True
    assert readiness["artifact_id"] == second.production_readiness["artifact_id"]

    checklist_by_id = {row["item_id"]: row for row in readiness["checklist"]}
    assert checklist_by_id["config_drift_check_passed"]["passed"] is True
    assert checklist_by_id["distributed_audit_stream_ready"]["passed"] is True
    assert checklist_by_id["rollback_dry_run_validated"]["passed"] is True


def test_phase19_replay_determinism_gate_blocks_promotion_changes() -> None:
    learning = _base_learning_summary()
    learning["rollback_dry_run_validated"] = True
    learning["manual_live_env_gate"] = {
        "live_go": True,
        "confirmation_file_exists": True,
        "confirmation_file": "ops/live_operator_confirmation.txt",
    }
    learning["replay_batch_status"]["deterministic"] = False
    learning["operator_approval_artifact"] = {
        "artifact_id": "approval-determinism-fail",
        "stage": "limited_live",
        "approved": True,
        "approver": "operator_a",
        "approval_ts": 1_700_000_010.0,
        "reason_codes": ["manual_gate_ok"],
        "metadata": {"ticket": "OPS-99"},
    }
    ops = UniverseOpsService().assess(
        world=_healthy_world(),
        shield=ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=[], kill_switch=False),
        research=PromotionState(current_stage="paper_mode", next_stage="limited_live", ready_to_promote=True, score=0.80),
        learning_summary=learning,
        execution_intelligence=_base_execution_intel(),
    )
    decision = ops.rollout_governance["decision"]
    assert decision["promotion_change_requested"] is True
    assert decision["replay_determinism_gate_passed"] is False
    assert decision["approved"] is False
    assert "replay_determinism_gate_failed" in decision["reason_codes"]
    evidence = ops.rollout_governance["evidence_bundles"][0]
    assert evidence["replay_contract"]["deterministic"] is False
    checklist_by_id = {row["item_id"]: row for row in ops.production_readiness["checklist"]}
    assert checklist_by_id["replay_determinism_gate_passed"]["required"] is True
    assert checklist_by_id["replay_determinism_gate_passed"]["passed"] is False


def test_phase19_replay_and_rollback_evidence_are_deterministic_under_replay() -> None:
    learning = _base_learning_summary()
    learning["rollback_dry_run_validated"] = True
    learning["manual_live_env_gate"] = {
        "live_go": True,
        "confirmation_file_exists": True,
        "confirmation_file": "ops/live_operator_confirmation.txt",
    }
    learning["operator_approval_artifact"] = {
        "artifact_id": "approval-replay-evidence",
        "stage": "limited_live",
        "approved": True,
        "approver": "operator_b",
        "approval_ts": 1_700_000_020.0,
        "reason_codes": ["manual_gate_ok"],
        "metadata": {"ticket": "OPS-100"},
    }
    service = UniverseOpsService()
    first = service.assess(
        world=_healthy_world(),
        shield=ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=[], kill_switch=False),
        research=PromotionState(current_stage="paper_mode", next_stage="limited_live", ready_to_promote=True, score=0.80),
        learning_summary=learning,
        execution_intelligence=_base_execution_intel(),
    )
    second = service.assess(
        world=_healthy_world(),
        shield=ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=[], kill_switch=False),
        research=PromotionState(current_stage="paper_mode", next_stage="limited_live", ready_to_promote=True, score=0.80),
        learning_summary=learning,
        execution_intelligence=_base_execution_intel(),
    )
    decision_first = first.rollout_governance["decision"]
    decision_second = second.rollout_governance["decision"]
    assert decision_first["replay_determinism_gate_passed"] is True
    assert decision_first["replay_contract_id"] == decision_second["replay_contract_id"]
    evidence_first = first.rollout_governance["evidence_bundles"][0]
    evidence_second = second.rollout_governance["evidence_bundles"][0]
    assert evidence_first["bundle_id"] == evidence_second["bundle_id"]
    assert evidence_first["replay_contract_id"] == decision_first["replay_contract_id"]
    rollback_first = first.rollout_governance["rollback_readiness"]["records"]
    rollback_second = second.rollout_governance["rollback_readiness"]["records"]
    assert rollback_first["replay_promotion_contract_id"] == decision_first["replay_contract_id"]
    assert rollback_first["replay_determinism_gate_passed"] is True
    assert rollback_first["promotion_change_requested"] is True
    assert rollback_first["replay_promotion_contract_id"] == rollback_second["replay_promotion_contract_id"]


def test_phase22_rollback_dry_run_artifact_can_validate_governance_rollback_readiness() -> None:
    learning = _base_learning_summary()
    learning["manual_live_env_gate"] = {
        "live_go": True,
        "confirmation_file_exists": True,
        "confirmation_file": "ops/live_operator_confirmation.txt",
    }
    learning["rollback_dry_run_artifact"] = {
        "validated": True,
        "artifact_id": "rollback-artifact-1",
        "reason_codes": ["runtime_audit_validated"],
    }
    ops = UniverseOpsService().assess(
        world=_healthy_world(),
        shield=ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=[], kill_switch=False),
        research=PromotionState(current_stage="paper_mode", next_stage="limited_live", ready_to_promote=True, score=0.80),
        learning_summary=learning,
        execution_intelligence=_base_execution_intel(),
    )
    rollback = ops.rollout_governance["rollback_readiness"]
    assert rollback["dry_run_validated"] is True
    assert rollback["rollback_ready"] is True
    assert rollback["records"]["rollback_dry_run_artifact_id"] == "rollback-artifact-1"
    assert rollback["records"]["rollback_dry_run_source"] == "rollback_artifact"


def test_phase22_rollback_readiness_is_false_when_dry_run_not_validated() -> None:
    ops = UniverseOpsService().assess(
        world=_healthy_world(),
        shield=ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=[], kill_switch=False),
        research=PromotionState(current_stage="paper_mode", next_stage="limited_live", ready_to_promote=True, score=0.80),
        learning_summary=_base_learning_summary(),
        execution_intelligence=_base_execution_intel(),
    )
    rollback = ops.rollout_governance["rollback_readiness"]
    assert rollback["dry_run_validated"] is False
    assert rollback["rollback_ready"] is False
    assert "rollback_dry_run_not_validated" in rollback["reason_codes"]


def test_phase24_dual_control_requires_manual_live_env_gate_even_with_operator_approval() -> None:
    learning = _base_learning_summary()
    learning["rollback_dry_run_validated"] = True
    learning["operator_approval_artifact"] = {
        "artifact_id": "approval-without-env-gate",
        "stage": "limited_live",
        "approved": True,
        "approver": "operator_c",
        "approval_ts": 1_700_000_030.0,
        "reason_codes": ["manual_gate_ok"],
        "metadata": {"ticket": "OPS-101"},
    }
    learning["manual_live_env_gate"] = {
        "live_go": False,
        "confirmation_file_exists": False,
        "confirmation_file": "ops/live_operator_confirmation.txt",
    }
    ops = UniverseOpsService().assess(
        world=_healthy_world(),
        shield=ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=[], kill_switch=False),
        research=PromotionState(current_stage="paper_mode", next_stage="limited_live", ready_to_promote=True, score=0.80),
        learning_summary=learning,
        execution_intelligence=_base_execution_intel(),
    )
    decision = ops.rollout_governance["decision"]
    assert decision["operator_approval_present"] is True
    assert decision["manual_live_env_gate_present"] is False
    assert decision["approved"] is False
    assert "manual_live_env_gate_required" in decision["reason_codes"]


def test_phase24_dual_control_accepts_env_operator_approval_artifact(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "live_governance_approval.json"
    artifact_path.write_text(
        json.dumps(
            {
                "artifact_id": "env-approval-1",
                "stage": "limited_live_ready",
                "approved": True,
                "approver": "operator_env",
                "approval_ts": 1_700_000_040.0,
                "reason_codes": ["env_artifact_ok"],
                "metadata": {"source": "test"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTONOMOUS_UNIVERSE_OPS_ENV_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("AUTONOMOUS_LIVE_OPERATOR_APPROVAL_ARTIFACT_FILE", str(artifact_path))
    learning = _base_learning_summary()
    learning["rollback_dry_run_validated"] = True
    learning["manual_live_env_gate"] = {
        "live_go": True,
        "confirmation_file_exists": True,
        "confirmation_file": "ops/live_operator_confirmation.txt",
    }
    ops = UniverseOpsService().assess(
        world=_healthy_world(),
        shield=ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=[], kill_switch=False),
        research=PromotionState(current_stage="paper_mode", next_stage="limited_live", ready_to_promote=True, score=0.80),
        learning_summary=learning,
        execution_intelligence=_base_execution_intel(),
    )
    decision = ops.rollout_governance["decision"]
    assert decision["operator_approval_present"] is True
    assert decision["manual_live_env_gate_present"] is True
    assert decision["approved"] is True
