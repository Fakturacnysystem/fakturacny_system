from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from statistics import mean, pstdev
from typing import Any, Iterable, Mapping

from .memory import DecisionPacket
from .state import WorldStateSnapshot


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


def build_promotion_replay_contract(
    *,
    batch_status: Mapping[str, Any],
    top_strategy_candidates: Iterable[Mapping[str, Any]] = (),
    quarantine_strategy_fingerprints: Iterable[str] = (),
) -> dict[str, Any]:
    status = _safe_mapping(batch_status)
    reproducibility = _safe_mapping(status.get("reproducibility_metadata", {}))
    session_id = str(status.get("session_id", reproducibility.get("replay_session_id", "")) or "")
    top_fingerprints = sorted(
        {
            str(row.get("strategy_fingerprint", "") or "")
            for row in top_strategy_candidates
            if isinstance(row, Mapping) and str(row.get("strategy_fingerprint", "") or "")
        }
    )
    from_status_quarantine = status.get("quarantine_strategy_fingerprints", [])
    status_quarantine_list = [str(item) for item in from_status_quarantine] if isinstance(from_status_quarantine, list) else []
    quarantine = sorted(
        {
            *[str(item) for item in quarantine_strategy_fingerprints if str(item)],
            *[str(item) for item in status_quarantine_list if str(item)],
        }
    )
    scenario_fingerprints_raw = reproducibility.get("scenario_fingerprints", [])
    inferred_markers_raw = reproducibility.get("inferred_markers", [])
    scenario_fingerprints = sorted(str(item) for item in scenario_fingerprints_raw) if isinstance(scenario_fingerprints_raw, list) else []
    inferred_markers = sorted(str(item) for item in inferred_markers_raw) if isinstance(inferred_markers_raw, list) else []
    packet_fingerprint = str(reproducibility.get("packet_fingerprint", "") or "")
    if not packet_fingerprint:
        packet_fingerprint = _stable_hash(
            {
                "batch_id": str(status.get("batch_id", "") or ""),
                "session_id": session_id,
                "top_strategy_fingerprints": top_fingerprints,
                "quarantine_strategy_fingerprints": quarantine,
            }
        )
    contract_payload = {
        "contract_version": "phase19_promotion_replay_contract_v1",
        "batch_id": str(status.get("batch_id", "") or ""),
        "session_id": session_id,
        "algorithm_version": str(reproducibility.get("algorithm_version", "phase8_replay:v1") or "phase8_replay:v1"),
        "packet_fingerprint": packet_fingerprint,
        "scenario_fingerprints": scenario_fingerprints,
        "mission_filter": str(reproducibility.get("mission_filter", "") or ""),
        "capital_scale": float(_safe_float(reproducibility.get("capital_scale", 0.0), 0.0)),
        "processed_packets": max(0, _safe_int(status.get("processed_packets", 0), 0)),
        "scenario_count": max(0, _safe_int(status.get("scenario_count", 0), 0)),
        "trace_count": max(0, _safe_int(status.get("trace_count", 0), 0)),
        "deterministic": bool(status.get("deterministic", True)),
        "failed": bool(status.get("failed", False)),
        "top_strategy_fingerprints": top_fingerprints,
        "quarantine_strategy_fingerprints": quarantine,
        "inferred_markers": inferred_markers,
    }
    required_fields_missing = [
        key
        for key in ("batch_id", "session_id", "algorithm_version", "packet_fingerprint")
        if not str(contract_payload.get(key, "") or "")
    ]
    contract_payload["required_fields_missing"] = required_fields_missing
    contract_payload["contract_ready"] = len(required_fields_missing) == 0
    contract_payload["contract_id"] = _stable_hash(contract_payload)
    return contract_payload


def _stage_from_value(value: str | PromotionStage | None) -> "PromotionStage":
    if isinstance(value, PromotionStage):
        return value
    raw = str(value or PromotionStage.OFFLINE_REPLAY.value).strip().lower()
    aliases = {
        "sandbox_shadow": PromotionStage.OFFLINE_REPLAY.value,
        "shadow_live": PromotionStage.SHADOW_READY.value,
        "micro_capital_live": PromotionStage.PAPER_READY.value,
        "scaled_live": PromotionStage.LIMITED_LIVE_READY.value,
        "core_live": PromotionStage.SCALED_LIVE_CANDIDATE.value,
    }
    raw = aliases.get(raw, raw)
    for stage in PromotionStage:
        if stage.value == raw:
            return stage
    return PromotionStage.OFFLINE_REPLAY


@dataclass(frozen=True)
class ReplayScenario:
    symbol: str
    timeframe: str
    liquidity_regime: str
    volatility_regime: str
    mission_context: dict[str, Any] = field(default_factory=dict)
    shield_escalation_context: dict[str, Any] = field(default_factory=dict)
    execution_constraints: dict[str, Any] = field(default_factory=dict)
    capital_envelope: dict[str, Any] = field(default_factory=dict)
    dataset_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.dataset_fingerprint:
            object.__setattr__(
                self,
                "dataset_fingerprint",
                _stable_hash(
                    {
                        "symbol": self.symbol,
                        "timeframe": self.timeframe,
                        "liquidity_regime": self.liquidity_regime,
                        "volatility_regime": self.volatility_regime,
                        "mission_context": dict(self.mission_context),
                        "shield_escalation_context": dict(self.shield_escalation_context),
                        "execution_constraints": dict(self.execution_constraints),
                        "capital_envelope": dict(self.capital_envelope),
                    }
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "liquidity_regime": self.liquidity_regime,
            "volatility_regime": self.volatility_regime,
            "mission_context": dict(self.mission_context),
            "shield_escalation_context": dict(self.shield_escalation_context),
            "execution_constraints": dict(self.execution_constraints),
            "capital_envelope": dict(self.capital_envelope),
            "dataset_fingerprint": self.dataset_fingerprint,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ReplayScenario":
        return cls(
            symbol=str(raw.get("symbol", "") or ""),
            timeframe=str(raw.get("timeframe", "intraday") or "intraday"),
            liquidity_regime=str(raw.get("liquidity_regime", "NORMAL") or "NORMAL"),
            volatility_regime=str(raw.get("volatility_regime", "LOW_VOL") or "LOW_VOL"),
            mission_context=_safe_mapping(raw.get("mission_context", {})),
            shield_escalation_context=_safe_mapping(raw.get("shield_escalation_context", {})),
            execution_constraints=_safe_mapping(raw.get("execution_constraints", {})),
            capital_envelope=_safe_mapping(raw.get("capital_envelope", {})),
            dataset_fingerprint=str(raw.get("dataset_fingerprint", "") or ""),
        )


@dataclass(frozen=True)
class ReplayDecisionTrace:
    strategy_fingerprint: str
    scenario_fingerprint: str
    ordered_decision_timeline: list[dict[str, Any]]
    mission_selection: dict[str, Any]
    proposal_ranking: list[dict[str, Any]]
    execution_posture: dict[str, Any]
    risk_posture: dict[str, Any]
    realized_pnl: float
    unrealized_pnl: float
    drawdown_curve: list[float]
    trade_duration_stats: dict[str, float]
    slippage_estimate: float
    fill_ratio_estimate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_fingerprint": self.strategy_fingerprint,
            "scenario_fingerprint": self.scenario_fingerprint,
            "ordered_decision_timeline": [dict(row) for row in self.ordered_decision_timeline],
            "mission_selection": dict(self.mission_selection),
            "proposal_ranking": [dict(row) for row in self.proposal_ranking],
            "execution_posture": dict(self.execution_posture),
            "risk_posture": dict(self.risk_posture),
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "drawdown_curve": [float(value) for value in self.drawdown_curve],
            "trade_duration_stats": dict(self.trade_duration_stats),
            "slippage_estimate": float(self.slippage_estimate),
            "fill_ratio_estimate": float(self.fill_ratio_estimate),
        }


@dataclass(frozen=True)
class StrategyReplayGrade:
    stability_score: float
    risk_adjusted_return: float
    drawdown_severity: float
    volatility_of_edge: float
    capital_efficiency: float
    regime_consistency: float
    shield_penalty_score: float
    determinism_score: float
    overall_grade: float
    strategy_fingerprint: str = ""
    sample_count: int = 0
    regime_diversity_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stability_score": float(self.stability_score),
            "risk_adjusted_return": float(self.risk_adjusted_return),
            "drawdown_severity": float(self.drawdown_severity),
            "volatility_of_edge": float(self.volatility_of_edge),
            "capital_efficiency": float(self.capital_efficiency),
            "regime_consistency": float(self.regime_consistency),
            "shield_penalty_score": float(self.shield_penalty_score),
            "determinism_score": float(self.determinism_score),
            "overall_grade": float(self.overall_grade),
            "strategy_fingerprint": self.strategy_fingerprint,
            "sample_count": int(self.sample_count),
            "regime_diversity_count": int(self.regime_diversity_count),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "StrategyReplayGrade":
        return cls(
            stability_score=_safe_float(raw.get("stability_score", 0.0), 0.0),
            risk_adjusted_return=_safe_float(raw.get("risk_adjusted_return", 0.0), 0.0),
            drawdown_severity=_safe_float(raw.get("drawdown_severity", 0.0), 0.0),
            volatility_of_edge=_safe_float(raw.get("volatility_of_edge", 0.0), 0.0),
            capital_efficiency=_safe_float(raw.get("capital_efficiency", 0.0), 0.0),
            regime_consistency=_safe_float(raw.get("regime_consistency", 0.0), 0.0),
            shield_penalty_score=_safe_float(raw.get("shield_penalty_score", 0.0), 0.0),
            determinism_score=_safe_float(raw.get("determinism_score", 0.0), 0.0),
            overall_grade=_safe_float(raw.get("overall_grade", 0.0), 0.0),
            strategy_fingerprint=str(raw.get("strategy_fingerprint", "") or ""),
            sample_count=_safe_int(raw.get("sample_count", 0), 0),
            regime_diversity_count=_safe_int(raw.get("regime_diversity_count", 0), 0),
        )


class PromotionStage(str, Enum):
    OFFLINE_REPLAY = "offline_replay"
    WALK_FORWARD_VALIDATED = "walk_forward_validated"
    SHADOW_READY = "shadow_ready"
    PAPER_READY = "paper_ready"
    LIMITED_LIVE_READY = "limited_live_ready"
    SCALED_LIVE_CANDIDATE = "scaled_live_candidate"
    SANDBOX_SHADOW = "sandbox_shadow"
    SHADOW_LIVE = "shadow_live"
    MICRO_CAPITAL_LIVE = "micro_capital_live"
    SCALED_LIVE = "scaled_live"
    CORE_LIVE = "core_live"
    DEMOTION_WATCH = "demotion_watch"
    QUARANTINE = "quarantine"


@dataclass(frozen=True)
class PromotionDecision:
    strategy_fingerprint: str
    current_stage: PromotionStage
    next_stage_candidate: PromotionStage | None
    promotion_confidence: float
    capital_scaling_factor: float
    required_observation_window: int
    safety_override_flag: bool
    promotion_reason_codes: tuple[str, ...] = field(default_factory=tuple)
    demotion_reason_codes: tuple[str, ...] = field(default_factory=tuple)
    activation_recommendation: str = "hold"
    quarantine_recommendation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_fingerprint": self.strategy_fingerprint,
            "current_stage": self.current_stage.value,
            "next_stage_candidate": self.next_stage_candidate.value if self.next_stage_candidate is not None else None,
            "promotion_confidence": float(self.promotion_confidence),
            "capital_scaling_factor": float(self.capital_scaling_factor),
            "required_observation_window": int(self.required_observation_window),
            "safety_override_flag": bool(self.safety_override_flag),
            "promotion_reason_codes": list(self.promotion_reason_codes),
            "demotion_reason_codes": list(self.demotion_reason_codes),
            "activation_recommendation": self.activation_recommendation,
            "quarantine_recommendation": bool(self.quarantine_recommendation),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PromotionDecision":
        next_raw = raw.get("next_stage_candidate")
        return cls(
            strategy_fingerprint=str(raw.get("strategy_fingerprint", "") or ""),
            current_stage=_stage_from_value(raw.get("current_stage")),
            next_stage_candidate=_stage_from_value(next_raw) if next_raw not in {None, ""} else None,
            promotion_confidence=_safe_float(raw.get("promotion_confidence", 0.0), 0.0),
            capital_scaling_factor=_safe_float(raw.get("capital_scaling_factor", 0.0), 0.0),
            required_observation_window=max(1, _safe_int(raw.get("required_observation_window", 1), 1)),
            safety_override_flag=bool(raw.get("safety_override_flag", False)),
            promotion_reason_codes=tuple(str(code) for code in raw.get("promotion_reason_codes", []) if str(code)),
            demotion_reason_codes=tuple(str(code) for code in raw.get("demotion_reason_codes", []) if str(code)),
            activation_recommendation=str(raw.get("activation_recommendation", "hold") or "hold"),
            quarantine_recommendation=bool(raw.get("quarantine_recommendation", False)),
        )


@dataclass(frozen=True)
class ActivationGateDecision:
    strategy_fingerprint: str
    allowed: bool
    resolved_stage: PromotionStage
    capital_scaling_factor: float
    per_strategy_exposure_ceiling: float
    risk_multiplier: float
    kill_switch: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_fingerprint": self.strategy_fingerprint,
            "allowed": bool(self.allowed),
            "resolved_stage": self.resolved_stage.value,
            "capital_scaling_factor": float(self.capital_scaling_factor),
            "per_strategy_exposure_ceiling": float(self.per_strategy_exposure_ceiling),
            "risk_multiplier": float(self.risk_multiplier),
            "kill_switch": bool(self.kill_switch),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ReplayBatchStatus:
    enabled: bool
    batch_id: str
    processed_packets: int
    scenario_count: int
    deterministic: bool
    failed: bool
    failure_reason: str
    backlog_depth: int
    reproducibility_metadata: dict[str, Any] = field(default_factory=dict)
    strategy_grades: list[StrategyReplayGrade] = field(default_factory=list)
    traces: list[ReplayDecisionTrace] = field(default_factory=list)
    quarantine_strategy_fingerprints: list[str] = field(default_factory=list)
    memory_grading_drift: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        grades = [row.to_dict() for row in self.strategy_grades]
        top = sorted(grades, key=lambda row: float(row.get("overall_grade", 0.0)), reverse=True)[:5]
        return {
            "enabled": bool(self.enabled),
            "batch_id": self.batch_id,
            "processed_packets": int(self.processed_packets),
            "scenario_count": int(self.scenario_count),
            "deterministic": bool(self.deterministic),
            "failed": bool(self.failed),
            "failure_reason": self.failure_reason,
            "backlog_depth": int(self.backlog_depth),
            "reproducibility_metadata": dict(self.reproducibility_metadata),
            "strategy_grades": grades,
            "trace_count": int(len(self.traces)),
            "quarantine_strategy_fingerprints": sorted(set(str(item) for item in self.quarantine_strategy_fingerprints if str(item))),
            "memory_grading_drift": float(self.memory_grading_drift),
            "top_strategy_candidates": top,
        }


@dataclass(frozen=True)
class ReconstructedDecision:
    cycle_id: str
    symbol: str
    venue: str
    mission: str
    selected_strategy: str
    execution_constraints: dict[str, Any]
    shield_context: dict[str, Any]
    inferred_markers: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "symbol": self.symbol,
            "venue": self.venue,
            "mission": self.mission,
            "selected_strategy": self.selected_strategy,
            "execution_constraints": dict(self.execution_constraints),
            "shield_context": dict(self.shield_context),
            "inferred_markers": [str(item) for item in self.inferred_markers],
        }


@dataclass(frozen=True)
class WalkForwardHoldoutEvaluation:
    session_id: str
    train_batch: dict[str, Any]
    holdout_batch: dict[str, Any]
    walk_forward_batches: list[dict[str, Any]]
    holdout_overall_grade: float
    inferred_markers: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "train_batch": dict(self.train_batch),
            "holdout_batch": dict(self.holdout_batch),
            "walk_forward_batches": [dict(row) for row in self.walk_forward_batches],
            "holdout_overall_grade": float(self.holdout_overall_grade),
            "inferred_markers": [str(item) for item in self.inferred_markers],
        }


@dataclass(frozen=True)
class ComparativeReplayEvaluation:
    session_id: str
    baseline_batch: dict[str, Any]
    counterfactual_batch: dict[str, Any]
    deltas: dict[str, Any]
    inferred_markers: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "baseline_batch": dict(self.baseline_batch),
            "counterfactual_batch": dict(self.counterfactual_batch),
            "deltas": dict(self.deltas),
            "inferred_markers": [str(item) for item in self.inferred_markers],
        }


@dataclass(frozen=True)
class ReplaySessionResult:
    session_id: str
    batch_status: dict[str, Any]
    reconstructed_decisions: list[dict[str, Any]]
    walk_forward: dict[str, Any]
    comparative_counterfactual: dict[str, Any]
    inferred_markers: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "batch_status": dict(self.batch_status),
            "reconstructed_decisions": [dict(row) for row in self.reconstructed_decisions],
            "walk_forward": dict(self.walk_forward),
            "comparative_counterfactual": dict(self.comparative_counterfactual),
            "inferred_markers": [str(item) for item in self.inferred_markers],
        }


@dataclass(frozen=True)
class PromotionLadderState:
    decisions: list[PromotionDecision] = field(default_factory=list)
    activation_gates: list[ActivationGateDecision] = field(default_factory=list)
    top_strategy_candidates: list[dict[str, Any]] = field(default_factory=list)
    quarantine_strategy_list: list[str] = field(default_factory=list)
    promotion_readiness_score: float = 0.0
    promotion_engine_enabled: bool = True
    fallback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [row.to_dict() for row in self.decisions],
            "activation_gates": [row.to_dict() for row in self.activation_gates],
            "top_strategy_candidates": [dict(row) for row in self.top_strategy_candidates],
            "quarantine_strategy_list": sorted(set(str(item) for item in self.quarantine_strategy_list if str(item))),
            "promotion_readiness_score": float(self.promotion_readiness_score),
            "promotion_engine_enabled": bool(self.promotion_engine_enabled),
            "fallback_reason": self.fallback_reason,
        }


class ReplayLadderEngine:
    """Deterministic replay and grading layer for promotion decisions."""

    def __init__(
        self,
        *,
        max_batch_packets: int = 200,
        max_timeline_points: int = 64,
    ) -> None:
        self.max_batch_packets = max(10, int(max_batch_packets))
        self.max_timeline_points = max(8, int(max_timeline_points))

    def run_batch(
        self,
        *,
        packets: Iterable[DecisionPacket],
        scenarios: Iterable[ReplayScenario] = (),
        mission_filter: str = "",
        capital_scale: float = 1.0,
        replay_session_id: str = "",
        inferred_markers: Iterable[str] = (),
    ) -> ReplayBatchStatus:
        rows = sorted(list(packets), key=lambda row: (float(row.ts), str(row.cycle_id)))
        if mission_filter:
            rows = [row for row in rows if str(row.mission.get("mission", "")) == str(mission_filter)]
        backlog_depth = max(0, len(rows) - self.max_batch_packets)
        marker_list = [str(item) for item in inferred_markers if str(item)]
        replay_rows = rows[-self.max_batch_packets :]
        if not replay_rows:
            session_id = replay_session_id or _stable_hash({"session": "empty", "mission_filter": mission_filter, "capital_scale": capital_scale})
            batch_id = _stable_hash({"empty": True, "mission_filter": mission_filter})
            return ReplayBatchStatus(
                enabled=True,
                batch_id=batch_id,
                processed_packets=0,
                scenario_count=0,
                deterministic=True,
                failed=False,
                failure_reason="",
                backlog_depth=0,
                reproducibility_metadata={
                    "algorithm_version": "phase8_replay:v1",
                    "packet_fingerprint": _stable_hash({"packets": []}),
                    "scenario_fingerprints": [],
                    "mission_filter": str(mission_filter or ""),
                    "capital_scale": float(capital_scale),
                    "replay_session_id": session_id,
                    "inferred_markers": marker_list,
                },
            )

        scenario_rows = self._build_scenarios(replay_rows, scenarios=scenarios)
        traces = self._build_traces(replay_rows, scenario_rows=scenario_rows, capital_scale=capital_scale)
        grades = self._grade_traces(traces)
        quarantine = self._quarantine_candidates(replay_rows)
        grading_drift = self._memory_grading_drift(replay_rows, grades)
        packet_fingerprint = _stable_hash(
            {
                "packets": [
                    {
                        "cycle_id": row.cycle_id,
                        "world_state_fingerprint": row.world_state_fingerprint,
                        "selected_strategy": row.selected_strategy,
                        "realized_pnl_quote": float(row.realized_pnl_quote),
                        "realized_slippage_bps": float(row.realized_slippage_bps),
                    }
                    for row in replay_rows
                ]
            }
        )
        scenario_fingerprints = sorted(row.dataset_fingerprint for row in scenario_rows)
        batch_id = _stable_hash(
            {
                "packet_fingerprint": packet_fingerprint,
                "scenario_fingerprints": scenario_fingerprints,
                "mission_filter": str(mission_filter or ""),
                "capital_scale": float(capital_scale),
            }
        )
        session_id = replay_session_id or _stable_hash(
            {
                "packet_fingerprint": packet_fingerprint,
                "mission_filter": mission_filter,
                "capital_scale": float(capital_scale),
                "scenario_fingerprints": scenario_fingerprints,
            }
        )
        return ReplayBatchStatus(
            enabled=True,
            batch_id=batch_id,
            processed_packets=len(replay_rows),
            scenario_count=len(scenario_rows),
            deterministic=True,
            failed=False,
            failure_reason="",
            backlog_depth=backlog_depth,
            reproducibility_metadata={
                "algorithm_version": "phase8_replay:v1",
                "packet_fingerprint": packet_fingerprint,
                "scenario_fingerprints": scenario_fingerprints,
                "mission_filter": str(mission_filter or ""),
                "capital_scale": float(capital_scale),
                "regime_segments": self._regime_segments(replay_rows),
                "replay_session_id": session_id,
                "inferred_markers": marker_list,
            },
            strategy_grades=grades,
            traces=traces,
            quarantine_strategy_fingerprints=quarantine,
            memory_grading_drift=grading_drift,
        )

    def reconstruct_decisions(self, packets: Iterable[DecisionPacket]) -> list[ReconstructedDecision]:
        rows = sorted(list(packets), key=lambda row: (float(row.ts), str(row.cycle_id)))
        out: list[ReconstructedDecision] = []
        for packet in rows:
            execution = _safe_mapping(packet.execution_plan)
            shield = _safe_mapping(packet.shield)
            inferred: list[str] = []
            mission = str(packet.mission.get("mission", "") or "")
            if not mission:
                mission = "unknown"
                inferred.append("inferred:mission_missing")
            order_type = str(execution.get("order_type", "") or "")
            if not order_type:
                execution["order_type"] = "limit"
                inferred.append("inferred:order_type_defaulted")
            if "maker_taker" not in execution or not str(execution.get("maker_taker", "")):
                execution["maker_taker"] = "maker"
                inferred.append("inferred:maker_taker_defaulted")
            if "target_notional_quote" not in execution:
                execution["target_notional_quote"] = 0.0
                inferred.append("inferred:target_notional_defaulted")
            if "mode" not in shield and "shield_mode" in shield:
                shield["mode"] = str(shield.get("shield_mode", "normal"))
                inferred.append("inferred:shield_mode_alias")
            if "mode" not in shield:
                shield["mode"] = "normal"
                inferred.append("inferred:shield_mode_defaulted")
            out.append(
                ReconstructedDecision(
                    cycle_id=str(packet.cycle_id),
                    symbol=str(packet.symbol),
                    venue=str(packet.venue),
                    mission=mission,
                    selected_strategy=str(packet.selected_strategy or ""),
                    execution_constraints=execution,
                    shield_context=shield,
                    inferred_markers=tuple(dict.fromkeys(inferred)),
                )
            )
        return out

    def run_walk_forward_holdout(
        self,
        *,
        packets: Iterable[DecisionPacket],
        scenarios: Iterable[ReplayScenario] = (),
        mission_filter: str = "",
        capital_scale: float = 1.0,
        holdout_ratio: float = 0.20,
        walk_forward_window: int = 32,
        walk_forward_step: int = 16,
        replay_session_id: str = "",
    ) -> WalkForwardHoldoutEvaluation:
        rows = sorted(list(packets), key=lambda row: (float(row.ts), str(row.cycle_id)))
        if mission_filter:
            rows = [row for row in rows if str(row.mission.get("mission", "")) == str(mission_filter)]
        session_id = replay_session_id or _stable_hash(
            {
                "mode": "walk_forward_holdout",
                "mission_filter": mission_filter,
                "capital_scale": float(capital_scale),
                "packet_ids": [row.cycle_id for row in rows],
                "holdout_ratio": float(holdout_ratio),
                "walk_forward_window": int(walk_forward_window),
                "walk_forward_step": int(walk_forward_step),
            }
        )
        if not rows:
            empty = self.run_batch(
                packets=[],
                scenarios=scenarios,
                mission_filter=mission_filter,
                capital_scale=capital_scale,
                replay_session_id=session_id,
                inferred_markers=("inferred:empty_walk_forward_holdout",),
            )
            return WalkForwardHoldoutEvaluation(
                session_id=session_id,
                train_batch=empty.to_dict(),
                holdout_batch=empty.to_dict(),
                walk_forward_batches=[],
                holdout_overall_grade=0.0,
                inferred_markers=("inferred:empty_walk_forward_holdout",),
            )

        holdout_count = max(1, min(len(rows), int(max(0.05, min(0.50, float(holdout_ratio))) * len(rows))))
        train_rows = rows[:-holdout_count] if len(rows) > holdout_count else rows[: max(1, len(rows) - 1)]
        holdout_rows = rows[-holdout_count:] if rows else []
        if not train_rows:
            train_rows = rows[:1]
        train_batch = self.run_batch(
            packets=train_rows,
            scenarios=scenarios,
            mission_filter=mission_filter,
            capital_scale=capital_scale,
            replay_session_id=session_id,
            inferred_markers=("inferred:walk_forward_train_segment",),
        )
        holdout_batch = self.run_batch(
            packets=holdout_rows,
            scenarios=scenarios,
            mission_filter=mission_filter,
            capital_scale=capital_scale,
            replay_session_id=session_id,
            inferred_markers=("inferred:walk_forward_holdout_segment",),
        )
        window = max(8, int(walk_forward_window))
        step = max(4, int(walk_forward_step))
        max_batches = 12
        walk_forward_batches: list[dict[str, Any]] = []
        starts = list(range(0, max(1, len(train_rows) - window + 1), step))
        if not starts:
            starts = [0]
        for idx, start in enumerate(starts[:max_batches]):
            segment = train_rows[start : start + window]
            if not segment:
                continue
            batch = self.run_batch(
                packets=segment,
                scenarios=scenarios,
                mission_filter=mission_filter,
                capital_scale=capital_scale,
                replay_session_id=session_id,
                inferred_markers=(f"inferred:walk_forward_window_{idx}",),
            )
            payload = batch.to_dict()
            payload["segment_start"] = int(start)
            payload["segment_end"] = int(start + len(segment))
            walk_forward_batches.append(payload)
        holdout_grade = self._mean_overall_grade(holdout_batch.strategy_grades)
        return WalkForwardHoldoutEvaluation(
            session_id=session_id,
            train_batch=train_batch.to_dict(),
            holdout_batch=holdout_batch.to_dict(),
            walk_forward_batches=walk_forward_batches,
            holdout_overall_grade=holdout_grade,
            inferred_markers=("inferred:walk_forward_holdout_evaluation",),
        )

    def compare_counterfactual(
        self,
        *,
        packets: Iterable[DecisionPacket],
        scenarios: Iterable[ReplayScenario] = (),
        mission_filter: str = "",
        baseline_capital_scale: float = 1.0,
        counterfactual_capital_scale: float = 0.65,
        counterfactual_constraints: Mapping[str, Any] | None = None,
        replay_session_id: str = "",
    ) -> ComparativeReplayEvaluation:
        rows = sorted(list(packets), key=lambda row: (float(row.ts), str(row.cycle_id)))
        if mission_filter:
            rows = [row for row in rows if str(row.mission.get("mission", "")) == str(mission_filter)]
        constraints = dict(counterfactual_constraints or {})
        session_id = replay_session_id or _stable_hash(
            {
                "mode": "counterfactual",
                "mission_filter": mission_filter,
                "baseline_capital_scale": float(baseline_capital_scale),
                "counterfactual_capital_scale": float(counterfactual_capital_scale),
                "constraints": constraints,
                "packet_ids": [row.cycle_id for row in rows],
            }
        )
        baseline = self.run_batch(
            packets=rows,
            scenarios=scenarios,
            mission_filter=mission_filter,
            capital_scale=baseline_capital_scale,
            replay_session_id=session_id,
            inferred_markers=("inferred:counterfactual_baseline",),
        )
        cf_scale = _clamp(
            float(constraints.get("capital_scale_override", counterfactual_capital_scale)),
            0.01,
            2.0,
        )
        counterfactual = self.run_batch(
            packets=rows,
            scenarios=scenarios,
            mission_filter=mission_filter,
            capital_scale=cf_scale,
            replay_session_id=session_id,
            inferred_markers=("inferred:counterfactual_projection",),
        )
        baseline_mean = self._mean_overall_grade(baseline.strategy_grades)
        counterfactual_mean = self._mean_overall_grade(counterfactual.strategy_grades)
        by_strategy_delta: dict[str, float] = {}
        baseline_map = {row.strategy_fingerprint: row.overall_grade for row in baseline.strategy_grades}
        counter_map = {row.strategy_fingerprint: row.overall_grade for row in counterfactual.strategy_grades}
        for fingerprint in sorted(set(baseline_map.keys()) | set(counter_map.keys())):
            by_strategy_delta[fingerprint] = float(counter_map.get(fingerprint, 0.0) - baseline_map.get(fingerprint, 0.0))
        return ComparativeReplayEvaluation(
            session_id=session_id,
            baseline_batch=baseline.to_dict(),
            counterfactual_batch=counterfactual.to_dict(),
            deltas={
                "overall_grade_delta": float(counterfactual_mean - baseline_mean),
                "memory_grading_drift_delta": float(counterfactual.memory_grading_drift - baseline.memory_grading_drift),
                "by_strategy_overall_grade_delta": by_strategy_delta,
                "counterfactual_constraints": constraints,
            },
            inferred_markers=(
                "inferred:counterfactual_from_baseline_packets",
                "inferred:counterfactual_not_live_executed",
            ),
        )

    def run_session(
        self,
        *,
        packets: Iterable[DecisionPacket],
        scenarios: Iterable[ReplayScenario] = (),
        mission_filter: str = "",
        capital_scale: float = 1.0,
        holdout_ratio: float = 0.20,
        walk_forward_window: int = 32,
        walk_forward_step: int = 16,
        counterfactual_capital_scale: float = 0.65,
        counterfactual_constraints: Mapping[str, Any] | None = None,
    ) -> ReplaySessionResult:
        rows = sorted(list(packets), key=lambda row: (float(row.ts), str(row.cycle_id)))
        session_id = _stable_hash(
            {
                "mode": "replay_session",
                "mission_filter": mission_filter,
                "capital_scale": float(capital_scale),
                "holdout_ratio": float(holdout_ratio),
                "walk_forward_window": int(walk_forward_window),
                "walk_forward_step": int(walk_forward_step),
                "counterfactual_capital_scale": float(counterfactual_capital_scale),
                "counterfactual_constraints": dict(counterfactual_constraints or {}),
                "packet_ids": [row.cycle_id for row in rows],
            }
        )
        batch = self.run_batch(
            packets=rows,
            scenarios=scenarios,
            mission_filter=mission_filter,
            capital_scale=capital_scale,
            replay_session_id=session_id,
            inferred_markers=("inferred:deterministic_replay_session",),
        )
        reconstructed = [row.to_dict() for row in self.reconstruct_decisions(rows)][-self.max_timeline_points :]
        walk_forward = self.run_walk_forward_holdout(
            packets=rows,
            scenarios=scenarios,
            mission_filter=mission_filter,
            capital_scale=capital_scale,
            holdout_ratio=holdout_ratio,
            walk_forward_window=walk_forward_window,
            walk_forward_step=walk_forward_step,
            replay_session_id=session_id,
        )
        comparative = self.compare_counterfactual(
            packets=rows,
            scenarios=scenarios,
            mission_filter=mission_filter,
            baseline_capital_scale=capital_scale,
            counterfactual_capital_scale=counterfactual_capital_scale,
            counterfactual_constraints=counterfactual_constraints,
            replay_session_id=session_id,
        )
        return ReplaySessionResult(
            session_id=session_id,
            batch_status=batch.to_dict(),
            reconstructed_decisions=reconstructed,
            walk_forward=walk_forward.to_dict(),
            comparative_counterfactual=comparative.to_dict(),
            inferred_markers=(
                "inferred:session_reconstruction",
                "inferred:session_walk_forward_holdout",
                "inferred:session_counterfactual_comparison",
            ),
        )

    def _mean_overall_grade(self, grades: Iterable[StrategyReplayGrade]) -> float:
        rows = list(grades)
        if not rows:
            return 0.0
        return _clamp(mean(float(row.overall_grade) for row in rows), 0.0, 1.0)

    def _build_scenarios(
        self,
        rows: list[DecisionPacket],
        *,
        scenarios: Iterable[ReplayScenario],
    ) -> list[ReplayScenario]:
        provided = [row if isinstance(row, ReplayScenario) else ReplayScenario.from_mapping(row) for row in scenarios]
        if provided:
            return sorted(provided, key=lambda row: row.dataset_fingerprint)
        out: dict[tuple[str, str, str, str], ReplayScenario] = {}
        for packet in rows:
            symbol = str(packet.symbol or "").upper()
            liquidity = str(packet.world_state.get("market_state", {}).get("liquidity_regime", "NORMAL"))
            volatility = str(packet.world_state.get("market_state", {}).get("volatility_regime", "LOW_VOL"))
            mission = str(packet.mission.get("mission", "unknown") or "unknown")
            duration = _safe_float(packet.mission.get("duration_hint_s", 300.0), 300.0)
            if duration <= 180.0:
                timeframe = "micro"
            elif duration <= 1_200.0:
                timeframe = "intraday"
            else:
                timeframe = "swing"
            key = (symbol, timeframe, liquidity, volatility)
            if key not in out:
                out[key] = ReplayScenario(
                    symbol=symbol,
                    timeframe=timeframe,
                    liquidity_regime=liquidity,
                    volatility_regime=volatility,
                    mission_context={"mission": mission},
                    shield_escalation_context={"mode": str(packet.shield.get("mode", "normal"))},
                    execution_constraints={
                        "order_type": str(packet.execution_plan.get("order_type", "limit")),
                        "maker_taker": str(packet.execution_plan.get("maker_taker", "maker")),
                    },
                    capital_envelope={
                        "target_notional_quote": _safe_float(packet.execution_plan.get("target_notional_quote", 0.0), 0.0),
                        "equity_quote": _safe_float(packet.world_state.get("portfolio_state", {}).get("equity_quote", 0.0), 0.0),
                    },
                    dataset_fingerprint=str(packet.world_state_fingerprint or ""),
                )
        synthetic: list[ReplayScenario] = []
        for row in sorted(out.values(), key=lambda item: item.dataset_fingerprint):
            synthetic.append(
                ReplayScenario(
                    symbol=row.symbol,
                    timeframe=row.timeframe,
                    liquidity_regime="THIN",
                    volatility_regime="HIGH_VOL",
                    mission_context={**row.mission_context, "synthetic": True},
                    shield_escalation_context={**row.shield_escalation_context, "simulated_escalation_penalty": 0.12},
                    execution_constraints=dict(row.execution_constraints),
                    capital_envelope={**row.capital_envelope, "scenario": "stress"},
                    dataset_fingerprint=_stable_hash({"base": row.dataset_fingerprint, "synthetic": "stress"}),
                )
            )
        merged = list(out.values()) + synthetic
        return sorted(merged, key=lambda row: row.dataset_fingerprint)

    def _matches_scenario(self, packet: DecisionPacket, scenario: ReplayScenario) -> bool:
        if str(packet.symbol or "").upper() != str(scenario.symbol or "").upper():
            return False
        market = _safe_mapping(packet.world_state.get("market_state", {}))
        liquidity = str(market.get("liquidity_regime", "NORMAL") or "NORMAL")
        volatility = str(market.get("volatility_regime", "LOW_VOL") or "LOW_VOL")
        mission = str(packet.mission.get("mission", "unknown") or "unknown")
        if scenario.liquidity_regime and liquidity != scenario.liquidity_regime:
            return False
        if scenario.volatility_regime and volatility != scenario.volatility_regime:
            return False
        expected_mission = str(scenario.mission_context.get("mission", "") or "")
        if expected_mission and mission != expected_mission:
            return False
        return True

    def _strategy_fingerprint(self, packet: DecisionPacket) -> str:
        return _stable_hash(
            {
                "strategy": str(packet.selected_strategy or ""),
                "symbol": str(packet.symbol or ""),
                "mission": str(packet.mission.get("mission", "unknown")),
                "venue": str(packet.venue or ""),
            }
        )

    def _timeline_point(self, packet: DecisionPacket, *, capital_scale: float) -> dict[str, Any]:
        execution = _safe_mapping(packet.execution_plan)
        world_state = _safe_mapping(packet.world_state)
        portfolio = _safe_mapping(world_state.get("portfolio_state", world_state.get("portfolio", {})))
        return {
            "cycle_id": str(packet.cycle_id),
            "ts": float(packet.ts),
            "mission": str(packet.mission.get("mission", "")),
            "selected_strategy": str(packet.selected_strategy or ""),
            "realized_pnl_quote_scaled": float(packet.realized_pnl_quote) * float(capital_scale),
            "unrealized_pnl_quote": _safe_float(portfolio.get("unrealized_pnl_quote", 0.0), 0.0),
            "drawdown_pct": _safe_float(portfolio.get("drawdown_pct", 0.0), 0.0),
            "slippage_bps": _safe_float(packet.realized_slippage_bps, 0.0),
            "fill_ratio": _clamp(_safe_float(packet.actual_fill.get("fill_ratio", 1.0), 1.0), 0.0, 1.0),
            "target_notional_quote_scaled": _safe_float(execution.get("target_notional_quote", 0.0), 0.0) * float(capital_scale),
            "shield_mode": str(packet.shield.get("mode", packet.shield.get("shield_mode", "normal"))),
            "regime": str(_safe_mapping(world_state.get("market_state", {})).get("regime", "unknown")),
        }

    def _build_traces(
        self,
        rows: list[DecisionPacket],
        *,
        scenario_rows: list[ReplayScenario],
        capital_scale: float,
    ) -> list[ReplayDecisionTrace]:
        grouped: dict[tuple[str, str], list[DecisionPacket]] = {}
        for scenario in scenario_rows:
            for packet in rows:
                if not self._matches_scenario(packet, scenario):
                    continue
                key = (self._strategy_fingerprint(packet), scenario.dataset_fingerprint)
                grouped.setdefault(key, []).append(packet)

        traces: list[ReplayDecisionTrace] = []
        for (strategy_fingerprint, scenario_fingerprint), packets in sorted(grouped.items()):
            ordered = sorted(packets, key=lambda row: (float(row.ts), str(row.cycle_id)))
            ordered = ordered[-self.max_timeline_points :]
            if not ordered:
                continue
            timeline = [self._timeline_point(packet, capital_scale=capital_scale) for packet in ordered]
            last = ordered[-1]
            first = ordered[0]
            proposal_ranking = []
            if isinstance(last.parliament.get("selected_top", []), list):
                for row in last.parliament.get("selected_top", []):
                    if isinstance(row, Mapping):
                        proposal_ranking.append(
                            {
                                "strategy": str(row.get("strategy", "")),
                                "expected_value_bps": _safe_float(row.get("expected_value_bps", 0.0), 0.0),
                                "confidence": _safe_float(row.get("confidence", 0.0), 0.0),
                            }
                        )
            if not proposal_ranking and isinstance(last.parliament.get("ranking", []), list):
                for row in last.parliament.get("ranking", []):
                    if isinstance(row, Mapping):
                        proposal = _safe_mapping(row.get("proposal", {}))
                        proposal_ranking.append(
                            {
                                "strategy": str(proposal.get("strategy", "")),
                                "score": _safe_float(row.get("score", 0.0), 0.0),
                                "expected_value_bps": _safe_float(proposal.get("expected_value_bps", 0.0), 0.0),
                            }
                        )
            durations = []
            for packet in ordered:
                for proposal in packet.proposals:
                    if str(proposal.get("strategy", "")) == str(packet.selected_strategy):
                        durations.append(_safe_float(proposal.get("expected_hold_time_s", 0.0), 0.0))
            if not durations:
                durations = [60.0]
            scenario = next((row for row in scenario_rows if row.dataset_fingerprint == scenario_fingerprint), None)
            simulated_penalty = _safe_float(
                _safe_mapping(scenario.shield_escalation_context).get("simulated_escalation_penalty", 0.0) if scenario else 0.0,
                0.0,
            )
            trace = ReplayDecisionTrace(
                strategy_fingerprint=strategy_fingerprint,
                scenario_fingerprint=scenario_fingerprint,
                ordered_decision_timeline=timeline,
                mission_selection={"mission": str(last.mission.get("mission", "unknown")), "confidence": _safe_float(last.mission.get("confidence", 0.0), 0.0)},
                proposal_ranking=proposal_ranking,
                execution_posture={
                    "order_type": str(last.execution_plan.get("order_type", "none")),
                    "maker_taker": str(last.execution_plan.get("maker_taker", "none")),
                    "target_notional_quote_scaled": _safe_float(last.execution_plan.get("target_notional_quote", 0.0), 0.0) * float(capital_scale),
                    "capital_scale": float(capital_scale),
                },
                risk_posture={
                    "shield_mode": str(last.shield.get("mode", last.shield.get("shield_mode", "normal"))),
                    "kill_switch": bool(last.shield.get("kill_switch", False)),
                    "simulated_escalation_penalty": float(simulated_penalty),
                },
                realized_pnl=sum(float(point["realized_pnl_quote_scaled"]) for point in timeline),
                unrealized_pnl=mean(float(point["unrealized_pnl_quote"]) for point in timeline),
                drawdown_curve=[float(point["drawdown_pct"]) for point in timeline],
                trade_duration_stats={
                    "count": float(len(durations)),
                    "mean_s": float(mean(durations)),
                    "min_s": float(min(durations)),
                    "max_s": float(max(durations)),
                    "window_s": float(max(0.0, last.ts - first.ts)),
                },
                slippage_estimate=mean(float(point["slippage_bps"]) for point in timeline),
                fill_ratio_estimate=mean(float(point["fill_ratio"]) for point in timeline),
            )
            traces.append(trace)
        return sorted(traces, key=lambda row: (row.strategy_fingerprint, row.scenario_fingerprint))

    def _grade_traces(self, traces: list[ReplayDecisionTrace]) -> list[StrategyReplayGrade]:
        grouped: dict[str, list[ReplayDecisionTrace]] = {}
        for trace in traces:
            grouped.setdefault(trace.strategy_fingerprint, []).append(trace)

        out: list[StrategyReplayGrade] = []
        for strategy_fingerprint, strategy_traces in sorted(grouped.items()):
            points: list[dict[str, Any]] = []
            shield_penalties: list[float] = []
            capital_levels: list[float] = []
            regimes: set[str] = set()
            timeline_ids: list[str] = []
            for trace in strategy_traces:
                shield_penalties.append(
                    _clamp(
                        _safe_float(trace.risk_posture.get("simulated_escalation_penalty", 0.0), 0.0)
                        + (0.35 if str(trace.risk_posture.get("shield_mode", "normal")) in {"defensive", "observe_only", "hard_stop"} else 0.0),
                        0.0,
                        1.0,
                    )
                )
                capital_levels.append(_safe_float(trace.execution_posture.get("target_notional_quote_scaled", 0.0), 0.0))
                points.extend(trace.ordered_decision_timeline)
                for point in trace.ordered_decision_timeline:
                    regimes.add(str(point.get("regime", "unknown")))
                    timeline_ids.append(str(point.get("cycle_id", "")))
            if not points:
                continue

            pnl_series = [float(point.get("realized_pnl_quote_scaled", 0.0)) for point in points]
            drawdowns = [float(point.get("drawdown_pct", 0.0)) for point in points]
            slippages = [float(point.get("slippage_bps", 0.0)) for point in points]
            mean_pnl = mean(pnl_series)
            stdev_pnl = pstdev(pnl_series) if len(pnl_series) > 1 else 0.0
            max_drawdown = max(drawdowns) if drawdowns else 0.0
            avg_slippage = mean(slippages) if slippages else 0.0
            avg_capital = max(1.0, mean(capital_levels) if capital_levels else 1.0)
            shield_penalty = mean(shield_penalties) if shield_penalties else 0.0
            regime_diversity = len(regimes)
            determinism_score = 1.0
            if len(set(timeline_ids)) != len(timeline_ids):
                determinism_score = 0.85
            if timeline_ids != sorted(timeline_ids):
                determinism_score = min(determinism_score, 0.80)

            stability_score = _clamp(1.0 - (stdev_pnl / (abs(mean_pnl) + stdev_pnl + 1.0)), 0.0, 1.0)
            volatility_of_edge = _clamp(stdev_pnl / max(abs(mean_pnl), 1.0), 0.0, 2.0)
            drawdown_severity = _clamp(max_drawdown, 0.0, 1.0)
            capital_efficiency = _clamp(mean_pnl / avg_capital, -1.0, 1.0)
            risk_adjusted_return = _clamp(
                mean_pnl / max(1.0, (avg_slippage + 1.0) * (1.0 + max_drawdown * 10.0)),
                -1.0,
                1.0,
            )
            regime_consistency = _clamp(
                (min(regime_diversity, 3) / 3.0) * (1.0 - min(volatility_of_edge, 1.0) * 0.35),
                0.0,
                1.0,
            )
            overall_grade = _clamp(
                stability_score * 0.22
                + ((risk_adjusted_return + 1.0) / 2.0) * 0.23
                + ((capital_efficiency + 1.0) / 2.0) * 0.14
                + regime_consistency * 0.13
                + determinism_score * 0.13
                - drawdown_severity * 0.08
                - _clamp(volatility_of_edge / 2.0, 0.0, 1.0) * 0.04
                - shield_penalty * 0.07,
                0.0,
                1.0,
            )
            out.append(
                StrategyReplayGrade(
                    stability_score=stability_score,
                    risk_adjusted_return=risk_adjusted_return,
                    drawdown_severity=drawdown_severity,
                    volatility_of_edge=volatility_of_edge,
                    capital_efficiency=capital_efficiency,
                    regime_consistency=regime_consistency,
                    shield_penalty_score=shield_penalty,
                    determinism_score=determinism_score,
                    overall_grade=overall_grade,
                    strategy_fingerprint=strategy_fingerprint,
                    sample_count=len(points),
                    regime_diversity_count=regime_diversity,
                )
            )
        return sorted(out, key=lambda row: (row.strategy_fingerprint, -row.overall_grade))

    def _regime_segments(self, rows: list[DecisionPacket]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for packet in rows:
            regime = str(_safe_mapping(packet.world_state.get("market_state", {})).get("regime", "unknown") or "unknown")
            key = regime.upper()
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _quarantine_candidates(self, rows: list[DecisionPacket]) -> list[str]:
        cycle_fingerprints: dict[str, str] = {}
        quarantine: set[str] = set()
        for packet in rows:
            strategy_fingerprint = self._strategy_fingerprint(packet)
            if not packet.selected_strategy or not packet.world_state_fingerprint or not packet.cycle_id:
                quarantine.add(strategy_fingerprint)
                continue
            previous = cycle_fingerprints.get(packet.cycle_id)
            if previous is not None and previous != packet.world_state_fingerprint:
                quarantine.add(strategy_fingerprint)
            cycle_fingerprints[packet.cycle_id] = packet.world_state_fingerprint
        return sorted(quarantine)

    def _memory_grading_drift(self, rows: list[DecisionPacket], grades: list[StrategyReplayGrade]) -> float:
        replay_scores = {row.strategy_fingerprint: float(row.risk_adjusted_return) for row in grades}
        live_scores: dict[str, list[float]] = {}
        for packet in rows:
            fingerprint = self._strategy_fingerprint(packet)
            evaluation = _safe_mapping(packet.evaluation)
            if str(evaluation.get("status", "")) != "graded":
                continue
            live_scores.setdefault(fingerprint, []).append(_safe_float(evaluation.get("risk_adjusted_score", 0.0), 0.0))
        drifts: list[float] = []
        for fingerprint, replay_score in replay_scores.items():
            if fingerprint not in live_scores:
                continue
            live_score = mean(live_scores[fingerprint]) if live_scores[fingerprint] else 0.0
            drifts.append(abs(replay_score - live_score))
        if not drifts:
            return 0.0
        return _clamp(mean(drifts), 0.0, 1.5)


class PromotionLadderEngine:
    """Hysteresis-aware promotion decisions with replay evidence gates."""

    _STAGE_ORDER: tuple[PromotionStage, ...] = (
        PromotionStage.OFFLINE_REPLAY,
        PromotionStage.WALK_FORWARD_VALIDATED,
        PromotionStage.SHADOW_READY,
        PromotionStage.PAPER_READY,
        PromotionStage.LIMITED_LIVE_READY,
        PromotionStage.SCALED_LIVE_CANDIDATE,
    )

    _BASE_CAPITAL_BY_STAGE: dict[PromotionStage, float] = {
        PromotionStage.OFFLINE_REPLAY: 0.0,
        PromotionStage.WALK_FORWARD_VALIDATED: 0.0,
        PromotionStage.SHADOW_READY: 0.0,
        PromotionStage.PAPER_READY: 0.02,
        PromotionStage.LIMITED_LIVE_READY: 0.08,
        PromotionStage.SCALED_LIVE_CANDIDATE: 0.18,
        # Legacy aliases retained for backward compatibility.
        PromotionStage.SANDBOX_SHADOW: 0.0,
        PromotionStage.SHADOW_LIVE: 0.02,
        PromotionStage.MICRO_CAPITAL_LIVE: 0.08,
        PromotionStage.SCALED_LIVE: 0.25,
        PromotionStage.CORE_LIVE: 0.50,
        PromotionStage.DEMOTION_WATCH: 0.02,
        PromotionStage.QUARANTINE: 0.0,
    }

    def __init__(
        self,
        *,
        min_replay_evidence: int = 12,
        min_regime_diversity: int = 2,
        min_shield_consistency: float = 0.55,
        promote_hysteresis: int = 3,
        demote_hysteresis: int = 2,
        history_window: int = 24,
    ) -> None:
        self.min_replay_evidence = max(1, int(min_replay_evidence))
        self.min_regime_diversity = max(1, int(min_regime_diversity))
        self.min_shield_consistency = _clamp(min_shield_consistency, 0.0, 1.0)
        self.promote_hysteresis = max(1, int(promote_hysteresis))
        self.demote_hysteresis = max(1, int(demote_hysteresis))
        self.history_window = max(4, int(history_window))

    def evaluate(
        self,
        *,
        latest_grades: Iterable[StrategyReplayGrade],
        history: Mapping[str, list[StrategyReplayGrade]] | None = None,
        previous_decisions: Mapping[str, PromotionDecision] | None = None,
        inconsistent_fingerprints: Iterable[str] = (),
    ) -> list[PromotionDecision]:
        latest_map = {row.strategy_fingerprint: row for row in latest_grades if row.strategy_fingerprint}
        historical = dict(history or {})
        previous = dict(previous_decisions or {})
        inconsistent = set(str(item) for item in inconsistent_fingerprints if str(item))
        keys = sorted(set(latest_map.keys()) | set(historical.keys()) | set(previous.keys()) | inconsistent)
        decisions: list[PromotionDecision] = []
        for fingerprint in keys:
            current = previous.get(
                fingerprint,
                PromotionDecision(
                    strategy_fingerprint=fingerprint,
                    current_stage=PromotionStage.SANDBOX_SHADOW,
                    next_stage_candidate=PromotionStage.SANDBOX_SHADOW,
                    promotion_confidence=0.0,
                    capital_scaling_factor=0.0,
                    required_observation_window=self.min_replay_evidence,
                    safety_override_flag=False,
                ),
            )
            history_rows = list(historical.get(fingerprint, []))[-self.history_window :]
            if fingerprint in latest_map:
                history_rows.append(latest_map[fingerprint])
            if not history_rows:
                decisions.append(
                    PromotionDecision(
                        strategy_fingerprint=fingerprint,
                        current_stage=current.current_stage,
                        next_stage_candidate=current.current_stage,
                        promotion_confidence=0.0,
                        capital_scaling_factor=0.0,
                        required_observation_window=self.min_replay_evidence,
                        safety_override_flag=True,
                        promotion_reason_codes=("insufficient_replay_history",),
                        demotion_reason_codes=(),
                        activation_recommendation="hold",
                    )
                )
                continue

            confidence = _clamp(mean(row.overall_grade for row in history_rows), 0.0, 1.0)
            evidence = sum(max(1, int(row.sample_count)) for row in history_rows)
            regime_diversity = max(int(row.regime_diversity_count) for row in history_rows)
            shield_consistency = _clamp(1.0 - mean(row.shield_penalty_score for row in history_rows), 0.0, 1.0)
            promote_threshold = self._promotion_threshold(current.current_stage)
            demote_threshold = self._demotion_threshold(current.current_stage)
            promote_streak = self._streak(history_rows, threshold=promote_threshold, promote=True)
            demote_streak = self._streak(history_rows, threshold=demote_threshold, promote=False)

            promote_ready = (
                evidence >= self.min_replay_evidence
                and regime_diversity >= self.min_regime_diversity
                and shield_consistency >= self.min_shield_consistency
                and confidence >= promote_threshold
                and promote_streak >= self.promote_hysteresis
            )
            demote_ready = (
                confidence <= demote_threshold
                or shield_consistency < self.min_shield_consistency * 0.70
                or demote_streak >= self.demote_hysteresis
            )

            if fingerprint in inconsistent:
                next_stage = PromotionStage.QUARANTINE
                action = "quarantine"
                safety_override = True
                promotion_reasons = ("memory_inconsistency_detected",)
                demotion_reasons = ("memory_inconsistency_detected",)
            elif demote_ready and confidence <= 0.15:
                next_stage = PromotionStage.QUARANTINE
                action = "quarantine"
                safety_override = True
                promotion_reasons = ()
                demotion_reasons = ("severe_replay_degradation",)
            elif demote_ready:
                next_stage = self._demoted_stage(current.current_stage)
                action = "demote"
                safety_override = True
                promotion_reasons = ()
                demotion_reasons = ("hysteresis_demotion_gate",)
            elif promote_ready:
                next_stage = self._promoted_stage(current.current_stage)
                action = "activate" if next_stage != current.current_stage else "hold"
                safety_override = False
                promotion_reasons = (
                    "evidence_threshold_satisfied",
                    "regime_diversity_satisfied",
                    "shield_consistency_satisfied",
                    "hysteresis_promotion_gate",
                )
                demotion_reasons = ()
            else:
                next_stage = current.current_stage
                action = "hold"
                safety_override = False
                promotion_reasons = ("awaiting_additional_evidence",)
                demotion_reasons = ()

            # Backward-compatible public stages for legacy callers/tests.
            current_public = self._to_legacy_stage(current.current_stage)
            next_public = self._to_legacy_stage(next_stage)

            capital = self._base_capital(next_public) * _clamp(0.40 + confidence, 0.0, 1.2)
            decisions.append(
                PromotionDecision(
                    strategy_fingerprint=fingerprint,
                    current_stage=current_public,
                    next_stage_candidate=next_public,
                    promotion_confidence=confidence,
                    capital_scaling_factor=_clamp(capital, 0.0, 1.0),
                    required_observation_window=self.min_replay_evidence,
                    safety_override_flag=safety_override,
                    promotion_reason_codes=tuple(promotion_reasons),
                    demotion_reason_codes=tuple(demotion_reasons),
                    activation_recommendation=action,
                    quarantine_recommendation=next_stage == PromotionStage.QUARANTINE,
                )
            )
        return sorted(decisions, key=lambda row: (row.promotion_confidence, row.strategy_fingerprint), reverse=True)

    def _base_capital(self, stage: PromotionStage | None) -> float:
        if stage is None:
            return 0.0
        return float(self._BASE_CAPITAL_BY_STAGE.get(stage, 0.0))

    def _promotion_threshold(self, stage: PromotionStage) -> float:
        thresholds = {
            PromotionStage.OFFLINE_REPLAY: 0.54,
            PromotionStage.WALK_FORWARD_VALIDATED: 0.58,
            PromotionStage.SHADOW_READY: 0.61,
            PromotionStage.PAPER_READY: 0.64,
            PromotionStage.LIMITED_LIVE_READY: 0.68,
            PromotionStage.SCALED_LIVE_CANDIDATE: 0.72,
            PromotionStage.SANDBOX_SHADOW: 0.56,
            PromotionStage.SHADOW_LIVE: 0.60,
            PromotionStage.MICRO_CAPITAL_LIVE: 0.64,
            PromotionStage.SCALED_LIVE: 0.69,
            PromotionStage.CORE_LIVE: 0.74,
            PromotionStage.DEMOTION_WATCH: 0.62,
            PromotionStage.QUARANTINE: 0.70,
        }
        return float(thresholds.get(stage, 0.60))

    def _demotion_threshold(self, stage: PromotionStage) -> float:
        thresholds = {
            PromotionStage.OFFLINE_REPLAY: 0.20,
            PromotionStage.WALK_FORWARD_VALIDATED: 0.22,
            PromotionStage.SHADOW_READY: 0.24,
            PromotionStage.PAPER_READY: 0.27,
            PromotionStage.LIMITED_LIVE_READY: 0.31,
            PromotionStage.SCALED_LIVE_CANDIDATE: 0.35,
            PromotionStage.SANDBOX_SHADOW: 0.22,
            PromotionStage.SHADOW_LIVE: 0.24,
            PromotionStage.MICRO_CAPITAL_LIVE: 0.28,
            PromotionStage.SCALED_LIVE: 0.32,
            PromotionStage.CORE_LIVE: 0.36,
            PromotionStage.DEMOTION_WATCH: 0.26,
            PromotionStage.QUARANTINE: 0.20,
        }
        return float(thresholds.get(stage, 0.30))

    def _streak(self, rows: list[StrategyReplayGrade], *, threshold: float, promote: bool) -> int:
        streak = 0
        for row in reversed(rows):
            condition = row.overall_grade >= threshold if promote else row.overall_grade <= threshold
            if not condition:
                break
            streak += 1
        return streak

    def _promoted_stage(self, stage: PromotionStage) -> PromotionStage:
        if stage in {PromotionStage.DEMOTION_WATCH, PromotionStage.QUARANTINE}:
            return PromotionStage.OFFLINE_REPLAY
        if stage == PromotionStage.SANDBOX_SHADOW:
            # Legacy bootstrap should advance to shadow validation in one step.
            return PromotionStage.SHADOW_READY
        if stage not in self._STAGE_ORDER:
            legacy_map = {
                PromotionStage.SHADOW_LIVE: PromotionStage.SHADOW_READY,
                PromotionStage.MICRO_CAPITAL_LIVE: PromotionStage.PAPER_READY,
                PromotionStage.SCALED_LIVE: PromotionStage.LIMITED_LIVE_READY,
                PromotionStage.CORE_LIVE: PromotionStage.SCALED_LIVE_CANDIDATE,
            }
            stage = legacy_map.get(stage, PromotionStage.OFFLINE_REPLAY)
        if stage not in self._STAGE_ORDER:
            return PromotionStage.OFFLINE_REPLAY
        idx = self._STAGE_ORDER.index(stage)
        if idx + 1 >= len(self._STAGE_ORDER):
            return stage
        return self._STAGE_ORDER[idx + 1]

    def _demoted_stage(self, stage: PromotionStage) -> PromotionStage:
        if stage in {PromotionStage.SCALED_LIVE_CANDIDATE, PromotionStage.CORE_LIVE}:
            return PromotionStage.LIMITED_LIVE_READY
        if stage in {PromotionStage.LIMITED_LIVE_READY, PromotionStage.SCALED_LIVE}:
            return PromotionStage.PAPER_READY
        if stage in {PromotionStage.PAPER_READY, PromotionStage.MICRO_CAPITAL_LIVE}:
            return PromotionStage.SHADOW_READY
        if stage in {PromotionStage.SHADOW_READY, PromotionStage.SHADOW_LIVE}:
            return PromotionStage.WALK_FORWARD_VALIDATED
        if stage in {PromotionStage.WALK_FORWARD_VALIDATED, PromotionStage.SANDBOX_SHADOW}:
            return PromotionStage.OFFLINE_REPLAY
        if stage == PromotionStage.OFFLINE_REPLAY:
            return PromotionStage.OFFLINE_REPLAY
        return PromotionStage.DEMOTION_WATCH

    def _to_legacy_stage(self, stage: PromotionStage) -> PromotionStage:
        mapping = {
            PromotionStage.OFFLINE_REPLAY: PromotionStage.SANDBOX_SHADOW,
            PromotionStage.WALK_FORWARD_VALIDATED: PromotionStage.SANDBOX_SHADOW,
            PromotionStage.SHADOW_READY: PromotionStage.SHADOW_LIVE,
            PromotionStage.PAPER_READY: PromotionStage.MICRO_CAPITAL_LIVE,
            PromotionStage.LIMITED_LIVE_READY: PromotionStage.SCALED_LIVE,
            PromotionStage.SCALED_LIVE_CANDIDATE: PromotionStage.CORE_LIVE,
        }
        return mapping.get(stage, stage)


class AdaptiveActivationGate:
    """Adaptive capital gates on top of promotion decisions."""

    _RISK_MULTIPLIER_BY_STAGE: dict[PromotionStage, float] = {
        PromotionStage.OFFLINE_REPLAY: 0.0,
        PromotionStage.WALK_FORWARD_VALIDATED: 0.0,
        PromotionStage.SHADOW_READY: 0.0,
        PromotionStage.PAPER_READY: 0.15,
        PromotionStage.LIMITED_LIVE_READY: 0.40,
        PromotionStage.SCALED_LIVE_CANDIDATE: 0.70,
        PromotionStage.SANDBOX_SHADOW: 0.0,
        PromotionStage.SHADOW_LIVE: 0.20,
        PromotionStage.MICRO_CAPITAL_LIVE: 0.45,
        PromotionStage.SCALED_LIVE: 0.75,
        PromotionStage.CORE_LIVE: 1.00,
        PromotionStage.DEMOTION_WATCH: 0.15,
        PromotionStage.QUARANTINE: 0.0,
    }
    _EXPOSURE_CEILING_BY_STAGE: dict[PromotionStage, float] = {
        PromotionStage.OFFLINE_REPLAY: 0.0,
        PromotionStage.WALK_FORWARD_VALIDATED: 0.0,
        PromotionStage.SHADOW_READY: 0.0,
        PromotionStage.PAPER_READY: 0.03,
        PromotionStage.LIMITED_LIVE_READY: 0.08,
        PromotionStage.SCALED_LIVE_CANDIDATE: 0.16,
        PromotionStage.SANDBOX_SHADOW: 0.0,
        PromotionStage.SHADOW_LIVE: 0.03,
        PromotionStage.MICRO_CAPITAL_LIVE: 0.08,
        PromotionStage.SCALED_LIVE: 0.18,
        PromotionStage.CORE_LIVE: 0.30,
        PromotionStage.DEMOTION_WATCH: 0.02,
        PromotionStage.QUARANTINE: 0.0,
    }

    def __init__(
        self,
        *,
        infra_health_floor: float = 0.60,
        execution_stress_ceiling: float = 0.70,
        liquidity_stress_ceiling: float = 0.65,
        correlation_spike_ceiling: float = 0.75,
        concentration_ceiling: float = 0.70,
        divergence_kill_switch: float = 0.80,
    ) -> None:
        self.infra_health_floor = _clamp(infra_health_floor, 0.0, 1.0)
        self.execution_stress_ceiling = _clamp(execution_stress_ceiling, 0.0, 1.0)
        self.liquidity_stress_ceiling = _clamp(liquidity_stress_ceiling, 0.0, 1.0)
        self.correlation_spike_ceiling = _clamp(correlation_spike_ceiling, 0.0, 2.0)
        self.concentration_ceiling = _clamp(concentration_ceiling, 0.0, 1.0)
        self.divergence_kill_switch = _clamp(divergence_kill_switch, 0.0, 2.0)

    def apply(
        self,
        *,
        decisions: Iterable[PromotionDecision],
        world: WorldStateSnapshot,
        replay_live_divergence: float,
    ) -> list[ActivationGateDecision]:
        infra_health = _clamp(float(world.infra_state.health_score), 0.0, 1.0)
        execution_stress = _clamp(float(world.execution_state.execution_stress), 0.0, 1.0)
        liquidity_stress = self._liquidity_stress(world)
        correlation_spike = _clamp(float(world.venue_state.cross_venue_divergence_bps) / 100.0, 0.0, 2.0)
        concentration = _clamp(float(world.portfolio_state.concentration_score), 0.0, 1.0)
        divergence = _clamp(float(replay_live_divergence), 0.0, 2.0)
        kill_switch = (
            infra_health < self.infra_health_floor
            or execution_stress > self.execution_stress_ceiling
            or liquidity_stress > self.liquidity_stress_ceiling
            or correlation_spike > self.correlation_spike_ceiling
            or concentration > self.concentration_ceiling
            or divergence > self.divergence_kill_switch
        )
        shared_reasons: list[str] = []
        if infra_health < self.infra_health_floor:
            shared_reasons.append("infra_health_degraded")
        if execution_stress > self.execution_stress_ceiling:
            shared_reasons.append("execution_degradation")
        if liquidity_stress > self.liquidity_stress_ceiling:
            shared_reasons.append("liquidity_stress")
        if correlation_spike > self.correlation_spike_ceiling:
            shared_reasons.append("cross_asset_correlation_spike")
        if concentration > self.concentration_ceiling:
            shared_reasons.append("portfolio_concentration")
        if divergence > self.divergence_kill_switch:
            shared_reasons.append("replay_live_divergence")

        out: list[ActivationGateDecision] = []
        for decision in decisions:
            target_stage = decision.next_stage_candidate or decision.current_stage
            if kill_switch:
                resolved_stage = PromotionStage.SANDBOX_SHADOW
                risk_multiplier = 0.0
                exposure = 0.0
                capital = 0.0
                allowed = False
                reasons = tuple(shared_reasons + ["hard_kill_switch"])
            elif target_stage == PromotionStage.QUARANTINE:
                resolved_stage = PromotionStage.QUARANTINE
                risk_multiplier = 0.0
                exposure = 0.0
                capital = 0.0
                allowed = False
                reasons = tuple(["strategy_quarantined"])
            else:
                resolved_stage = target_stage
                risk_multiplier = float(self._RISK_MULTIPLIER_BY_STAGE.get(resolved_stage, 0.0))
                exposure = float(self._EXPOSURE_CEILING_BY_STAGE.get(resolved_stage, 0.0))
                capital = _clamp(float(decision.capital_scaling_factor) * risk_multiplier, 0.0, 1.0)
                allowed = capital > 0.0 and not decision.safety_override_flag
                reasons = tuple(shared_reasons + (["safety_override_blocked"] if decision.safety_override_flag else []))
            out.append(
                ActivationGateDecision(
                    strategy_fingerprint=decision.strategy_fingerprint,
                    allowed=allowed,
                    resolved_stage=resolved_stage,
                    capital_scaling_factor=capital,
                    per_strategy_exposure_ceiling=exposure,
                    risk_multiplier=risk_multiplier,
                    kill_switch=kill_switch,
                    reason_codes=reasons,
                )
            )
        return sorted(out, key=lambda row: row.strategy_fingerprint)

    def _liquidity_stress(self, world: WorldStateSnapshot) -> float:
        regime = str(world.market_state.liquidity_regime or "NORMAL").upper()
        spread = _safe_float(world.market_state.spread_bps, 0.0)
        depth = _safe_float(world.market_state.depth_notional, 0.0)
        base = 0.0
        if regime == "THIN":
            base += 0.60
        elif regime == "NORMAL":
            base += 0.30
        base += _clamp(spread / 80.0, 0.0, 1.0) * 0.30
        if depth <= 1_000.0:
            base += 0.20
        return _clamp(base, 0.0, 1.5)
