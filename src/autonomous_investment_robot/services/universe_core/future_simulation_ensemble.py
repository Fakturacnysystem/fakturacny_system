from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping

from .future_simulation_engine import DeterministicFutureSimulationEngine
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


@dataclass(frozen=True)
class EnsembleConfidenceContract:
    overall_confidence: float
    tree_count: int
    deterministic: bool
    bounded_compute: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_confidence": float(self.overall_confidence),
            "tree_count": int(self.tree_count),
            "deterministic": bool(self.deterministic),
            "bounded_compute": bool(self.bounded_compute),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class EnsembleScenarioResult:
    ensemble_id: str
    deterministic: bool
    bounded_compute: bool
    tree_limit: int
    branch_limit: int
    trees: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    aggregate_pnl_envelope: dict[str, Any] = field(default_factory=dict)
    confidence: EnsembleConfidenceContract | None = None
    replay_export: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ensemble_id": self.ensemble_id,
            "deterministic": bool(self.deterministic),
            "bounded_compute": bool(self.bounded_compute),
            "tree_limit": int(self.tree_limit),
            "branch_limit": int(self.branch_limit),
            "trees": [dict(row) for row in self.trees],
            "aggregate_pnl_envelope": dict(self.aggregate_pnl_envelope),
            "confidence": self.confidence.to_dict() if self.confidence is not None else {},
            "replay_export": dict(self.replay_export),
        }


class FutureSimulationEnsembleEngine:
    """Phase 45 bounded deterministic multi-tree future-simulation ensemble."""

    def __init__(self, *, max_trees: int = 3, max_branches: int = 5, max_depth: int = 2) -> None:
        self.max_trees = max(1, int(max_trees))
        self.max_branches = max(2, int(max_branches))
        self.max_depth = max(1, int(max_depth))

    def simulate(
        self,
        *,
        seed_payload: Mapping[str, Any],
        market_energy: MarketEnergyState,
        expected_edge_bps: float,
        capital_scale: float,
    ) -> EnsembleScenarioResult:
        engine = DeterministicFutureSimulationEngine(max_branches=self.max_branches, max_depth=self.max_depth)
        trees: list[dict[str, Any]] = []
        expected_rows: list[float] = []
        worst_rows: list[float] = []
        best_rows: list[float] = []
        confidence_rows: list[float] = []
        for idx in range(self.max_trees):
            payload = {
                **dict(seed_payload),
                "ensemble_tree_index": idx,
                "ensemble_tree_count": self.max_trees,
            }
            tree = engine.simulate(
                seed_payload=payload,
                market_energy=market_energy,
                expected_edge_bps=_safe_float(expected_edge_bps, 0.0),
                capital_scale=_safe_float(capital_scale, 0.0),
            ).to_dict()
            trees.append(
                {
                    "tree_index": idx,
                    "tree_id": tree.get("scenario_tree", {}).get("tree_id", ""),
                    "seed": tree.get("scenario_tree", {}).get("seed", 0),
                    "branch_count": len(tree.get("scenario_tree", {}).get("branches", [])),
                    "pnl_envelope": dict(tree.get("pnl_envelope", {})),
                    "confidence": dict(tree.get("confidence", {})),
                    "replay_export": dict(tree.get("replay_export", {})),
                }
            )
            pnl = tree.get("pnl_envelope", {})
            expected_rows.append(_safe_float(pnl.get("expected", 0.0), 0.0))
            worst_rows.append(_safe_float(pnl.get("worst_case", 0.0), 0.0))
            best_rows.append(_safe_float(pnl.get("best_case", 0.0), 0.0))
            confidence_rows.append(_safe_float(tree.get("confidence", {}).get("overall", 0.0), 0.0))
        aggregate = {
            "expected": sum(expected_rows) / max(1, len(expected_rows)),
            "worst_case": min(worst_rows) if worst_rows else 0.0,
            "best_case": max(best_rows) if best_rows else 0.0,
        }
        overall_conf = _clamp(sum(confidence_rows) / max(1, len(confidence_rows)), 0.0, 1.0)
        confidence = EnsembleConfidenceContract(
            overall_confidence=overall_conf,
            tree_count=len(trees),
            deterministic=True,
            bounded_compute=True,
            reason_codes=("phase45_ensemble_deterministic",),
        )
        ensemble_id = _stable_hash(
            {
                "phase": 45,
                "tree_ids": [str(row.get("tree_id", "")) for row in trees],
                "expected": round(_safe_float(aggregate.get("expected", 0.0), 0.0), 6),
                "worst_case": round(_safe_float(aggregate.get("worst_case", 0.0), 0.0), 6),
                "confidence": round(overall_conf, 6),
            }
        )[:24]
        replay_export = {
            "schema": "phase45_future_simulation_ensemble_v1",
            "ensemble_id": ensemble_id,
            "tree_count": len(trees),
            "tree_limit": self.max_trees,
            "branch_limit": self.max_branches,
            "bounded_compute": True,
        }
        return EnsembleScenarioResult(
            ensemble_id=ensemble_id,
            deterministic=True,
            bounded_compute=True,
            tree_limit=self.max_trees,
            branch_limit=self.max_branches,
            trees=tuple(trees),
            aggregate_pnl_envelope=aggregate,
            confidence=confidence,
            replay_export=replay_export,
        )
