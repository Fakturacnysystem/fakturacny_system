from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping

from .market_energy_physics import MarketEnergyState


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


def _stable_unit_interval(payload: Mapping[str, Any]) -> float:
    digest = sha256(json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).digest()
    return float(digest[0]) / 255.0


@dataclass(frozen=True)
class ScenarioBranch:
    branch_id: str
    name: str
    probability: float
    stress_score: float
    pnl_expectation: float
    pnl_worst: float
    pnl_best: float
    tags: tuple[str, ...] = field(default_factory=tuple)
    children: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "name": self.name,
            "probability": float(self.probability),
            "stress_score": float(self.stress_score),
            "pnl_expectation": float(self.pnl_expectation),
            "pnl_worst": float(self.pnl_worst),
            "pnl_best": float(self.pnl_best),
            "tags": [str(item) for item in self.tags],
            "children": [str(item) for item in self.children],
        }


@dataclass(frozen=True)
class ScenarioTree:
    tree_id: str
    root_id: str
    seed: int
    max_depth: int
    bounded: bool
    branches: list[ScenarioBranch] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tree_id": self.tree_id,
            "root_id": self.root_id,
            "seed": int(self.seed),
            "max_depth": int(self.max_depth),
            "bounded": bool(self.bounded),
            "branches": [row.to_dict() for row in self.branches],
        }


@dataclass(frozen=True)
class FutureStressPath:
    path_id: str
    label: str
    stress_curve: tuple[float, ...] = field(default_factory=tuple)
    liquidity_curve: tuple[float, ...] = field(default_factory=tuple)
    volatility_curve: tuple[float, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_id": self.path_id,
            "label": self.label,
            "stress_curve": [float(item) for item in self.stress_curve],
            "liquidity_curve": [float(item) for item in self.liquidity_curve],
            "volatility_curve": [float(item) for item in self.volatility_curve],
        }


@dataclass(frozen=True)
class BlackSwanCase:
    case_id: str
    trigger: str
    severity: float
    loss_estimate: float
    recovery_days: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "trigger": self.trigger,
            "severity": float(self.severity),
            "loss_estimate": float(self.loss_estimate),
            "recovery_days": float(self.recovery_days),
        }


@dataclass(frozen=True)
class PnLEnvelope:
    expected: float
    downside_95: float
    upside_95: float
    worst_case: float
    best_case: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected": float(self.expected),
            "downside_95": float(self.downside_95),
            "upside_95": float(self.upside_95),
            "worst_case": float(self.worst_case),
            "best_case": float(self.best_case),
        }


@dataclass(frozen=True)
class ScenarioConfidence:
    overall: float
    coverage: float
    data_quality: float
    deterministic: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": float(self.overall),
            "coverage": float(self.coverage),
            "data_quality": float(self.data_quality),
            "deterministic": bool(self.deterministic),
        }


@dataclass(frozen=True)
class FutureSimulationResult:
    scenario_tree: ScenarioTree
    stress_path: FutureStressPath
    black_swan: BlackSwanCase
    pnl_envelope: PnLEnvelope
    confidence: ScenarioConfidence
    replay_export: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_tree": self.scenario_tree.to_dict(),
            "stress_path": self.stress_path.to_dict(),
            "black_swan": self.black_swan.to_dict(),
            "pnl_envelope": self.pnl_envelope.to_dict(),
            "confidence": self.confidence.to_dict(),
            "replay_export": dict(self.replay_export),
        }


class DeterministicFutureSimulationEngine:
    """Phase 29 bounded, seeded scenario branching and replay export."""

    def __init__(self, *, max_branches: int = 5, max_depth: int = 2) -> None:
        self.max_branches = max(2, int(max_branches))
        self.max_depth = max(1, int(max_depth))

    def simulate(
        self,
        *,
        seed_payload: Mapping[str, Any],
        market_energy: MarketEnergyState,
        expected_edge_bps: float,
        capital_scale: float,
    ) -> FutureSimulationResult:
        seed_hash = _stable_hash(seed_payload)
        seed = int(seed_hash[:12], 16) % 1_000_000_007
        base_stress = _clamp(market_energy.instability.instability_score, 0.0, 1.0)
        edge = _safe_float(expected_edge_bps, 0.0)
        cap = _clamp(_safe_float(capital_scale, 0.0), 0.0, 2.0)
        branches: list[ScenarioBranch] = []
        branch_specs = (
            ("base_case", 0.45, 0.0, ("base",)),
            ("adverse_case", 0.25, 0.20, ("stress",)),
            ("liquidity_void", 0.15, 0.35, ("liquidity_void", "stress")),
            ("black_swan", 0.05, 0.65, ("black_swan", "tail")),
            ("upside_case", 0.10, -0.10, ("upside",)),
        )
        for idx, (name, probability, stress_shift, tags) in enumerate(branch_specs[: self.max_branches]):
            local = _stable_unit_interval({"seed": seed, "branch": name, "idx": idx})
            stress = _clamp(base_stress + stress_shift + (local - 0.5) * 0.10, 0.0, 1.0)
            pnl_mean = (edge * cap / 100.0) * (1.0 - stress * 0.85)
            spread = max(abs(pnl_mean) * 0.75, 0.10 + stress * 0.40)
            branches.append(
                ScenarioBranch(
                    branch_id=_stable_hash({"seed": seed, "name": name})[:16],
                    name=name,
                    probability=float(probability),
                    stress_score=stress,
                    pnl_expectation=pnl_mean,
                    pnl_worst=pnl_mean - spread,
                    pnl_best=pnl_mean + spread,
                    tags=tuple(tags),
                    children=tuple(),
                )
            )
        total_prob = sum(row.probability for row in branches) or 1.0
        normalized = [
            ScenarioBranch(
                branch_id=row.branch_id,
                name=row.name,
                probability=row.probability / total_prob,
                stress_score=row.stress_score,
                pnl_expectation=row.pnl_expectation,
                pnl_worst=row.pnl_worst,
                pnl_best=row.pnl_best,
                tags=row.tags,
                children=row.children,
            )
            for row in branches
        ]
        tree = ScenarioTree(
            tree_id=_stable_hash({"seed": seed, "tree": "phase29"})[:16],
            root_id=normalized[0].branch_id if normalized else "",
            seed=seed,
            max_depth=self.max_depth,
            bounded=len(normalized) <= self.max_branches,
            branches=normalized,
        )
        stress_curve = tuple(_clamp(base_stress + step * 0.05, 0.0, 1.0) for step in range(6))
        liq_curve = tuple(_clamp(1.0 - value * 0.70, 0.0, 1.0) for value in stress_curve)
        vol_curve = tuple(_clamp(0.20 + value * 0.80, 0.0, 1.0) for value in stress_curve)
        stress_path = FutureStressPath(
            path_id=_stable_hash({"seed": seed, "path": "stress"})[:16],
            label="deterministic_stress_path",
            stress_curve=stress_curve,
            liquidity_curve=liq_curve,
            volatility_curve=vol_curve,
        )
        swan_severity = _clamp(base_stress + 0.35, 0.0, 1.0)
        black_swan = BlackSwanCase(
            case_id=_stable_hash({"seed": seed, "case": "black_swan"})[:16],
            trigger="liquidity_freeze_and_venue_outage",
            severity=swan_severity,
            loss_estimate=-(0.60 + swan_severity * 0.80) * max(0.25, cap),
            recovery_days=1.0 + swan_severity * 10.0,
        )
        expected = sum(row.pnl_expectation * row.probability for row in normalized)
        worst = min([row.pnl_worst for row in normalized] + [black_swan.loss_estimate])
        best = max([row.pnl_best for row in normalized] + [expected])
        envelope = PnLEnvelope(
            expected=expected,
            downside_95=min(expected * 0.75, worst * 0.95),
            upside_95=max(expected * 1.25, best * 0.95),
            worst_case=worst,
            best_case=best,
        )
        data_quality = _clamp(1.0 - (market_energy.instability.instability_score * 0.35), 0.05, 1.0)
        confidence = ScenarioConfidence(
            overall=_clamp(data_quality * 0.70 + (1.0 if tree.bounded else 0.0) * 0.30, 0.0, 1.0),
            coverage=_clamp(len(normalized) / float(self.max_branches), 0.0, 1.0),
            data_quality=data_quality,
            deterministic=True,
        )
        replay_export = {
            "schema": "phase29_scenario_tree_v1",
            "seed": seed,
            "tree_hash": _stable_hash(tree.to_dict()),
            "branch_count": len(normalized),
            "bounded_compute": bool(tree.bounded),
        }
        return FutureSimulationResult(
            scenario_tree=tree,
            stress_path=stress_path,
            black_swan=black_swan,
            pnl_envelope=envelope,
            confidence=confidence,
            replay_export=replay_export,
        )
