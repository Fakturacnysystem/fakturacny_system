from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping

from .capital_survival_doctrine import SurvivalDoctrineDecision
from .evolutionary_strategy_research import EvolutionaryResearchState


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommitteeVoteTrace:
    committee: str
    vote: str
    confidence: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "committee": self.committee,
            "vote": self.vote,
            "confidence": float(self.confidence),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class InternalDisagreementMap:
    severity: float
    disagreements: list[dict[str, Any]] = field(default_factory=list)
    vetoes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": float(self.severity),
            "disagreements": [dict(row) for row in self.disagreements],
            "vetoes": [str(item) for item in self.vetoes],
        }


@dataclass(frozen=True)
class CapitalAllocationDecision:
    target_gross_exposure: float
    target_cash_reserve: float
    hedge_ratio: float
    confidence: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_gross_exposure": float(self.target_gross_exposure),
            "target_cash_reserve": float(self.target_cash_reserve),
            "hedge_ratio": float(self.hedge_ratio),
            "confidence": float(self.confidence),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class CommitteeDecisionBundle:
    bundle_id: str
    research_vote: CommitteeVoteTrace
    risk_vote: CommitteeVoteTrace
    execution_vote: CommitteeVoteTrace
    portfolio_vote: CommitteeVoteTrace
    capital_allocation: CapitalAllocationDecision
    disagreement_map: InternalDisagreementMap
    safety_veto: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "research_vote": self.research_vote.to_dict(),
            "risk_vote": self.risk_vote.to_dict(),
            "execution_vote": self.execution_vote.to_dict(),
            "portfolio_vote": self.portfolio_vote.to_dict(),
            "capital_allocation": self.capital_allocation.to_dict(),
            "disagreement_map": self.disagreement_map.to_dict(),
            "safety_veto": bool(self.safety_veto),
        }


@dataclass(frozen=True)
class FundBrainRecommendation:
    recommendation_id: str
    approved: bool
    mode: str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    bundle: CommitteeDecisionBundle | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "approved": bool(self.approved),
            "mode": self.mode,
            "reason_codes": [str(item) for item in self.reason_codes],
            "bundle": self.bundle.to_dict() if self.bundle is not None else None,
        }


class AutonomousFundBrain:
    """Phase 34 committee-style recommendation layer with explicit disagreement/veto."""

    def recommend(
        self,
        *,
        cycle_id: str,
        research: EvolutionaryResearchState,
        survival: SurvivalDoctrineDecision,
        execution_quality_score: float,
    ) -> FundBrainRecommendation:
        research_vote = CommitteeVoteTrace(
            committee="research",
            vote="approve" if research.promotion_gate.eligible else "hold",
            confidence=_clamp(research.fitness.score, 0.0, 1.0),
            reason_codes=tuple(research.promotion_gate.reason_codes),
        )
        risk_vote = CommitteeVoteTrace(
            committee="risk",
            vote="veto" if survival.safety_veto else "approve",
            confidence=_clamp(survival.existential_risk.score, 0.0, 1.0),
            reason_codes=tuple(survival.reason_codes),
        )
        execution_vote = CommitteeVoteTrace(
            committee="execution",
            vote="approve" if _safe_float(execution_quality_score, 0.0) >= 0.50 else "hold",
            confidence=_clamp(_safe_float(execution_quality_score, 0.0), 0.0, 1.0),
            reason_codes=tuple(["execution_quality_check"]),
        )
        portfolio_vote = CommitteeVoteTrace(
            committee="portfolio",
            vote="defensive" if survival.recommendation_mode in {"survival", "defensive"} else "balanced",
            confidence=_clamp(1.0 - survival.existential_risk.score * 0.50, 0.0, 1.0),
            reason_codes=tuple(["capital_preservation_priority"]),
        )
        allocation = CapitalAllocationDecision(
            target_gross_exposure=0.10 if survival.recommendation_mode == "survival" else 0.35 if survival.recommendation_mode == "defensive" else 0.65,
            target_cash_reserve=_clamp(survival.capital_bunker.cash_reserve_ratio, 0.0, 1.0),
            hedge_ratio=_clamp(survival.capital_bunker.hedge_ratio, 0.0, 1.0),
            confidence=_clamp((research.fitness.score + (1.0 - survival.existential_risk.score)) / 2.0, 0.0, 1.0),
            reason_codes=tuple(["committee_allocation_consensus"]),
        )
        disagreements: list[dict[str, Any]] = []
        vetoes: list[str] = []
        if risk_vote.vote == "veto":
            vetoes.append("risk_committee_veto")
        if research_vote.vote == "approve" and risk_vote.vote == "veto":
            disagreements.append({"between": ["research", "risk"], "reason": "alpha_vs_survival"})
        elif risk_vote.vote == "veto":
            disagreements.append({"between": ["risk", "portfolio"], "reason": "survival_override"})
        if execution_vote.vote == "hold" and research_vote.vote == "approve":
            disagreements.append({"between": ["execution", "research"], "reason": "execution_quality_mismatch"})
        severity = _clamp(len(disagreements) * 0.45 + (1.0 if vetoes else 0.0) * 0.35, 0.0, 1.0)
        disagreement_map = InternalDisagreementMap(
            severity=severity,
            disagreements=disagreements,
            vetoes=vetoes,
        )
        bundle = CommitteeDecisionBundle(
            bundle_id=_stable_hash({"phase": 34, "cycle_id": cycle_id, "research": research_vote.vote, "risk": risk_vote.vote})[:16],
            research_vote=research_vote,
            risk_vote=risk_vote,
            execution_vote=execution_vote,
            portfolio_vote=portfolio_vote,
            capital_allocation=allocation,
            disagreement_map=disagreement_map,
            safety_veto=bool(vetoes),
        )
        approved = bool(
            not bundle.safety_veto
            and research_vote.vote == "approve"
            and execution_vote.vote != "hold"
        )
        mode = "blocked" if bundle.safety_veto else "recommend" if approved else "hold"
        reasons = list(vetoes)
        if not approved and not vetoes:
            reasons.append("committee_consensus_not_reached")
        return FundBrainRecommendation(
            recommendation_id=_stable_hash({"phase": 34, "bundle_id": bundle.bundle_id, "mode": mode})[:16],
            approved=approved,
            mode=mode,
            reason_codes=tuple(reasons),
            bundle=bundle,
        )
