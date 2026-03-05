from __future__ import annotations

from autonomous_investment_robot.backtest.walk_forward import overfit_penalty, summarize_walk_forward_oos, walk_forward_oos, walk_forward_quality_gate


def simulate_backtest(prices: list[float], fee_bps: float = 2.0, slippage_bps: float = 3.0, funding_bps: float = 1.0) -> list[dict]:
    rows = []
    total_cost = (fee_bps + slippage_bps + funding_bps) / 10000
    equity = 1.0
    for i, price in enumerate(prices):
        prev = prices[i - 1] if i > 0 else price
        ret = 0.0 if i == 0 else (price / prev) - 1
        strategy_ret = ret - total_cost
        equity *= (1 + strategy_ret)
        rows.append({"price": price, "ret": ret, "strategy_ret": strategy_ret, "equity": equity})
    return rows


def run_walk_forward_oos(
    prices: list[float],
    *,
    train: int,
    test: int,
    fee_bps: float = 2.0,
    slippage_bps: float = 3.0,
    funding_bps: float = 1.0,
) -> dict:
    rows = simulate_backtest(prices, fee_bps=fee_bps, slippage_bps=slippage_bps, funding_bps=funding_bps)
    splits = walk_forward_oos(rows, train=train, test=test)
    summary = summarize_walk_forward_oos(splits)
    penalty = overfit_penalty(splits)
    gate = walk_forward_quality_gate(summary, penalty)
    return {"splits": splits, "summary": summary, "penalty": penalty, "gate": gate}
