from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


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


class MemoryEngine:
    """Persistent decision memory for replay, grading, and offline learning."""

    def __init__(self, run_dir: str, *, max_records: int = 5_000) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.records_path = self.run_dir / "universe_memory.jsonl"
        self.evaluations_path = self.run_dir / "universe_memory_evaluations.jsonl"
        self.max_records = max(100, int(max_records))

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
        packet_id = cycle_id or _stable_hash({"ts": round(ts, 6), "symbol": symbol, "venue": venue, "world": world_payload, "strategy": selected_strategy})
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

    def record(self, packet: DecisionPacket) -> None:
        self._append(self.records_path, packet.to_dict())

    def grade(
        self,
        packet: DecisionPacket,
        *,
        realized_pnl_quote: float,
        realized_slippage_bps: float,
        realized_regime: str,
        fill_ratio: float = 0.0,
    ) -> DecisionPacket:
        grade = "win" if realized_pnl_quote > 0.0 else "loss" if realized_pnl_quote < 0.0 else "flat"
        updated = DecisionPacket(
            cycle_id=packet.cycle_id,
            ts=packet.ts,
            symbol=packet.symbol,
            venue=packet.venue,
            world_state_fingerprint=packet.world_state_fingerprint,
            world_state=dict(packet.world_state),
            mission=dict(packet.mission),
            proposals=[dict(row) for row in packet.proposals],
            selected_strategy=packet.selected_strategy,
            selected_strategies=list(packet.selected_strategies),
            parliament_mode=packet.parliament_mode,
            parliament_no_trade=packet.parliament_no_trade,
            parliament_allocations=[dict(row) for row in packet.parliament_allocations],
            parliament=dict(packet.parliament),
            execution_plan=dict(packet.execution_plan),
            shield=dict(packet.shield),
            ops_snapshot=dict(packet.ops_snapshot),
            meta_intelligence=dict(packet.meta_intelligence),
            actual_fill={"fill_ratio": fill_ratio},
            realized_pnl_quote=float(realized_pnl_quote),
            realized_slippage_bps=float(realized_slippage_bps),
            realized_regime=str(realized_regime),
            evaluation={
                "status": "graded",
                "grade": grade,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._append(self.evaluations_path, updated.to_dict())
        return updated

    def load(self, *, graded: bool = False) -> list[DecisionPacket]:
        path = self.evaluations_path if graded else self.records_path
        if not path.exists():
            return []
        out: list[DecisionPacket] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            raw = json.loads(text)
            if isinstance(raw, Mapping):
                out.append(DecisionPacket.from_mapping(raw))
        return out

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

    def _append(self, path: Path, payload: Mapping[str, Any]) -> None:
        rows: list[str] = []
        if path.exists():
            rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows.append(json.dumps(dict(payload), sort_keys=True, default=str))
        if len(rows) > self.max_records:
            rows = rows[-self.max_records :]
        text = "\n".join(rows)
        if text:
            text += "\n"
        path.write_text(text, encoding="utf-8")
