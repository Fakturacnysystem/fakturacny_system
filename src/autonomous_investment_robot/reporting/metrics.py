from __future__ import annotations

from math import sqrt


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    m = sum(values) / len(values)
    return (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5


def sharpe(returns: list[float]) -> float:
    if not returns:
        return 0.0
    s = _std(returns)
    return 0.0 if s == 0 else (sum(returns) / len(returns)) / s * sqrt(252)


def sortino(returns: list[float]) -> float:
    downs = [r for r in returns if r < 0]
    s = _std(downs)
    return 0.0 if s == 0 else (sum(returns) / len(returns)) / s * sqrt(252)


def max_drawdown(equity: list[float]) -> float:
    peak = -10**9
    worst = 0.0
    for e in equity:
        peak = max(peak, e)
        dd = e / peak - 1
        worst = min(worst, dd)
    return worst
