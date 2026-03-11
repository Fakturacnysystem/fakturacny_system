from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .cross_asset import UniverseAllocation
from .mission import MissionDecision
from .parliament import ParliamentVerdict
from .research import PromotionState
from .shield import ShieldDecision
from .state import WorldStateSnapshot


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
        }


class UniverseOpsService:
    """Final production-readiness lens over world state, shield, and research ladder."""

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
    ) -> UniverseOpsSnapshot:
        blockers: list[str] = []
        notes: list[str] = []
        meta_payload = dict(meta_intelligence or {})
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
        top_alloc = max(list(allocations), key=lambda row: row.weight, default=None)
        if top_alloc is not None:
            notes.append(f"top_universe={top_alloc.universe_id}:{top_alloc.weight:.2f}")

        if blockers:
            rollout_stage = "shadow"
        elif research.current_stage == "scaled_live" and readiness >= 0.80:
            rollout_stage = "scaled_live"
        elif research.current_stage in {"limited_live", "scaled_live"} and readiness >= 0.70:
            rollout_stage = "limited_live"
        elif research.current_stage in {"paper_mode", "limited_live", "scaled_live"}:
            rollout_stage = "paper"
        else:
            rollout_stage = "research"
        return UniverseOpsSnapshot(
            readiness_score=max(0.0, min(1.0, readiness)),
            rollout_stage=rollout_stage,
            manual_gate_required=rollout_stage in {"paper", "limited_live", "scaled_live"},
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
        )
