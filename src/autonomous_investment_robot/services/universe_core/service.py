from __future__ import annotations

from hashlib import sha256
import json
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

from .cross_asset import CrossAssetAllocator, UniverseAllocation, UniverseAllocationInput
from .events import EventFabric, UniverseEventEnvelope, build_event
from .execution import ExecutionIntelligence, ExecutionPlan
from .memory import DecisionPacket, MemoryEngine
from .meta import MetaDecisionSnapshot, MetaIntelligenceEngine
from .mission import MissionDecision, MissionEngine, infer_strategy_family
from .ops import UniverseOpsService, UniverseOpsSnapshot
from .parliament import (
    PARLIAMENT_MODE_TOP_1,
    ParliamentVerdict,
    StrategyParliament,
    StrategyProposal,
    strategy_proposals_from_intent,
)
from .research import PromotionState, ResearchReplayLab
from .shield import ShieldDecision, UniverseShield
from .state import SymbolStateSnapshot, WorldStateGraph, WorldStateSnapshot, WorldStateStore


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


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
        shield: UniverseShield | None = None,
        memory: MemoryEngine | None = None,
        research: ResearchReplayLab | None = None,
        cross_asset_allocator: CrossAssetAllocator | None = None,
        ops: UniverseOpsService | None = None,
        meta: MetaIntelligenceEngine | None = None,
    ) -> None:
        self.run_dir = str(run_dir)
        self.fabric = fabric or EventFabric(self.run_dir)
        self.world_state_store = world_state_store or WorldStateStore(graph or WorldStateGraph())
        self.graph = self.world_state_store.graph
        self.mission_engine = mission_engine or MissionEngine()
        self.parliament = parliament or StrategyParliament()
        self.execution = execution or ExecutionIntelligence()
        self.shield = shield or UniverseShield()
        self.memory = memory or MemoryEngine(self.run_dir)
        self.research = research or ResearchReplayLab()
        self.cross_asset_allocator = cross_asset_allocator or CrossAssetAllocator()
        self.ops = ops or UniverseOpsService()
        self.meta = meta or MetaIntelligenceEngine(self.run_dir)

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
        ops_snapshot = self.ops.assess(
            world=world,
            shield=shield,
            research=research_state,
            allocations=allocations,
            mission=mission,
            verdict=verdict,
            meta_intelligence=meta_snapshot.to_dict(),
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
            meta_intelligence=meta_snapshot.to_dict(),
            cycle_id=cycle_id,
        )
        self.memory.record(packet)

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
        graded = self.memory.grade(
            packet,
            realized_pnl_quote=realized_pnl_quote,
            realized_slippage_bps=realized_slippage_bps,
            realized_regime=realized_regime,
            fill_ratio=fill_ratio,
        )
        try:
            self.meta.observe_outcome(graded)
        except Exception:
            pass
        return graded
