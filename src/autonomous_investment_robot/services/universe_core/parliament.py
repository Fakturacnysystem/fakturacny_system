from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping

from .mission import MissionDecision
from .state import WorldStateSnapshot


PARLIAMENT_MODE_TOP_1 = "top_1"
PARLIAMENT_MODE_TOP_N = "top_n"
PARLIAMENT_MODE_NO_TRADE = "no_trade"
_VALID_PARLIAMENT_MODES = {
    PARLIAMENT_MODE_TOP_1,
    PARLIAMENT_MODE_TOP_N,
    PARLIAMENT_MODE_NO_TRADE,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _normalize_side(value: str) -> str:
    side = str(value or "flat").strip().lower()
    if side in {"buy", "sell", "flat"}:
        return side
    return "flat"


def _normalize_mode(value: Any) -> str:
    mode = str(value or PARLIAMENT_MODE_TOP_1).strip().lower()
    if mode not in _VALID_PARLIAMENT_MODES:
        return PARLIAMENT_MODE_TOP_1
    return mode


@dataclass(frozen=True)
class StrategyProposal:
    strategy: str
    instrument: str
    action: str
    side: str
    target_notional_quote: float
    expected_value_bps: float
    confidence: float
    expected_hold_time_s: float
    execution_sensitivity: float
    slippage_risk_bps: float
    regime_compatibility: float
    risk_cost_bps: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    mission_compatibility: float = 1.0
    source: str = "strategy"
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_group: str = ""
    robustness_score: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy", str(self.strategy or "unknown_strategy"))
        object.__setattr__(self, "instrument", str(self.instrument or "UNKNOWN"))
        object.__setattr__(self, "action", str(self.action or "trade"))
        object.__setattr__(self, "side", _normalize_side(self.side))
        object.__setattr__(self, "target_notional_quote", max(0.0, _safe_float(self.target_notional_quote, 0.0)))
        object.__setattr__(self, "expected_value_bps", _safe_float(self.expected_value_bps, 0.0))
        object.__setattr__(self, "confidence", _clamp(_safe_float(self.confidence, 0.0), 0.0, 1.0))
        object.__setattr__(self, "expected_hold_time_s", max(1.0, _safe_float(self.expected_hold_time_s, 60.0)))
        object.__setattr__(self, "execution_sensitivity", _clamp(_safe_float(self.execution_sensitivity, 0.0), 0.0, 2.0))
        object.__setattr__(self, "slippage_risk_bps", max(0.0, _safe_float(self.slippage_risk_bps, 0.0)))
        object.__setattr__(self, "regime_compatibility", _clamp(_safe_float(self.regime_compatibility, 1.0), 0.0, 1.0))
        object.__setattr__(self, "risk_cost_bps", max(0.0, _safe_float(self.risk_cost_bps, 0.0)))
        object.__setattr__(self, "reason_codes", tuple(str(code) for code in self.reason_codes))
        object.__setattr__(self, "mission_compatibility", _clamp(_safe_float(self.mission_compatibility, 1.0), 0.0, 1.0))
        object.__setattr__(self, "source", str(self.source or "strategy"))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        object.__setattr__(self, "correlation_group", str(self.correlation_group or ""))
        object.__setattr__(self, "robustness_score", _clamp(_safe_float(self.robustness_score, 1.0), 0.0, 2.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "instrument": self.instrument,
            "action": self.action,
            "side": self.side,
            "target_notional_quote": float(self.target_notional_quote),
            "expected_value_bps": float(self.expected_value_bps),
            "confidence": float(self.confidence),
            "expected_hold_time_s": float(self.expected_hold_time_s),
            "execution_sensitivity": float(self.execution_sensitivity),
            "slippage_risk_bps": float(self.slippage_risk_bps),
            "regime_compatibility": float(self.regime_compatibility),
            "risk_cost_bps": float(self.risk_cost_bps),
            "reason_codes": list(self.reason_codes),
            "mission_compatibility": float(self.mission_compatibility),
            "source": self.source,
            "metadata": dict(self.metadata),
            "correlation_group": self.correlation_group,
            "robustness_score": float(self.robustness_score),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "StrategyProposal":
        return cls(
            strategy=str(payload.get("strategy", payload.get("strategy_name", "unknown_strategy"))),
            instrument=str(payload.get("instrument", payload.get("symbol", "UNKNOWN"))),
            action=str(payload.get("action", "trade")),
            side=str(payload.get("side", "flat")),
            target_notional_quote=_safe_float(payload.get("target_notional_quote", payload.get("notional_quote", 0.0)), 0.0),
            expected_value_bps=_safe_float(payload.get("expected_value_bps", payload.get("expected_edge_bps", 0.0)), 0.0),
            confidence=_safe_float(payload.get("confidence", 0.0), 0.0),
            expected_hold_time_s=_safe_float(payload.get("expected_hold_time_s", payload.get("hold_time_s", 60.0)), 60.0),
            execution_sensitivity=_safe_float(payload.get("execution_sensitivity", 0.0), 0.0),
            slippage_risk_bps=_safe_float(payload.get("slippage_risk_bps", payload.get("slippage_bps", 0.0)), 0.0),
            regime_compatibility=_safe_float(payload.get("regime_compatibility", payload.get("regime_fit", 1.0)), 1.0),
            risk_cost_bps=_safe_float(payload.get("risk_cost_bps", payload.get("cost_total_bps", 0.0)), 0.0),
            reason_codes=tuple(str(code) for code in payload.get("reason_codes", []) if str(code)),
            mission_compatibility=_safe_float(payload.get("mission_compatibility", 1.0), 1.0),
            source=str(payload.get("source", "strategy")),
            metadata=dict(payload.get("metadata", {}) or {}),
            correlation_group=str(payload.get("correlation_group", "")),
            robustness_score=_safe_float(payload.get("robustness_score", 1.0), 1.0),
        )


# Backward-compatibility alias referenced by existing imports.
StrategyProposalContract = StrategyProposal


@dataclass(frozen=True)
class RankedProposal:
    proposal: StrategyProposal
    score: float
    diagnostics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal": self.proposal.to_dict(),
            "score": float(self.score),
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(frozen=True)
class ParliamentAllocation:
    strategy: str
    side: str
    score: float
    weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "side": self.side,
            "score": float(self.score),
            "weight": float(self.weight),
        }


@dataclass(frozen=True)
class ParliamentVerdict:
    selected: StrategyProposal
    ranking: list[RankedProposal]
    allocations: list[ParliamentAllocation]
    selection_mode: str
    no_trade: bool
    reasons: list[str]
    selected_top: list[StrategyProposal] = field(default_factory=list)
    diagnostics: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "selection_mode", _normalize_mode(self.selection_mode))
        object.__setattr__(self, "reasons", [str(reason) for reason in self.reasons])
        if not self.selected_top:
            object.__setattr__(self, "selected_top", [self.selected] if not self.no_trade else [])

    def to_dict(self) -> dict[str, Any]:
        selected_top = [row.to_dict() for row in self.selected_top]
        selected_strategies = [row.strategy for row in self.selected_top]
        return {
            "selected": self.selected.to_dict(),
            "selected_top": selected_top,
            "selected_strategies": selected_strategies,
            "ranking": [row.to_dict() for row in self.ranking],
            "allocations": [row.to_dict() for row in self.allocations],
            "selection_mode": self.selection_mode,
            "mode": self.selection_mode,
            "no_trade": bool(self.no_trade),
            "reasons": list(self.reasons),
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(frozen=True)
class StrategyMetaState:
    active_strategy: str = ""
    strategy_confidence: float = 0.0
    allocation_mode: str = ""
    parliament_timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_strategy": self.active_strategy,
            "strategy_confidence": self.strategy_confidence,
            "allocation_mode": self.allocation_mode,
            "parliament_timestamp": self.parliament_timestamp,
        }


def no_trade_guardian(symbol: str, *, reason: str = "no_edge") -> StrategyProposal:
    return StrategyProposal(
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
        reason_codes=(str(reason or "no_edge"),),
        mission_compatibility=1.0,
        source="guardian",
        metadata={"family": "guardian"},
        robustness_score=1.0,
    )


class StrategyParliament:
    MIN_SCORE = 0.50
    MAX_SELECTED = 3

    def __init__(self, *, min_score: float = MIN_SCORE, max_selected: int = MAX_SELECTED) -> None:
        self.min_score = max(0.0, float(min_score))
        self.max_selected = max(1, int(max_selected))

    def judge(
        self,
        proposals: Iterable[StrategyProposal],
        *,
        world: WorldStateSnapshot,
        mission: MissionDecision,
        selection_mode: str = PARLIAMENT_MODE_TOP_1,
        top_n: int = 2,
        score_floor: float | None = None,
    ) -> ParliamentVerdict:
        mode = _normalize_mode(selection_mode)
        symbol = str(world.market_state.primary_symbol or world.asset_state.primary_symbol or "UNKNOWN")
        rows = [proposal if isinstance(proposal, StrategyProposal) else StrategyProposal.from_mapping(proposal) for proposal in proposals]
        if not rows:
            rows = [no_trade_guardian(symbol, reason="no_proposals")]
        if not any(row.strategy == "no_trade_guardian" for row in rows):
            rows.append(no_trade_guardian(symbol))

        if mode == PARLIAMENT_MODE_NO_TRADE or mission.mission == "observation_only":
            guardian = no_trade_guardian(symbol, reason="mission_observation_only")
            ranking = [RankedProposal(proposal=guardian, score=0.0, diagnostics={"blocked": 1.0})]
            return ParliamentVerdict(
                selected=guardian,
                selected_top=[],
                ranking=ranking,
                allocations=[],
                selection_mode=PARLIAMENT_MODE_NO_TRADE,
                no_trade=True,
                reasons=["mission_observation_only"],
                diagnostics={"best_score": 0.0, "selected_count": 0.0},
            )

        group_counts = Counter(
            str(row.correlation_group or "").strip().lower()
            for row in rows
            if row.strategy != "no_trade_guardian" and str(row.correlation_group or "").strip()
        )
        side_counts = Counter(row.side for row in rows if row.strategy != "no_trade_guardian" and row.side in {"buy", "sell"})

        ranked: list[RankedProposal] = []
        for row in rows:
            score, diagnostics = self._score(row, world=world, mission=mission)
            group = str(row.correlation_group or "").strip().lower()
            if group and group_counts.get(group, 0) > 1:
                corr_penalty = min(0.30, 0.10 * float(group_counts[group] - 1))
                score *= (1.0 - corr_penalty)
                diagnostics["correlation_penalty"] = corr_penalty
            if row.side in {"buy", "sell"} and side_counts.get(row.side, 0) > 2:
                crowd_penalty = min(0.20, 0.05 * float(side_counts[row.side] - 2))
                score *= (1.0 - crowd_penalty)
                diagnostics["directional_crowding_penalty"] = crowd_penalty
            diagnostics["composite_score"] = max(0.0, score)
            ranked.append(RankedProposal(proposal=row, score=max(0.0, score), diagnostics=diagnostics))

        ranked.sort(
            key=lambda item: (
                -float(item.score),
                item.proposal.strategy,
                item.proposal.side,
                item.proposal.instrument,
            )
        )

        score_threshold = self.min_score if score_floor is None else max(0.0, float(score_floor))
        eligible = [
            row
            for row in ranked
            if row.score > score_threshold and row.proposal.strategy != "no_trade_guardian"
        ]
        if not eligible:
            guardian = no_trade_guardian(symbol, reason="no_positive_edge")
            return ParliamentVerdict(
                selected=guardian,
                selected_top=[],
                ranking=ranked,
                allocations=[],
                selection_mode=PARLIAMENT_MODE_NO_TRADE,
                no_trade=True,
                reasons=["no_positive_edge"],
                diagnostics={
                    "best_score": float(ranked[0].score) if ranked else 0.0,
                    "score_floor": float(score_threshold),
                    "selected_count": 0.0,
                },
            )

        top_limit = 1 if mode == PARLIAMENT_MODE_TOP_1 else max(1, min(int(top_n), self.max_selected))
        selected_ranked = eligible[:top_limit]
        selected_top = [row.proposal for row in selected_ranked]
        allocations = self._allocate(selected_ranked)
        selected = selected_top[0]
        final_mode = PARLIAMENT_MODE_TOP_N if len(selected_top) > 1 else PARLIAMENT_MODE_TOP_1
        return ParliamentVerdict(
            selected=selected,
            selected_top=selected_top,
            ranking=ranked,
            allocations=allocations,
            selection_mode=final_mode,
            no_trade=False,
            reasons=["selected_best", f"mode:{final_mode}"],
            diagnostics={
                "best_score": float(selected_ranked[0].score),
                "score_floor": float(score_threshold),
                "selected_count": float(len(selected_top)),
            },
        )

    def _score(
        self,
        proposal: StrategyProposal,
        *,
        world: WorldStateSnapshot,
        mission: MissionDecision,
    ) -> tuple[float, dict[str, float]]:
        expected_edge = max(0.0, float(proposal.expected_value_bps))
        confidence = _clamp(float(proposal.confidence), 0.0, 1.0)
        regime_fit = _clamp(float(proposal.regime_compatibility), 0.0, 1.0)
        mission_fit = _clamp(float(proposal.mission_compatibility), 0.0, 1.0)
        robustness = _clamp(float(proposal.robustness_score), 0.0, 2.0)
        reward = expected_edge * confidence * max(0.30, regime_fit) * max(0.20, mission_fit) * max(0.25, robustness)

        execution_drag = float(proposal.execution_sensitivity) * float(world.execution_state.execution_stress) * 4.0
        slippage_drag = float(proposal.slippage_risk_bps) * (1.0 + float(world.execution_state.execution_stress) * 0.70)
        risk_drag = float(proposal.risk_cost_bps) + float(world.portfolio_state.own_account_stress) * 2.0
        telemetry_drag = float(world.infra_state.system_health_stress) * 1.5
        mission_penalty = max(0.0, 1.0 - mission_fit)
        base = reward - execution_drag - slippage_drag - risk_drag - telemetry_drag
        base *= max(0.0, 1.0 - mission_penalty * 0.40)

        if not mission.allow_new_risk and proposal.side == "buy":
            base *= 0.25
        if mission.no_trade_preferred and proposal.strategy != "no_trade_guardian":
            base *= 0.60
        if world.risk_state.observe_only and proposal.side == "buy":
            base *= 0.30
        if mission.aggressiveness_tier in {"high", "aggressive_if_quality"}:
            base *= 1.10
        elif mission.aggressiveness_tier in {"none", "very_low", "low"}:
            base *= 0.90
        base *= _clamp(float(mission.size_scale), 0.0, 1.25)

        diagnostics = {
            "reward": reward,
            "execution_drag": execution_drag,
            "slippage_drag": slippage_drag,
            "risk_drag": risk_drag,
            "telemetry_drag": telemetry_drag,
            "mission_penalty": mission_penalty,
        }
        return max(0.0, base), diagnostics

    def _allocate(self, ranked: list[RankedProposal]) -> list[ParliamentAllocation]:
        if not ranked:
            return []
        raw_scores = [max(0.0, float(row.score)) for row in ranked]
        total = sum(raw_scores)
        if total <= 0.0:
            equal = 1.0 / float(len(ranked))
            return [
                ParliamentAllocation(
                    strategy=row.proposal.strategy,
                    side=row.proposal.side,
                    score=float(row.score),
                    weight=equal,
                )
                for row in ranked
            ]
        return [
            ParliamentAllocation(
                strategy=row.proposal.strategy,
                side=row.proposal.side,
                score=float(row.score),
                weight=float(max(0.0, row.score) / total),
            )
            for row in ranked
        ]


def _stable_unit_interval(seed_payload: Mapping[str, Any]) -> float:
    raw = json.dumps(dict(seed_payload), sort_keys=True, default=str, separators=(",", ":"))
    return float(sha256(raw.encode("utf-8")).digest()[0]) / 255.0


def strategy_proposals_from_intent(intent: Any, *, mission: str = "") -> list[StrategyProposal]:
    symbol = str(getattr(intent, "symbol", "UNKNOWN") or "UNKNOWN")
    default_side = _normalize_side(str(getattr(intent, "side", "flat") or "flat"))
    default_notional = max(0.0, _safe_float(getattr(intent, "target_notional", 0.0), 0.0))
    why = getattr(intent, "why", {})
    payload = dict(why or {}) if isinstance(why, Mapping) else {}
    raw_components = payload.get("components", [])
    rows: list[StrategyProposal] = []
    if isinstance(raw_components, list):
        for idx, component in enumerate(raw_components):
            if not isinstance(component, Mapping):
                continue
            signal_notional = _safe_float(component.get("signal_notional", default_notional), default_notional)
            comp_side = _normalize_side(str(component.get("signal_side", default_side) or default_side))
            strategy = str(component.get("strategy", "") or f"component_{idx+1}")
            expected_edge = _safe_float(component.get("final_edge_bps", component.get("expected_edge_bps", 0.0)), 0.0)
            confidence = _safe_float(component.get("confidence", 0.5), 0.5)
            execution_sensitivity = _safe_float(component.get("execution_sensitivity", 0.4), 0.4)
            slippage_risk = _safe_float(component.get("slippage_risk_bps", component.get("impact_bps", 0.0)), 0.0)
            regime_fit = _safe_float(component.get("regime_fit", 1.0), 1.0)
            risk_cost = _safe_float(component.get("cost_total_bps", 0.0), 0.0)
            hold_time = _safe_float(component.get("expected_hold_time_s", 45.0), 45.0)
            reason_codes = component.get("reason_codes", [])
            if not isinstance(reason_codes, list):
                reason_codes = []
            rows.append(
                StrategyProposal(
                    strategy=strategy,
                    instrument=symbol,
                    action="trade" if comp_side in {"buy", "sell"} else "hold",
                    side=comp_side,
                    target_notional_quote=abs(signal_notional),
                    expected_value_bps=expected_edge,
                    confidence=confidence,
                    expected_hold_time_s=hold_time,
                    execution_sensitivity=execution_sensitivity,
                    slippage_risk_bps=slippage_risk,
                    regime_compatibility=regime_fit,
                    risk_cost_bps=risk_cost,
                    reason_codes=tuple(str(code) for code in reason_codes if str(code)),
                    mission_compatibility=1.0,
                    source="intent_component",
                    metadata={
                        "component_index": idx,
                        "mission_preview": str(mission or ""),
                        "signal_notional": signal_notional,
                        "allocator_weight_hint": _stable_unit_interval(
                            {
                                "symbol": symbol,
                                "strategy": strategy,
                                "mission": mission,
                                "component_index": idx,
                            }
                        ),
                    },
                    correlation_group=str(component.get("correlation_group", component.get("family", "")) or ""),
                    robustness_score=_safe_float(component.get("robustness_score", 1.0), 1.0),
                )
            )

    if not rows and default_side in {"buy", "sell"} and default_notional > 0.0:
        rows.append(
            StrategyProposal(
                strategy="intent_primary",
                instrument=symbol,
                action="trade",
                side=default_side,
                target_notional_quote=default_notional,
                expected_value_bps=_safe_float(payload.get("edge_bps", 0.0), 0.0),
                confidence=_safe_float(payload.get("confidence", 0.5), 0.5),
                expected_hold_time_s=_safe_float(payload.get("expected_hold_time_s", 45.0), 45.0),
                execution_sensitivity=_safe_float(payload.get("execution_sensitivity", 0.4), 0.4),
                slippage_risk_bps=_safe_float(payload.get("slippage_risk_bps", 0.0), 0.0),
                regime_compatibility=_safe_float(payload.get("regime_fit", 1.0), 1.0),
                risk_cost_bps=_safe_float(payload.get("cost_total_bps", 0.0), 0.0),
                reason_codes=("intent_fallback",),
                mission_compatibility=1.0,
                source="intent_fallback",
                metadata={"mission_preview": str(mission or "")},
            )
        )

    if not any(row.strategy == "no_trade_guardian" for row in rows):
        rows.append(no_trade_guardian(symbol))
    return rows

