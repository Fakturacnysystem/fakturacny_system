from __future__ import annotations

from hashlib import sha256
import json
import os
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

from .cross_asset import CrossAssetAllocator, UniverseAllocation, UniverseAllocationInput
from .causal_twin_bridge import CausalTwinBridge
from .adaptive_personality_engine import AdaptivePersonalityEngine
from .autonomous_fund_brain import AutonomousFundBrain
from .capital_constraint_compiler import CapitalConstraintCompiler
from .capital_survival_doctrine import CapitalSurvivalDoctrine
from .committee_escalation_protocol import CommitteeEscalationProtocol
from .cross_reality_signal import CrossRealitySignalFusion
from .cross_reality_integrity_guard import CrossRealityIntegrityGuard
from .evolutionary_strategy_research import EvolutionaryStrategyResearchLayer
from .events import EventFabric, UniverseEventEnvelope, build_event
from .execution import ExecutionIntelligence, ExecutionPlan
from .execution_intel import ExecutionDecisionEnvelope, ExecutionIntelligenceEngine
from .evidence_vault_index import EvidenceVaultIndexBuilder
from .future_simulation_ensemble import FutureSimulationEnsembleEngine
from .future_simulation_engine import DeterministicFutureSimulationEngine
from .global_market_brain import GlobalMarketBrain
from .global_market_calibration import GlobalMarketCalibrationEngine
from .institutional_gate_compiler import InstitutionalGateCompiler
from .institutional_readiness import InstitutionalReadinessEngine
from .intelligence_ledger import DeterministicIntelligenceLedger
from .macro_micro_decision_bridge import MacroMicroDecisionBridge
from .market_energy_physics import MarketEnergyPhysicsModel
from .memory import DecisionPacket, MemoryEngine
from .meta import MetaDecisionSnapshot, MetaIntelligenceEngine
from .mission import MissionDecision, MissionEngine, infer_strategy_family
from .multi_horizon_decision import MultiHorizonDecisionLayer
from .ops import UniverseOpsService, UniverseOpsSnapshot
from .phase50_certification import Phase50CertificationCompiler
from .personality_stability_governor import PersonalityStabilityGovernor
from .scenario_portfolio_netting import ScenarioPortfolioNettingEngine
from .parliament import (
    PARLIAMENT_MODE_TOP_1,
    ParliamentVerdict,
    StrategyParliament,
    StrategyProposal,
    strategy_proposals_from_intent,
)
from .replay_ladder import (
    ActivationGateDecision,
    AdaptiveActivationGate,
    PromotionDecision,
    PromotionLadderEngine,
    PromotionLadderState,
    PromotionStage,
    ReplayLadderEngine,
    StrategyReplayGrade,
)
from .replay_distributed_bridge import ReplayDistributedBridge
from .research import PromotionState, ResearchReplayLab
from .shield import ShieldDecision, UniverseShield
from .state import SymbolStateSnapshot, WorldStateGraph, WorldStateSnapshot, WorldStateStore


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


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _normalize_learning_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = _safe_mapping(payload or {})
    out = dict(raw)
    errors = raw.get("errors", [])
    if not isinstance(errors, list):
        errors = [str(errors)] if str(errors) else []
    out["grading_state_summary"] = _safe_mapping(raw.get("grading_state_summary", {}))
    out["latest_policy_grade_summary"] = _safe_mapping(raw.get("latest_policy_grade_summary", {}))
    out["promotion_candidates_count"] = max(0, _safe_int(raw.get("promotion_candidates_count", 0), 0))
    out["demotion_candidates_count"] = max(0, _safe_int(raw.get("demotion_candidates_count", 0), 0))
    out["retirement_candidates_count"] = max(0, _safe_int(raw.get("retirement_candidates_count", 0), 0))
    out["shield_aware_learning_summary"] = _safe_mapping(raw.get("shield_aware_learning_summary", {}))
    out["memory_compaction_summary"] = _safe_mapping(raw.get("memory_compaction_summary", {}))
    out["replay_evidence_summary"] = _safe_mapping(raw.get("replay_evidence_summary", {}))
    out["bounded_retention_health"] = _safe_mapping(raw.get("bounded_retention_health", {"status": "unknown"}))
    out["errors"] = [str(item) for item in errors if str(item)]
    return out


@dataclass(frozen=True)
class UniverseMindCycleResult:
    world_state: WorldStateSnapshot
    mission: MissionDecision
    parliament: ParliamentVerdict
    execution_plan: ExecutionPlan
    shield: ShieldDecision
    decision_packet: DecisionPacket
    published_events: list[UniverseEventEnvelope] = field(default_factory=list)
    research: PromotionState | None = None
    allocations: list[UniverseAllocation] = field(default_factory=list)
    ops_snapshot: UniverseOpsSnapshot | None = None
    meta_snapshot: MetaDecisionSnapshot | None = None
    execution_intelligence: ExecutionDecisionEnvelope | None = None
    advanced_intelligence: dict[str, Any] = field(default_factory=dict)


class UniverseMind:
    """Unified autonomous control layer over state, mission, strategy, execution, and memory."""

    def __init__(
        self,
        run_dir: str,
        *,
        fabric: EventFabric | None = None,
        graph: WorldStateGraph | None = None,
        world_state_store: WorldStateStore | None = None,
        mission_engine: MissionEngine | None = None,
        parliament: StrategyParliament | None = None,
        execution: ExecutionIntelligence | None = None,
        execution_intel: ExecutionIntelligenceEngine | None = None,
        shield: UniverseShield | None = None,
        memory: MemoryEngine | None = None,
        research: ResearchReplayLab | None = None,
        cross_asset_allocator: CrossAssetAllocator | None = None,
        ops: UniverseOpsService | None = None,
        meta: MetaIntelligenceEngine | None = None,
        replay_ladder: ReplayLadderEngine | None = None,
        promotion_ladder: PromotionLadderEngine | None = None,
        activation_gate: AdaptiveActivationGate | None = None,
        global_market_brain: GlobalMarketBrain | None = None,
        multi_horizon_layer: MultiHorizonDecisionLayer | None = None,
        market_energy_model: MarketEnergyPhysicsModel | None = None,
        future_simulation: DeterministicFutureSimulationEngine | None = None,
        cross_reality_fusion: CrossRealitySignalFusion | None = None,
        personality_engine: AdaptivePersonalityEngine | None = None,
        survival_doctrine: CapitalSurvivalDoctrine | None = None,
        evolutionary_research: EvolutionaryStrategyResearchLayer | None = None,
        fund_brain: AutonomousFundBrain | None = None,
        institutional_readiness: InstitutionalReadinessEngine | None = None,
        intelligence_ledger: DeterministicIntelligenceLedger | None = None,
        scenario_portfolio_netting: ScenarioPortfolioNettingEngine | None = None,
        capital_constraint_compiler: CapitalConstraintCompiler | None = None,
        global_market_calibration: GlobalMarketCalibrationEngine | None = None,
        cross_reality_integrity_guard: CrossRealityIntegrityGuard | None = None,
        personality_stability_governor: PersonalityStabilityGovernor | None = None,
        committee_escalation_protocol: CommitteeEscalationProtocol | None = None,
        institutional_gate_compiler: InstitutionalGateCompiler | None = None,
        macro_micro_decision_bridge: MacroMicroDecisionBridge | None = None,
        future_simulation_ensemble: FutureSimulationEnsembleEngine | None = None,
        causal_twin_bridge: CausalTwinBridge | None = None,
        replay_distributed_bridge: ReplayDistributedBridge | None = None,
        evidence_vault_index: EvidenceVaultIndexBuilder | None = None,
        phase50_certification: Phase50CertificationCompiler | None = None,
    ) -> None:
        self.run_dir = str(run_dir)
        self.fabric = fabric or EventFabric(self.run_dir)
        self.world_state_store = world_state_store or WorldStateStore(graph or WorldStateGraph())
        self.graph = self.world_state_store.graph
        self.mission_engine = mission_engine or MissionEngine()
        self.parliament = parliament or StrategyParliament()
        self.execution = execution or ExecutionIntelligence()
        self.execution_intel = execution_intel or ExecutionIntelligenceEngine()
        self.shield = shield or UniverseShield()
        self.memory = memory or MemoryEngine(self.run_dir)
        self.research = research or ResearchReplayLab()
        self.cross_asset_allocator = cross_asset_allocator or CrossAssetAllocator()
        self.ops = ops or UniverseOpsService()
        self.meta = meta or MetaIntelligenceEngine(self.run_dir)
        self.replay_ladder = replay_ladder or ReplayLadderEngine()
        self.promotion_ladder = promotion_ladder or PromotionLadderEngine()
        self.activation_gate = activation_gate or AdaptiveActivationGate()
        self.global_market_brain = global_market_brain or GlobalMarketBrain()
        self.multi_horizon_layer = multi_horizon_layer or MultiHorizonDecisionLayer()
        self.market_energy_model = market_energy_model or MarketEnergyPhysicsModel()
        self.future_simulation = future_simulation or DeterministicFutureSimulationEngine()
        self.cross_reality_fusion = cross_reality_fusion or CrossRealitySignalFusion()
        self.personality_engine = personality_engine or AdaptivePersonalityEngine()
        self.survival_doctrine = survival_doctrine or CapitalSurvivalDoctrine()
        self.evolutionary_research = evolutionary_research or EvolutionaryStrategyResearchLayer()
        self.fund_brain = fund_brain or AutonomousFundBrain()
        self.institutional_readiness = institutional_readiness or InstitutionalReadinessEngine()
        self.intelligence_ledger = intelligence_ledger or DeterministicIntelligenceLedger()
        self.scenario_portfolio_netting = scenario_portfolio_netting or ScenarioPortfolioNettingEngine()
        self.capital_constraint_compiler = capital_constraint_compiler or CapitalConstraintCompiler()
        self.global_market_calibration = global_market_calibration or GlobalMarketCalibrationEngine()
        self.cross_reality_integrity_guard = cross_reality_integrity_guard or CrossRealityIntegrityGuard()
        self.personality_stability_governor = personality_stability_governor or PersonalityStabilityGovernor()
        self.committee_escalation_protocol = committee_escalation_protocol or CommitteeEscalationProtocol()
        self.institutional_gate_compiler = institutional_gate_compiler or InstitutionalGateCompiler()
        self.macro_micro_decision_bridge = macro_micro_decision_bridge or MacroMicroDecisionBridge()
        self.future_simulation_ensemble = future_simulation_ensemble or FutureSimulationEnsembleEngine()
        self.causal_twin_bridge = causal_twin_bridge or CausalTwinBridge()
        self.replay_distributed_bridge = replay_distributed_bridge or ReplayDistributedBridge()
        self.evidence_vault_index = evidence_vault_index or EvidenceVaultIndexBuilder()
        self.phase50_certification = phase50_certification or Phase50CertificationCompiler()

    def _project_event(self, event: UniverseEventEnvelope) -> None:
        try:
            self.world_state_store.apply_event(event)
        except Exception as exc:
            self.graph.record_error(f"projection_failed:{event.event_type}:{exc}")

    def get_world_state(self) -> WorldStateSnapshot:
        try:
            return self.world_state_store.get_world_state()
        except Exception as exc:
            self.graph.record_error(f"snapshot_failed:{exc}")
            return self.graph.snapshot()

    def get_symbol_state(self, symbol: str) -> SymbolStateSnapshot:
        return self.world_state_store.get_symbol_state(symbol)

    def _replay_feature_enabled(self) -> bool:
        return _env_bool("UNIVERSE_REPLAY_PROMOTION_ENABLED", False)

    def _conservative_promotion_state(
        self,
        *,
        strategy_fingerprints: Iterable[str],
        reason: str,
    ) -> PromotionLadderState:
        decisions = [
            PromotionDecision(
                strategy_fingerprint=fingerprint,
                current_stage=PromotionStage.OFFLINE_REPLAY,
                next_stage_candidate=PromotionStage.OFFLINE_REPLAY,
                promotion_confidence=0.0,
                capital_scaling_factor=0.0,
                required_observation_window=self.promotion_ladder.min_replay_evidence,
                safety_override_flag=True,
                promotion_reason_codes=("conservative_ranking_fallback",),
                demotion_reason_codes=(str(reason),),
                activation_recommendation="hold",
            )
            for fingerprint in sorted(set(str(item) for item in strategy_fingerprints if str(item)))
        ]
        return PromotionLadderState(
            decisions=decisions,
            activation_gates=[],
            top_strategy_candidates=[],
            quarantine_strategy_list=[],
            promotion_readiness_score=0.0,
            promotion_engine_enabled=False,
            fallback_reason=str(reason),
        )

    def _run_phase8_replay_ladder(
        self,
        *,
        mission: MissionDecision,
        world: WorldStateSnapshot,
        plan: ExecutionPlan,
    ) -> dict[str, Any]:
        if not self._replay_feature_enabled():
            return {}

        phase8_errors: list[str] = []
        replay_payload: dict[str, Any]
        ladder_payload: dict[str, Any]
        capital_scale = 1.0
        if plan.actionable:
            equity = max(1.0, float(world.portfolio_state.equity_quote or 0.0))
            capital_scale = _clamp(float(plan.target_notional_quote) / equity, 0.05, 2.0)

        try:
            graded_packets = self.memory.load(graded=True)
        except Exception as exc:
            replay_payload = {
                "enabled": True,
                "batch_id": _stable_hash({"phase8": "load_failed", "mission": mission.mission}),
                "processed_packets": 0,
                "scenario_count": 0,
                "deterministic": True,
                "failed": True,
                "failure_reason": f"replay_input_load_failed:{exc}",
                "backlog_depth": 0,
                "reproducibility_metadata": {},
                "strategy_grades": [],
                "trace_count": 0,
                "quarantine_strategy_fingerprints": [],
                "memory_grading_drift": 0.0,
                "top_strategy_candidates": [],
                "session_id": "",
                "reconstructed_decisions": [],
                "walk_forward": {},
                "comparative_counterfactual": {},
                "inferred_markers": [],
            }
            conservative = self._conservative_promotion_state(
                strategy_fingerprints=[],
                reason=f"replay_engine_failure:{exc}",
            )
            return {
                "replay_batch_status": replay_payload,
                "promotion_ladder_state": conservative.to_dict(),
                "errors": [f"replay_engine_failure:{exc}"],
            }

        try:
            replay_session = self.replay_ladder.run_session(
                packets=graded_packets,
                scenarios=(),
                mission_filter=mission.mission,
                capital_scale=capital_scale,
                holdout_ratio=0.20,
                walk_forward_window=32,
                walk_forward_step=16,
                counterfactual_capital_scale=max(0.05, capital_scale * 0.65),
                counterfactual_constraints={
                    "counterfactual_mode": "lower_capital_shadow",
                    "inference_only": True,
                },
            )
            replay_payload = dict(replay_session.batch_status)
            replay_payload["session_id"] = replay_session.session_id
            replay_payload["reconstructed_decisions"] = [dict(row) for row in replay_session.reconstructed_decisions]
            replay_payload["walk_forward"] = dict(replay_session.walk_forward)
            replay_payload["comparative_counterfactual"] = dict(replay_session.comparative_counterfactual)
            replay_payload["inferred_markers"] = [str(item) for item in replay_session.inferred_markers]
            self.memory.persist_replay_batch_status(replay_payload)
            self.memory.persist_replay_grades(
                batch_id=str(replay_payload.get("batch_id", "")),
                grades=[dict(row) for row in replay_payload.get("strategy_grades", []) if isinstance(row, Mapping)],
                reproducibility_metadata=_safe_mapping(replay_payload.get("reproducibility_metadata", {})),
            )
        except Exception as exc:
            replay_payload = {
                "enabled": True,
                "batch_id": _stable_hash({"phase8": "replay_failed", "mission": mission.mission}),
                "processed_packets": 0,
                "scenario_count": 0,
                "deterministic": True,
                "failed": True,
                "failure_reason": f"replay_engine_failure:{exc}",
                "backlog_depth": 0,
                "reproducibility_metadata": {},
                "strategy_grades": [],
                "trace_count": 0,
                "quarantine_strategy_fingerprints": [],
                "memory_grading_drift": 0.0,
                "top_strategy_candidates": [],
                "session_id": "",
                "reconstructed_decisions": [],
                "walk_forward": {},
                "comparative_counterfactual": {},
                "inferred_markers": [],
            }
            phase8_errors.append(f"replay_engine_failure:{exc}")
            try:
                self.memory.persist_replay_batch_status(replay_payload)
            except Exception as persist_exc:
                phase8_errors.append(f"replay_batch_persist_failed:{persist_exc}")
            conservative = self._conservative_promotion_state(
                strategy_fingerprints=[],
                reason=f"replay_engine_failure:{exc}",
            )
            ladder_payload = conservative.to_dict()
            try:
                self.memory.persist_promotion_ladder_state(ladder_payload)
            except Exception as persist_exc:
                phase8_errors.append(f"promotion_state_persist_failed:{persist_exc}")
            return {
                "replay_batch_status": replay_payload,
                "promotion_ladder_state": ladder_payload,
                "errors": phase8_errors,
            }

        latest_grades: list[StrategyReplayGrade] = []
        for row in replay_payload.get("strategy_grades", []):
            if not isinstance(row, Mapping):
                continue
            try:
                latest_grades.append(StrategyReplayGrade.from_mapping(row))
            except Exception as exc:
                phase8_errors.append(f"replay_grade_parse_failed:{exc}")

        history: dict[str, list[StrategyReplayGrade]] = {}
        inconsistent: list[str] = []
        try:
            history_payload, inconsistent = self.memory.load_replay_grade_history()
            for fingerprint, rows in history_payload.items():
                parsed: list[StrategyReplayGrade] = []
                for row in rows:
                    if not isinstance(row, Mapping):
                        inconsistent.append(str(fingerprint))
                        continue
                    try:
                        parsed.append(StrategyReplayGrade.from_mapping(row))
                    except Exception:
                        inconsistent.append(str(fingerprint))
                if parsed:
                    history[str(fingerprint)] = parsed
        except Exception as exc:
            phase8_errors.append(f"replay_grade_history_load_failed:{exc}")
            inconsistent.extend(row.strategy_fingerprint for row in latest_grades if row.strategy_fingerprint)

        previous_decisions: dict[str, PromotionDecision] = {}
        try:
            previous_state = self.memory.latest_promotion_ladder_state()
            for row in previous_state.get("decisions", []):
                if not isinstance(row, Mapping):
                    continue
                decision = PromotionDecision.from_mapping(row)
                if decision.strategy_fingerprint:
                    previous_decisions[decision.strategy_fingerprint] = decision
        except Exception as exc:
            phase8_errors.append(f"promotion_state_load_failed:{exc}")

        inconsistent = sorted(set(inconsistent + [str(item) for item in replay_payload.get("quarantine_strategy_fingerprints", []) if str(item)]))

        try:
            decisions = self.promotion_ladder.evaluate(
                latest_grades=latest_grades,
                history=history,
                previous_decisions=previous_decisions,
                inconsistent_fingerprints=inconsistent,
            )
        except Exception as exc:
            phase8_errors.append(f"promotion_engine_failure:{exc}")
            fallback = self._conservative_promotion_state(
                strategy_fingerprints=[row.strategy_fingerprint for row in latest_grades],
                reason=f"promotion_engine_failure:{exc}",
            )
            ladder_payload = fallback.to_dict()
            try:
                self.memory.persist_promotion_ladder_state(ladder_payload)
            except Exception as persist_exc:
                phase8_errors.append(f"promotion_state_persist_failed:{persist_exc}")
            return {
                "replay_batch_status": replay_payload,
                "promotion_ladder_state": ladder_payload,
                "errors": phase8_errors,
            }

        try:
            activation_gates = self.activation_gate.apply(
                decisions=decisions,
                world=world,
                replay_live_divergence=_safe_float(replay_payload.get("memory_grading_drift", 0.0), 0.0),
            )
        except Exception as exc:
            phase8_errors.append(f"activation_gate_failure:{exc}")
            forced_decisions: list[PromotionDecision] = []
            for row in decisions:
                forced_decisions.append(
                    PromotionDecision(
                        strategy_fingerprint=row.strategy_fingerprint,
                        current_stage=row.current_stage,
                        next_stage_candidate=PromotionStage.OFFLINE_REPLAY,
                        promotion_confidence=row.promotion_confidence,
                        capital_scaling_factor=0.0,
                        required_observation_window=row.required_observation_window,
                        safety_override_flag=True,
                        promotion_reason_codes=tuple(list(row.promotion_reason_codes) + ["activation_gate_failure_forced_sandbox"]),
                        demotion_reason_codes=row.demotion_reason_codes,
                        activation_recommendation="hold",
                        quarantine_recommendation=row.quarantine_recommendation,
                    )
                )
            decisions = forced_decisions
            activation_gates = [
                ActivationGateDecision(
                    strategy_fingerprint=row.strategy_fingerprint,
                    allowed=False,
                    resolved_stage=PromotionStage.OFFLINE_REPLAY,
                    capital_scaling_factor=0.0,
                    per_strategy_exposure_ceiling=0.0,
                    risk_multiplier=0.0,
                    kill_switch=True,
                    reason_codes=("activation_gate_failure_forced_sandbox",),
                )
                for row in decisions
            ]

        gate_by_fingerprint = {row.strategy_fingerprint: row for row in activation_gates}
        top_candidates: list[dict[str, Any]] = []
        for decision in decisions:
            gate = gate_by_fingerprint.get(decision.strategy_fingerprint)
            top_candidates.append(
                {
                    "strategy_fingerprint": decision.strategy_fingerprint,
                    "promotion_confidence": float(decision.promotion_confidence),
                    "current_stage": decision.current_stage.value,
                    "next_stage_candidate": decision.next_stage_candidate.value if decision.next_stage_candidate is not None else decision.current_stage.value,
                    "capital_scaling_factor": float(gate.capital_scaling_factor if gate is not None else decision.capital_scaling_factor),
                    "activation_allowed": bool(gate.allowed) if gate is not None else False,
                }
            )
        top_candidates.sort(key=lambda row: (bool(row.get("activation_allowed", False)), float(row.get("promotion_confidence", 0.0))), reverse=True)
        top_candidates = top_candidates[:5]
        quarantine = sorted(
            set(
                [row.strategy_fingerprint for row in decisions if row.next_stage_candidate == PromotionStage.QUARANTINE]
                + [str(item) for item in replay_payload.get("quarantine_strategy_fingerprints", []) if str(item)]
                + inconsistent
            )
        )
        readiness = 0.0
        if top_candidates:
            readiness = _clamp(max(_safe_float(row.get("promotion_confidence", 0.0), 0.0) for row in top_candidates), 0.0, 1.0)

        ladder_state = PromotionLadderState(
            decisions=decisions,
            activation_gates=activation_gates,
            top_strategy_candidates=top_candidates,
            quarantine_strategy_list=quarantine,
            promotion_readiness_score=readiness,
            promotion_engine_enabled=not bool(phase8_errors),
            fallback_reason=phase8_errors[0] if phase8_errors else "",
        )
        ladder_payload = ladder_state.to_dict()
        try:
            self.memory.persist_promotion_ladder_state(ladder_payload)
        except Exception as exc:
            phase8_errors.append(f"promotion_state_persist_failed:{exc}")

        return {
            "replay_batch_status": replay_payload,
            "promotion_ladder_state": ladder_payload,
            "errors": phase8_errors,
        }

    def _apply_mission_policy_to_proposals(
        self,
        proposals: Iterable[StrategyProposal],
        *,
        mission: MissionDecision,
        symbol: str,
    ) -> list[StrategyProposal]:
        if mission.mission == "observation_only":
            return [
                StrategyProposal(
                    strategy="no_trade_guardian",
                    instrument=symbol,
                    action="hold",
                    side="flat",
                    target_notional_quote=0.0,
                    expected_value_bps=0.0,
                    confidence=1.0,
                    expected_hold_time_s=60.0,
                    execution_sensitivity=0.0,
                    slippage_risk_bps=0.0,
                    regime_compatibility=1.0,
                    risk_cost_bps=0.0,
                    reason_codes=["mission_observation_only"],
                    mission_compatibility=1.0,
                    source="guard",
                    metadata={"mission_filtered": True, "family": "guardian"},
                )
            ]

        rows: list[StrategyProposal] = []
        for proposal in proposals:
            family = infer_strategy_family(proposal.strategy)
            reasons = list(proposal.reason_codes)
            blocked = family in set(mission.blocked_strategy_families)
            allowed_set = set(mission.allowed_strategy_families)
            explicitly_allowed = bool(not allowed_set or family in allowed_set)
            compatibility = float(proposal.mission_compatibility)

            if blocked:
                compatibility = 0.0
                reasons.append(f"mission_blocked_family:{family}")
            elif not explicitly_allowed and proposal.strategy != "no_trade_guardian":
                compatibility *= 0.25
                reasons.append(f"mission_deprioritized_family:{family}")
            if mission.allow_new_risk is False and proposal.side == "buy" and proposal.strategy != "no_trade_guardian":
                compatibility = min(compatibility, 0.10)
                reasons.append("mission_blocks_new_risk_buy")
            if mission.no_trade_preferred and proposal.strategy != "no_trade_guardian":
                compatibility = min(compatibility, 0.20)
                reasons.append("mission_no_trade_preferred")

            clipped_notional = float(proposal.target_notional_quote)
            if mission.clip_size_conservatively and proposal.side == "buy":
                clipped_notional = float(clipped_notional * 0.60)
                reasons.append("mission_conservative_size_clip")

            updated = replace(
                proposal,
                target_notional_quote=max(0.0, clipped_notional),
                mission_compatibility=max(0.0, min(1.0, compatibility)),
                reason_codes=reasons,
                metadata={
                    **proposal.metadata,
                    "mission": mission.mission,
                    "mission_family": family,
                    "mission_family_allowed": bool(explicitly_allowed),
                    "mission_family_blocked": bool(blocked),
                    "mission_execution_posture_hint": mission.execution_posture_hint,
                    "mission_shield_posture_hint": mission.shield_posture_hint,
                    "mission_aggressiveness_tier": mission.aggressiveness_tier,
                },
            )
            rows.append(updated)

        if not any(row.strategy == "no_trade_guardian" for row in rows):
            rows.append(
                StrategyProposal(
                    strategy="no_trade_guardian",
                    instrument=symbol,
                    action="hold",
                    side="flat",
                    target_notional_quote=0.0,
                    expected_value_bps=0.0,
                    confidence=1.0,
                    expected_hold_time_s=60.0,
                    execution_sensitivity=0.0,
                    slippage_risk_bps=0.0,
                    regime_compatibility=1.0,
                    risk_cost_bps=0.0,
                    reason_codes=["mission_guardian_added"],
                    mission_compatibility=1.0,
                    source="guard",
                    metadata={"mission_filtered": True, "family": "guardian"},
                )
            )
        return rows

    def _apply_execution_feedback_to_proposals(
        self,
        proposals: Iterable[StrategyProposal],
        *,
        learning_summary: Mapping[str, Any] | None,
    ) -> list[StrategyProposal]:
        payload = _safe_mapping(learning_summary)
        feedback = _safe_mapping(payload.get("execution_feedback_summary", {}))
        if not feedback:
            return list(proposals)
        fill_quality = _clamp(_safe_float(feedback.get("fill_quality_score", 0.7), 0.7), 0.0, 1.0)
        timing_error = _clamp(_safe_float(feedback.get("timing_error_score", 0.3), 0.3), 0.0, 1.0)
        opportunity_decay = _clamp(_safe_float(feedback.get("opportunity_decay_metric", 0.3), 0.3), 0.0, 1.0)
        slippage_error = max(0.0, _safe_float(feedback.get("realized_vs_expected_slippage", 0.0), 0.0))

        adjusted: list[StrategyProposal] = []
        for proposal in proposals:
            if proposal.strategy == "no_trade_guardian":
                adjusted.append(proposal)
                continue
            sensitivity = _clamp(proposal.execution_sensitivity, 0.0, 1.0)
            execution_penalty = _clamp(
                ((1.0 - fill_quality) * 0.25 * sensitivity)
                + (timing_error * 0.20 * sensitivity)
                + (opportunity_decay * 0.20 * sensitivity)
                + (min(slippage_error / 25.0, 1.0) * 0.15),
                0.0,
                0.75,
            )
            if execution_penalty <= 0.0:
                adjusted.append(proposal)
                continue
            updated = replace(
                proposal,
                expected_value_bps=max(0.0, proposal.expected_value_bps * (1.0 - execution_penalty)),
                reason_codes=list(proposal.reason_codes) + ["phase9_execution_feedback_penalty"],
                metadata={
                    **proposal.metadata,
                    "execution_feedback_penalty": execution_penalty,
                    "execution_feedback_fill_quality": fill_quality,
                    "execution_feedback_timing_error": timing_error,
                    "execution_feedback_decay": opportunity_decay,
                    "execution_feedback_slippage_error": slippage_error,
                },
            )
            adjusted.append(updated)
        return adjusted

    def emit(
        self,
        *,
        event_type: str,
        source: str,
        partition_key: str,
        payload: Mapping[str, Any],
        correlation_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> UniverseEventEnvelope | None:
        emitted = self.fabric.emit(
            event_type=event_type,
            source=source,
            partition_key=partition_key,
            payload=payload,
            correlation_id=correlation_id,
            metadata=metadata,
        )
        if emitted is not None:
            self._project_event(emitted)
        return emitted

    def ingest(self, event: UniverseEventEnvelope | Mapping[str, Any]) -> UniverseEventEnvelope | None:
        if isinstance(event, UniverseEventEnvelope):
            envelope = event
        else:
            raw_ts = event.get("ts")
            ts_value = None if raw_ts in {None, ""} else _safe_float(raw_ts, 0.0)
            envelope = build_event(
                event_type=str(event.get("event_type", "")),
                source=str(event.get("source", "unknown")),
                partition_key=str(event.get("partition_key", "global")),
                payload=dict(event.get("payload", {}) or {}),
                event_id=str(event.get("event_id", "") or "") or None,
                idempotency_key=str(event.get("idempotency_key", "") or "") or None,
                correlation_id=str(event.get("correlation_id", "") or ""),
                metadata=dict(event.get("metadata", {}) or {}),
                ts=ts_value,
            )
        published = self.fabric.publish(envelope)
        if published is not None:
            self._project_event(published)
        return published

    def replay(self) -> list[UniverseEventEnvelope]:
        return self.fabric.replay()

    def ingest_decision_context(self, context: Any, *, venue: str = "synthetic", source: str = "decision_context") -> list[UniverseEventEnvelope]:
        symbol = str(getattr(context, "symbol", "UNKNOWN") or "UNKNOWN")
        features = getattr(context, "features", {}) if isinstance(getattr(context, "features", {}), Mapping) else {}
        market_watch = getattr(context, "market_watch", {}) if isinstance(getattr(context, "market_watch", {}), Mapping) else {}
        trend_2m_bps = _safe_float(market_watch.get("trend_2m_bps", 0.0), 0.0)
        realized_vol = _safe_float(features.get("realized_vol", 0.0), 0.0)
        regime = "PANIC" if realized_vol >= 0.03 else "TREND" if abs(trend_2m_bps) >= 25.0 else "RANGE"
        liquidity_regime = "THIN" if _safe_float(getattr(context, "depth_notional", 0.0), 0.0) < 1_000.0 else "DEEP" if _safe_float(getattr(context, "depth_notional", 0.0), 0.0) > 10_000.0 else "NORMAL"
        volatility_regime = "HIGH_VOL" if realized_vol >= 0.015 or _safe_float(getattr(context, "spread_bps", 0.0), 0.0) >= 40.0 else "LOW_VOL"
        events: list[UniverseEventEnvelope] = []
        for event_type, payload in (
            (
                "MarketTickEvent",
                {
                    "symbol": symbol,
                    "venue": venue,
                    "market_class": str(getattr(context, "market_class", "crypto_spot") or "crypto_spot"),
                    "mid": _safe_float(getattr(context, "mid", 0.0), 0.0),
                    "spread_bps": _safe_float(getattr(context, "spread_bps", 0.0), 0.0),
                    "trend_bps": trend_2m_bps,
                    "realized_vol": realized_vol,
                },
            ),
            (
                "BookSnapshotEvent",
                {
                    "symbol": symbol,
                    "venue": venue,
                    "spread_bps": _safe_float(getattr(context, "spread_bps", 0.0), 0.0),
                    "depth_notional": _safe_float(getattr(context, "depth_notional", 0.0), 0.0),
                },
            ),
            (
                "AccountSnapshotEvent",
                {
                    "symbol": symbol,
                    "venue": venue,
                    "equity_quote": max(_safe_float(getattr(context, "quote_free", 0.0), 0.0), _safe_float(getattr(context, "position_notional_quote", 0.0), 0.0) + _safe_float(getattr(context, "quote_free", 0.0), 0.0)),
                    "free_quote": _safe_float(getattr(context, "quote_free", 0.0), 0.0),
                    "exposure_quote": abs(_safe_float(getattr(context, "signed_exposure_notional_quote", 0.0), 0.0)),
                    "drawdown_pct": _safe_float(getattr(context, "drawdown_pct", 0.0), 0.0),
                },
            ),
            (
                "HealthEvent",
                {
                    "symbol": symbol,
                    "venue": venue,
                    "status": "OK" if _safe_float(getattr(context, "latency_ms", 0.0), 0.0) < 250.0 else "WARN",
                    "latency_ms": _safe_float(getattr(context, "latency_ms", 0.0), 0.0),
                    "health_score": max(0.0, min(1.0, 1.0 - _safe_float(getattr(context, "latency_ms", 0.0), 0.0) / 1_000.0)),
                    "rejection_ratio": 0.0,
                    "stale_feed": False,
                    "desync": False,
                },
            ),
            (
                "RiskEvent",
                {
                    "symbol": symbol,
                    "venue": venue,
                    "model_confidence": _safe_float(getattr(context, "forecast_confidence", 0.5), 0.5),
                    "uncertainty_bps": _safe_float(getattr(context, "forecast_sigma", 0.0), 0.0),
                    "mode": "normal",
                    "observe_only": False,
                    "hard_stop": False,
                },
            ),
            (
                "RegimeEvent",
                {
                    "symbol": symbol,
                    "venue": venue,
                    "regime": regime,
                    "confidence": _safe_float(getattr(context, "forecast_confidence", 0.5), 0.5),
                    "volatility_regime": volatility_regime,
                    "liquidity_regime": liquidity_regime,
                    "expansion_state": "EXPANSION" if realized_vol >= 0.01 else "COMPRESSION",
                    "panic": regime == "PANIC",
                },
            ),
        ):
            row = self.emit(event_type=event_type, source=source, partition_key=symbol, payload=payload)
            if row is not None:
                events.append(row)
        return events

    def run_cycle(
        self,
        *,
        symbol: str,
        venue: str,
        proposals: Iterable[StrategyProposal] | None = None,
        cross_asset_inputs: Iterable[UniverseAllocationInput] | None = None,
        parliament_mode: str = PARLIAMENT_MODE_TOP_1,
        parliament_top_n: int = 2,
        parliament_score_floor: float | None = None,
        correlation_id: str = "",
    ) -> UniverseMindCycleResult:
        decision_world = self.get_world_state()
        mission = self.mission_engine.choose(decision_world, previous_mission=decision_world.strategy_state.last_mission)
        published_events: list[UniverseEventEnvelope] = []
        pre_learning_summary: dict[str, Any] = {}
        try:
            pre_learning_summary = _normalize_learning_summary(self.memory.learning_snapshot().to_dict())
        except Exception:
            pre_learning_summary = _normalize_learning_summary({})
        mission_event = self.emit(
            event_type="MissionEvent",
            source="universe_mind",
            partition_key=symbol,
            payload={"symbol": symbol, "venue": venue, **mission.to_dict()},
            correlation_id=correlation_id,
        )
        if mission_event is not None:
            published_events.append(mission_event)

        proposal_rows = list(proposals or [])
        if not proposal_rows:
            proposal_rows = [
                StrategyProposal(
                    strategy="no_trade_guardian",
                    instrument=symbol,
                    action="hold",
                    side="flat",
                    target_notional_quote=0.0,
                    expected_value_bps=0.0,
                    confidence=1.0,
                    expected_hold_time_s=60.0,
                    execution_sensitivity=0.0,
                    slippage_risk_bps=0.0,
                    regime_compatibility=1.0,
                    risk_cost_bps=0.0,
                    reason_codes=["no_proposals"],
                    mission_compatibility=1.0,
                    source="guard",
                )
            ]
        proposal_rows = self._apply_mission_policy_to_proposals(proposal_rows, mission=mission, symbol=symbol)
        proposal_rows = self._apply_execution_feedback_to_proposals(
            proposal_rows,
            learning_summary=pre_learning_summary,
        )
        cycle_id = _stable_hash(
            {
                "symbol": symbol,
                "venue": venue,
                "correlation_id": correlation_id,
                "world_state_fingerprint": self.memory.fingerprint_world_state(decision_world.to_dict()),
                "mission": mission.mission,
                "proposal_strategies": [row.strategy for row in proposal_rows],
            }
        )
        meta_for_shield: Mapping[str, Any] | None = None
        meta_available_for_shield = True
        try:
            proposal_rows, meta_snapshot = self.meta.adapt_proposals(
                proposal_rows,
                world=decision_world,
                mission=mission,
                cycle_id=cycle_id,
            )
            meta_for_shield = meta_snapshot.to_dict()
        except Exception as exc:
            fallback_note = f"meta_intelligence_error:{exc}"
            meta_snapshot = MetaDecisionSnapshot(
                regime_cluster=str(decision_world.market_state.regime or "unknown"),
                exploration_budget=0.0,
                exploitation_budget=1.0,
                risk_scale=1.0,
                strategy_weights=[],
                memory_records=0,
                notes=[fallback_note],
            )
            proposal_rows = [
                replace(
                    row,
                    metadata={**row.metadata, "meta": {"error": str(exc)}},
                    reason_codes=tuple(list(row.reason_codes) + [fallback_note]),
                )
                for row in proposal_rows
            ]
            meta_for_shield = None
            meta_available_for_shield = False
        for proposal in proposal_rows:
            event = self.emit(
                event_type="StrategyProposalEvent",
                source="universe_mind",
                partition_key=symbol,
                payload={"symbol": symbol, "venue": venue, **proposal.to_dict()},
                correlation_id=correlation_id,
            )
            if event is not None:
                published_events.append(event)

        verdict = self.parliament.judge(
            proposal_rows,
            world=decision_world,
            mission=mission,
            selection_mode=parliament_mode,
            top_n=parliament_top_n,
            score_floor=parliament_score_floor,
        )
        plan = self.execution.build_plan(verdict.selected, world=decision_world, mission=mission)
        execution_decision = self.execution_intel.evaluate(
            proposal=verdict.selected,
            baseline_plan=plan,
            world=decision_world,
            mission=mission,
            learning_summary=pre_learning_summary,
        )
        plan = execution_decision.plan
        merged_meta_for_shield = dict(meta_for_shield or {})
        merged_meta_for_shield["meta_available"] = bool(meta_available_for_shield)
        merged_meta_for_shield.update(execution_decision.to_shield_meta())
        meta_for_shield = merged_meta_for_shield
        shield = self.shield.assess(
            world=decision_world,
            mission=mission,
            verdict=verdict,
            plan=plan,
            meta_diagnostics=meta_for_shield,
            cycle_id=cycle_id,
        )
        if shield.approved and plan.actionable:
            plan = plan.scaled(shield.size_scale)
        else:
            reason = shield.reason_codes[0] if shield.reason_codes else "shield_block"
            plan = plan.as_non_actionable(reason)

        shield_event = self.emit(
            event_type="RiskEvent",
            source="universe_shield",
            partition_key=symbol,
            payload={
                "symbol": symbol,
                "venue": venue,
                "mode": shield.mode,
                "previous_mode": shield.previous_mode,
                "observe_only": shield.mode in {"observe_only", "observe-only"} or shield.no_trade_forced,
                "hard_stop": bool(shield.kill_switch or shield.hard_stop_forced),
                "risk_flags": list(shield.escalation_reason_codes or shield.reason_codes),
                "hysteresis_state": dict(shield.hysteresis_state),
                "no_trade_forced": bool(shield.no_trade_forced),
                "hard_stop_forced": bool(shield.hard_stop_forced),
                "recovery_eligibility": dict(shield.recovery_eligibility),
                "model_confidence": decision_world.confidence_score,
                "uncertainty_bps": decision_world.risk_state.uncertainty_bps,
            },
            correlation_id=correlation_id,
        )
        if shield_event is not None:
            published_events.append(shield_event)

        plan_event = self.emit(
            event_type="ExecutionPlanEvent",
            source="universe_exec",
            partition_key=symbol,
            payload={"symbol": symbol, "venue": venue, "strategy": verdict.selected.strategy, **plan.to_dict()},
            correlation_id=correlation_id,
        )
        if plan_event is not None:
            published_events.append(plan_event)

        world = self.get_world_state()
        allocations = self.cross_asset_allocator.allocate(list(cross_asset_inputs or []))
        research_state = self.research.assess(self.memory.load(graded=True))
        advanced_intelligence: dict[str, Any] = {}
        survival_decision = None
        fund_recommendation = None
        try:
            global_market_state = self.global_market_brain.assess(
                world=world,
                payload=_safe_mapping(pre_learning_summary.get("market_context_inputs", {})),
            )
            advanced_intelligence["phase26_global_market_state"] = global_market_state.to_dict()
        except Exception as exc:
            advanced_intelligence["phase26_global_market_state"] = {"error": f"phase26_failed:{exc}"}
            global_market_state = self.global_market_brain.assess(world=world, payload={})
        try:
            horizon_alignment = self.multi_horizon_layer.assess(
                world=world,
                global_market=global_market_state,
                mission=mission,
                verdict=verdict,
                plan=plan,
            )
            advanced_intelligence["phase27_horizon_alignment"] = horizon_alignment.to_dict()
        except Exception as exc:
            advanced_intelligence["phase27_horizon_alignment"] = {"error": f"phase27_failed:{exc}"}
            horizon_alignment = self.multi_horizon_layer.assess(
                world=world,
                global_market=global_market_state,
                mission=mission,
                verdict=verdict,
                plan=plan,
            )
        try:
            market_energy = self.market_energy_model.assess(
                world=world,
                global_market=global_market_state,
                horizon=horizon_alignment,
            )
            advanced_intelligence["phase28_market_energy"] = market_energy.to_dict()
        except Exception as exc:
            advanced_intelligence["phase28_market_energy"] = {"error": f"phase28_failed:{exc}"}
            market_energy = self.market_energy_model.assess(
                world=world,
                global_market=global_market_state,
                horizon=horizon_alignment,
            )
        try:
            equity_quote = max(1.0, _safe_float(world.portfolio_state.equity_quote, 1.0))
            capital_scale = _clamp(_safe_float(plan.target_notional_quote, 0.0) / equity_quote, 0.0, 2.0)
            simulation = self.future_simulation.simulate(
                seed_payload={
                    "symbol": symbol,
                    "venue": venue,
                    "mission": mission.mission,
                    "selected_strategy": verdict.selected.strategy,
                    "market_regime": world.market_state.regime,
                    "liquidity_regime": world.market_state.liquidity_regime,
                    "volatility_regime": world.market_state.volatility_regime,
                },
                market_energy=market_energy,
                expected_edge_bps=_safe_float(verdict.selected.expected_value_bps, 0.0),
                capital_scale=capital_scale,
            )
            advanced_intelligence["phase29_future_simulation"] = simulation.to_dict()
        except Exception as exc:
            advanced_intelligence["phase29_future_simulation"] = {"error": f"phase29_failed:{exc}"}
            simulation = None
        try:
            phase45_ensemble = self.future_simulation_ensemble.simulate(
                seed_payload={
                    "symbol": symbol,
                    "venue": venue,
                    "mission": mission.mission,
                    "selected_strategy": verdict.selected.strategy,
                    "market_regime": world.market_state.regime,
                    "liquidity_regime": world.market_state.liquidity_regime,
                    "volatility_regime": world.market_state.volatility_regime,
                },
                market_energy=market_energy,
                expected_edge_bps=_safe_float(verdict.selected.expected_value_bps, 0.0),
                capital_scale=_clamp(_safe_float(plan.target_notional_quote, 0.0) / max(1.0, _safe_float(world.portfolio_state.equity_quote, 1.0)), 0.0, 2.0),
            )
            advanced_intelligence["phase45_future_simulation_ensemble"] = phase45_ensemble.to_dict()
        except Exception as exc:
            advanced_intelligence["phase45_future_simulation_ensemble"] = {"error": f"phase45_failed:{exc}"}
        try:
            cross_reality = self.cross_reality_fusion.fuse(
                payload=_safe_mapping(pre_learning_summary.get("cross_reality_inputs", {}))
            )
            advanced_intelligence["phase30_cross_reality_signal"] = cross_reality.to_dict()
        except Exception as exc:
            advanced_intelligence["phase30_cross_reality_signal"] = {"error": f"phase30_failed:{exc}"}
            cross_reality = self.cross_reality_fusion.fuse(payload={})
        try:
            phase40_integrity = self.cross_reality_integrity_guard.assess(
                cross_reality_signal=cross_reality.to_dict(),
            )
            advanced_intelligence["phase40_cross_reality_integrity"] = phase40_integrity.to_dict()
        except Exception as exc:
            advanced_intelligence["phase40_cross_reality_integrity"] = {"error": f"phase40_failed:{exc}"}
            phase40_integrity = None
        try:
            personality = self.personality_engine.assess(
                cycle_id=cycle_id,
                as_of_ts=_safe_float(world.as_of_time, 0.0),
                horizon=horizon_alignment,
                energy=market_energy,
                cross_reality=cross_reality,
                safety_hard_stop=bool(shield.kill_switch or shield.hard_stop_forced),
            )
            advanced_intelligence["phase31_personality_trace"] = personality.to_dict()
        except Exception as exc:
            advanced_intelligence["phase31_personality_trace"] = {"error": f"phase31_failed:{exc}"}
            personality = self.personality_engine.assess(
                cycle_id=cycle_id,
                as_of_ts=_safe_float(world.as_of_time, 0.0),
                horizon=horizon_alignment,
                energy=market_energy,
                cross_reality=cross_reality,
                safety_hard_stop=True,
            )
        try:
            governed_personality, phase41_budget, phase41_violation = self.personality_stability_governor.enforce(
                trace=personality,
                safety_hard_stop=bool(shield.kill_switch or shield.hard_stop_forced),
            )
            personality = governed_personality
            advanced_intelligence["phase31_personality_trace"] = personality.to_dict()
            advanced_intelligence["phase41_personality_stability"] = {
                "deterministic": True,
                "budget": phase41_budget.to_dict(),
                "violation": phase41_violation.to_dict() if phase41_violation is not None else None,
            }
        except Exception as exc:
            advanced_intelligence["phase41_personality_stability"] = {"error": f"phase41_failed:{exc}"}
        try:
            survival_decision = self.survival_doctrine.assess(
                world=world,
                energy=market_energy,
                cross_reality=cross_reality,
                personality=personality,
                integrity_escalation=(
                    phase40_integrity.to_dict()
                    if phase40_integrity is not None
                    else _safe_mapping(advanced_intelligence.get("phase40_cross_reality_integrity", {}))
                ),
            )
            advanced_intelligence["phase32_survival_doctrine"] = survival_decision.to_dict()
        except Exception as exc:
            advanced_intelligence["phase32_survival_doctrine"] = {"error": f"phase32_failed:{exc}"}
        try:
            replay_batch = _safe_mapping(pre_learning_summary.get("replay_batch_status", {}))
            performance_rows = replay_batch.get("strategy_grades", [])
            research_evolution = self.evolutionary_research.evolve(
                cycle_id=cycle_id,
                selected_strategy=verdict.selected.strategy,
                performance_samples=performance_rows if isinstance(performance_rows, list) else [],
            )
            advanced_intelligence["phase33_evolutionary_research"] = research_evolution.to_dict()
        except Exception as exc:
            advanced_intelligence["phase33_evolutionary_research"] = {"error": f"phase33_failed:{exc}"}
            research_evolution = self.evolutionary_research.evolve(
                cycle_id=cycle_id,
                selected_strategy=verdict.selected.strategy,
                performance_samples=[],
            )
        try:
            quality_score = _safe_float(
                _safe_mapping(execution_decision.to_dict().get("quality_estimate", {})).get("execution_quality_score", 0.0),
                0.0,
            )
            fund_recommendation = self.fund_brain.recommend(
                cycle_id=cycle_id,
                research=research_evolution,
                survival=survival_decision or self.survival_doctrine.assess(
                    world=world,
                    energy=market_energy,
                    cross_reality=cross_reality,
                    personality=personality,
                    integrity_escalation=_safe_mapping(advanced_intelligence.get("phase40_cross_reality_integrity", {})),
                ),
                execution_quality_score=quality_score,
            )
            advanced_intelligence["phase34_fund_brain"] = fund_recommendation.to_dict()
        except Exception as exc:
            advanced_intelligence["phase34_fund_brain"] = {"error": f"phase34_failed:{exc}"}

        learning_summary: dict[str, Any] = {}
        try:
            learning_summary = _normalize_learning_summary(self.memory.learning_snapshot().to_dict())
        except Exception as exc:
            learning_summary = _normalize_learning_summary({"errors": [f"learning_snapshot_unavailable:{exc}"]})
            learning_summary["grading_state_summary"] = {"status": "unavailable"}
            learning_summary["bounded_retention_health"] = {"status": "degraded"}
        meta_payload = dict(meta_snapshot.to_dict())
        meta_payload["execution_intelligence"] = execution_decision.to_dict()
        meta_payload["execution_feedback_summary"] = execution_decision.feedback_metrics()
        meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        ops_snapshot = self.ops.assess(
            world=world,
            shield=shield,
            research=research_state,
            allocations=allocations,
            mission=mission,
            verdict=verdict,
            meta_intelligence=meta_payload,
            learning_summary=learning_summary,
            execution_intelligence=execution_decision.to_dict(),
            memory_records_written=0,
        )
        packet = self.memory.build_packet(
            symbol=symbol,
            venue=venue,
            world_state=world.to_dict(),
            mission=mission.to_dict(),
            proposals=[proposal.to_dict() for proposal in proposal_rows],
            selected_strategy=verdict.selected.strategy,
            selected_strategies=[row.strategy for row in verdict.selected_top] if verdict.selected_top else [],
            parliament=verdict.to_dict(),
            parliament_mode=verdict.selection_mode,
            parliament_no_trade=verdict.no_trade,
            parliament_allocations=[row.to_dict() for row in verdict.allocations],
            execution_plan=plan.to_dict(),
            shield=shield.to_dict(),
            ops_snapshot=ops_snapshot.to_dict(),
            meta_intelligence=meta_payload,
            cycle_id=cycle_id,
        )
        memory_records_written = 0
        memory_error = ""
        try:
            packet = self.memory.record(packet)
            memory_records_written = 1
        except Exception as exc:
            memory_error = f"memory_record_failed:{exc}"
            try:
                self.graph.record_error(memory_error)
            except Exception:
                pass
        phase8_summary: dict[str, Any] = {}
        if self._replay_feature_enabled():
            phase8_summary = self._run_phase8_replay_ladder(
                mission=mission,
                world=world,
                plan=plan,
            )

        try:
            learning_summary = _normalize_learning_summary(self.memory.learning_snapshot().to_dict())
        except Exception as exc:
            learning_summary = _normalize_learning_summary(
                {
                    **learning_summary,
                    "errors": [*list(learning_summary.get("errors", [])), f"learning_snapshot_unavailable:{exc}"],
                    "bounded_retention_health": {"status": "degraded"},
                }
            )
        if phase8_summary:
            replay_batch_status = _safe_mapping(phase8_summary.get("replay_batch_status", {}))
            promotion_ladder_state = _safe_mapping(phase8_summary.get("promotion_ladder_state", {}))
            if replay_batch_status:
                learning_summary["replay_batch_status"] = replay_batch_status
                learning_summary["replay_backlog_depth"] = max(0, _safe_int(replay_batch_status.get("backlog_depth", 0), 0))
                learning_summary["memory_grading_drift"] = _safe_float(replay_batch_status.get("memory_grading_drift", 0.0), 0.0)
                learning_summary["replay_session_id"] = str(
                    replay_batch_status.get(
                        "session_id",
                        _safe_mapping(replay_batch_status.get("reproducibility_metadata", {})).get("replay_session_id", ""),
                    )
                    or ""
                )
                reconstructed_rows = replay_batch_status.get("reconstructed_decisions", [])
                learning_summary["decision_reconstruction_count"] = len(reconstructed_rows) if isinstance(reconstructed_rows, list) else 0
                walk_forward_payload = _safe_mapping(replay_batch_status.get("walk_forward", {}))
                counterfactual_payload = _safe_mapping(replay_batch_status.get("comparative_counterfactual", {}))
                learning_summary["walk_forward_holdout_grade"] = _safe_float(walk_forward_payload.get("holdout_overall_grade", 0.0), 0.0)
                learning_summary["counterfactual_overall_grade_delta"] = _safe_float(
                    _safe_mapping(counterfactual_payload.get("deltas", {})).get("overall_grade_delta", 0.0),
                    0.0,
                )
            if promotion_ladder_state:
                learning_summary["promotion_ladder_state"] = promotion_ladder_state
                top_candidates = promotion_ladder_state.get("top_strategy_candidates", [])
                quarantine_list = promotion_ladder_state.get("quarantine_strategy_list", [])
                learning_summary["top_strategy_candidates"] = [dict(row) for row in top_candidates] if isinstance(top_candidates, list) else []
                learning_summary["quarantine_strategy_list"] = [str(item) for item in quarantine_list] if isinstance(quarantine_list, list) else []
                learning_summary["promotion_readiness_score"] = _safe_float(promotion_ladder_state.get("promotion_readiness_score", 0.0), 0.0)
            phase8_errors = phase8_summary.get("errors", [])
            if isinstance(phase8_errors, list) and phase8_errors:
                learning_summary["errors"] = [
                    *list(learning_summary.get("errors", [])),
                    *(str(item) for item in phase8_errors if str(item)),
                ]
        if memory_error:
            learning_summary["errors"] = [*list(learning_summary.get("errors", [])), memory_error]
        learning_summary = _normalize_learning_summary(learning_summary)
        if fund_recommendation is not None and survival_decision is not None:
            try:
                readiness_report = self.institutional_readiness.compile(
                    cycle_id=cycle_id,
                    ops_snapshot=ops_snapshot.to_dict(),
                    fund_recommendation=fund_recommendation,
                    survival=survival_decision,
                )
                advanced_intelligence["phase35_institutional_readiness"] = readiness_report.to_dict()
                meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
            except Exception as exc:
                advanced_intelligence["phase35_institutional_readiness"] = {"error": f"phase35_failed:{exc}"}
                meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        try:
            phase42_escalation = self.committee_escalation_protocol.compile(
                cycle_id=cycle_id,
                fund_recommendation=fund_recommendation.to_dict() if fund_recommendation is not None else _safe_mapping(advanced_intelligence.get("phase34_fund_brain", {})),
                survival_doctrine=survival_decision.to_dict() if survival_decision is not None else _safe_mapping(advanced_intelligence.get("phase32_survival_doctrine", {})),
            )
            advanced_intelligence["phase42_committee_escalation"] = phase42_escalation.to_dict()
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        except Exception as exc:
            advanced_intelligence["phase42_committee_escalation"] = {"error": f"phase42_failed:{exc}"}
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        try:
            phase43_gate = self.institutional_gate_compiler.compile(
                cycle_id=cycle_id,
                institutional_readiness=_safe_mapping(advanced_intelligence.get("phase35_institutional_readiness", {})),
                committee_escalation=_safe_mapping(advanced_intelligence.get("phase42_committee_escalation", {})),
                manual_gate_override=_safe_mapping(pre_learning_summary.get("manual_live_env_gate", {})),
            )
            advanced_intelligence["phase43_institutional_gate"] = phase43_gate.to_dict()
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        except Exception as exc:
            advanced_intelligence["phase43_institutional_gate"] = {"error": f"phase43_failed:{exc}"}
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        try:
            phase44_bridge = self.macro_micro_decision_bridge.bridge(
                global_market_state=_safe_mapping(advanced_intelligence.get("phase26_global_market_state", {})),
                calibration_state=_safe_mapping(advanced_intelligence.get("phase39_global_market_calibration", {})),
                capital_constraints=_safe_mapping(advanced_intelligence.get("phase38_capital_constraints", {})),
                execution_intelligence=execution_decision.to_dict(),
            )
            advanced_intelligence["phase44_macro_micro_bridge"] = phase44_bridge.to_dict()
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        except Exception as exc:
            advanced_intelligence["phase44_macro_micro_bridge"] = {"error": f"phase44_failed:{exc}"}
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        try:
            phase30_payload = _safe_mapping(advanced_intelligence.get("phase30_cross_reality_signal", {}))
            phase26_payload = _safe_mapping(advanced_intelligence.get("phase26_global_market_state", {}))
            twin_state = {
                "as_of_ts": _safe_float(world.as_of_time, 0.0),
                "stale": bool(world.infra_state.stale_feed or world.infra_state.desync),
                "confidence": _safe_float(_safe_mapping(phase26_payload.get("confidence", {})).get("overall", 0.5), 0.5),
                "trend_bps": _safe_float(world.market_state.trend_bias_bps, 0.0),
                "order_flow_pressure": _safe_float(world.market_state.order_flow_aggression, 0.0),
                "spread_bps": _safe_float(world.market_state.spread_bps, 0.0),
                "vol": _safe_float(world.market_state.realized_vol, 0.0),
                "liquidity_pressure": _clamp(1.0 - _safe_float(world.execution_state.execution_stress, 0.0), -1.0, 1.0),
                "multimodal_score": _safe_float(_safe_mapping(phase30_payload.get("diagnostics", {})).get("phase", 0.0), 0.0),
                "macro_risk_on": _safe_float(phase26_payload.get("risk_on_score", 0.0), 0.0),
                "sentiment_score": _safe_float(_safe_mapping(phase26_payload.get("sentiment", {})).get("sentiment_score", 0.0), 0.0),
            }
            phase46_alignment = self.causal_twin_bridge.align(
                simulation_ensemble=_safe_mapping(advanced_intelligence.get("phase45_future_simulation_ensemble", {})),
                twin_state=twin_state,
            )
            advanced_intelligence["phase46_causal_twin_alignment"] = phase46_alignment.to_dict()
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        except Exception as exc:
            advanced_intelligence["phase46_causal_twin_alignment"] = {"error": f"phase46_failed:{exc}"}
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        try:
            phase45_payload = _safe_mapping(advanced_intelligence.get("phase45_future_simulation_ensemble", {}))
            from autonomous_investment_robot.services.distributed.compute_bridge import LocalComputeBridge

            phase47_distributed = self.replay_distributed_bridge.compile(
                run_id=str(phase45_payload.get("ensemble_id", cycle_id) or cycle_id),
                symbols=[symbol],
                ensemble_payload=phase45_payload,
                compute_health=LocalComputeBridge().health(),
                failed_symbols=[],
            )
            advanced_intelligence["phase47_replay_distributed_bridge"] = phase47_distributed.to_dict()
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        except Exception as exc:
            advanced_intelligence["phase47_replay_distributed_bridge"] = {"error": f"phase47_failed:{exc}"}
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        try:
            phase36_ledger = self.intelligence_ledger.compile(
                cycle_id=cycle_id,
                world=world,
                advanced_intelligence=advanced_intelligence,
            )
            advanced_intelligence["phase36_intelligence_ledger"] = phase36_ledger.to_dict()
        except Exception as exc:
            advanced_intelligence["phase36_intelligence_ledger"] = {"error": f"phase36_failed:{exc}"}
        try:
            phase37_netting = self.scenario_portfolio_netting.net(
                world=world,
                primary_symbol=symbol,
                primary_plan_notional_quote=_safe_float(plan.target_notional_quote, 0.0),
                primary_simulation=_safe_mapping(advanced_intelligence.get("phase29_future_simulation", {})),
            )
            advanced_intelligence["phase37_portfolio_netting"] = phase37_netting.to_dict()
        except Exception as exc:
            advanced_intelligence["phase37_portfolio_netting"] = {"error": f"phase37_failed:{exc}"}
        try:
            phase38_constraints = self.capital_constraint_compiler.compile(
                world=world,
                plan=plan.to_dict(),
                shield=shield.to_dict(),
                survival_doctrine=_safe_mapping(advanced_intelligence.get("phase32_survival_doctrine", {})),
                netting_envelope=_safe_mapping(advanced_intelligence.get("phase37_portfolio_netting", {})),
            )
            advanced_intelligence["phase38_capital_constraints"] = phase38_constraints.to_dict()
        except Exception as exc:
            advanced_intelligence["phase38_capital_constraints"] = {"error": f"phase38_failed:{exc}"}
        try:
            phase39_calibration = self.global_market_calibration.calibrate(
                global_market_state=_safe_mapping(advanced_intelligence.get("phase26_global_market_state", {})),
            )
            advanced_intelligence["phase39_global_market_calibration"] = phase39_calibration.to_dict()
        except Exception as exc:
            advanced_intelligence["phase39_global_market_calibration"] = {"error": f"phase39_failed:{exc}"}
        try:
            phase48_index = self.evidence_vault_index.build(
                packet=packet.to_dict(),
                ops_snapshot=ops_snapshot.to_dict(),
                advanced_intelligence=advanced_intelligence,
            )
            advanced_intelligence["phase48_evidence_vault_index"] = phase48_index.to_dict()
        except Exception as exc:
            advanced_intelligence["phase48_evidence_vault_index"] = {"error": f"phase48_failed:{exc}"}
        meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        ops_snapshot = self.ops.assess(
            world=world,
            shield=shield,
            research=research_state,
            allocations=allocations,
            mission=mission,
            verdict=verdict,
            meta_intelligence=meta_payload,
            learning_summary=learning_summary,
            execution_intelligence=execution_decision.to_dict(),
            memory_records_written=memory_records_written,
        )
        phase49_payload = _safe_mapping(
            _safe_mapping(getattr(ops_snapshot, "governance_observability", {})).get("phase49_canary_envelope", {})
        )
        if phase49_payload:
            advanced_intelligence["phase49_live_canary_envelope"] = phase49_payload
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        try:
            phase_key_map = {
                36: "phase36_intelligence_ledger",
                37: "phase37_portfolio_netting",
                38: "phase38_capital_constraints",
                39: "phase39_global_market_calibration",
                40: "phase40_cross_reality_integrity",
                41: "phase41_personality_stability",
                42: "phase42_committee_escalation",
                43: "phase43_institutional_gate",
                44: "phase44_macro_micro_bridge",
                45: "phase45_future_simulation_ensemble",
                46: "phase46_causal_twin_alignment",
                47: "phase47_replay_distributed_bridge",
                48: "phase48_evidence_vault_index",
                49: "phase49_live_canary_envelope",
            }
            completed = []
            for phase_no, phase_key in phase_key_map.items():
                payload = _safe_mapping(advanced_intelligence.get(phase_key, {}))
                if payload and "error" not in payload:
                    completed.append(int(phase_no))
            if len(completed) == len(phase_key_map):
                completed.append(50)
            phase50_cert = self.phase50_certification.compile(
                advanced_intelligence=advanced_intelligence,
                ops_snapshot=ops_snapshot.to_dict(),
                completed_phases=completed,
            )
            advanced_intelligence["phase50_certification"] = phase50_cert.to_dict()
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        except Exception as exc:
            advanced_intelligence["phase50_certification"] = {"error": f"phase50_failed:{exc}"}
            meta_payload["advanced_intelligence"] = dict(advanced_intelligence)
        packet = replace(packet, meta_intelligence=dict(meta_payload))
        packet = self.memory.with_learning_snapshot(
            packet,
            ops_snapshot=ops_snapshot.to_dict(),
            learning_summary=learning_summary,
        )
        if memory_records_written:
            try:
                self.memory.update_packet(packet)
            except Exception as exc:
                try:
                    self.graph.record_error(f"memory_packet_update_failed:{exc}")
                except Exception:
                    pass

        return UniverseMindCycleResult(
            world_state=world,
            mission=mission,
            parliament=verdict,
            execution_plan=plan,
            shield=shield,
            decision_packet=packet,
            published_events=published_events,
            research=research_state,
            allocations=allocations,
            ops_snapshot=ops_snapshot,
            meta_snapshot=meta_snapshot,
            execution_intelligence=execution_decision,
            advanced_intelligence=advanced_intelligence,
        )

    def run_cycle_from_intent(
        self,
        intent: Any,
        *,
        venue: str = "synthetic",
        cross_asset_inputs: Iterable[UniverseAllocationInput] | None = None,
        parliament_mode: str = PARLIAMENT_MODE_TOP_1,
        parliament_top_n: int = 2,
        parliament_score_floor: float | None = None,
    ) -> UniverseMindCycleResult:
        world = self.get_world_state()
        mission_preview = self.mission_engine.choose(world, previous_mission=world.strategy_state.last_mission)
        proposals = strategy_proposals_from_intent(intent, mission=mission_preview.mission)
        symbol = str(getattr(intent, "symbol", "UNKNOWN") or "UNKNOWN")
        return self.run_cycle(
            symbol=symbol,
            venue=venue,
            proposals=proposals,
            cross_asset_inputs=cross_asset_inputs,
            parliament_mode=parliament_mode,
            parliament_top_n=parliament_top_n,
            parliament_score_floor=parliament_score_floor,
        )

    def grade_cycle(
        self,
        packet: DecisionPacket,
        *,
        realized_pnl_quote: float,
        realized_slippage_bps: float,
        realized_regime: str,
        fill_ratio: float = 0.0,
    ) -> DecisionPacket:
        try:
            graded = self.memory.grade(
                packet,
                realized_pnl_quote=realized_pnl_quote,
                realized_slippage_bps=realized_slippage_bps,
                realized_regime=realized_regime,
                fill_ratio=fill_ratio,
            )
        except Exception as exc:
            payload = packet.to_dict()
            payload["evaluation"] = {
                "status": "graded_failed",
                "error": f"memory_grade_failed:{exc}",
            }
            graded = DecisionPacket.from_mapping(payload)
        try:
            self.meta.observe_outcome(graded)
        except Exception:
            pass
        return graded
