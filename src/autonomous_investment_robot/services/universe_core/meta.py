from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .memory import DecisionPacket
from .mission import MissionDecision
from .parliament import StrategyProposal
from .state import WorldStateSnapshot


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _stable_unit_interval(payload: Mapping[str, Any]) -> float:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return float(sha256(raw.encode("utf-8")).digest()[0]) / 255.0


@dataclass(frozen=True)
class StrategyPerformanceStats:
    samples: int
    wins: int
    avg_pnl_quote: float
    avg_slippage_bps: float

    @property
    def win_rate(self) -> float:
        return float(self.wins) / max(self.samples, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "samples": int(self.samples),
            "wins": int(self.wins),
            "win_rate": float(self.win_rate),
            "avg_pnl_quote": float(self.avg_pnl_quote),
            "avg_slippage_bps": float(self.avg_slippage_bps),
        }


@dataclass(frozen=True)
class MetaPerformanceRecord:
    cycle_id: str
    ts: float
    strategy: str
    regime_cluster: str
    realized_pnl_quote: float
    realized_slippage_bps: float
    grade: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "ts": float(self.ts),
            "strategy": self.strategy,
            "regime_cluster": self.regime_cluster,
            "realized_pnl_quote": float(self.realized_pnl_quote),
            "realized_slippage_bps": float(self.realized_slippage_bps),
            "grade": self.grade,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "MetaPerformanceRecord":
        return cls(
            cycle_id=str(raw.get("cycle_id", "")),
            ts=_safe_float(raw.get("ts", 0.0), 0.0),
            strategy=str(raw.get("strategy", "unknown")),
            regime_cluster=str(raw.get("regime_cluster", "unknown")),
            realized_pnl_quote=_safe_float(raw.get("realized_pnl_quote", 0.0), 0.0),
            realized_slippage_bps=_safe_float(raw.get("realized_slippage_bps", 0.0), 0.0),
            grade=str(raw.get("grade", "flat")),
        )


class PersistentPerformanceMemory:
    """Bounded persistent storage for meta-intelligence performance signals."""

    def __init__(self, run_dir: str, *, max_records: int = 2_000) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "universe_meta_performance.jsonl"
        self.max_records = max(1, int(max_records))
        self._cache: list[MetaPerformanceRecord] | None = None

    def load(self) -> list[MetaPerformanceRecord]:
        if self._cache is not None:
            return list(self._cache)
        if not self.path.exists():
            self._cache = []
            return []
        out: list[MetaPerformanceRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except Exception:
                continue
            if isinstance(payload, Mapping):
                out.append(MetaPerformanceRecord.from_mapping(payload))
        if len(out) > self.max_records:
            out = out[-self.max_records :]
            self._write_all(out)
        self._cache = list(out)
        return list(out)

    def record(self, row: MetaPerformanceRecord) -> None:
        rows = self.load()
        rows.append(row)
        if len(rows) > self.max_records:
            rows = rows[-self.max_records :]
        self._write_all(rows)
        self._cache = list(rows)

    def size(self) -> int:
        return len(self.load())

    def strategy_stats(self, strategy: str, regime_cluster: str) -> StrategyPerformanceStats:
        strategy_name = str(strategy or "").strip()
        cluster_name = str(regime_cluster or "").strip() or "unknown"
        rows = self.load()
        regime_rows = [row for row in rows if row.strategy == strategy_name and row.regime_cluster == cluster_name]
        if regime_rows:
            return self._aggregate(regime_rows)
        global_rows = [row for row in rows if row.strategy == strategy_name]
        if global_rows:
            return self._aggregate(global_rows)
        return StrategyPerformanceStats(samples=0, wins=0, avg_pnl_quote=0.0, avg_slippage_bps=0.0)

    def _aggregate(self, rows: Iterable[MetaPerformanceRecord]) -> StrategyPerformanceStats:
        batch = list(rows)
        samples = len(batch)
        wins = sum(1 for row in batch if row.realized_pnl_quote > 0.0)
        pnl = sum(row.realized_pnl_quote for row in batch)
        slippage = sum(row.realized_slippage_bps for row in batch)
        return StrategyPerformanceStats(
            samples=samples,
            wins=wins,
            avg_pnl_quote=pnl / max(samples, 1),
            avg_slippage_bps=slippage / max(samples, 1),
        )

    def _write_all(self, rows: Iterable[MetaPerformanceRecord]) -> None:
        payload = "\n".join(json.dumps(row.to_dict(), sort_keys=True, separators=(",", ":")) for row in rows)
        if payload:
            payload += "\n"
        self.path.write_text(payload, encoding="utf-8")


@dataclass(frozen=True)
class MetaStrategyWeight:
    strategy: str
    sample_count: int
    adaptive_weight: float
    exploration_weight: float
    exploitation_weight: float
    total_weight: float
    adjusted_expected_value_bps: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "sample_count": int(self.sample_count),
            "adaptive_weight": float(self.adaptive_weight),
            "exploration_weight": float(self.exploration_weight),
            "exploitation_weight": float(self.exploitation_weight),
            "total_weight": float(self.total_weight),
            "adjusted_expected_value_bps": float(self.adjusted_expected_value_bps),
        }


@dataclass(frozen=True)
class MetaDecisionSnapshot:
    regime_cluster: str
    exploration_budget: float
    exploitation_budget: float
    risk_scale: float
    strategy_weights: list[MetaStrategyWeight] = field(default_factory=list)
    memory_records: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_cluster": self.regime_cluster,
            "exploration_budget": float(self.exploration_budget),
            "exploitation_budget": float(self.exploitation_budget),
            "risk_scale": float(self.risk_scale),
            "strategy_weights": [row.to_dict() for row in self.strategy_weights],
            "memory_records": int(self.memory_records),
            "notes": list(self.notes),
        }


class RegimeClusterIntelligence:
    """Condenses raw market/risk posture into a stable meta regime cluster."""

    def classify(self, world: WorldStateSnapshot) -> str:
        regime = str(world.market_state.regime or "RANGE")
        vol = str(world.market_state.volatility_regime or "LOW_VOL")
        liq = str(world.market_state.liquidity_regime or "NORMAL")
        expansion = str(world.market_state.expansion_state or "COMPRESSION")
        if regime == "PANIC" or vol == "HIGH_VOL":
            return "stress"
        if liq == "THIN":
            return "thin_liquidity"
        if regime == "TREND" and liq in {"NORMAL", "DEEP"}:
            return "trend_quality"
        if regime == "RANGE" and expansion == "COMPRESSION":
            return "range_compression"
        return "neutral"


class ExplorationExploitationAllocator:
    """Deterministic exploration scheduler keyed by cycle/strategy identity."""

    def __init__(
        self,
        *,
        base_exploration: float = 0.20,
        min_samples: int = 8,
        max_exploration: float = 0.45,
        jitter: float = 0.04,
    ) -> None:
        self.base_exploration = _clamp(base_exploration, 0.0, 1.0)
        self.min_samples = max(1, int(min_samples))
        self.max_exploration = _clamp(max_exploration, 0.0, 1.0)
        self.jitter = _clamp(jitter, 0.0, 0.25)

    def budget(self, *, sample_count: int, strategy: str, regime_cluster: str, cycle_id: str) -> tuple[float, float]:
        learned = _clamp(float(sample_count) / float(self.min_samples), 0.0, 1.0)
        baseline = self.base_exploration * (1.0 - learned)
        jitter = (_stable_unit_interval({"cycle_id": cycle_id, "strategy": strategy, "cluster": regime_cluster}) - 0.5) * 2.0 * self.jitter
        exploration = _clamp(baseline + jitter, 0.0, self.max_exploration)
        exploitation = _clamp(1.0 - exploration, 0.0, 1.0)
        return exploration, exploitation


class MetaRiskStabilizer:
    """Conservative size stabilizer applied after adaptive weighting."""

    def risk_scale(self, *, world: WorldStateSnapshot, mission: MissionDecision) -> tuple[float, list[str]]:
        scale = 1.0
        notes: list[str] = []
        drawdown = max(0.0, float(world.portfolio_state.drawdown_pct))
        execution_stress = _clamp(float(world.execution_state.execution_stress), 0.0, 1.0)
        scale *= _clamp(1.0 - drawdown * 3.5, 0.35, 1.0)
        scale *= _clamp(1.0 - execution_stress * 0.70, 0.40, 1.0)
        if str(world.market_state.volatility_regime) == "HIGH_VOL":
            scale *= 0.82
            notes.append("high_volatility")
        if str(world.market_state.liquidity_regime) == "THIN":
            scale *= 0.76
            notes.append("thin_liquidity")
        if not mission.allow_new_risk:
            scale = min(scale, 0.50)
            notes.append("mission_blocks_new_risk")
        if mission.no_trade_preferred:
            scale = min(scale, 0.40)
            notes.append("mission_prefers_no_trade")
        return _clamp(scale, 0.10, 1.0), notes


class MetaIntelligenceEngine:
    """Adaptive strategy weighting + regime intelligence + bounded performance memory."""

    def __init__(
        self,
        run_dir: str,
        *,
        performance_memory: PersistentPerformanceMemory | None = None,
        clusterer: RegimeClusterIntelligence | None = None,
        allocator: ExplorationExploitationAllocator | None = None,
        risk_stabilizer: MetaRiskStabilizer | None = None,
    ) -> None:
        self.performance_memory = performance_memory or PersistentPerformanceMemory(run_dir)
        self.clusterer = clusterer or RegimeClusterIntelligence()
        self.allocator = allocator or ExplorationExploitationAllocator()
        self.risk_stabilizer = risk_stabilizer or MetaRiskStabilizer()

    def adapt_proposals(
        self,
        proposals: Iterable[StrategyProposal],
        *,
        world: WorldStateSnapshot,
        mission: MissionDecision,
        cycle_id: str,
    ) -> tuple[list[StrategyProposal], MetaDecisionSnapshot]:
        rows = list(proposals)
        regime_cluster = self.clusterer.classify(world)
        risk_scale, risk_notes = self.risk_stabilizer.risk_scale(world=world, mission=mission)

        adjusted: list[StrategyProposal] = []
        weights: list[MetaStrategyWeight] = []
        exploration_samples: list[float] = []
        exploitation_samples: list[float] = []
        for proposal in rows:
            if proposal.strategy == "no_trade_guardian" or proposal.side not in {"buy", "sell"}:
                adjusted.append(
                    replace(
                        proposal,
                        metadata={
                            **proposal.metadata,
                            "meta": {
                                "regime_cluster": regime_cluster,
                                "risk_scale": risk_scale,
                                "adaptive_weight": 1.0,
                            },
                        },
                    )
                )
                continue

            stats = self.performance_memory.strategy_stats(proposal.strategy, regime_cluster)
            adaptive_weight = self._adaptive_weight(proposal=proposal, stats=stats)
            explore_weight, exploit_weight = self.allocator.budget(
                sample_count=stats.samples,
                strategy=proposal.strategy,
                regime_cluster=regime_cluster,
                cycle_id=cycle_id,
            )
            exploration_bonus = explore_weight * (0.35 if stats.samples < self.allocator.min_samples else 0.10)
            exploration_bonus += explore_weight * (
                (_stable_unit_interval({"cycle_id": cycle_id, "strategy": proposal.strategy, "phase": "exploration"}) - 0.5) * 0.10
            )
            total_weight = _clamp(adaptive_weight + exploration_bonus, 0.25, 1.80)
            adjusted_expected_value = float(proposal.expected_value_bps) * total_weight
            adjusted_confidence = _clamp(float(proposal.confidence) * (0.90 + 0.10 * exploit_weight), 0.0, 1.0)
            size_weight = _clamp(total_weight, 0.30, 1.60)
            adjusted_notional = float(proposal.target_notional_quote) * risk_scale * size_weight
            updated = replace(
                proposal,
                target_notional_quote=max(0.0, adjusted_notional),
                expected_value_bps=adjusted_expected_value,
                confidence=adjusted_confidence,
                reason_codes=tuple(
                    list(proposal.reason_codes)
                    + [
                        f"meta_regime_cluster:{regime_cluster}",
                        f"meta_weight:{total_weight:.3f}",
                    ]
                ),
                metadata={
                    **proposal.metadata,
                    "meta": {
                        "regime_cluster": regime_cluster,
                        "risk_scale": risk_scale,
                        "stats": stats.to_dict(),
                        "adaptive_weight": adaptive_weight,
                        "exploration_weight": explore_weight,
                        "exploitation_weight": exploit_weight,
                        "total_weight": total_weight,
                    },
                },
            )
            adjusted.append(updated)
            weights.append(
                MetaStrategyWeight(
                    strategy=proposal.strategy,
                    sample_count=stats.samples,
                    adaptive_weight=adaptive_weight,
                    exploration_weight=explore_weight,
                    exploitation_weight=exploit_weight,
                    total_weight=total_weight,
                    adjusted_expected_value_bps=adjusted_expected_value,
                )
            )
            exploration_samples.append(explore_weight)
            exploitation_samples.append(exploit_weight)

        snapshot = MetaDecisionSnapshot(
            regime_cluster=regime_cluster,
            exploration_budget=sum(exploration_samples) / max(len(exploration_samples), 1),
            exploitation_budget=sum(exploitation_samples) / max(len(exploitation_samples), 1),
            risk_scale=risk_scale,
            strategy_weights=weights,
            memory_records=self.performance_memory.size(),
            notes=list(risk_notes),
        )
        return adjusted, snapshot

    def observe_outcome(self, packet: DecisionPacket) -> None:
        strategies = [str(name) for name in packet.selected_strategies if str(name)]
        if not strategies and packet.selected_strategy:
            strategies = [str(packet.selected_strategy)]
        if not strategies:
            return
        meta = dict(packet.meta_intelligence or {})
        regime_cluster = str(meta.get("regime_cluster", "")) or str(packet.realized_regime or "unknown")
        grade = str(packet.evaluation.get("grade", "flat") if isinstance(packet.evaluation, Mapping) else "flat")
        pnl_per_strategy = float(packet.realized_pnl_quote) / max(len(strategies), 1)
        ts = float(packet.ts) if packet.ts > 0.0 else datetime.now(timezone.utc).timestamp()
        for strategy in strategies:
            self.performance_memory.record(
                MetaPerformanceRecord(
                    cycle_id=str(packet.cycle_id),
                    ts=ts,
                    strategy=str(strategy),
                    regime_cluster=regime_cluster,
                    realized_pnl_quote=pnl_per_strategy,
                    realized_slippage_bps=float(packet.realized_slippage_bps),
                    grade=grade,
                )
            )

    def _adaptive_weight(self, *, proposal: StrategyProposal, stats: StrategyPerformanceStats) -> float:
        if stats.samples <= 0:
            return 1.0
        pnl_score = _clamp(0.50 + stats.avg_pnl_quote / 20.0, 0.0, 1.20)
        slip_penalty = _clamp(stats.avg_slippage_bps / 25.0, 0.0, 0.50)
        weight = 0.65 + (0.45 * stats.win_rate) + (0.35 * pnl_score) - slip_penalty
        if stats.avg_pnl_quote < 0.0:
            weight *= 0.85
        if float(proposal.regime_compatibility) < 0.40:
            weight *= 0.90
        return _clamp(weight, 0.35, 1.60)
