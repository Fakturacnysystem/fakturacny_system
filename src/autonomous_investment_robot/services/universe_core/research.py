from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .memory import DecisionPacket


PROMOTION_LADDER: tuple[str, ...] = (
    "offline_replay",
    "walk_forward",
    "shadow_mode",
    "paper_mode",
    "limited_live",
    "scaled_live",
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass(frozen=True)
class ReplayStageResult:
    stage: str
    passed: bool
    score: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "passed": self.passed,
            "score": self.score,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class PromotionState:
    current_stage: str
    next_stage: str | None
    ready_to_promote: bool
    score: float
    results: list[ReplayStageResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "current_stage": self.current_stage,
            "next_stage": self.next_stage,
            "ready_to_promote": self.ready_to_promote,
            "score": self.score,
            "results": [row.to_dict() for row in self.results],
        }


class ResearchReplayLab:
    """Promotion ladder for replay -> paper -> limited live -> scaled live."""

    def assess(self, packets: Iterable[DecisionPacket]) -> PromotionState:
        rows = list(packets)
        total = len(rows)
        wins = sum(1 for row in rows if float(row.realized_pnl_quote) > 0.0)
        avg_pnl = sum(float(row.realized_pnl_quote) for row in rows) / max(total, 1)
        avg_slippage = sum(float(row.realized_slippage_bps) for row in rows) / max(total, 1)
        win_rate = wins / max(total, 1)
        pnl_score = _clamp(0.5 + avg_pnl / max(total, 1) / 10.0, 0.0, 1.0)
        slippage_score = _clamp(1.0 - (avg_slippage / 20.0), 0.0, 1.0)
        base_score = _clamp(win_rate * 0.50 + pnl_score * 0.30 + slippage_score * 0.20, 0.0, 1.0)

        requirements = {
            "offline_replay": (3, 0.40),
            "walk_forward": (5, 0.45),
            "shadow_mode": (8, 0.50),
            "paper_mode": (10, 0.55),
            "limited_live": (12, 0.60),
            "scaled_live": (20, 0.72),
        }
        results: list[ReplayStageResult] = []
        highest_passed = "offline_replay"
        for stage in PROMOTION_LADDER:
            min_records, min_score = requirements[stage]
            passed = total >= min_records and base_score >= min_score
            notes = [
                f"records={total}/{min_records}",
                f"score={base_score:.3f}/{min_score:.3f}",
                f"win_rate={win_rate:.3f}",
                f"avg_slippage_bps={avg_slippage:.2f}",
            ]
            results.append(ReplayStageResult(stage=stage, passed=passed, score=base_score, notes=notes))
            if passed:
                highest_passed = stage
            else:
                break
        current_index = PROMOTION_LADDER.index(highest_passed)
        next_stage = PROMOTION_LADDER[current_index + 1] if current_index + 1 < len(PROMOTION_LADDER) else None
        ready = bool(next_stage and results[current_index].passed)
        return PromotionState(
            current_stage=highest_passed,
            next_stage=next_stage,
            ready_to_promote=ready,
            score=base_score,
            results=results,
        )
