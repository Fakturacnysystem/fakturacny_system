from __future__ import annotations

from autonomous_investment_robot.core.contracts import WaitDominanceReport


def evaluate_wait_dominance(*, base_edge_bps: float, stressed_edge_bps: float, wait_bonus_bps: float, fragility_index: float) -> WaitDominanceReport:
    trade_now_score = stressed_edge_bps - fragility_index * max(abs(base_edge_bps), 1.0)
    wait_score = stressed_edge_bps + wait_bonus_bps
    wait_dominant = wait_score > trade_now_score
    return WaitDominanceReport(
        wait_value_score=wait_score,
        trade_now_score=trade_now_score,
        wait_dominant=wait_dominant,
        reasons=["wait_edge_better" if wait_dominant else "trade_now_edge_better"],
        metadata={"base_edge_bps": base_edge_bps, "wait_bonus_bps": wait_bonus_bps},
    )
