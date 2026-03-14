from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


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


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class DecisionPacket:
    cycle_id: str
    ts: float
    symbol: str
    venue: str
    world_state_fingerprint: str
    world_state: dict[str, Any]
    mission: dict[str, Any]
    proposals: list[dict[str, Any]]
    selected_strategy: str
    parliament: dict[str, Any]
    execution_plan: dict[str, Any]
    shield: dict[str, Any]
    ops_snapshot: dict[str, Any]
    meta_intelligence: dict[str, Any] = field(default_factory=dict)
    selected_strategies: list[str] = field(default_factory=list)
    parliament_mode: str = "top_1"
    parliament_no_trade: bool = False
    parliament_allocations: list[dict[str, Any]] = field(default_factory=list)
    actual_fill: dict[str, Any] = field(default_factory=dict)
    realized_pnl_quote: float = 0.0
    realized_slippage_bps: float = 0.0
    realized_regime: str = ""
    evaluation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "ts": self.ts,
            "symbol": self.symbol,
            "venue": self.venue,
            "world_state_fingerprint": self.world_state_fingerprint,
            "world_state": dict(self.world_state),
            "mission": dict(self.mission),
            "proposals": [dict(row) for row in self.proposals],
            "selected_strategy": self.selected_strategy,
            "selected_strategies": list(self.selected_strategies),
            "parliament_mode": self.parliament_mode,
            "parliament_no_trade": self.parliament_no_trade,
            "parliament_allocations": [dict(row) for row in self.parliament_allocations],
            "parliament": dict(self.parliament),
            "execution_plan": dict(self.execution_plan),
            "shield": dict(self.shield),
            "ops_snapshot": dict(self.ops_snapshot),
            "meta_intelligence": dict(self.meta_intelligence),
            "actual_fill": dict(self.actual_fill),
            "realized_pnl_quote": self.realized_pnl_quote,
            "realized_slippage_bps": self.realized_slippage_bps,
            "realized_regime": self.realized_regime,
            "evaluation": dict(self.evaluation),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DecisionPacket":
        proposals = raw.get("proposals", [])
        selected_strategies = raw.get("selected_strategies", [])
        parliament_allocations = raw.get("parliament_allocations", [])
        meta_payload = raw.get("meta_intelligence", raw.get("meta", {}))
        parliament_payload = dict(raw.get("parliament", {}) or {})
        if not selected_strategies:
            selected_top = parliament_payload.get("selected_top", [])
            if isinstance(selected_top, list):
                selected_strategies = [
                    str(row.get("strategy", row.get("strategy_name", "")))
                    for row in selected_top
                    if isinstance(row, Mapping) and str(row.get("strategy", row.get("strategy_name", "")))
                ]
        mode = str(
            raw.get(
                "parliament_mode",
                parliament_payload.get("selection_mode", parliament_payload.get("mode", "top_1")),
            )
            or "top_1"
        )
        return cls(
            cycle_id=str(raw.get("cycle_id", "") or ""),
            ts=float(raw.get("ts", 0.0) or 0.0),
            symbol=str(raw.get("symbol", "") or ""),
            venue=str(raw.get("venue", "") or ""),
            world_state_fingerprint=str(raw.get("world_state_fingerprint", "") or ""),
            world_state=dict(raw.get("world_state", {}) or {}),
            mission=dict(raw.get("mission", {}) or {}),
            proposals=[dict(row) for row in proposals] if isinstance(proposals, list) else [],
            selected_strategy=str(raw.get("selected_strategy", "") or ""),
            selected_strategies=[str(name) for name in selected_strategies] if isinstance(selected_strategies, list) else [],
            parliament_mode=mode,
            parliament_no_trade=bool(raw.get("parliament_no_trade", False)),
            parliament_allocations=[dict(row) for row in parliament_allocations] if isinstance(parliament_allocations, list) else [],
            parliament=parliament_payload,
            execution_plan=dict(raw.get("execution_plan", {}) or {}),
            shield=dict(raw.get("shield", {}) or {}),
            ops_snapshot=dict(raw.get("ops_snapshot", {}) or {}),
            meta_intelligence=dict(meta_payload or {}),
            actual_fill=dict(raw.get("actual_fill", {}) or {}),
            realized_pnl_quote=float(raw.get("realized_pnl_quote", 0.0) or 0.0),
            realized_slippage_bps=float(raw.get("realized_slippage_bps", 0.0) or 0.0),
            realized_regime=str(raw.get("realized_regime", "") or ""),
            evaluation=dict(raw.get("evaluation", {}) or {}),
        )


@dataclass(frozen=True)
class DecisionFingerprint:
    fingerprint: str
    version: str = "decision_fingerprint:v1"
    components: tuple[str, ...] = (
        "cycle_id",
        "symbol",
        "venue",
        "world_state_fingerprint",
        "mission",
        "selected_strategy",
        "shield_mode",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "version": self.version,
            "components": list(self.components),
        }

    @classmethod
    def from_packet(cls, packet: DecisionPacket) -> "DecisionFingerprint":
        payload = {
            "cycle_id": packet.cycle_id,
            "symbol": packet.symbol,
            "venue": packet.venue,
            "world_state_fingerprint": packet.world_state_fingerprint,
            "mission": packet.mission,
            "selected_strategy": packet.selected_strategy,
            "shield_mode": str(packet.shield.get("mode", packet.shield.get("shield_mode", "normal"))),
        }
        return cls(fingerprint=_stable_hash(payload))

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "DecisionFingerprint":
        return cls(fingerprint=_stable_hash(payload))


class OutcomeGrade(str, Enum):
    PENDING = "pending"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    SEVERE_NEGATIVE = "severe_negative"


class OutcomeGradeReason(str, Enum):
    PENDING_OUTCOME = "pending_outcome"
    POSITIVE_REALIZED_PNL = "positive_realized_pnl"
    FLAT_OUTCOME = "flat_outcome"
    NEGATIVE_REALIZED_PNL = "negative_realized_pnl"
    SEVERE_LOSS = "severe_loss"
    EXPECTED_EDGE_MISS = "expected_edge_miss"
    EXECUTION_SLIPPAGE_DRAG = "execution_slippage_drag"
    SHIELD_ESCALATION_PRESSURE = "shield_escalation_pressure"
    SHIELD_STABLE = "shield_stable"
    NO_TRADE_CORRECT = "no_trade_correct"
    NO_TRADE_MISS = "no_trade_miss"


@dataclass(frozen=True)
class DecisionOutcomeGrade:
    outcome_grade: OutcomeGrade
    grade_score: float
    risk_adjusted_score: float
    reason_codes: tuple[str, ...]
    expected_vs_realized_delta_quote: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_grade": self.outcome_grade.value,
            "grade_score": float(self.grade_score),
            "risk_adjusted_score": float(self.risk_adjusted_score),
            "reason_codes": list(self.reason_codes),
            "expected_vs_realized_delta_quote": float(self.expected_vs_realized_delta_quote),
        }


@dataclass(frozen=True)
class GradeWindowSummary:
    sample_count: int
    pending_count: int
    positive_count: int
    neutral_count: int
    negative_count: int
    severe_negative_count: int
    average_grade_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": int(self.sample_count),
            "pending_count": int(self.pending_count),
            "positive_count": int(self.positive_count),
            "neutral_count": int(self.neutral_count),
            "negative_count": int(self.negative_count),
            "severe_negative_count": int(self.severe_negative_count),
            "average_grade_score": float(self.average_grade_score),
        }


@dataclass(frozen=True)
class StrategyPolicyGrade:
    strategy: str
    mission: str
    shield_mode: str
    window: GradeWindowSummary
    avg_pnl_quote: float
    avg_slippage_bps: float
    shield_escalation_rate: float
    replay_eligible_ratio: float
    risk_adjusted_score: float
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "mission": self.mission,
            "shield_mode": self.shield_mode,
            "window": self.window.to_dict(),
            "avg_pnl_quote": float(self.avg_pnl_quote),
            "avg_slippage_bps": float(self.avg_slippage_bps),
            "shield_escalation_rate": float(self.shield_escalation_rate),
            "replay_eligible_ratio": float(self.replay_eligible_ratio),
            "risk_adjusted_score": float(self.risk_adjusted_score),
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class PolicyGradeRecord:
    strategy: str
    mission: str
    shield_mode: str
    sample_count: int
    risk_adjusted_score: float
    recommendation: str
    updated_ts: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "mission": self.mission,
            "shield_mode": self.shield_mode,
            "sample_count": int(self.sample_count),
            "risk_adjusted_score": float(self.risk_adjusted_score),
            "recommendation": self.recommendation,
            "updated_ts": float(self.updated_ts),
        }


@dataclass(frozen=True)
class PromotionEvidenceBundle:
    strategy: str
    mission: str
    shield_mode: str
    sample_count: int
    win_rate: float
    severe_rate: float
    replay_eligible_ratio: float
    shield_escalation_rate: float
    risk_adjusted_score: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "mission": self.mission,
            "shield_mode": self.shield_mode,
            "sample_count": int(self.sample_count),
            "win_rate": float(self.win_rate),
            "severe_rate": float(self.severe_rate),
            "replay_eligible_ratio": float(self.replay_eligible_ratio),
            "shield_escalation_rate": float(self.shield_escalation_rate),
            "risk_adjusted_score": float(self.risk_adjusted_score),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ReplayPromotionCandidate:
    strategy: str
    evidence: PromotionEvidenceBundle
    recommended_size_cap: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "evidence": self.evidence.to_dict(),
            "recommended_size_cap": float(self.recommended_size_cap),
        }


@dataclass(frozen=True)
class LearningCandidateRecord:
    candidate_id: str
    candidate_type: str
    strategy: str
    mission: str
    shield_mode: str
    confidence: float
    evidence_count: int
    replay_eligible: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    recommended_action: str = "hold"

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_type": self.candidate_type,
            "strategy": self.strategy,
            "mission": self.mission,
            "shield_mode": self.shield_mode,
            "confidence": float(self.confidence),
            "evidence_count": int(self.evidence_count),
            "replay_eligible": bool(self.replay_eligible),
            "reason_codes": list(self.reason_codes),
            "recommended_action": self.recommended_action,
        }


@dataclass(frozen=True)
class PromotionGateDecision:
    eligible: bool
    candidates: list[ReplayPromotionCandidate] = field(default_factory=list)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    min_samples: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": bool(self.eligible),
            "candidates": [row.to_dict() for row in self.candidates],
            "reason_codes": list(self.reason_codes),
            "min_samples": int(self.min_samples),
        }


@dataclass(frozen=True)
class DemotionGateDecision:
    triggered: bool
    candidates: list[LearningCandidateRecord] = field(default_factory=list)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggered": bool(self.triggered),
            "candidates": [row.to_dict() for row in self.candidates],
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class RetirementGateDecision:
    triggered: bool
    candidates: list[LearningCandidateRecord] = field(default_factory=list)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggered": bool(self.triggered),
            "candidates": [row.to_dict() for row in self.candidates],
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class MemoryRetentionPolicy:
    max_records: int = 5_000
    recent_reserve_ratio: float = 0.70
    representative_per_bucket: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_records": int(self.max_records),
            "recent_reserve_ratio": float(self.recent_reserve_ratio),
            "representative_per_bucket": int(self.representative_per_bucket),
        }


@dataclass(frozen=True)
class ReplayRetentionPolicy:
    max_replay_batches: int = 512
    max_promotion_snapshots: int = 512
    max_grade_history_per_strategy: int = 32
    max_reconstructed_decisions: int = 128
    max_walk_forward_batches: int = 24

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_replay_batches": int(self.max_replay_batches),
            "max_promotion_snapshots": int(self.max_promotion_snapshots),
            "max_grade_history_per_strategy": int(self.max_grade_history_per_strategy),
            "max_reconstructed_decisions": int(self.max_reconstructed_decisions),
            "max_walk_forward_batches": int(self.max_walk_forward_batches),
        }


@dataclass(frozen=True)
class MemoryCompactionDecision:
    applied: bool
    before_count: int
    after_count: int
    dropped_count: int
    kept_recent_count: int
    kept_priority_count: int
    representative_kept: int
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": bool(self.applied),
            "before_count": int(self.before_count),
            "after_count": int(self.after_count),
            "dropped_count": int(self.dropped_count),
            "kept_recent_count": int(self.kept_recent_count),
            "kept_priority_count": int(self.kept_priority_count),
            "representative_kept": int(self.representative_kept),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class MemoryArchiveSummary:
    as_of_ts: float
    decision: MemoryCompactionDecision
    bucket_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_ts": float(self.as_of_ts),
            "decision": self.decision.to_dict(),
            "bucket_counts": dict(self.bucket_counts),
        }


@dataclass(frozen=True)
class DecisionMemoryRecord:
    run_id: str
    decision_id: str
    ts: float
    symbol: str
    instrument: str
    world_state_fingerprint: str
    decision_fingerprint: DecisionFingerprint
    mission_summary: dict[str, Any]
    parliament_summary: dict[str, Any]
    execution_summary: dict[str, Any]
    shield_summary: dict[str, Any]
    strategy_health_summary: dict[str, Any]
    meta_allocation_summary: dict[str, Any]
    realized_outcome_summary: dict[str, Any]
    pnl_quote: float
    drawdown_contribution: float
    slippage_bps: float
    replay_eligible: bool
    grading_status: str
    retention_priority: float
    group_key: str
    data_version: str = "decision_memory:v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "decision_id": self.decision_id,
            "ts": float(self.ts),
            "symbol": self.symbol,
            "instrument": self.instrument,
            "world_state_fingerprint": self.world_state_fingerprint,
            "decision_fingerprint": self.decision_fingerprint.to_dict(),
            "mission_summary": dict(self.mission_summary),
            "parliament_summary": dict(self.parliament_summary),
            "execution_summary": dict(self.execution_summary),
            "shield_summary": dict(self.shield_summary),
            "strategy_health_summary": dict(self.strategy_health_summary),
            "meta_allocation_summary": dict(self.meta_allocation_summary),
            "realized_outcome_summary": dict(self.realized_outcome_summary),
            "pnl_quote": float(self.pnl_quote),
            "drawdown_contribution": float(self.drawdown_contribution),
            "slippage_bps": float(self.slippage_bps),
            "replay_eligible": bool(self.replay_eligible),
            "grading_status": self.grading_status,
            "retention_priority": float(self.retention_priority),
            "group_key": self.group_key,
            "data_version": self.data_version,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DecisionMemoryRecord":
        fp_raw = _safe_mapping(raw.get("decision_fingerprint", {}))
        return cls(
            run_id=str(raw.get("run_id", "")),
            decision_id=str(raw.get("decision_id", "")),
            ts=_safe_float(raw.get("ts", 0.0), 0.0),
            symbol=str(raw.get("symbol", "")),
            instrument=str(raw.get("instrument", "")),
            world_state_fingerprint=str(raw.get("world_state_fingerprint", "")),
            decision_fingerprint=DecisionFingerprint(
                fingerprint=str(fp_raw.get("fingerprint", "")),
                version=str(fp_raw.get("version", "decision_fingerprint:v1")),
                components=tuple(str(name) for name in fp_raw.get("components", []) if str(name)),
            ),
            mission_summary=_safe_mapping(raw.get("mission_summary", {})),
            parliament_summary=_safe_mapping(raw.get("parliament_summary", {})),
            execution_summary=_safe_mapping(raw.get("execution_summary", {})),
            shield_summary=_safe_mapping(raw.get("shield_summary", {})),
            strategy_health_summary=_safe_mapping(raw.get("strategy_health_summary", {})),
            meta_allocation_summary=_safe_mapping(raw.get("meta_allocation_summary", {})),
            realized_outcome_summary=_safe_mapping(raw.get("realized_outcome_summary", {})),
            pnl_quote=_safe_float(raw.get("pnl_quote", 0.0), 0.0),
            drawdown_contribution=_safe_float(raw.get("drawdown_contribution", 0.0), 0.0),
            slippage_bps=_safe_float(raw.get("slippage_bps", 0.0), 0.0),
            replay_eligible=bool(raw.get("replay_eligible", False)),
            grading_status=str(raw.get("grading_status", "pending")),
            retention_priority=_safe_float(raw.get("retention_priority", 0.0), 0.0),
            group_key=str(raw.get("group_key", "")),
            data_version=str(raw.get("data_version", "decision_memory:v1")),
        )


@dataclass(frozen=True)
class DecisionMemorySnapshot:
    as_of_ts: float
    total_records: int
    graded_records: int
    replay_eligible_records: int
    by_mission: dict[str, int]
    by_strategy: dict[str, int]
    by_shield_mode: dict[str, int]
    grading_state_summary: dict[str, Any]
    latest_policy_grade_summary: dict[str, Any]
    promotion_candidates_count: int
    demotion_candidates_count: int
    retirement_candidates_count: int
    shield_aware_learning_summary: dict[str, Any]
    memory_compaction_summary: dict[str, Any]
    replay_evidence_summary: dict[str, Any]
    bounded_retention_health: dict[str, Any]
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
    execution_feedback_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_ts": float(self.as_of_ts),
            "total_records": int(self.total_records),
            "graded_records": int(self.graded_records),
            "replay_eligible_records": int(self.replay_eligible_records),
            "by_mission": dict(self.by_mission),
            "by_strategy": dict(self.by_strategy),
            "by_shield_mode": dict(self.by_shield_mode),
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
            "execution_feedback_summary": dict(self.execution_feedback_summary),
        }


class MemoryEngine:
    """Persistent decision memory for replay, grading, policy recommendations, and bounded retention."""

    def __init__(
        self,
        run_dir: str,
        *,
        max_records: int = 5_000,
        retention_policy: MemoryRetentionPolicy | None = None,
        replay_retention_policy: ReplayRetentionPolicy | None = None,
        min_policy_samples: int = 6,
    ) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.records_path = self.run_dir / "universe_memory.jsonl"
        self.evaluations_path = self.run_dir / "universe_memory_evaluations.jsonl"
        self.decision_memory_path = self.run_dir / "universe_decision_memory.jsonl"
        self.policy_grade_path = self.run_dir / "universe_policy_grades.jsonl"
        self.learning_candidates_path = self.run_dir / "universe_learning_candidates.jsonl"
        self.archive_summary_path = self.run_dir / "universe_memory_archive_summary.json"
        self.replay_batch_path = self.run_dir / "universe_replay_batches.jsonl"
        self.replay_grade_history_path = self.run_dir / "universe_replay_grade_history.jsonl"
        self.promotion_ladder_path = self.run_dir / "universe_promotion_ladder.jsonl"
        self.replay_fingerprint_index_path = self.run_dir / "universe_replay_fingerprint_index.json"
        self.max_records = max(1, int(max_records))
        self.retention_policy = retention_policy or MemoryRetentionPolicy(max_records=self.max_records)
        self.replay_retention_policy = replay_retention_policy or ReplayRetentionPolicy(
            max_replay_batches=min(2_000, max(50, self.max_records)),
            max_promotion_snapshots=min(2_000, max(50, self.max_records)),
            max_grade_history_per_strategy=32,
            max_reconstructed_decisions=128,
            max_walk_forward_batches=24,
        )
        self.min_policy_samples = max(3, int(min_policy_samples))
        self.max_replay_grade_history_per_strategy = max(4, int(self.replay_retention_policy.max_grade_history_per_strategy))
        self._last_compaction = MemoryCompactionDecision(
            applied=False,
            before_count=0,
            after_count=0,
            dropped_count=0,
            kept_recent_count=0,
            kept_priority_count=0,
            representative_kept=0,
            reason_codes=("not_required",),
        )

    def fingerprint_world_state(self, world_state: Mapping[str, Any]) -> str:
        return _stable_hash(world_state)

    def build_packet(
        self,
        *,
        symbol: str,
        venue: str,
        world_state: Mapping[str, Any],
        mission: Mapping[str, Any],
        proposals: Iterable[Mapping[str, Any]],
        selected_strategy: str,
        parliament: Mapping[str, Any],
        selected_strategies: Iterable[str] = (),
        parliament_mode: str = "top_1",
        parliament_no_trade: bool = False,
        parliament_allocations: Iterable[Mapping[str, Any]] = (),
        execution_plan: Mapping[str, Any],
        shield: Mapping[str, Any],
        ops_snapshot: Mapping[str, Any],
        meta_intelligence: Mapping[str, Any] | None = None,
        cycle_id: str | None = None,
    ) -> DecisionPacket:
        ts = datetime.now(timezone.utc).timestamp()
        world_payload = dict(world_state)
        parliament_payload = dict(parliament)
        selected_list = [str(name) for name in selected_strategies if str(name)]
        if not selected_list:
            selected_top = parliament_payload.get("selected_top", [])
            if isinstance(selected_top, list):
                for row in selected_top:
                    if isinstance(row, Mapping):
                        name = str(row.get("strategy", row.get("strategy_name", "")) or "")
                        if name:
                            selected_list.append(name)
        if not selected_list and selected_strategy:
            selected_list = [str(selected_strategy)]
        allocation_rows = [dict(row) for row in parliament_allocations]
        if not allocation_rows:
            raw_allocations = parliament_payload.get("allocations", [])
            if isinstance(raw_allocations, list):
                allocation_rows = [dict(row) for row in raw_allocations if isinstance(row, Mapping)]
        mode = str(parliament_mode or parliament_payload.get("selection_mode", "top_1") or "top_1")
        no_trade = bool(parliament_no_trade or parliament_payload.get("no_trade", False))
        packet_id = cycle_id or _stable_hash(
            {
                "ts": round(ts, 6),
                "symbol": symbol,
                "venue": venue,
                "world": world_payload,
                "strategy": selected_strategy,
            }
        )
        return DecisionPacket(
            cycle_id=packet_id,
            ts=ts,
            symbol=str(symbol),
            venue=str(venue),
            world_state_fingerprint=self.fingerprint_world_state(world_payload),
            world_state=world_payload,
            mission=dict(mission),
            proposals=[dict(row) for row in proposals],
            selected_strategy=str(selected_strategy),
            selected_strategies=selected_list,
            parliament_mode=mode,
            parliament_no_trade=no_trade,
            parliament_allocations=allocation_rows,
            parliament=parliament_payload,
            execution_plan=dict(execution_plan),
            shield=dict(shield),
            ops_snapshot=dict(ops_snapshot),
            meta_intelligence=dict(meta_intelligence or {}),
            evaluation={"status": "pending"},
        )

    def build_decision_memory_record(self, packet: DecisionPacket) -> DecisionMemoryRecord:
        mission_summary = {
            "mission": str(packet.mission.get("mission", packet.mission.get("mission_type", "unknown"))),
            "confidence": _safe_float(packet.mission.get("confidence", 0.0), 0.0),
            "reason_codes": list(packet.mission.get("reason_codes", [])) if isinstance(packet.mission.get("reason_codes", []), list) else [],
        }
        selected_strategies = list(packet.selected_strategies) if packet.selected_strategies else [packet.selected_strategy]
        parliament_summary = {
            "selected_strategy": str(packet.selected_strategy or ""),
            "selected_strategies": [str(name) for name in selected_strategies if str(name)],
            "mode": str(packet.parliament_mode),
            "no_trade": bool(packet.parliament_no_trade),
            "reasons": list(packet.parliament.get("reasons", [])) if isinstance(packet.parliament.get("reasons", []), list) else [],
            "best_score": _safe_float(packet.parliament.get("diagnostics", {}).get("best_score", 0.0) if isinstance(packet.parliament.get("diagnostics", {}), Mapping) else 0.0, 0.0),
        }
        execution_summary = {
            "actionable": bool(packet.execution_plan.get("actionable", False)),
            "side": str(packet.execution_plan.get("side", "flat")),
            "order_type": str(packet.execution_plan.get("order_type", "none")),
            "target_notional_quote": _safe_float(packet.execution_plan.get("target_notional_quote", 0.0), 0.0),
            "maker_taker": str(packet.execution_plan.get("maker_taker", "maker")),
            "urgency": str(packet.execution_plan.get("urgency", packet.execution_plan.get("urgency_tier", "normal"))),
            "execution_personality_mode": str(
                _safe_mapping(packet.execution_plan.get("meta", {})).get("execution_personality_mode", "")
            ),
            "expected_total_cost_bps": _safe_float(
                _safe_mapping(packet.execution_plan.get("execution_quality_estimate", {})).get("expected_total_cost_bps", 0.0),
                0.0,
            ),
            "expected_net_edge_bps": _safe_float(packet.execution_plan.get("expected_net_edge_bps", 0.0), 0.0),
            "fill_quality_score": _safe_float(
                _safe_mapping(_safe_mapping(packet.execution_plan.get("meta", {})).get("execution_feedback_metrics", {})).get(
                    "fill_quality_score",
                    _safe_mapping(packet.execution_plan.get("execution_quality_estimate", {})).get("expected_fill_quality", 0.0),
                ),
                0.0,
            ),
            "timing_error_score": _safe_float(
                _safe_mapping(_safe_mapping(packet.execution_plan.get("meta", {})).get("execution_feedback_metrics", {})).get(
                    "timing_error_score",
                    0.0,
                ),
                0.0,
            ),
            "realized_vs_expected_slippage": _safe_float(
                _safe_mapping(_safe_mapping(packet.execution_plan.get("meta", {})).get("execution_feedback_metrics", {})).get(
                    "realized_vs_expected_slippage",
                    0.0,
                ),
                0.0,
            ),
            "opportunity_decay_metric": _safe_float(
                _safe_mapping(_safe_mapping(packet.execution_plan.get("meta", {})).get("execution_feedback_metrics", {})).get(
                    "opportunity_decay_metric",
                    0.0,
                ),
                0.0,
            ),
        }
        exec_meta = _safe_mapping(_safe_mapping(packet.execution_plan.get("meta", {})).get("execution_intelligence", {}))
        exec_advisory = _safe_mapping(
            exec_meta.get(
                "advisory_escalation",
                _safe_mapping(_safe_mapping(packet.execution_plan.get("meta", {})).get("execution_advisory", {})),
            )
        )
        exec_survival = _safe_mapping(exec_meta.get("survival_protocol", {}))
        exec_spoofing = _safe_mapping(exec_meta.get("spoofing_heuristic", {}))
        execution_summary.update(
            {
                "execution_advisory_severity": str(exec_advisory.get("severity", "")),
                "execution_advisory_score": _safe_float(exec_advisory.get("severity_score", 0.0), 0.0),
                "execution_advisory_reason_codes": [str(item) for item in exec_advisory.get("reason_codes", [])]
                if isinstance(exec_advisory.get("reason_codes", []), list)
                else [],
                "execution_survival_protocol": str(exec_survival.get("protocol", "")),
                "execution_spoofing_score": _safe_float(exec_spoofing.get("oscillation_score", 0.0), 0.0),
                "execution_spoofing_flag": bool(exec_spoofing.get("spoof_like_flag", False)),
            }
        )
        shield_mode = str(packet.shield.get("shield_mode", packet.shield.get("mode", "normal")) or "normal")
        shield_summary = {
            "mode": shield_mode,
            "previous_mode": str(packet.shield.get("previous_mode", packet.shield.get("previous_shield_mode", shield_mode)) or shield_mode),
            "approved": bool(packet.shield.get("approved", False)),
            "no_trade_forced": bool(packet.shield.get("no_trade_forced", False)),
            "hard_stop_forced": bool(packet.shield.get("hard_stop_forced", False)),
            "escalation_reason_codes": list(packet.shield.get("escalation_reason_codes", packet.shield.get("reason_codes", []))),
        }
        strategy_health_summary = _safe_mapping(packet.shield.get("strategy_health_summary", {}))
        if not strategy_health_summary:
            strategy_health_summary = _safe_mapping(packet.ops_snapshot.get("strategy_health_summary", {}))

        meta_strategy_weights = packet.meta_intelligence.get("strategy_weights", [])
        meta_allocation_summary = {
            "regime_cluster": str(packet.meta_intelligence.get("regime_cluster", "")),
            "risk_scale": _safe_float(packet.meta_intelligence.get("risk_scale", 1.0), 1.0),
            "strategy_weights": [dict(row) for row in meta_strategy_weights] if isinstance(meta_strategy_weights, list) else [],
        }

        outcome_grade = str(packet.evaluation.get("outcome_grade", packet.evaluation.get("grade", "pending")))
        realized_outcome_summary = {
            "evaluation_status": str(packet.evaluation.get("status", "pending")),
            "outcome_grade": outcome_grade,
            "reason_codes": list(packet.evaluation.get("reason_codes", [])) if isinstance(packet.evaluation.get("reason_codes", []), list) else [],
            "risk_adjusted_score": _safe_float(packet.evaluation.get("risk_adjusted_score", 0.0), 0.0),
            "realized_regime": str(packet.realized_regime or ""),
        }

        replay_eligible = bool(packet.cycle_id and packet.world_state_fingerprint and packet.selected_strategy)
        drawdown = _safe_float(packet.world_state.get("portfolio", {}).get("drawdown_pct", 0.0) if isinstance(packet.world_state.get("portfolio", {}), Mapping) else 0.0, 0.0)
        record = DecisionMemoryRecord(
            run_id=self.run_dir.name,
            decision_id=str(packet.cycle_id),
            ts=float(packet.ts),
            symbol=str(packet.symbol),
            instrument=str(packet.symbol),
            world_state_fingerprint=str(packet.world_state_fingerprint),
            decision_fingerprint=DecisionFingerprint.from_packet(packet),
            mission_summary=mission_summary,
            parliament_summary=parliament_summary,
            execution_summary=execution_summary,
            shield_summary=shield_summary,
            strategy_health_summary=strategy_health_summary,
            meta_allocation_summary=meta_allocation_summary,
            realized_outcome_summary=realized_outcome_summary,
            pnl_quote=_safe_float(packet.realized_pnl_quote, 0.0),
            drawdown_contribution=drawdown,
            slippage_bps=_safe_float(packet.realized_slippage_bps, 0.0),
            replay_eligible=replay_eligible,
            grading_status=str(packet.evaluation.get("status", "pending")),
            retention_priority=0.0,
            group_key="",
        )
        priority = self._compute_retention_priority(record)
        group_key = self._group_key(record)
        return DecisionMemoryRecord(
            **{
                **record.to_dict(),
                "decision_fingerprint": record.decision_fingerprint,
                "retention_priority": priority,
                "group_key": group_key,
            }
        )

    def grade_outcome(self, packet: DecisionPacket) -> DecisionOutcomeGrade:
        if str(packet.evaluation.get("status", "pending")) != "graded" and not packet.realized_regime and abs(float(packet.realized_pnl_quote)) < 1e-12:
            return DecisionOutcomeGrade(
                outcome_grade=OutcomeGrade.PENDING,
                grade_score=0.0,
                risk_adjusted_score=0.0,
                reason_codes=(OutcomeGradeReason.PENDING_OUTCOME.value,),
                expected_vs_realized_delta_quote=0.0,
            )

        target_notional = max(1.0, abs(_safe_float(packet.execution_plan.get("target_notional_quote", 0.0), 0.0)))
        expected_edge_bps = self._expected_edge_bps(packet)
        expected_quote = (expected_edge_bps / 10_000.0) * target_notional
        realized_quote = _safe_float(packet.realized_pnl_quote, 0.0)
        slippage_bps = max(0.0, _safe_float(packet.realized_slippage_bps, 0.0))
        shield_mode = str(packet.shield.get("shield_mode", packet.shield.get("mode", "normal")) or "normal")
        parliament_no_trade = bool(packet.parliament_no_trade or packet.selected_strategy == "no_trade_guardian")

        pnl_score = _clamp(realized_quote / max(1.0, target_notional * 0.005), -1.0, 1.0)
        execution_penalty = _clamp(slippage_bps / 25.0, 0.0, 1.0)
        shield_penalty_map = {
            "normal": 0.0,
            "cautious": 0.07,
            "defensive": 0.18,
            "observe_only": 0.32,
            "hard_stop": 0.50,
        }
        shield_penalty = float(shield_penalty_map.get(shield_mode, 0.10))
        grade_score = pnl_score - (execution_penalty * 0.25) - shield_penalty

        reasons: list[str] = []
        if realized_quote > 0.0:
            reasons.append(OutcomeGradeReason.POSITIVE_REALIZED_PNL.value)
        elif realized_quote < 0.0:
            reasons.append(OutcomeGradeReason.NEGATIVE_REALIZED_PNL.value)
        else:
            reasons.append(OutcomeGradeReason.FLAT_OUTCOME.value)

        if expected_quote > 0.0 and realized_quote < expected_quote * 0.2:
            reasons.append(OutcomeGradeReason.EXPECTED_EDGE_MISS.value)
        if slippage_bps >= 6.0:
            reasons.append(OutcomeGradeReason.EXECUTION_SLIPPAGE_DRAG.value)
        if shield_mode in {"cautious", "defensive", "observe_only", "hard_stop"}:
            reasons.append(OutcomeGradeReason.SHIELD_ESCALATION_PRESSURE.value)
        else:
            reasons.append(OutcomeGradeReason.SHIELD_STABLE.value)

        if parliament_no_trade:
            if abs(realized_quote) <= 0.25:
                grade_score += 0.20
                reasons.append(OutcomeGradeReason.NO_TRADE_CORRECT.value)
            elif realized_quote > target_notional * 0.004:
                grade_score -= 0.20
                reasons.append(OutcomeGradeReason.NO_TRADE_MISS.value)

        risk_adjusted_score = grade_score - (_clamp(_safe_float(packet.world_state.get("portfolio", {}).get("drawdown_pct", 0.0), 0.0), 0.0, 1.0) * 0.30)

        if risk_adjusted_score <= -0.75 or realized_quote <= -(target_notional * 0.01):
            outcome = OutcomeGrade.SEVERE_NEGATIVE
            reasons.append(OutcomeGradeReason.SEVERE_LOSS.value)
        elif risk_adjusted_score <= -0.20:
            outcome = OutcomeGrade.NEGATIVE
        elif risk_adjusted_score < 0.25:
            outcome = OutcomeGrade.NEUTRAL
        else:
            outcome = OutcomeGrade.POSITIVE

        return DecisionOutcomeGrade(
            outcome_grade=outcome,
            grade_score=_clamp(grade_score, -1.5, 1.5),
            risk_adjusted_score=_clamp(risk_adjusted_score, -1.5, 1.5),
            reason_codes=tuple(dict.fromkeys(reasons)),
            expected_vs_realized_delta_quote=float(realized_quote - expected_quote),
        )

    def record(self, packet: DecisionPacket) -> DecisionPacket:
        self._upsert_packet(self.records_path, packet)
        record = self.build_decision_memory_record(packet)
        self._upsert_decision_memory(record)
        return packet

    def update_packet(self, packet: DecisionPacket, *, graded: bool = False) -> None:
        path = self.evaluations_path if graded else self.records_path
        self._upsert_packet(path, packet)

    def with_learning_snapshot(
        self,
        packet: DecisionPacket,
        *,
        ops_snapshot: Mapping[str, Any] | None = None,
        learning_summary: Mapping[str, Any] | None = None,
    ) -> DecisionPacket:
        raw = packet.to_dict()
        if ops_snapshot is not None:
            raw["ops_snapshot"] = dict(ops_snapshot)
        if learning_summary is not None:
            evaluation = dict(raw.get("evaluation", {}) or {})
            evaluation["learning_summary"] = dict(learning_summary)
            raw["evaluation"] = evaluation
        return DecisionPacket.from_mapping(raw)

    def grade(
        self,
        packet: DecisionPacket,
        *,
        realized_pnl_quote: float,
        realized_slippage_bps: float,
        realized_regime: str,
        fill_ratio: float = 0.0,
    ) -> DecisionPacket:
        pending = DecisionPacket.from_mapping(
            {
                **packet.to_dict(),
                "actual_fill": {"fill_ratio": fill_ratio},
                "realized_pnl_quote": float(realized_pnl_quote),
                "realized_slippage_bps": float(realized_slippage_bps),
                "realized_regime": str(realized_regime),
                "evaluation": {
                    "status": "graded",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
        )
        outcome = self.grade_outcome(pending)
        legacy_grade = (
            "win"
            if outcome.outcome_grade == OutcomeGrade.POSITIVE
            else "loss"
            if outcome.outcome_grade in {OutcomeGrade.NEGATIVE, OutcomeGrade.SEVERE_NEGATIVE}
            else "flat"
        )
        updated = DecisionPacket.from_mapping(
            {
                **pending.to_dict(),
                "evaluation": {
                    "status": "graded",
                    "grade": legacy_grade,
                    "outcome_grade": outcome.outcome_grade.value,
                    "reason_codes": list(outcome.reason_codes),
                    "grade_score": outcome.grade_score,
                    "risk_adjusted_score": outcome.risk_adjusted_score,
                    "expected_vs_realized_delta_quote": outcome.expected_vs_realized_delta_quote,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
        )
        self._upsert_packet(self.evaluations_path, updated)
        self._upsert_decision_memory(self.build_decision_memory_record(updated))
        return updated

    def load(self, *, graded: bool = False) -> list[DecisionPacket]:
        path = self.evaluations_path if graded else self.records_path
        rows = self._read_jsonl(path)
        out: list[DecisionPacket] = []
        for raw in rows:
            out.append(DecisionPacket.from_mapping(raw))
        return out

    def load_memory_records(self) -> list[DecisionMemoryRecord]:
        rows = self._read_jsonl(self.decision_memory_path)
        records = [DecisionMemoryRecord.from_mapping(row) for row in rows]
        by_id: dict[str, DecisionMemoryRecord] = {}
        for row in records:
            existing = by_id.get(row.decision_id)
            if existing is None or row.ts >= existing.ts:
                by_id[row.decision_id] = row
        return sorted(by_id.values(), key=lambda row: (row.ts, row.decision_id))

    def persist_replay_batch_status(self, payload: Mapping[str, Any]) -> None:
        rows = self._read_jsonl(self.replay_batch_path)
        rows.append(self._compact_replay_batch_payload(dict(payload)))
        limit = max(1, int(self.replay_retention_policy.max_replay_batches))
        if len(rows) > limit:
            rows = rows[-limit:]
        self._write_jsonl(self.replay_batch_path, rows)

    def persist_replay_grades(
        self,
        *,
        batch_id: str,
        grades: Iterable[Mapping[str, Any]],
        reproducibility_metadata: Mapping[str, Any] | None = None,
    ) -> None:
        rows = self._read_jsonl(self.replay_grade_history_path)
        metadata = dict(reproducibility_metadata or {})
        as_of_ts = _safe_float(metadata.get("as_of_ts", metadata.get("latest_packet_ts", 0.0)), 0.0)
        for grade in grades:
            payload = dict(grade)
            strategy_fingerprint = str(payload.get("strategy_fingerprint", "") or "")
            if not strategy_fingerprint:
                continue
            rows.append(
                {
                    "batch_id": str(batch_id or ""),
                    "strategy_fingerprint": strategy_fingerprint,
                    "as_of_ts": float(as_of_ts),
                    "overall_grade": _safe_float(payload.get("overall_grade", 0.0), 0.0),
                    "grade": payload,
                    "reproducibility_metadata": dict(metadata),
                }
            )
        compacted = self._compact_replay_grade_rows(rows)
        self._write_jsonl(self.replay_grade_history_path, compacted)

        index = self._read_replay_index()
        for row in compacted:
            strategy_fingerprint = str(row.get("strategy_fingerprint", "") or "")
            if not strategy_fingerprint:
                continue
            existing = dict(index.get(strategy_fingerprint, {}))
            existing["latest_replay_grade"] = dict(row.get("grade", {}) or {})
            existing["last_replay_batch_id"] = str(row.get("batch_id", "") or "")
            existing["reproducibility_metadata"] = dict(row.get("reproducibility_metadata", {}) or {})
            index[strategy_fingerprint] = existing
        self._write_replay_index(index)

    def load_replay_grade_history(self) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        rows = self._read_jsonl(self.replay_grade_history_path)
        history: dict[str, list[dict[str, Any]]] = {}
        inconsistent: set[str] = set()
        for row in rows:
            strategy_fingerprint = str(row.get("strategy_fingerprint", "") or "")
            grade_payload = _safe_mapping(row.get("grade", {}))
            if not strategy_fingerprint or not grade_payload or "overall_grade" not in grade_payload:
                if strategy_fingerprint:
                    inconsistent.add(strategy_fingerprint)
                continue
            history.setdefault(strategy_fingerprint, []).append(grade_payload)
        for strategy_fingerprint, grade_rows in list(history.items()):
            history[strategy_fingerprint] = grade_rows[-self.max_replay_grade_history_per_strategy :]
        return history, sorted(inconsistent)

    def persist_promotion_ladder_state(self, payload: Mapping[str, Any]) -> None:
        rows = self._read_jsonl(self.promotion_ladder_path)
        rows.append(dict(payload))
        limit = max(1, int(self.replay_retention_policy.max_promotion_snapshots))
        if len(rows) > limit:
            rows = rows[-limit:]
        self._write_jsonl(self.promotion_ladder_path, rows)

        index = self._read_replay_index()
        for row in payload.get("decisions", []):
            if not isinstance(row, Mapping):
                continue
            strategy_fingerprint = str(row.get("strategy_fingerprint", "") or "")
            if not strategy_fingerprint:
                continue
            existing = dict(index.get(strategy_fingerprint, {}))
            existing["latest_promotion_decision"] = dict(row)
            existing["latest_stage"] = str(row.get("next_stage_candidate", row.get("current_stage", "sandbox_shadow")) or "sandbox_shadow")
            index[strategy_fingerprint] = existing
        self._write_replay_index(index)

    def latest_replay_batch_status(self) -> dict[str, Any]:
        rows = self._read_jsonl(self.replay_batch_path)
        if not rows:
            return {}
        return dict(rows[-1])

    def latest_promotion_ladder_state(self) -> dict[str, Any]:
        rows = self._read_jsonl(self.promotion_ladder_path)
        if not rows:
            return {}
        return dict(rows[-1])

    def replay_fingerprint_lookup(self, strategy_fingerprint: str) -> dict[str, Any]:
        key = str(strategy_fingerprint or "")
        if not key:
            return {}
        index = self._read_replay_index()
        return dict(index.get(key, {}) if isinstance(index.get(key, {}), Mapping) else {})

    def learning_snapshot(self) -> DecisionMemorySnapshot:
        records = self.load_memory_records()
        by_mission: dict[str, int] = {}
        by_strategy: dict[str, int] = {}
        by_shield_mode: dict[str, int] = {}
        graded_records = 0
        replay_records = 0
        escalation_count = 0
        feedback_samples = 0
        fill_quality_sum = 0.0
        timing_error_sum = 0.0
        slippage_gap_sum = 0.0
        opportunity_decay_sum = 0.0
        for row in records:
            mission = str(row.mission_summary.get("mission", "unknown") or "unknown")
            strategy = str(row.parliament_summary.get("selected_strategy", "unknown") or "unknown")
            shield_mode = str(row.shield_summary.get("mode", "normal") or "normal")
            by_mission[mission] = by_mission.get(mission, 0) + 1
            by_strategy[strategy] = by_strategy.get(strategy, 0) + 1
            by_shield_mode[shield_mode] = by_shield_mode.get(shield_mode, 0) + 1
            if row.grading_status == "graded":
                graded_records += 1
            if row.replay_eligible:
                replay_records += 1
            if shield_mode in {"cautious", "defensive", "observe_only", "hard_stop"}:
                escalation_count += 1
            fill_quality = _safe_float(row.execution_summary.get("fill_quality_score", 0.0), 0.0)
            timing_error = _safe_float(row.execution_summary.get("timing_error_score", 0.0), 0.0)
            slippage_gap = _safe_float(row.execution_summary.get("realized_vs_expected_slippage", 0.0), 0.0)
            decay = _safe_float(row.execution_summary.get("opportunity_decay_metric", 0.0), 0.0)
            if fill_quality > 0.0 or timing_error > 0.0 or slippage_gap > 0.0 or decay > 0.0:
                feedback_samples += 1
                fill_quality_sum += fill_quality
                timing_error_sum += timing_error
                slippage_gap_sum += slippage_gap
                opportunity_decay_sum += decay

        policy_grades = self._build_policy_grades(records)
        self._persist_policy_grades(policy_grades)
        promotion = self._promotion_gate(policy_grades)
        demotion = self._demotion_gate(policy_grades)
        retirement = self._retirement_gate(policy_grades)
        self._persist_learning_candidates(promotion=promotion, demotion=demotion, retirement=retirement)

        top_policy = sorted(policy_grades, key=lambda row: row.risk_adjusted_score, reverse=True)
        latest_policy_grade_summary = {
            "top_policy": top_policy[0].to_dict() if top_policy else {},
            "weakest_policy": top_policy[-1].to_dict() if top_policy else {},
            "total_policy_grades": len(policy_grades),
        }
        grading_state_summary = {
            "total": len(records),
            "graded": graded_records,
            "pending": max(0, len(records) - graded_records),
            "grade_coverage": (graded_records / max(len(records), 1)),
        }
        shield_aware_learning_summary = {
            "shield_escalation_share": escalation_count / max(len(records), 1),
            "stable_share": by_shield_mode.get("normal", 0) / max(len(records), 1),
            "hard_stop_share": by_shield_mode.get("hard_stop", 0) / max(len(records), 1),
        }
        replay_evidence_summary = {
            "replay_eligible_records": replay_records,
            "replay_eligible_ratio": replay_records / max(len(records), 1),
            "promotion_candidates": len(promotion.candidates),
        }
        execution_feedback_summary = {
            "sample_count": int(feedback_samples),
            "fill_quality_score": (fill_quality_sum / max(feedback_samples, 1)),
            "timing_error_score": (timing_error_sum / max(feedback_samples, 1)),
            "realized_vs_expected_slippage": (slippage_gap_sum / max(feedback_samples, 1)),
            "opportunity_decay_metric": (opportunity_decay_sum / max(feedback_samples, 1)),
        }
        replay_batch_status = self.latest_replay_batch_status()
        promotion_ladder_state = self.latest_promotion_ladder_state()
        replay_session_id = str(
            replay_batch_status.get(
                "session_id",
                _safe_mapping(replay_batch_status.get("reproducibility_metadata", {})).get("replay_session_id", ""),
            )
            or ""
        )
        walk_forward_payload = _safe_mapping(replay_batch_status.get("walk_forward", {}))
        counterfactual_payload = _safe_mapping(replay_batch_status.get("comparative_counterfactual", {}))
        replay_evidence_summary["replay_session_id"] = replay_session_id
        walk_forward_holdout_grade = _safe_float(walk_forward_payload.get("holdout_overall_grade", 0.0), 0.0)
        counterfactual_overall_grade_delta = _safe_float(
            _safe_mapping(counterfactual_payload.get("deltas", {})).get("overall_grade_delta", 0.0),
            0.0,
        )
        replay_evidence_summary["walk_forward_holdout_grade"] = walk_forward_holdout_grade
        replay_evidence_summary["counterfactual_overall_grade_delta"] = counterfactual_overall_grade_delta
        reconstructed_rows = replay_batch_status.get("reconstructed_decisions", [])
        decision_reconstruction_count = len(reconstructed_rows) if isinstance(reconstructed_rows, list) else 0
        top_strategy_candidates: list[dict[str, Any]] = []
        raw_top = promotion_ladder_state.get("top_strategy_candidates", [])
        if isinstance(raw_top, list):
            top_strategy_candidates = [dict(row) for row in raw_top if isinstance(row, Mapping)]
        if not top_strategy_candidates:
            replay_top = replay_batch_status.get("top_strategy_candidates", [])
            if isinstance(replay_top, list):
                top_strategy_candidates = [dict(row) for row in replay_top if isinstance(row, Mapping)]
        quarantine_strategy_list = []
        raw_quarantine = promotion_ladder_state.get("quarantine_strategy_list", replay_batch_status.get("quarantine_strategy_fingerprints", []))
        if isinstance(raw_quarantine, list):
            quarantine_strategy_list = [str(item) for item in raw_quarantine if str(item)]
        promotion_readiness_score = _safe_float(promotion_ladder_state.get("promotion_readiness_score", 0.0), 0.0)
        if promotion_readiness_score <= 0.0 and top_strategy_candidates:
            promotion_readiness_score = max(
                _safe_float(row.get("promotion_confidence", row.get("overall_grade", 0.0)), 0.0) for row in top_strategy_candidates
            )
        replay_backlog_depth = max(0, _safe_int(replay_batch_status.get("backlog_depth", 0), 0))
        memory_grading_drift = _safe_float(replay_batch_status.get("memory_grading_drift", 0.0), 0.0)
        bounded_retention_health = {
            "max_records": int(self.retention_policy.max_records),
            "current_records": int(len(records)),
            "within_limit": bool(len(records) <= self.retention_policy.max_records),
            "retention_ratio": len(records) / max(self.retention_policy.max_records, 1),
            "replay_retention_policy": self.replay_retention_policy.to_dict(),
        }

        return DecisionMemorySnapshot(
            as_of_ts=datetime.now(timezone.utc).timestamp(),
            total_records=len(records),
            graded_records=graded_records,
            replay_eligible_records=replay_records,
            by_mission=by_mission,
            by_strategy=by_strategy,
            by_shield_mode=by_shield_mode,
            grading_state_summary=grading_state_summary,
            latest_policy_grade_summary=latest_policy_grade_summary,
            promotion_candidates_count=len(promotion.candidates),
            demotion_candidates_count=len(demotion.candidates),
            retirement_candidates_count=len(retirement.candidates),
            shield_aware_learning_summary=shield_aware_learning_summary,
            memory_compaction_summary=self._load_compaction_summary(),
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
            execution_feedback_summary=execution_feedback_summary,
        )

    def aggregate_performance(self, packets: Iterable[DecisionPacket]) -> dict[str, Any]:
        summary: dict[str, dict[str, float]] = {"mission": {}, "strategy": {}, "regime": {}}
        counts: dict[str, dict[str, int]] = {"mission": {}, "strategy": {}, "regime": {}}
        wins = 0
        total = 0
        for packet in packets:
            total += 1
            if float(packet.realized_pnl_quote) > 0.0:
                wins += 1
            mission = str(packet.mission.get("mission", "unknown"))
            regime = str(packet.realized_regime or packet.world_state.get("current_world_state", "unknown"))
            strategy = str(packet.selected_strategy or "unknown")
            for bucket, key, value in (
                ("mission", mission, packet.realized_pnl_quote),
                ("strategy", strategy, packet.realized_pnl_quote),
                ("regime", regime, packet.realized_pnl_quote),
            ):
                summary[bucket][key] = summary[bucket].get(key, 0.0) + float(value)
                counts[bucket][key] = counts[bucket].get(key, 0) + 1
        avg_summary = {
            bucket: {
                key: (summary[bucket][key] / max(counts[bucket][key], 1))
                for key in summary[bucket]
            }
            for bucket in summary
        }
        return {
            "total_records": total,
            "win_rate": wins / max(total, 1),
            "avg_realized_pnl_by": avg_summary,
        }

    def _expected_edge_bps(self, packet: DecisionPacket) -> float:
        if isinstance(packet.parliament.get("diagnostics", {}), Mapping):
            best = _safe_float(packet.parliament.get("diagnostics", {}).get("best_score", 0.0), 0.0)
            if best > 0.0:
                return best
        for row in packet.proposals:
            if str(row.get("strategy", "")) == packet.selected_strategy:
                return _safe_float(row.get("expected_value_bps", 0.0), 0.0)
        return _safe_float(packet.execution_plan.get("expected_net_edge_bps", 0.0), 0.0)

    def _compute_retention_priority(self, record: DecisionMemoryRecord) -> float:
        score = 0.20
        outcome = str(record.realized_outcome_summary.get("outcome_grade", "pending"))
        if outcome == OutcomeGrade.SEVERE_NEGATIVE.value:
            score += 1.10
        elif outcome == OutcomeGrade.NEGATIVE.value:
            score += 0.80
        elif outcome == OutcomeGrade.POSITIVE.value:
            score += 0.55
        score += min(1.0, abs(float(record.pnl_quote)) / 15.0)
        score += min(0.50, float(record.slippage_bps) / 30.0)
        if str(record.shield_summary.get("mode", "normal")) in {"observe_only", "hard_stop"}:
            score += 0.35
        if record.replay_eligible:
            score += 0.25
        return _clamp(score, 0.0, 5.0)

    def _group_key(self, record: DecisionMemoryRecord) -> str:
        return "|".join(
            [
                str(record.mission_summary.get("mission", "unknown")),
                str(record.parliament_summary.get("selected_strategy", "unknown")),
                str(record.shield_summary.get("mode", "normal")),
            ]
        )

    def _build_policy_grades(self, records: list[DecisionMemoryRecord]) -> list[StrategyPolicyGrade]:
        groups: dict[tuple[str, str, str], list[DecisionMemoryRecord]] = {}
        for row in records:
            if row.grading_status != "graded":
                continue
            key = (
                str(row.parliament_summary.get("selected_strategy", "unknown") or "unknown"),
                str(row.mission_summary.get("mission", "unknown") or "unknown"),
                str(row.shield_summary.get("mode", "normal") or "normal"),
            )
            groups.setdefault(key, []).append(row)

        out: list[StrategyPolicyGrade] = []
        for (strategy, mission, shield_mode), bucket in groups.items():
            positive = 0
            neutral = 0
            negative = 0
            severe = 0
            pending = 0
            grade_sum = 0.0
            pnl_sum = 0.0
            slip_sum = 0.0
            replay_count = 0
            shield_stress_count = 0
            for row in bucket:
                outcome = str(row.realized_outcome_summary.get("outcome_grade", "pending"))
                score = _safe_float(row.realized_outcome_summary.get("risk_adjusted_score", 0.0), 0.0)
                if outcome == OutcomeGrade.POSITIVE.value:
                    positive += 1
                elif outcome == OutcomeGrade.NEUTRAL.value:
                    neutral += 1
                elif outcome == OutcomeGrade.NEGATIVE.value:
                    negative += 1
                elif outcome == OutcomeGrade.SEVERE_NEGATIVE.value:
                    severe += 1
                else:
                    pending += 1
                grade_sum += score
                pnl_sum += float(row.pnl_quote)
                slip_sum += float(row.slippage_bps)
                replay_count += 1 if row.replay_eligible else 0
                if str(row.shield_summary.get("mode", "normal")) in {"cautious", "defensive", "observe_only", "hard_stop"}:
                    shield_stress_count += 1

            sample = len(bucket)
            window = GradeWindowSummary(
                sample_count=sample,
                pending_count=pending,
                positive_count=positive,
                neutral_count=neutral,
                negative_count=negative,
                severe_negative_count=severe,
                average_grade_score=(grade_sum / max(sample, 1)),
            )
            shield_escalation_rate = shield_stress_count / max(sample, 1)
            replay_ratio = replay_count / max(sample, 1)
            risk_adjusted = window.average_grade_score - (shield_escalation_rate * 0.20) - (_clamp(slip_sum / max(sample, 1) / 30.0, 0.0, 0.40))
            recommendation = "hold"
            if risk_adjusted >= 0.25 and severe / max(sample, 1) <= 0.05:
                recommendation = "promote_candidate"
            elif risk_adjusted <= -0.45 or severe / max(sample, 1) >= 0.30:
                recommendation = "retire_candidate"
            elif risk_adjusted <= -0.10 or (negative + severe) / max(sample, 1) >= 0.45:
                recommendation = "demote_candidate"

            out.append(
                StrategyPolicyGrade(
                    strategy=strategy,
                    mission=mission,
                    shield_mode=shield_mode,
                    window=window,
                    avg_pnl_quote=pnl_sum / max(sample, 1),
                    avg_slippage_bps=slip_sum / max(sample, 1),
                    shield_escalation_rate=shield_escalation_rate,
                    replay_eligible_ratio=replay_ratio,
                    risk_adjusted_score=risk_adjusted,
                    recommendation=recommendation,
                )
            )
        out.sort(key=lambda row: (row.strategy, row.mission, row.shield_mode))
        return out

    def _promotion_gate(self, grades: list[StrategyPolicyGrade]) -> PromotionGateDecision:
        candidates: list[ReplayPromotionCandidate] = []
        for row in grades:
            if row.window.sample_count < self.min_policy_samples:
                continue
            severe_rate = row.window.severe_negative_count / max(row.window.sample_count, 1)
            win_rate = row.window.positive_count / max(row.window.sample_count, 1)
            if row.risk_adjusted_score < 0.25 or severe_rate > 0.05:
                continue
            if row.replay_eligible_ratio < 0.80 or row.shield_escalation_rate > 0.40:
                continue
            evidence = PromotionEvidenceBundle(
                strategy=row.strategy,
                mission=row.mission,
                shield_mode=row.shield_mode,
                sample_count=row.window.sample_count,
                win_rate=win_rate,
                severe_rate=severe_rate,
                replay_eligible_ratio=row.replay_eligible_ratio,
                shield_escalation_rate=row.shield_escalation_rate,
                risk_adjusted_score=row.risk_adjusted_score,
                reason_codes=("sufficient_samples", "shield_stable", "positive_risk_adjusted_score"),
            )
            size_cap = _clamp(0.40 + row.risk_adjusted_score * 0.40, 0.40, 0.90)
            candidates.append(ReplayPromotionCandidate(strategy=row.strategy, evidence=evidence, recommended_size_cap=size_cap))

        return PromotionGateDecision(
            eligible=bool(candidates),
            candidates=sorted(candidates, key=lambda row: row.evidence.risk_adjusted_score, reverse=True),
            reason_codes=("promotion_gated",),
            min_samples=self.min_policy_samples,
        )

    def _demotion_gate(self, grades: list[StrategyPolicyGrade]) -> DemotionGateDecision:
        rows: list[LearningCandidateRecord] = []
        for row in grades:
            if row.window.sample_count < self.min_policy_samples:
                continue
            neg_rate = (row.window.negative_count + row.window.severe_negative_count) / max(row.window.sample_count, 1)
            if row.risk_adjusted_score <= -0.10 or neg_rate >= 0.45:
                rows.append(
                    LearningCandidateRecord(
                        candidate_id=_stable_hash({"type": "demote", "strategy": row.strategy, "mission": row.mission, "mode": row.shield_mode}),
                        candidate_type="demotion",
                        strategy=row.strategy,
                        mission=row.mission,
                        shield_mode=row.shield_mode,
                        confidence=_clamp(abs(row.risk_adjusted_score), 0.0, 1.0),
                        evidence_count=row.window.sample_count,
                        replay_eligible=row.replay_eligible_ratio >= 0.70,
                        reason_codes=("degrading_performance",),
                        recommended_action="reduce_allocation",
                    )
                )
        return DemotionGateDecision(triggered=bool(rows), candidates=rows, reason_codes=("demotion_gated",))

    def _retirement_gate(self, grades: list[StrategyPolicyGrade]) -> RetirementGateDecision:
        rows: list[LearningCandidateRecord] = []
        for row in grades:
            if row.window.sample_count < self.min_policy_samples:
                continue
            severe_rate = row.window.severe_negative_count / max(row.window.sample_count, 1)
            if severe_rate >= 0.30 or row.risk_adjusted_score <= -0.45:
                rows.append(
                    LearningCandidateRecord(
                        candidate_id=_stable_hash({"type": "retire", "strategy": row.strategy, "mission": row.mission, "mode": row.shield_mode}),
                        candidate_type="retirement",
                        strategy=row.strategy,
                        mission=row.mission,
                        shield_mode=row.shield_mode,
                        confidence=_clamp(severe_rate + abs(row.risk_adjusted_score), 0.0, 1.0),
                        evidence_count=row.window.sample_count,
                        replay_eligible=row.replay_eligible_ratio >= 0.70,
                        reason_codes=("toxic_failure_pattern",),
                        recommended_action="retire_candidate",
                    )
                )
        return RetirementGateDecision(triggered=bool(rows), candidates=rows, reason_codes=("retirement_gated",))

    def _persist_policy_grades(self, grades: list[StrategyPolicyGrade]) -> None:
        now_ts = datetime.now(timezone.utc).timestamp()
        rows = [
            PolicyGradeRecord(
                strategy=row.strategy,
                mission=row.mission,
                shield_mode=row.shield_mode,
                sample_count=row.window.sample_count,
                risk_adjusted_score=row.risk_adjusted_score,
                recommendation=row.recommendation,
                updated_ts=now_ts,
            ).to_dict()
            for row in grades
        ]
        self._write_jsonl(self.policy_grade_path, rows)

    def _persist_learning_candidates(
        self,
        *,
        promotion: PromotionGateDecision,
        demotion: DemotionGateDecision,
        retirement: RetirementGateDecision,
    ) -> None:
        rows: list[dict[str, Any]] = []
        for candidate in promotion.candidates:
            rows.append(
                LearningCandidateRecord(
                    candidate_id=_stable_hash({"type": "promotion", "strategy": candidate.strategy, "mission": candidate.evidence.mission, "mode": candidate.evidence.shield_mode}),
                    candidate_type="promotion",
                    strategy=candidate.strategy,
                    mission=candidate.evidence.mission,
                    shield_mode=candidate.evidence.shield_mode,
                    confidence=_clamp(candidate.evidence.risk_adjusted_score, 0.0, 1.0),
                    evidence_count=candidate.evidence.sample_count,
                    replay_eligible=candidate.evidence.replay_eligible_ratio >= 0.80,
                    reason_codes=tuple(candidate.evidence.reason_codes),
                    recommended_action="replay_promotion_candidate",
                ).to_dict()
            )
        rows.extend(row.to_dict() for row in demotion.candidates)
        rows.extend(row.to_dict() for row in retirement.candidates)
        self._write_jsonl(self.learning_candidates_path, rows)

    def _upsert_packet(self, path: Path, packet: DecisionPacket) -> None:
        rows = self._read_jsonl(path)
        payload = packet.to_dict()
        key = str(payload.get("cycle_id", ""))
        replaced = False
        for idx, row in enumerate(rows):
            if str(row.get("cycle_id", "")) == key:
                rows[idx] = payload
                replaced = True
                break
        if not replaced:
            rows.append(payload)
        if len(rows) > self.max_records:
            rows = rows[-self.max_records :]
        self._write_jsonl(path, rows)

    def _upsert_decision_memory(self, record: DecisionMemoryRecord) -> None:
        rows = self._read_jsonl(self.decision_memory_path)
        payload = record.to_dict()
        key = str(payload.get("decision_id", ""))
        replaced = False
        for idx, row in enumerate(rows):
            if str(row.get("decision_id", "")) == key:
                rows[idx] = payload
                replaced = True
                break
        if not replaced:
            rows.append(payload)

        compacted = self._compact_memory_rows(rows)
        self._write_jsonl(self.decision_memory_path, compacted)

    def _compact_memory_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        limit = max(1, int(self.retention_policy.max_records))
        if len(rows) <= limit:
            self._last_compaction = MemoryCompactionDecision(
                applied=False,
                before_count=len(rows),
                after_count=len(rows),
                dropped_count=0,
                kept_recent_count=len(rows),
                kept_priority_count=0,
                representative_kept=0,
                reason_codes=("within_limit",),
            )
            self._persist_compaction_summary(rows)
            return rows

        records = [DecisionMemoryRecord.from_mapping(row) for row in rows]
        records.sort(key=lambda row: (row.ts, row.decision_id))
        recent_keep = max(1, int(limit * _clamp(self.retention_policy.recent_reserve_ratio, 0.30, 0.95)))
        recent = records[-recent_keep:]
        older = records[:-recent_keep]
        slots = max(0, limit - len(recent))

        ranked = sorted(
            older,
            key=lambda row: (
                -float(row.retention_priority),
                -abs(float(row.pnl_quote)),
                -float(row.ts),
                row.decision_id,
            ),
        )
        selected: list[DecisionMemoryRecord] = []
        bucket_counter: dict[str, int] = {}
        rep_limit = max(0, int(self.retention_policy.representative_per_bucket))
        for row in ranked:
            if len(selected) >= slots:
                break
            bucket = row.group_key
            if bucket_counter.get(bucket, 0) >= rep_limit:
                continue
            selected.append(row)
            bucket_counter[bucket] = bucket_counter.get(bucket, 0) + 1
        for row in ranked:
            if len(selected) >= slots:
                break
            if row in selected:
                continue
            selected.append(row)

        kept_records = sorted(selected + recent, key=lambda row: (row.ts, row.decision_id))
        self._last_compaction = MemoryCompactionDecision(
            applied=True,
            before_count=len(records),
            after_count=len(kept_records),
            dropped_count=max(0, len(records) - len(kept_records)),
            kept_recent_count=len(recent),
            kept_priority_count=len(selected),
            representative_kept=sum(bucket_counter.values()),
            reason_codes=("bounded_retention", "priority_compaction"),
        )
        payload = [row.to_dict() for row in kept_records]
        self._persist_compaction_summary(payload)
        return payload

    def _persist_compaction_summary(self, rows: list[dict[str, Any]]) -> None:
        bucket_counts: dict[str, int] = {}
        for row in rows:
            bucket = str(row.get("group_key", ""))
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        summary = MemoryArchiveSummary(
            as_of_ts=datetime.now(timezone.utc).timestamp(),
            decision=self._last_compaction,
            bucket_counts=bucket_counts,
        )
        self.archive_summary_path.write_text(json.dumps(summary.to_dict(), sort_keys=True), encoding="utf-8")

    def _compact_replay_batch_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        compacted = dict(payload)
        reconstructed = compacted.get("reconstructed_decisions", [])
        if isinstance(reconstructed, list):
            max_reconstructed = max(1, int(self.replay_retention_policy.max_reconstructed_decisions))
            compacted["reconstructed_decisions"] = [dict(row) for row in reconstructed[-max_reconstructed:] if isinstance(row, Mapping)]
        walk_forward = compacted.get("walk_forward", {})
        if isinstance(walk_forward, Mapping):
            walk_payload = dict(walk_forward)
            wf_batches = walk_payload.get("walk_forward_batches", [])
            if isinstance(wf_batches, list):
                max_batches = max(1, int(self.replay_retention_policy.max_walk_forward_batches))
                walk_payload["walk_forward_batches"] = [dict(row) for row in wf_batches[-max_batches:] if isinstance(row, Mapping)]
            compacted["walk_forward"] = walk_payload
        comparative = compacted.get("comparative_counterfactual", {})
        if isinstance(comparative, Mapping):
            compacted["comparative_counterfactual"] = dict(comparative)
        return compacted

    def _compact_replay_grade_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_strategy: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            strategy_fingerprint = str(row.get("strategy_fingerprint", "") or "")
            if not strategy_fingerprint:
                continue
            by_strategy.setdefault(strategy_fingerprint, []).append(dict(row))
        compacted: list[dict[str, Any]] = []
        for strategy_fingerprint in sorted(by_strategy.keys()):
            ordered = by_strategy[strategy_fingerprint]
            ordered.sort(
                key=lambda row: (
                    _safe_float(row.get("as_of_ts", 0.0), 0.0),
                    str(row.get("batch_id", "") or ""),
                )
            )
            compacted.extend(ordered[-self.max_replay_grade_history_per_strategy :])
        if len(compacted) > self.max_records:
            compacted = compacted[-self.max_records :]
        return compacted

    def _read_replay_index(self) -> dict[str, Any]:
        if not self.replay_fingerprint_index_path.exists():
            return {}
        try:
            payload = json.loads(self.replay_fingerprint_index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return dict(payload) if isinstance(payload, Mapping) else {}

    def _write_replay_index(self, payload: Mapping[str, Any]) -> None:
        self.replay_fingerprint_index_path.write_text(
            json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":")),
            encoding="utf-8",
        )

    def _load_compaction_summary(self) -> dict[str, Any]:
        if not self.archive_summary_path.exists():
            return self._last_compaction.to_dict()
        try:
            payload = json.loads(self.archive_summary_path.read_text(encoding="utf-8"))
        except Exception:
            return self._last_compaction.to_dict()
        return dict(payload) if isinstance(payload, Mapping) else self._last_compaction.to_dict()

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except Exception:
                continue
            if isinstance(payload, Mapping):
                out.append(dict(payload))
        return out

    def _write_jsonl(self, path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
        payload = "\n".join(json.dumps(dict(row), sort_keys=True, default=str, separators=(",", ":")) for row in rows)
        if payload:
            payload += "\n"
        path.write_text(payload, encoding="utf-8")
