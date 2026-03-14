from __future__ import annotations

from hashlib import sha256
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .cross_asset import UniverseAllocation
from .live_canary_envelope import LiveCanaryEnvelopeCompiler
from .mission import MissionDecision
from .parliament import ParliamentVerdict
from .replay_ladder import build_promotion_replay_contract
from .research import PromotionState
from .shield import ShieldDecision
from .state import WorldStateSnapshot


PHASE10_ROLLOUT_STAGES: tuple[str, ...] = (
    "offline_replay",
    "shadow_ready",
    "paper_ready",
    "limited_live_ready",
    "scaled_live_candidate",
    "blocked",
)

_STAGE_RANK: dict[str, int] = {
    "offline_replay": 0,
    "shadow_ready": 1,
    "paper_ready": 2,
    "limited_live_ready": 3,
    "scaled_live_candidate": 4,
    "blocked": 5,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_bridge_enabled() -> bool:
    # Hermetic by default: do not ingest operator gate approvals from process env
    # unless explicitly enabled for controlled runtime wiring.
    return _truthy(os.getenv("AUTONOMOUS_UNIVERSE_OPS_ENV_BRIDGE_ENABLED", "0"))


def _normalize_rollout_stage(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "research": "offline_replay",
        "walk_forward": "offline_replay",
        "walk_forward_validated": "offline_replay",
        "sandbox_shadow": "offline_replay",
        "shadow": "shadow_ready",
        "shadow_mode": "shadow_ready",
        "shadow_live": "shadow_ready",
        "paper": "paper_ready",
        "paper_mode": "paper_ready",
        "micro_capital_live": "paper_ready",
        "limited_live": "limited_live_ready",
        "scaled_live": "limited_live_ready",
        "core_live": "scaled_live_candidate",
        "scaled_live_candidate": "scaled_live_candidate",
        "demotion_watch": "blocked",
        "quarantine": "blocked",
        "observe_only": "blocked",
        "hard_stop": "blocked",
    }
    normalized = aliases.get(raw, raw)
    if normalized not in _STAGE_RANK:
        return "offline_replay"
    return normalized


def _is_live_candidate_stage(stage: str) -> bool:
    return _normalize_rollout_stage(stage) in {"paper_ready", "limited_live_ready", "scaled_live_candidate"}


@dataclass(frozen=True)
class ActivationGateContract:
    strategy_fingerprint: str
    allowed: bool
    resolved_stage: str
    capital_scaling_factor: float
    per_strategy_exposure_ceiling: float
    risk_multiplier: float
    kill_switch: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_fingerprint": self.strategy_fingerprint,
            "allowed": bool(self.allowed),
            "resolved_stage": self.resolved_stage,
            "capital_scaling_factor": float(self.capital_scaling_factor),
            "per_strategy_exposure_ceiling": float(self.per_strategy_exposure_ceiling),
            "risk_multiplier": float(self.risk_multiplier),
            "kill_switch": bool(self.kill_switch),
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ActivationGateContract":
        reasons = payload.get("reason_codes", [])
        return cls(
            strategy_fingerprint=str(payload.get("strategy_fingerprint", "") or ""),
            allowed=bool(payload.get("allowed", False)),
            resolved_stage=_normalize_rollout_stage(payload.get("resolved_stage", "")),
            capital_scaling_factor=_clamp(_safe_float(payload.get("capital_scaling_factor", 0.0), 0.0), 0.0, 1.0),
            per_strategy_exposure_ceiling=_clamp(_safe_float(payload.get("per_strategy_exposure_ceiling", 0.0), 0.0), 0.0, 1.0),
            risk_multiplier=_clamp(_safe_float(payload.get("risk_multiplier", 0.0), 0.0), 0.0, 2.0),
            kill_switch=bool(payload.get("kill_switch", False)),
            reason_codes=tuple(str(item) for item in reasons) if isinstance(reasons, list) else (),
        )


@dataclass(frozen=True)
class OperatorApprovalArtifact:
    artifact_id: str
    stage: str
    approved: bool
    approver: str
    approval_ts: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "stage": self.stage,
            "approved": bool(self.approved),
            "approver": self.approver,
            "approval_ts": float(self.approval_ts),
            "reason_codes": list(self.reason_codes),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "OperatorApprovalArtifact":
        reasons = payload.get("reason_codes", [])
        return cls(
            artifact_id=str(payload.get("artifact_id", "") or ""),
            stage=_normalize_rollout_stage(payload.get("stage", "")),
            approved=bool(payload.get("approved", False)),
            approver=str(payload.get("approver", "") or ""),
            approval_ts=max(0.0, _safe_float(payload.get("approval_ts", 0.0), 0.0)),
            reason_codes=tuple(str(item) for item in reasons) if isinstance(reasons, list) else (),
            metadata=_safe_mapping(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class PromotionEvidenceBundle:
    bundle_id: str
    stage: str
    replay_batch_id: str
    replay_session_id: str
    replay_contract_id: str = ""
    strategy_fingerprints: tuple[str, ...] = field(default_factory=tuple)
    replay_contract: dict[str, Any] = field(default_factory=dict)
    execution_diagnostics: dict[str, Any] = field(default_factory=dict)
    regression_metrics: dict[str, Any] = field(default_factory=dict)
    safety_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "stage": self.stage,
            "replay_batch_id": self.replay_batch_id,
            "replay_session_id": self.replay_session_id,
            "replay_contract_id": self.replay_contract_id,
            "strategy_fingerprints": list(self.strategy_fingerprints),
            "replay_contract": dict(self.replay_contract),
            "execution_diagnostics": dict(self.execution_diagnostics),
            "regression_metrics": dict(self.regression_metrics),
            "safety_metrics": dict(self.safety_metrics),
        }


@dataclass(frozen=True)
class PromotionGovernanceDecision:
    decision_id: str
    candidate_stage: str
    resolved_stage: str
    approved: bool
    blocked: bool
    regression_gate_passed: bool
    safety_gate_passed: bool
    activation_gate_passed: bool
    replay_determinism_gate_passed: bool
    operator_approval_required: bool
    operator_approval_present: bool
    manual_live_env_gate_required: bool = False
    manual_live_env_gate_present: bool = False
    replay_contract_id: str = ""
    promotion_change_requested: bool = False
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "candidate_stage": self.candidate_stage,
            "resolved_stage": self.resolved_stage,
            "approved": bool(self.approved),
            "blocked": bool(self.blocked),
            "regression_gate_passed": bool(self.regression_gate_passed),
            "safety_gate_passed": bool(self.safety_gate_passed),
            "activation_gate_passed": bool(self.activation_gate_passed),
            "replay_determinism_gate_passed": bool(self.replay_determinism_gate_passed),
            "operator_approval_required": bool(self.operator_approval_required),
            "operator_approval_present": bool(self.operator_approval_present),
            "manual_live_env_gate_required": bool(self.manual_live_env_gate_required),
            "manual_live_env_gate_present": bool(self.manual_live_env_gate_present),
            "replay_contract_id": self.replay_contract_id,
            "promotion_change_requested": bool(self.promotion_change_requested),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class RollbackReadinessRecord:
    rollback_ready: bool
    dry_run_validated: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    feature_flags: dict[str, Any] = field(default_factory=dict)
    records: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollback_ready": bool(self.rollback_ready),
            "dry_run_validated": bool(self.dry_run_validated),
            "reason_codes": list(self.reason_codes),
            "feature_flags": dict(self.feature_flags),
            "records": dict(self.records),
        }


@dataclass(frozen=True)
class RolloutGovernanceSnapshot:
    stage: str
    decision: PromotionGovernanceDecision
    activation_gates: list[ActivationGateContract] = field(default_factory=list)
    operator_approvals: list[OperatorApprovalArtifact] = field(default_factory=list)
    evidence_bundles: list[PromotionEvidenceBundle] = field(default_factory=list)
    rollback_readiness: RollbackReadinessRecord = field(
        default_factory=lambda: RollbackReadinessRecord(rollback_ready=True, dry_run_validated=False)
    )
    observability: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "decision": self.decision.to_dict(),
            "activation_gates": [row.to_dict() for row in self.activation_gates],
            "operator_approvals": [row.to_dict() for row in self.operator_approvals],
            "evidence_bundles": [row.to_dict() for row in self.evidence_bundles],
            "rollback_readiness": self.rollback_readiness.to_dict(),
            "observability": dict(self.observability),
        }


@dataclass(frozen=True)
class ProductionReadinessArtifact:
    artifact_id: str
    stage: str
    replay_ready: bool
    shadow_ready: bool
    paper_ready: bool
    limited_live_ready: bool
    scaled_live_candidate_ready: bool
    blocked: bool
    manual_gate_required: bool
    manual_gate_satisfied: bool
    rollback_ready: bool
    rollback_dry_run_validated: bool
    checklist: list[dict[str, Any]] = field(default_factory=list)
    evidence_bundle_ids: tuple[str, ...] = field(default_factory=tuple)
    observability: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "stage": self.stage,
            "replay_ready": bool(self.replay_ready),
            "shadow_ready": bool(self.shadow_ready),
            "paper_ready": bool(self.paper_ready),
            "limited_live_ready": bool(self.limited_live_ready),
            "scaled_live_candidate_ready": bool(self.scaled_live_candidate_ready),
            "blocked": bool(self.blocked),
            "manual_gate_required": bool(self.manual_gate_required),
            "manual_gate_satisfied": bool(self.manual_gate_satisfied),
            "rollback_ready": bool(self.rollback_ready),
            "rollback_dry_run_validated": bool(self.rollback_dry_run_validated),
            "checklist": [dict(row) for row in self.checklist],
            "evidence_bundle_ids": [str(item) for item in self.evidence_bundle_ids],
            "observability": dict(self.observability),
        }


@dataclass(frozen=True)
class UniverseOpsSnapshot:
    readiness_score: float
    rollout_stage: str
    manual_gate_required: bool
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    world_state_available: bool = True
    world_state_as_of: float = 0.0
    domain_freshness_s: dict[str, float] = field(default_factory=dict)
    world_state_summary: dict[str, Any] = field(default_factory=dict)
    primary_symbol_state: dict[str, Any] = field(default_factory=dict)
    mission_selected: str = "observation_only"
    mission_confidence: float = 0.0
    mission_reason_codes: list[str] = field(default_factory=list)
    execution_posture_hint: str = ""
    shield_posture_hint: str = ""
    conservative_fallback_flag: bool = False
    mission_transition: dict[str, Any] = field(default_factory=dict)
    allowed_strategy_families: list[str] = field(default_factory=list)
    no_trade_preference: bool = False
    parliament_mode: str = "top_1"
    parliament_no_trade: bool = False
    parliament_selected_strategies: list[str] = field(default_factory=list)
    parliament_reasons: list[str] = field(default_factory=list)
    parliament_top_score: float = 0.0
    parliament_allocations: list[dict[str, Any]] = field(default_factory=list)
    meta_regime_cluster: str = ""
    meta_exploration_budget: float = 0.0
    meta_exploitation_budget: float = 1.0
    meta_risk_scale: float = 1.0
    meta_memory_records: int = 0
    meta_strategy_weights: list[dict[str, Any]] = field(default_factory=list)
    shield_mode: str = "normal"
    previous_shield_mode: str = "normal"
    escalation_reason_codes: list[str] = field(default_factory=list)
    escalation_inputs_summary: dict[str, Any] = field(default_factory=dict)
    strategy_health_summary: dict[str, Any] = field(default_factory=dict)
    meta_risk_summary: dict[str, Any] = field(default_factory=dict)
    hysteresis_state: dict[str, Any] = field(default_factory=dict)
    no_trade_forced: bool = False
    hard_stop_forced: bool = False
    recovery_eligibility: dict[str, Any] = field(default_factory=dict)
    memory_records_written: int = 0
    grading_state_summary: dict[str, Any] = field(default_factory=dict)
    latest_policy_grade_summary: dict[str, Any] = field(default_factory=dict)
    promotion_candidates_count: int = 0
    demotion_candidates_count: int = 0
    retirement_candidates_count: int = 0
    shield_aware_learning_summary: dict[str, Any] = field(default_factory=dict)
    memory_compaction_summary: dict[str, Any] = field(default_factory=dict)
    replay_evidence_summary: dict[str, Any] = field(default_factory=dict)
    bounded_retention_health: dict[str, Any] = field(default_factory=dict)
    replay_batch_status: dict[str, Any] = field(default_factory=dict)
    promotion_ladder_state: dict[str, Any] = field(default_factory=dict)
    top_strategy_candidates: list[dict[str, Any]] = field(default_factory=list)
    quarantine_strategy_list: list[str] = field(default_factory=list)
    promotion_readiness_score: float = 0.0
    replay_backlog_depth: int = 0
    memory_grading_drift: float = 0.0
    replay_session_id: str = ""
    decision_reconstruction_count: int = 0
    walk_forward_holdout_grade: float = 0.0
    counterfactual_overall_grade_delta: float = 0.0
    execution_personality_mode: str = ""
    execution_stress_index: float = 0.0
    execution_quality_score: float = 0.0
    execution_abort: bool = False
    execution_abort_reason_codes: list[str] = field(default_factory=list)
    execution_expected_total_cost_bps: float = 0.0
    execution_expected_net_edge_bps: float = 0.0
    execution_risk_scale_hint: float = 1.0
    execution_liquidity_flags: list[str] = field(default_factory=list)
    execution_advisory_severity: str = ""
    execution_advisory_score: float = 0.0
    execution_advisory_reason_codes: list[str] = field(default_factory=list)
    execution_survival_protocol: str = ""
    execution_spoofing_score: float = 0.0
    execution_spoofing_flag: bool = False
    advanced_intelligence: dict[str, Any] = field(default_factory=dict)
    phase26_global_market_state: dict[str, Any] = field(default_factory=dict)
    phase27_horizon_alignment: dict[str, Any] = field(default_factory=dict)
    phase28_market_energy: dict[str, Any] = field(default_factory=dict)
    phase29_future_simulation: dict[str, Any] = field(default_factory=dict)
    phase30_cross_reality_signal: dict[str, Any] = field(default_factory=dict)
    phase31_personality_trace: dict[str, Any] = field(default_factory=dict)
    phase32_survival_doctrine: dict[str, Any] = field(default_factory=dict)
    phase33_evolutionary_research: dict[str, Any] = field(default_factory=dict)
    phase34_fund_brain: dict[str, Any] = field(default_factory=dict)
    phase35_institutional_readiness: dict[str, Any] = field(default_factory=dict)
    rollout_governance: dict[str, Any] = field(default_factory=dict)
    governance_observability: dict[str, Any] = field(default_factory=dict)
    production_readiness: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "readiness_score": self.readiness_score,
            "rollout_stage": self.rollout_stage,
            "manual_gate_required": self.manual_gate_required,
            "blockers": list(self.blockers),
            "notes": list(self.notes),
            "world_state_available": self.world_state_available,
            "world_state_as_of": self.world_state_as_of,
            "domain_freshness_s": dict(self.domain_freshness_s),
            "world_state_summary": dict(self.world_state_summary),
            "primary_symbol_state": dict(self.primary_symbol_state),
            "mission_selected": self.mission_selected,
            "mission_confidence": self.mission_confidence,
            "mission_reason_codes": list(self.mission_reason_codes),
            "execution_posture_hint": self.execution_posture_hint,
            "shield_posture_hint": self.shield_posture_hint,
            "conservative_fallback_flag": self.conservative_fallback_flag,
            "mission_transition": dict(self.mission_transition),
            "allowed_strategy_families": list(self.allowed_strategy_families),
            "no_trade_preference": self.no_trade_preference,
            "parliament_mode": self.parliament_mode,
            "parliament_no_trade": self.parliament_no_trade,
            "parliament_selected_strategies": list(self.parliament_selected_strategies),
            "parliament_reasons": list(self.parliament_reasons),
            "parliament_top_score": float(self.parliament_top_score),
            "parliament_allocations": [dict(row) for row in self.parliament_allocations],
            "meta_regime_cluster": self.meta_regime_cluster,
            "meta_exploration_budget": float(self.meta_exploration_budget),
            "meta_exploitation_budget": float(self.meta_exploitation_budget),
            "meta_risk_scale": float(self.meta_risk_scale),
            "meta_memory_records": int(self.meta_memory_records),
            "meta_strategy_weights": [dict(row) for row in self.meta_strategy_weights],
            "shield_mode": self.shield_mode,
            "previous_shield_mode": self.previous_shield_mode,
            "escalation_reason_codes": list(self.escalation_reason_codes),
            "escalation_inputs_summary": dict(self.escalation_inputs_summary),
            "strategy_health_summary": dict(self.strategy_health_summary),
            "meta_risk_summary": dict(self.meta_risk_summary),
            "hysteresis_state": dict(self.hysteresis_state),
            "no_trade_forced": bool(self.no_trade_forced),
            "hard_stop_forced": bool(self.hard_stop_forced),
            "recovery_eligibility": dict(self.recovery_eligibility),
            "memory_records_written": int(self.memory_records_written),
            "grading_state_summary": dict(self.grading_state_summary),
            "latest_policy_grade_summary": dict(self.latest_policy_grade_summary),
            "promotion_candidates_count": int(self.promotion_candidates_count),
            "demotion_candidates_count": int(self.demotion_candidates_count),
            "retirement_candidates_count": int(self.retirement_candidates_count),
            "shield_aware_learning_summary": dict(self.shield_aware_learning_summary),
            "memory_compaction_summary": dict(self.memory_compaction_summary),
            "replay_evidence_summary": dict(self.replay_evidence_summary),
            "bounded_retention_health": dict(self.bounded_retention_health),
            "replay_batch_status": dict(self.replay_batch_status),
            "promotion_ladder_state": dict(self.promotion_ladder_state),
            "top_strategy_candidates": [dict(row) for row in self.top_strategy_candidates],
            "quarantine_strategy_list": [str(item) for item in self.quarantine_strategy_list],
            "promotion_readiness_score": float(self.promotion_readiness_score),
            "replay_backlog_depth": int(self.replay_backlog_depth),
            "memory_grading_drift": float(self.memory_grading_drift),
            "replay_session_id": self.replay_session_id,
            "decision_reconstruction_count": int(self.decision_reconstruction_count),
            "walk_forward_holdout_grade": float(self.walk_forward_holdout_grade),
            "counterfactual_overall_grade_delta": float(self.counterfactual_overall_grade_delta),
            "execution_personality_mode": self.execution_personality_mode,
            "execution_stress_index": float(self.execution_stress_index),
            "execution_quality_score": float(self.execution_quality_score),
            "execution_abort": bool(self.execution_abort),
            "execution_abort_reason_codes": list(self.execution_abort_reason_codes),
            "execution_expected_total_cost_bps": float(self.execution_expected_total_cost_bps),
            "execution_expected_net_edge_bps": float(self.execution_expected_net_edge_bps),
            "execution_risk_scale_hint": float(self.execution_risk_scale_hint),
            "execution_liquidity_flags": [str(item) for item in self.execution_liquidity_flags],
            "execution_advisory_severity": self.execution_advisory_severity,
            "execution_advisory_score": float(self.execution_advisory_score),
            "execution_advisory_reason_codes": [str(item) for item in self.execution_advisory_reason_codes],
            "execution_survival_protocol": self.execution_survival_protocol,
            "execution_spoofing_score": float(self.execution_spoofing_score),
            "execution_spoofing_flag": bool(self.execution_spoofing_flag),
            "advanced_intelligence": dict(self.advanced_intelligence),
            "phase26_global_market_state": dict(self.phase26_global_market_state),
            "phase27_horizon_alignment": dict(self.phase27_horizon_alignment),
            "phase28_market_energy": dict(self.phase28_market_energy),
            "phase29_future_simulation": dict(self.phase29_future_simulation),
            "phase30_cross_reality_signal": dict(self.phase30_cross_reality_signal),
            "phase31_personality_trace": dict(self.phase31_personality_trace),
            "phase32_survival_doctrine": dict(self.phase32_survival_doctrine),
            "phase33_evolutionary_research": dict(self.phase33_evolutionary_research),
            "phase34_fund_brain": dict(self.phase34_fund_brain),
            "phase35_institutional_readiness": dict(self.phase35_institutional_readiness),
            "rollout_governance": dict(self.rollout_governance),
            "governance_observability": dict(self.governance_observability),
            "production_readiness": dict(self.production_readiness),
        }


class UniverseOpsService:
    """Final production-readiness lens over world state, shield, and research ladder."""

    def __init__(self, *, canary_compiler: LiveCanaryEnvelopeCompiler | None = None) -> None:
        self.canary_compiler = canary_compiler or LiveCanaryEnvelopeCompiler()

    def assess(
        self,
        *,
        world: WorldStateSnapshot,
        shield: ShieldDecision,
        research: PromotionState,
        allocations: Iterable[UniverseAllocation] = (),
        mission: MissionDecision | None = None,
        verdict: ParliamentVerdict | None = None,
        meta_intelligence: Mapping[str, Any] | None = None,
        learning_summary: Mapping[str, Any] | None = None,
        execution_intelligence: Mapping[str, Any] | None = None,
        memory_records_written: int = 0,
    ) -> UniverseOpsSnapshot:
        blockers: list[str] = []
        notes: list[str] = []
        meta_payload = dict(meta_intelligence or {})
        advanced_payload = _safe_mapping(meta_payload.get("advanced_intelligence", {}))
        learning_payload = dict(learning_summary or {})
        world_summary = world.summary()
        primary_symbol = world.market_state.primary_symbol or world.asset_state.primary_symbol
        primary_symbol_state = world.get_symbol_state(primary_symbol).to_dict() if primary_symbol else {}
        selected_mission = mission.mission if mission is not None else str(world.strategy_state.last_mission or "observation_only")
        mission_confidence = float(mission.confidence) if mission is not None else float(world.confidence_score)
        mission_reasons = list(mission.reason_codes) if mission is not None else []
        execution_posture_hint = str(mission.execution_posture_hint) if mission is not None else ""
        shield_posture_hint = str(mission.shield_posture_hint) if mission is not None else ""
        conservative_fallback_flag = bool(mission.is_conservative_fallback) if mission is not None else False
        mission_transition = {
            "previous_mission": str(mission.previous_mission),
            "current_mission": str(mission.mission),
            "changed": bool(mission.previous_mission and mission.previous_mission != mission.mission),
            "transition_reason": str(mission.transition_reason),
        } if mission is not None else {}
        allowed_strategy_families = list(mission.allowed_strategy_families) if mission is not None else list(world.strategy_state.mission_allowed_strategy_families)
        no_trade_preference = bool(mission.no_trade_preferred) if mission is not None else bool(world.strategy_state.mission_no_trade_preference)
        parliament_mode = str(verdict.selection_mode) if verdict is not None else "top_1"
        parliament_no_trade = bool(verdict.no_trade) if verdict is not None else (selected_mission == "observation_only")
        parliament_selected = [row.strategy for row in verdict.selected_top] if verdict is not None and verdict.selected_top else []
        parliament_reasons = list(verdict.reasons) if verdict is not None else []
        parliament_top_score = float(verdict.ranking[0].score) if verdict is not None and verdict.ranking else 0.0
        parliament_allocations = [row.to_dict() for row in verdict.allocations] if verdict is not None else []
        meta_regime_cluster = str(meta_payload.get("regime_cluster", ""))
        meta_exploration_budget = float(meta_payload.get("exploration_budget", 0.0) or 0.0)
        meta_exploitation_budget = float(meta_payload.get("exploitation_budget", 1.0) or 1.0)
        meta_risk_scale = float(meta_payload.get("risk_scale", 1.0) or 1.0)
        meta_memory_records = int(float(meta_payload.get("memory_records", 0) or 0))
        raw_weights = meta_payload.get("strategy_weights", [])
        meta_strategy_weights = [dict(row) for row in raw_weights] if isinstance(raw_weights, list) else []
        phase26_global_market_state = _safe_mapping(advanced_payload.get("phase26_global_market_state", {}))
        phase27_horizon_alignment = _safe_mapping(advanced_payload.get("phase27_horizon_alignment", {}))
        phase28_market_energy = _safe_mapping(advanced_payload.get("phase28_market_energy", {}))
        phase29_future_simulation = _safe_mapping(advanced_payload.get("phase29_future_simulation", {}))
        phase30_cross_reality_signal = _safe_mapping(advanced_payload.get("phase30_cross_reality_signal", {}))
        phase31_personality_trace = _safe_mapping(advanced_payload.get("phase31_personality_trace", {}))
        phase32_survival_doctrine = _safe_mapping(advanced_payload.get("phase32_survival_doctrine", {}))
        phase33_evolutionary_research = _safe_mapping(advanced_payload.get("phase33_evolutionary_research", {}))
        phase34_fund_brain = _safe_mapping(advanced_payload.get("phase34_fund_brain", {}))
        phase35_institutional_readiness = _safe_mapping(advanced_payload.get("phase35_institutional_readiness", {}))
        phase42_committee_escalation = _safe_mapping(advanced_payload.get("phase42_committee_escalation", {}))
        shield_mode = str(getattr(shield, "mode", "normal") or "normal")
        previous_shield_mode = str(getattr(shield, "previous_mode", shield_mode) or shield_mode)
        escalation_reason_codes = list(getattr(shield, "escalation_reason_codes", list(getattr(shield, "reason_codes", []))))
        escalation_inputs_summary = dict(getattr(shield, "escalation_inputs_summary", {}) or {})
        strategy_health_summary = dict(getattr(shield, "strategy_health_summary", {}) or {})
        meta_risk_summary = dict(getattr(shield, "meta_risk_summary", {}) or {})
        hysteresis_state = dict(getattr(shield, "hysteresis_state", {}) or {})
        no_trade_forced = bool(getattr(shield, "no_trade_forced", shield_mode in {"observe_only", "hard_stop"}))
        hard_stop_forced = bool(getattr(shield, "hard_stop_forced", getattr(shield, "kill_switch", False)))
        recovery_eligibility = dict(getattr(shield, "recovery_eligibility", {}) or {})
        grading_state_summary = dict(learning_payload.get("grading_state_summary", {}) or {})
        latest_policy_grade_summary = dict(learning_payload.get("latest_policy_grade_summary", {}) or {})
        promotion_candidates_count = int(float(learning_payload.get("promotion_candidates_count", 0) or 0))
        demotion_candidates_count = int(float(learning_payload.get("demotion_candidates_count", 0) or 0))
        retirement_candidates_count = int(float(learning_payload.get("retirement_candidates_count", 0) or 0))
        shield_aware_learning_summary = dict(learning_payload.get("shield_aware_learning_summary", {}) or {})
        memory_compaction_summary = dict(learning_payload.get("memory_compaction_summary", {}) or {})
        replay_evidence_summary = dict(learning_payload.get("replay_evidence_summary", {}) or {})
        bounded_retention_health = dict(learning_payload.get("bounded_retention_health", {}) or {})
        replay_batch_status = dict(learning_payload.get("replay_batch_status", {}) or {})
        promotion_ladder_state = dict(learning_payload.get("promotion_ladder_state", {}) or {})
        raw_top_candidates = learning_payload.get("top_strategy_candidates", [])
        top_strategy_candidates = [dict(row) for row in raw_top_candidates] if isinstance(raw_top_candidates, list) else []
        raw_quarantine = learning_payload.get("quarantine_strategy_list", [])
        quarantine_strategy_list = [str(item) for item in raw_quarantine] if isinstance(raw_quarantine, list) else []
        promotion_readiness_score = float(learning_payload.get("promotion_readiness_score", 0.0) or 0.0)
        replay_backlog_depth = max(0, int(float(learning_payload.get("replay_backlog_depth", 0) or 0)))
        memory_grading_drift = float(learning_payload.get("memory_grading_drift", 0.0) or 0.0)
        replay_session_id = str(learning_payload.get("replay_session_id", "") or "")
        decision_reconstruction_count = max(0, int(float(learning_payload.get("decision_reconstruction_count", 0) or 0)))
        walk_forward_holdout_grade = float(learning_payload.get("walk_forward_holdout_grade", 0.0) or 0.0)
        counterfactual_overall_grade_delta = float(learning_payload.get("counterfactual_overall_grade_delta", 0.0) or 0.0)
        execution_payload = dict(execution_intelligence or {})
        execution_shape = execution_payload.get("order_book_shape", {})
        shape_mapping = dict(execution_shape) if isinstance(execution_shape, Mapping) else {}
        quality_payload = execution_payload.get("quality_estimate", {})
        quality_mapping = dict(quality_payload) if isinstance(quality_payload, Mapping) else {}
        stress_payload = execution_payload.get("stress_index", {})
        stress_mapping = dict(stress_payload) if isinstance(stress_payload, Mapping) else {}
        abort_payload = execution_payload.get("abort_decision", {})
        abort_mapping = dict(abort_payload) if isinstance(abort_payload, Mapping) else {}
        advisory_payload = execution_payload.get("advisory_escalation", {})
        advisory_mapping = dict(advisory_payload) if isinstance(advisory_payload, Mapping) else {}
        survival_payload = execution_payload.get("survival_doctrine", {})
        survival_mapping = dict(survival_payload) if isinstance(survival_payload, Mapping) else {}
        spoofing_payload = execution_payload.get("spoofing_heuristic", {})
        spoofing_mapping = dict(spoofing_payload) if isinstance(spoofing_payload, Mapping) else {}
        execution_mode = str(execution_payload.get("mode", "") or "")
        execution_stress_index = float(stress_mapping.get("score", 0.0) or 0.0)
        execution_quality_score = float(quality_mapping.get("execution_quality_score", 0.0) or 0.0)
        execution_abort = bool(abort_mapping.get("should_abort", False))
        raw_abort_reasons = abort_mapping.get("reason_codes", [])
        execution_abort_reason_codes = [str(item) for item in raw_abort_reasons] if isinstance(raw_abort_reasons, list) else []
        execution_expected_total_cost_bps = float(quality_mapping.get("expected_total_cost_bps", 0.0) or 0.0)
        execution_expected_net_edge_bps = float(quality_mapping.get("expected_net_edge_bps", 0.0) or 0.0)
        execution_risk_scale_hint = float(execution_payload.get("risk_scale_hint", 1.0) or 1.0)
        execution_advisory_severity = str(advisory_mapping.get("severity", "") or "")
        execution_advisory_score = float(advisory_mapping.get("severity_score", 0.0) or 0.0)
        raw_advisory_reasons = advisory_mapping.get("reason_codes", [])
        execution_advisory_reason_codes = [str(item) for item in raw_advisory_reasons] if isinstance(raw_advisory_reasons, list) else []
        execution_survival_protocol = str(survival_mapping.get("protocol", "") or "")
        execution_spoofing_score = float(spoofing_mapping.get("oscillation_score", 0.0) or 0.0)
        execution_spoofing_flag = bool(spoofing_mapping.get("spoof_like_flag", False))
        execution_liquidity_flags = [
            flag
            for flag, active in {
                "thin_book": bool(shape_mapping.get("thin_book", False)),
                "wide_spread": bool(shape_mapping.get("wide_spread", False)),
                "sudden_depth_drop": bool(shape_mapping.get("sudden_depth_drop", False)),
            }.items()
            if active
        ]
        readiness = research.score * 0.45 + world.confidence_score * 0.25 + world.state_stability * 0.20
        readiness += (0.10 if shield.approved else 0.0)
        readiness *= max(0.70, min(1.0, 0.70 + 0.30 * meta_risk_scale))
        if shield.kill_switch:
            blockers.append("shield_kill_switch")
        if world.infra_state.stale_feed:
            blockers.append("stale_feed")
        if world.infra_state.desync:
            blockers.append("venue_desync")
        if world.risk_state.hard_stop:
            blockers.append("risk_hard_stop")
        if world.execution_state.execution_stress >= 0.70:
            blockers.append("execution_degradation")
        if not world.metadata.graph_available:
            blockers.append("world_state_unavailable")
        notes.append(f"promotion_stage={research.current_stage}")
        notes.append(f"shield_mode={shield.mode}")
        notes.append(f"world_state={world.current_world_state}")
        notes.append(f"mission={selected_mission}")
        if meta_regime_cluster:
            notes.append(f"meta_regime_cluster={meta_regime_cluster}")
            notes.append(f"meta_explore={meta_exploration_budget:.2f}")
            notes.append(f"meta_risk_scale={meta_risk_scale:.2f}")
        if learning_payload:
            notes.append(f"learning_records={int(learning_payload.get('total_records', 0) or 0)}")
            notes.append(f"learning_policy_grades={int(latest_policy_grade_summary.get('total_policy_grades', 0) or 0)}")
            notes.append(f"replay_backlog_depth={replay_backlog_depth}")
            notes.append(f"promotion_readiness={promotion_readiness_score:.2f}")
            notes.append(f"walk_forward_holdout={walk_forward_holdout_grade:.2f}")
            notes.append(f"counterfactual_delta={counterfactual_overall_grade_delta:.2f}")
        if execution_mode:
            notes.append(f"exec_mode={execution_mode}")
            notes.append(f"exec_stress={execution_stress_index:.2f}")
            notes.append(f"exec_net_edge={execution_expected_net_edge_bps:.2f}")
        if phase26_global_market_state:
            notes.append(f"phase26_market_stress={_safe_float(phase26_global_market_state.get('market_stress', 0.0), 0.0):.2f}")
        if phase27_horizon_alignment:
            notes.append(f"phase27_alignment={_safe_float(phase27_horizon_alignment.get('alignment_score', 0.0), 0.0):.2f}")
        if phase32_survival_doctrine:
            existential = _safe_mapping(phase32_survival_doctrine.get("existential_risk", {}))
            notes.append(f"phase32_existential={str(existential.get('level', 'unknown'))}")
        if phase35_institutional_readiness:
            notes.append(f"phase35_readiness={_safe_float(phase35_institutional_readiness.get('readiness_score', 0.0), 0.0):.2f}")
        if phase42_committee_escalation:
            notes.append(f"phase42_escalation_level={str(phase42_committee_escalation.get('level', 'unknown'))}")
            notes.append(f"phase42_operator_ack={bool(phase42_committee_escalation.get('requires_operator_ack', False))}")
        top_alloc = max(list(allocations), key=lambda row: row.weight, default=None)
        if top_alloc is not None:
            notes.append(f"top_universe={top_alloc.universe_id}:{top_alloc.weight:.2f}")
        governance = self._build_rollout_governance(
            world=world,
            shield=shield,
            research=research,
            blockers=blockers,
            learning_payload=learning_payload,
            replay_batch_status=replay_batch_status,
            promotion_ladder_state=promotion_ladder_state,
            top_strategy_candidates=top_strategy_candidates,
            quarantine_strategy_list=quarantine_strategy_list,
            promotion_readiness_score=promotion_readiness_score,
            walk_forward_holdout_grade=walk_forward_holdout_grade,
            counterfactual_overall_grade_delta=counterfactual_overall_grade_delta,
            memory_grading_drift=memory_grading_drift,
            execution_mode=execution_mode,
            execution_stress_index=execution_stress_index,
            execution_abort=execution_abort,
            execution_advisory_severity=execution_advisory_severity,
            execution_expected_net_edge_bps=execution_expected_net_edge_bps,
        )
        notes.append(f"governance_stage={governance.stage}")
        notes.append(f"governance_decision={governance.decision.decision_id[:10]}")
        if governance.decision.reason_codes:
            notes.append(f"governance_reasons={','.join(governance.decision.reason_codes[:3])}")
        production_readiness = self._build_production_readiness_artifact(
            governance=governance,
            world=world,
            learning_payload=learning_payload,
        )
        phase32_survival_doctrine = _safe_mapping(advanced_payload.get("phase32_survival_doctrine", {}))
        phase42_committee_escalation = _safe_mapping(advanced_payload.get("phase42_committee_escalation", {}))
        phase43_institutional_gate = _safe_mapping(advanced_payload.get("phase43_institutional_gate", {}))
        phase48_evidence_index = _safe_mapping(advanced_payload.get("phase48_evidence_vault_index", {}))
        phase49_envelope = self.canary_compiler.compile(
            rollout_stage=governance.stage,
            manual_gate_required=bool(
                governance.decision.operator_approval_required
                or governance.decision.manual_live_env_gate_required
            ),
            manual_gate_present=bool(
                governance.decision.operator_approval_present
                and (
                    (not governance.decision.manual_live_env_gate_required)
                    or governance.decision.manual_live_env_gate_present
                )
            ),
            safety_veto=bool(
                phase42_committee_escalation.get("safety_veto", False)
                or phase32_survival_doctrine.get("safety_veto", False)
            ),
            evidence_ready=bool(phase48_evidence_index.get("ready", False)),
            deployment_gate_open=bool(phase43_institutional_gate.get("gate_open", False)),
        )
        notes.append(f"phase10_artifact={production_readiness.artifact_id[:10]}")
        notes.append(f"phase49_canary_stage={phase49_envelope.resolved_stage}")
        rollout_stage = governance.stage
        manual_gate_required = bool(
            governance.decision.operator_approval_required
            and (
                (not governance.decision.operator_approval_present)
                or (governance.decision.manual_live_env_gate_required and not governance.decision.manual_live_env_gate_present)
            )
        )
        return UniverseOpsSnapshot(
            readiness_score=max(0.0, min(1.0, readiness)),
            rollout_stage=rollout_stage,
            manual_gate_required=manual_gate_required,
            blockers=blockers,
            notes=notes,
            world_state_available=bool(world.metadata.graph_available),
            world_state_as_of=float(world.as_of_time),
            domain_freshness_s=dict(world_summary.get("freshness_s", {})),
            world_state_summary=world_summary,
            primary_symbol_state=primary_symbol_state,
            mission_selected=selected_mission,
            mission_confidence=mission_confidence,
            mission_reason_codes=mission_reasons,
            execution_posture_hint=execution_posture_hint,
            shield_posture_hint=shield_posture_hint,
            conservative_fallback_flag=conservative_fallback_flag,
            mission_transition=mission_transition,
            allowed_strategy_families=allowed_strategy_families,
            no_trade_preference=no_trade_preference,
            parliament_mode=parliament_mode,
            parliament_no_trade=parliament_no_trade,
            parliament_selected_strategies=parliament_selected,
            parliament_reasons=parliament_reasons,
            parliament_top_score=parliament_top_score,
            parliament_allocations=parliament_allocations,
            meta_regime_cluster=meta_regime_cluster,
            meta_exploration_budget=meta_exploration_budget,
            meta_exploitation_budget=meta_exploitation_budget,
            meta_risk_scale=meta_risk_scale,
            meta_memory_records=meta_memory_records,
            meta_strategy_weights=meta_strategy_weights,
            shield_mode=shield_mode,
            previous_shield_mode=previous_shield_mode,
            escalation_reason_codes=escalation_reason_codes,
            escalation_inputs_summary=escalation_inputs_summary,
            strategy_health_summary=strategy_health_summary,
            meta_risk_summary=meta_risk_summary,
            hysteresis_state=hysteresis_state,
            no_trade_forced=no_trade_forced,
            hard_stop_forced=hard_stop_forced,
            recovery_eligibility=recovery_eligibility,
            memory_records_written=max(0, int(memory_records_written)),
            grading_state_summary=grading_state_summary,
            latest_policy_grade_summary=latest_policy_grade_summary,
            promotion_candidates_count=promotion_candidates_count,
            demotion_candidates_count=demotion_candidates_count,
            retirement_candidates_count=retirement_candidates_count,
            shield_aware_learning_summary=shield_aware_learning_summary,
            memory_compaction_summary=memory_compaction_summary,
            replay_evidence_summary=replay_evidence_summary,
            bounded_retention_health=bounded_retention_health,
            replay_batch_status=replay_batch_status,
            promotion_ladder_state=promotion_ladder_state,
            top_strategy_candidates=top_strategy_candidates,
            quarantine_strategy_list=quarantine_strategy_list,
            promotion_readiness_score=promotion_readiness_score,
            replay_backlog_depth=replay_backlog_depth,
            memory_grading_drift=memory_grading_drift,
            replay_session_id=replay_session_id,
            decision_reconstruction_count=decision_reconstruction_count,
            walk_forward_holdout_grade=walk_forward_holdout_grade,
            counterfactual_overall_grade_delta=counterfactual_overall_grade_delta,
            execution_personality_mode=execution_mode,
            execution_stress_index=execution_stress_index,
            execution_quality_score=execution_quality_score,
            execution_abort=execution_abort,
            execution_abort_reason_codes=execution_abort_reason_codes,
            execution_expected_total_cost_bps=execution_expected_total_cost_bps,
            execution_expected_net_edge_bps=execution_expected_net_edge_bps,
            execution_risk_scale_hint=execution_risk_scale_hint,
            execution_liquidity_flags=execution_liquidity_flags,
            execution_advisory_severity=execution_advisory_severity,
            execution_advisory_score=execution_advisory_score,
            execution_advisory_reason_codes=execution_advisory_reason_codes,
            execution_survival_protocol=execution_survival_protocol,
            execution_spoofing_score=execution_spoofing_score,
            execution_spoofing_flag=execution_spoofing_flag,
            advanced_intelligence=advanced_payload,
            phase26_global_market_state=phase26_global_market_state,
            phase27_horizon_alignment=phase27_horizon_alignment,
            phase28_market_energy=phase28_market_energy,
            phase29_future_simulation=phase29_future_simulation,
            phase30_cross_reality_signal=phase30_cross_reality_signal,
            phase31_personality_trace=phase31_personality_trace,
            phase32_survival_doctrine=phase32_survival_doctrine,
            phase33_evolutionary_research=phase33_evolutionary_research,
            phase34_fund_brain=phase34_fund_brain,
            phase35_institutional_readiness=phase35_institutional_readiness,
            rollout_governance=governance.to_dict(),
            governance_observability={
                **dict(governance.observability),
                **dict(production_readiness.observability),
                "phase49_canary_envelope": phase49_envelope.to_dict(),
                "phase42_escalation_summary": {
                    "level": str(phase42_committee_escalation.get("level", "")),
                    "requires_operator_ack": bool(phase42_committee_escalation.get("requires_operator_ack", False)),
                    "safety_veto": bool(phase42_committee_escalation.get("safety_veto", False)),
                },
            },
            production_readiness=production_readiness.to_dict(),
        )

    def _build_rollout_governance(
        self,
        *,
        world: WorldStateSnapshot,
        shield: ShieldDecision,
        research: PromotionState,
        blockers: list[str],
        learning_payload: Mapping[str, Any],
        replay_batch_status: Mapping[str, Any],
        promotion_ladder_state: Mapping[str, Any],
        top_strategy_candidates: list[dict[str, Any]],
        quarantine_strategy_list: list[str],
        promotion_readiness_score: float,
        walk_forward_holdout_grade: float,
        counterfactual_overall_grade_delta: float,
        memory_grading_drift: float,
        execution_mode: str,
        execution_stress_index: float,
        execution_abort: bool,
        execution_advisory_severity: str,
        execution_expected_net_edge_bps: float,
    ) -> RolloutGovernanceSnapshot:
        activation_gates = self._parse_activation_gates(promotion_ladder_state)
        candidate_stage = self._candidate_stage_from_signals(
            research_stage=research.current_stage,
            activation_gates=activation_gates,
            top_strategy_candidates=top_strategy_candidates,
        )
        current_stage = _normalize_rollout_stage(research.current_stage)
        promotion_change_requested = bool(
            _STAGE_RANK.get(candidate_stage, 0) > _STAGE_RANK.get(current_stage, 0)
        )
        replay_contract = build_promotion_replay_contract(
            batch_status=replay_batch_status,
            top_strategy_candidates=top_strategy_candidates,
            quarantine_strategy_fingerprints=quarantine_strategy_list,
        )
        replay_contract_id = str(replay_contract.get("contract_id", "") or "")
        replay_failed = bool(replay_batch_status.get("failed", False))
        replay_determinism_gate_passed = bool(
            replay_contract.get("contract_ready", False)
            and replay_contract.get("deterministic", False)
            and not replay_failed
        )
        regression_signals_passed = bool(
            (not replay_failed)
            and float(promotion_readiness_score) >= 0.55
            and float(walk_forward_holdout_grade) >= 0.50
            and float(memory_grading_drift) <= 0.35
            and float(counterfactual_overall_grade_delta) >= -0.20
        )
        regression_gate_passed = bool(
            regression_signals_passed
            and (not promotion_change_requested or replay_determinism_gate_passed)
        )
        safety_reasons: list[str] = []
        if blockers:
            safety_reasons.extend(blockers)
        if bool(getattr(shield, "kill_switch", False)):
            safety_reasons.append("shield_kill_switch")
        if bool(getattr(shield, "hard_stop_forced", False)):
            safety_reasons.append("hard_stop_forced")
        if execution_abort:
            safety_reasons.append("phase9_execution_abort")
        if str(execution_advisory_severity or "").lower() == "critical":
            safety_reasons.append("critical_execution_advisory")
        if float(execution_stress_index) >= 0.80:
            safety_reasons.append("execution_stress_high")
        if float(execution_expected_net_edge_bps) <= 0.0:
            safety_reasons.append("non_positive_expected_net_edge")
        if quarantine_strategy_list:
            safety_reasons.append("quarantine_candidates_present")
        safety_gate_passed = len(safety_reasons) == 0

        stage_requires_activation_gate = _is_live_candidate_stage(candidate_stage)
        activation_gate_passed = bool(
            not stage_requires_activation_gate
            or any(row.allowed and not row.kill_switch for row in activation_gates)
        )
        reason_codes: list[str] = []
        if not regression_gate_passed:
            reason_codes.append("regression_gate_failed")
        if promotion_change_requested and not replay_determinism_gate_passed:
            reason_codes.append("replay_determinism_gate_failed")
            if not replay_contract.get("contract_ready", False):
                reason_codes.append("replay_contract_incomplete")
        if not safety_gate_passed:
            reason_codes.append("safety_gate_failed")
        if not activation_gate_passed:
            reason_codes.append("activation_gate_failed")
        if candidate_stage == "blocked":
            reason_codes.append("candidate_stage_blocked")

        operator_approvals = self._parse_operator_approvals(
            learning_payload=learning_payload,
            candidate_stage=candidate_stage,
            base_reasons=reason_codes,
            manual_gate_required=stage_requires_activation_gate,
            replay_batch_status=replay_batch_status,
        )
        operator_approval_present = any(row.approved and row.stage == candidate_stage for row in operator_approvals)
        operator_approval_required = stage_requires_activation_gate
        manual_live_env_gate_present, manual_live_env_gate_details = self._resolve_manual_live_env_gate(learning_payload)
        manual_live_env_gate_required = stage_requires_activation_gate
        if operator_approval_required and not operator_approval_present:
            reason_codes.append("manual_live_gate_required")
        if manual_live_env_gate_required and not manual_live_env_gate_present:
            reason_codes.append("manual_live_env_gate_required")

        approved = bool(
            candidate_stage != "blocked"
            and
            regression_gate_passed
            and safety_gate_passed
            and activation_gate_passed
            and (not operator_approval_required or operator_approval_present)
            and (not manual_live_env_gate_required or manual_live_env_gate_present)
        )
        resolved_stage = candidate_stage if approved else "blocked"
        decision = PromotionGovernanceDecision(
            decision_id=_stable_hash(
                {
                    "candidate_stage": candidate_stage,
                    "resolved_stage": resolved_stage,
                    "replay_batch_id": str(replay_batch_status.get("batch_id", "")),
                    "replay_session_id": str(learning_payload.get("replay_session_id", "")),
                    "promotion_readiness_score": float(promotion_readiness_score),
                    "walk_forward_holdout_grade": float(walk_forward_holdout_grade),
                    "counterfactual_overall_grade_delta": float(counterfactual_overall_grade_delta),
                    "memory_grading_drift": float(memory_grading_drift),
                    "execution_mode": execution_mode,
                    "execution_stress_index": float(execution_stress_index),
                    "replay_contract_id": replay_contract_id,
                    "replay_determinism_gate_passed": bool(replay_determinism_gate_passed),
                    "promotion_change_requested": bool(promotion_change_requested),
                    "manual_live_env_gate_present": bool(manual_live_env_gate_present),
                }
            ),
            candidate_stage=candidate_stage,
            resolved_stage=resolved_stage,
            approved=approved,
            blocked=not approved,
            regression_gate_passed=regression_gate_passed,
            safety_gate_passed=safety_gate_passed,
            activation_gate_passed=activation_gate_passed,
            replay_determinism_gate_passed=replay_determinism_gate_passed,
            operator_approval_required=operator_approval_required,
            operator_approval_present=operator_approval_present,
            manual_live_env_gate_required=manual_live_env_gate_required,
            manual_live_env_gate_present=manual_live_env_gate_present,
            replay_contract_id=replay_contract_id,
            promotion_change_requested=promotion_change_requested,
            reason_codes=tuple(dict.fromkeys(str(code) for code in reason_codes if str(code))),
        )
        replay_session_id = str(learning_payload.get("replay_session_id", "") or "")
        if not replay_session_id:
            replay_session_id = str(_safe_mapping(replay_batch_status.get("reproducibility_metadata", {})).get("replay_session_id", "") or "")
        evidence = PromotionEvidenceBundle(
            bundle_id=_stable_hash(
                {
                    "decision_id": decision.decision_id,
                    "candidate_stage": candidate_stage,
                    "top_strategy_candidates": [str(row.get("strategy_fingerprint", "")) for row in top_strategy_candidates],
                    "execution_mode": execution_mode,
                }
            ),
            stage=candidate_stage,
            replay_batch_id=str(replay_batch_status.get("batch_id", "") or ""),
            replay_session_id=replay_session_id,
            replay_contract_id=replay_contract_id,
            strategy_fingerprints=tuple(
                str(row.get("strategy_fingerprint", ""))
                for row in top_strategy_candidates
                if str(row.get("strategy_fingerprint", ""))
            ),
            replay_contract=replay_contract,
            execution_diagnostics={
                "mode": execution_mode,
                "stress_index": float(execution_stress_index),
                "execution_abort": bool(execution_abort),
                "advisory_severity": str(execution_advisory_severity or ""),
                "expected_net_edge_bps": float(execution_expected_net_edge_bps),
            },
            regression_metrics={
                "promotion_readiness_score": float(promotion_readiness_score),
                "walk_forward_holdout_grade": float(walk_forward_holdout_grade),
                "counterfactual_overall_grade_delta": float(counterfactual_overall_grade_delta),
                "memory_grading_drift": float(memory_grading_drift),
                "replay_failed": bool(replay_failed),
                "replay_contract_id": replay_contract_id,
                "replay_determinism_gate_passed": bool(replay_determinism_gate_passed),
                "promotion_change_requested": bool(promotion_change_requested),
            },
            safety_metrics={
                "world_graph_available": bool(world.metadata.graph_available),
                "shield_mode": str(getattr(shield, "mode", "normal") or "normal"),
                "shield_kill_switch": bool(getattr(shield, "kill_switch", False)),
                "hard_stop_forced": bool(getattr(shield, "hard_stop_forced", False)),
                "blockers": list(blockers),
                "quarantine_strategy_list": [str(item) for item in quarantine_strategy_list],
            },
        )
        rollback_artifact = _safe_mapping(
            learning_payload.get(
                "rollback_dry_run_artifact",
                learning_payload.get("rollback_dry_run", {}),
            )
        )
        rollback_from_flag = bool(learning_payload.get("rollback_dry_run_validated", False))
        rollback_from_artifact = bool(rollback_artifact.get("validated", False))
        rollback_dry_run = bool(rollback_from_flag or rollback_from_artifact)
        rollback_artifact_id = str(rollback_artifact.get("artifact_id", "") or "")
        rollback_reasons: list[str] = []
        if not rollback_dry_run:
            rollback_reasons.append("rollback_dry_run_not_validated")
            if rollback_artifact:
                rollback_reasons.append("rollback_dry_run_artifact_not_validated")
        if promotion_change_requested and not replay_determinism_gate_passed:
            rollback_reasons.append("replay_determinism_not_verified_for_promotion_change")
        rollback_reasons.append("additive_phase10_contract")
        rollback = RollbackReadinessRecord(
            rollback_ready=rollback_dry_run,
            dry_run_validated=rollback_dry_run,
            reason_codes=tuple(rollback_reasons),
            feature_flags={
                "UNIVERSE_REPLAY_PROMOTION_ENABLED": bool(
                    _safe_mapping(replay_batch_status).get("enabled", False)
                ),
                "manual_live_gate_required": bool(operator_approval_required),
                "manual_live_env_gate_required": bool(manual_live_env_gate_required),
                "rollback_dry_run_artifact_present": bool(rollback_artifact),
            },
            records={
                "replay_batch_id": str(replay_batch_status.get("batch_id", "") or ""),
                "decision_id": decision.decision_id,
                "governance_stage": resolved_stage,
                "replay_promotion_contract_id": replay_contract_id,
                "replay_determinism_gate_passed": bool(replay_determinism_gate_passed),
                "promotion_change_requested": bool(promotion_change_requested),
                "rollback_dry_run_artifact_id": rollback_artifact_id,
                "rollback_dry_run_source": "learning_payload_flag" if rollback_from_flag else "rollback_artifact" if rollback_from_artifact else "none",
                "rollback_dry_run_artifact_reason_codes": [
                    str(code) for code in rollback_artifact.get("reason_codes", []) if str(code)
                ] if isinstance(rollback_artifact.get("reason_codes", []), list) else [],
                "manual_live_env_gate": dict(manual_live_env_gate_details),
            },
        )
        observability = {
            "governance_decision_id": decision.decision_id,
            "governance_candidate_stage": candidate_stage,
            "governance_resolved_stage": resolved_stage,
            "governance_current_stage": current_stage,
            "activation_gate_count": len(activation_gates),
            "activation_allowed_count": sum(1 for row in activation_gates if row.allowed),
            "operator_approval_count": len(operator_approvals),
            "operator_approval_present": bool(operator_approval_present),
            "manual_live_env_gate_required": bool(manual_live_env_gate_required),
            "manual_live_env_gate_present": bool(manual_live_env_gate_present),
            "evidence_bundle_count": 1,
            "regression_gate_passed": bool(regression_gate_passed),
            "replay_determinism_gate_passed": bool(replay_determinism_gate_passed),
            "promotion_change_requested": bool(promotion_change_requested),
            "replay_promotion_contract_id": replay_contract_id,
            "safety_gate_passed": bool(safety_gate_passed),
            "rollback_ready": bool(rollback.rollback_ready),
            "rollback_dry_run_validated": bool(rollback.dry_run_validated),
            "rollback_dry_run_artifact_id": rollback_artifact_id,
            "replay_failed": bool(replay_failed),
            "quarantine_count": len(quarantine_strategy_list),
        }
        return RolloutGovernanceSnapshot(
            stage=resolved_stage,
            decision=decision,
            activation_gates=activation_gates,
            operator_approvals=operator_approvals,
            evidence_bundles=[evidence],
            rollback_readiness=rollback,
            observability=observability,
        )

    def _build_production_readiness_artifact(
        self,
        *,
        governance: RolloutGovernanceSnapshot,
        world: WorldStateSnapshot,
        learning_payload: Mapping[str, Any],
    ) -> ProductionReadinessArtifact:
        stage = _normalize_rollout_stage(governance.stage)
        decision = governance.decision
        blocked = bool(decision.blocked or stage == "blocked")
        manual_gate_satisfied = bool(
            (not decision.operator_approval_required)
            or (decision.operator_approval_present and decision.manual_live_env_gate_present)
        )
        replay_ready = bool(decision.regression_gate_passed)
        shadow_ready = bool(replay_ready and decision.safety_gate_passed)
        paper_ready = bool(shadow_ready and decision.activation_gate_passed)
        limited_live_ready = bool(decision.approved and stage in {"limited_live_ready", "scaled_live_candidate"})
        scaled_live_candidate_ready = bool(decision.approved and stage == "scaled_live_candidate")
        rollback = governance.rollback_readiness
        checklist: list[dict[str, Any]] = [
            {"item_id": "world_state_graph_available", "passed": bool(world.metadata.graph_available), "required": True},
            {"item_id": "regression_gate_passed", "passed": bool(decision.regression_gate_passed), "required": True},
            {"item_id": "safety_gate_passed", "passed": bool(decision.safety_gate_passed), "required": True},
            {"item_id": "activation_gate_passed", "passed": bool(decision.activation_gate_passed), "required": True},
            {
                "item_id": "replay_determinism_gate_passed",
                "passed": bool(decision.replay_determinism_gate_passed),
                "required": bool(decision.promotion_change_requested),
            },
            {"item_id": "manual_live_gate_satisfied", "passed": bool(manual_gate_satisfied), "required": bool(decision.operator_approval_required)},
            {
                "item_id": "manual_live_env_gate_satisfied",
                "passed": bool(decision.manual_live_env_gate_present),
                "required": bool(decision.manual_live_env_gate_required),
            },
            {"item_id": "rollback_ready", "passed": bool(rollback.rollback_ready), "required": True},
            {"item_id": "rollback_dry_run_validated", "passed": bool(rollback.dry_run_validated), "required": True},
            {"item_id": "evidence_bundle_present", "passed": bool(governance.evidence_bundles), "required": True},
        ]
        if "config_drift_check_passed" in learning_payload:
            checklist.append(
                {
                    "item_id": "config_drift_check_passed",
                    "passed": bool(learning_payload.get("config_drift_check_passed", False)),
                    "required": True,
                }
            )
        if "distributed_audit_stream_ready" in learning_payload:
            checklist.append(
                {
                    "item_id": "distributed_audit_stream_ready",
                    "passed": bool(learning_payload.get("distributed_audit_stream_ready", False)),
                    "required": True,
                }
            )
        evidence_ids = tuple(row.bundle_id for row in governance.evidence_bundles if row.bundle_id)
        artifact_id = _stable_hash(
            {
                "decision_id": decision.decision_id,
                "stage": stage,
                "blocked": blocked,
                "manual_gate_required": bool(decision.operator_approval_required),
                "manual_gate_satisfied": bool(manual_gate_satisfied),
                "rollback_ready": bool(rollback.rollback_ready),
                "rollback_dry_run_validated": bool(rollback.dry_run_validated),
                "checklist": checklist,
                "evidence_bundle_ids": list(evidence_ids),
            }
        )
        observability = {
            "phase10_artifact_id": artifact_id,
            "phase10_stage": stage,
            "phase10_blocked": bool(blocked),
            "phase10_replay_ready": bool(replay_ready),
            "phase10_shadow_ready": bool(shadow_ready),
            "phase10_paper_ready": bool(paper_ready),
            "phase10_limited_live_ready": bool(limited_live_ready),
            "phase10_scaled_live_candidate_ready": bool(scaled_live_candidate_ready),
            "phase10_manual_gate_required": bool(decision.operator_approval_required),
            "phase10_manual_gate_satisfied": bool(manual_gate_satisfied),
            "phase24_manual_live_env_gate_required": bool(decision.manual_live_env_gate_required),
            "phase24_manual_live_env_gate_satisfied": bool(decision.manual_live_env_gate_present),
            "phase10_rollback_ready": bool(rollback.rollback_ready),
            "phase10_rollback_dry_run_validated": bool(rollback.dry_run_validated),
            "phase19_replay_determinism_gate_passed": bool(decision.replay_determinism_gate_passed),
            "phase19_promotion_change_requested": bool(decision.promotion_change_requested),
            "phase19_replay_contract_id": str(decision.replay_contract_id or ""),
        }
        return ProductionReadinessArtifact(
            artifact_id=artifact_id,
            stage=stage,
            replay_ready=replay_ready,
            shadow_ready=shadow_ready,
            paper_ready=paper_ready,
            limited_live_ready=limited_live_ready,
            scaled_live_candidate_ready=scaled_live_candidate_ready,
            blocked=blocked,
            manual_gate_required=bool(decision.operator_approval_required),
            manual_gate_satisfied=manual_gate_satisfied,
            rollback_ready=bool(rollback.rollback_ready),
            rollback_dry_run_validated=bool(rollback.dry_run_validated),
            checklist=checklist,
            evidence_bundle_ids=evidence_ids,
            observability=observability,
        )

    def _candidate_stage_from_signals(
        self,
        *,
        research_stage: str,
        activation_gates: list[ActivationGateContract],
        top_strategy_candidates: list[dict[str, Any]],
    ) -> str:
        stages: list[str] = [_normalize_rollout_stage(research_stage)]
        for gate in activation_gates:
            stages.append(_normalize_rollout_stage(gate.resolved_stage))
        for row in top_strategy_candidates:
            stages.append(_normalize_rollout_stage(row.get("next_stage_candidate", "")))
            stages.append(_normalize_rollout_stage(row.get("current_stage", "")))
        best = "offline_replay"
        for stage in stages:
            if _STAGE_RANK.get(stage, 0) > _STAGE_RANK.get(best, 0):
                best = stage
        return best

    def _parse_activation_gates(self, promotion_ladder_state: Mapping[str, Any]) -> list[ActivationGateContract]:
        raw_rows = promotion_ladder_state.get("activation_gates", [])
        if not isinstance(raw_rows, list):
            return []
        parsed: list[ActivationGateContract] = []
        for row in raw_rows:
            if not isinstance(row, Mapping):
                continue
            parsed.append(ActivationGateContract.from_mapping(row))
        return parsed

    def _resolve_manual_live_env_gate(self, learning_payload: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
        override = _safe_mapping(learning_payload.get("manual_live_env_gate", {}))
        if override:
            live_go = bool(override.get("live_go", False))
            confirmation_file_exists = bool(override.get("confirmation_file_exists", False))
            confirmation_file = str(override.get("confirmation_file", "") or "")
            return (
                bool(live_go and confirmation_file_exists),
                {
                    "source": "learning_payload",
                    "live_go": live_go,
                    "confirmation_file_exists": confirmation_file_exists,
                    "confirmation_file": confirmation_file,
                },
            )
        if not _env_bridge_enabled():
            return (
                False,
                {
                    "source": "environment_disabled",
                    "enabled": False,
                    "live_go": False,
                    "confirmation_file_exists": False,
                    "confirmation_file": "",
                },
            )
        live_go = _truthy(os.getenv("AUTONOMOUS_LIVE_GO"))
        confirmation_file = str(os.getenv("AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE", "") or "").strip()
        if not confirmation_file:
            return (
                False,
                {
                    "source": "environment",
                    "enabled": True,
                    "live_go": bool(live_go),
                    "confirmation_file_exists": False,
                    "confirmation_file": "",
                },
            )
        confirmation_path = (
            (Path(confirmation_file).resolve())
            if Path(confirmation_file).is_absolute()
            else (Path.cwd() / confirmation_file).resolve()
        )
        confirmation_file_exists = bool(confirmation_path.exists())
        return (
            bool(live_go and confirmation_file_exists),
            {
                "source": "environment",
                "live_go": bool(live_go),
                "confirmation_file_exists": confirmation_file_exists,
                "confirmation_file": str(confirmation_path),
            },
        )

    def _parse_operator_approvals(
        self,
        *,
        learning_payload: Mapping[str, Any],
        candidate_stage: str,
        base_reasons: list[str],
        manual_gate_required: bool,
        replay_batch_status: Mapping[str, Any],
    ) -> list[OperatorApprovalArtifact]:
        out: list[OperatorApprovalArtifact] = []
        raw_list = learning_payload.get("operator_approval_artifacts", [])
        if isinstance(raw_list, list):
            for row in raw_list:
                if isinstance(row, Mapping):
                    artifact = OperatorApprovalArtifact.from_mapping(row)
                    if artifact.artifact_id:
                        out.append(artifact)
        single = learning_payload.get("operator_approval_artifact", {})
        if isinstance(single, Mapping):
            artifact = OperatorApprovalArtifact.from_mapping(single)
            if artifact.artifact_id:
                out.append(artifact)
        # Hermetic rule:
        # environment-sourced approval artifacts are opt-in and require an explicit file path.
        env_bridge = _env_bridge_enabled()
        env_artifact_file = str(os.getenv("AUTONOMOUS_LIVE_OPERATOR_APPROVAL_ARTIFACT_FILE", "") or "").strip()
        if env_bridge and env_artifact_file:
            env_artifact_path = (
                Path(env_artifact_file).resolve()
                if Path(env_artifact_file).is_absolute()
                else (Path.cwd() / env_artifact_file).resolve()
            )
        else:
            env_artifact_path = None
        if env_artifact_path is not None and env_artifact_path.exists():
            try:
                env_payload = json.loads(env_artifact_path.read_text(encoding="utf-8"))
                if isinstance(env_payload, Mapping):
                    artifact = OperatorApprovalArtifact.from_mapping(env_payload)
                    if artifact.artifact_id:
                        out.append(artifact)
            except Exception:
                pass
        if out:
            return out
        artifact_id = _stable_hash(
            {
                "stage": candidate_stage,
                "batch_id": str(replay_batch_status.get("batch_id", "")),
                "session_id": str(learning_payload.get("replay_session_id", "")),
            }
        )
        reasons: list[str] = list(base_reasons)
        if manual_gate_required:
            reasons.append("operator_approval_missing")
        else:
            reasons.append("operator_approval_not_required")
        out.append(
            OperatorApprovalArtifact(
                artifact_id=artifact_id,
                stage=candidate_stage,
                approved=False,
                approver="",
                approval_ts=0.0,
                reason_codes=tuple(dict.fromkeys(reasons)),
                metadata={"auto_generated": True},
            )
        )
        return out
