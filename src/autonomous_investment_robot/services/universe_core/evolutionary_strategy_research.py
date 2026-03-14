from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping

from .memory import PromotionEvidenceBundle, PromotionGateDecision, ReplayPromotionCandidate


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
class StrategyGenome:
    genome_id: str
    strategy: str
    parent_genome_id: str
    parameters: dict[str, float] = field(default_factory=dict)
    mutation_seed: int = 0
    offline_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "genome_id": self.genome_id,
            "strategy": self.strategy,
            "parent_genome_id": self.parent_genome_id,
            "parameters": {str(k): float(v) for k, v in dict(self.parameters).items()},
            "mutation_seed": int(self.mutation_seed),
            "offline_only": bool(self.offline_only),
        }


@dataclass(frozen=True)
class MutationCandidate:
    mutation_id: str
    genome: StrategyGenome
    expected_impact: float
    risk_penalty: float
    seed: int
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutation_id": self.mutation_id,
            "genome": self.genome.to_dict(),
            "expected_impact": float(self.expected_impact),
            "risk_penalty": float(self.risk_penalty),
            "seed": int(self.seed),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class FitnessScore:
    genome_id: str
    score: float
    stability: float
    drawdown_penalty: float
    evidence_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "genome_id": self.genome_id,
            "score": float(self.score),
            "stability": float(self.stability),
            "drawdown_penalty": float(self.drawdown_penalty),
            "evidence_count": int(self.evidence_count),
        }


@dataclass(frozen=True)
class ExtinctionDecision:
    extinct: bool
    genome_id: str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "extinct": bool(self.extinct),
            "genome_id": self.genome_id,
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class ResearchSafetyEnvelope:
    offline_only: bool
    live_promotion_allowed: bool
    deterministic_seeded: bool
    promotion_evidence_required: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "offline_only": bool(self.offline_only),
            "live_promotion_allowed": bool(self.live_promotion_allowed),
            "deterministic_seeded": bool(self.deterministic_seeded),
            "promotion_evidence_required": bool(self.promotion_evidence_required),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class EvolutionaryResearchState:
    genome: StrategyGenome
    mutation: MutationCandidate
    fitness: FitnessScore
    promotion_gate: PromotionGateDecision
    extinction: ExtinctionDecision
    safety_envelope: ResearchSafetyEnvelope

    def to_dict(self) -> dict[str, Any]:
        return {
            "genome": self.genome.to_dict(),
            "mutation": self.mutation.to_dict(),
            "fitness": self.fitness.to_dict(),
            "promotion_gate": self.promotion_gate.to_dict(),
            "extinction": self.extinction.to_dict(),
            "safety_envelope": self.safety_envelope.to_dict(),
        }


class EvolutionaryStrategyResearchLayer:
    """Phase 33 offline-only deterministic mutation/evaluation scaffold."""

    def evolve(
        self,
        *,
        cycle_id: str,
        selected_strategy: str,
        performance_samples: Iterable[Mapping[str, Any]] = (),
    ) -> EvolutionaryResearchState:
        strategy = str(selected_strategy or "no_trade_guardian")
        seed = int(_stable_hash({"phase": 33, "cycle_id": cycle_id, "strategy": strategy})[:10], 16)
        base_params = {"entry_threshold": 0.50, "exit_threshold": 0.55, "risk_scale": 0.40}
        jitter = ((seed % 101) - 50) / 1_000.0
        parameters = {
            "entry_threshold": _clamp(base_params["entry_threshold"] + jitter, 0.05, 0.95),
            "exit_threshold": _clamp(base_params["exit_threshold"] + jitter * 0.80, 0.05, 0.95),
            "risk_scale": _clamp(base_params["risk_scale"] + jitter * 1.20, 0.01, 1.0),
        }
        genome = StrategyGenome(
            genome_id=_stable_hash({"phase": 33, "cycle_id": cycle_id, "strategy": strategy})[:16],
            strategy=strategy,
            parent_genome_id="",
            parameters=parameters,
            mutation_seed=seed,
            offline_only=True,
        )
        mutation = MutationCandidate(
            mutation_id=_stable_hash({"phase": 33, "genome": genome.genome_id})[:16],
            genome=genome,
            expected_impact=_clamp(0.50 + jitter * 4.0, 0.0, 1.0),
            risk_penalty=_clamp(abs(jitter) * 3.0, 0.0, 1.0),
            seed=seed,
            reason_codes=tuple(["deterministic_mutation_seed"]),
        )
        rows = [dict(item) for item in performance_samples if isinstance(item, Mapping)]
        evidence_count = len(rows)
        if rows:
            avg_grade = sum(_safe_float(row.get("overall_grade", 0.0), 0.0) for row in rows) / max(len(rows), 1)
            stability = sum(_safe_float(row.get("stability_score", 0.0), 0.0) for row in rows) / max(len(rows), 1)
            drawdown_penalty = _clamp(
                sum(_safe_float(row.get("drawdown_severity", 0.0), 0.0) for row in rows) / max(len(rows), 1),
                0.0,
                1.0,
            )
        else:
            avg_grade = 0.0
            stability = 0.0
            drawdown_penalty = 0.5
        fitness = FitnessScore(
            genome_id=genome.genome_id,
            score=_clamp(avg_grade - drawdown_penalty * 0.35, 0.0, 1.0),
            stability=_clamp(stability, 0.0, 1.0),
            drawdown_penalty=drawdown_penalty,
            evidence_count=evidence_count,
        )
        evidence = PromotionEvidenceBundle(
            strategy=genome.strategy,
            mission="offline_research",
            shield_mode="normal",
            sample_count=evidence_count,
            win_rate=_clamp(fitness.score, 0.0, 1.0),
            severe_rate=_clamp(drawdown_penalty, 0.0, 1.0),
            replay_eligible_ratio=1.0 if evidence_count >= 5 else 0.0,
            shield_escalation_rate=_clamp(drawdown_penalty * 0.6, 0.0, 1.0),
            risk_adjusted_score=fitness.score,
            reason_codes=tuple(["phase33_offline_candidate"]),
        )
        candidates = [
            ReplayPromotionCandidate(
                strategy=genome.strategy,
                evidence=evidence,
                recommended_size_cap=0.0 if evidence_count < 8 else _clamp(fitness.score * 0.5, 0.0, 0.5),
            )
        ]
        gate = PromotionGateDecision(
            eligible=bool(fitness.score >= 0.70 and evidence_count >= 8),
            candidates=candidates,
            reason_codes=tuple(
                ["insufficient_replay_evidence"]
                if evidence_count < 8
                else (["fitness_below_threshold"] if fitness.score < 0.70 else ["offline_candidate_ready"])
            ),
            min_samples=8,
        )
        extinction = ExtinctionDecision(
            extinct=bool(fitness.score <= 0.15 and evidence_count >= 8),
            genome_id=genome.genome_id,
            reason_codes=tuple(["fitness_extinction"] if fitness.score <= 0.15 and evidence_count >= 8 else ["retain_genome"]),
        )
        safety = ResearchSafetyEnvelope(
            offline_only=True,
            live_promotion_allowed=False,
            deterministic_seeded=True,
            promotion_evidence_required=True,
            reason_codes=tuple(["phase33_offline_only_no_autonomous_live_promotion"]),
        )
        return EvolutionaryResearchState(
            genome=genome,
            mutation=mutation,
            fitness=fitness,
            promotion_gate=gate,
            extinction=extinction,
            safety_envelope=safety,
        )
