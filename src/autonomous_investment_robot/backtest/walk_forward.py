from __future__ import annotations

from autonomous_investment_robot.reporting.metrics import max_drawdown, sharpe, sortino


def walk_forward_splits(rows: list[dict], train: int, test: int) -> list[tuple[list[dict], list[dict]]]:
    splits = []
    i = 0
    while i + train + test <= len(rows):
        splits.append((rows[i : i + train], rows[i + train : i + train + test]))
        i += test
    return splits


def evaluate_window(rows: list[dict]) -> dict[str, float]:
    if not rows:
        return {
            "trades": 0.0,
            "avg_return": 0.0,
            "total_return": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
        }
    returns = [float(r.get("strategy_ret", r.get("ret", 0.0))) for r in rows]
    equity = [float(r.get("equity", 1.0)) for r in rows]
    wins = len([r for r in returns if r > 0.0])
    first = equity[0] if equity else 1.0
    total_return = 0.0 if first == 0 else (equity[-1] / first - 1.0)
    dd = abs(max_drawdown(equity))
    return {
        "trades": float(len(rows)),
        "avg_return": sum(returns) / max(len(returns), 1),
        "total_return": total_return,
        "sharpe": sharpe(returns),
        "sortino": sortino(returns),
        "max_drawdown": dd,
        "win_rate": wins / max(len(returns), 1),
    }


def walk_forward_oos(rows: list[dict], train: int, test: int) -> list[dict]:
    out: list[dict] = []
    for idx, (train_rows, test_rows) in enumerate(walk_forward_splits(rows, train=train, test=test)):
        out.append(
            {
                "split": idx,
                "train_size": len(train_rows),
                "test_size": len(test_rows),
                "train_metrics": evaluate_window(train_rows),
                "oos_metrics": evaluate_window(test_rows),
            }
        )
    return out


def summarize_walk_forward_oos(results: list[dict]) -> dict[str, float]:
    if not results:
        return {"splits": 0.0, "avg_oos_return": 0.0, "avg_oos_sharpe": 0.0, "avg_oos_sortino": 0.0, "avg_oos_max_drawdown": 0.0}
    avg_oos_return = sum(float(r["oos_metrics"]["total_return"]) for r in results) / len(results)
    avg_oos_sharpe = sum(float(r["oos_metrics"]["sharpe"]) for r in results) / len(results)
    avg_oos_sortino = sum(float(r["oos_metrics"]["sortino"]) for r in results) / len(results)
    avg_oos_dd = sum(float(r["oos_metrics"]["max_drawdown"]) for r in results) / len(results)
    return {
        "splits": float(len(results)),
        "avg_oos_return": avg_oos_return,
        "avg_oos_sharpe": avg_oos_sharpe,
        "avg_oos_sortino": avg_oos_sortino,
        "avg_oos_max_drawdown": avg_oos_dd,
    }


def overfit_penalty(results: list[dict]) -> dict[str, float]:
    if not results:
        return {"pbo": 1.0, "deflated_sharpe": -1.0, "regime_stability": 0.0}
    overfit_hits = 0
    stability_scores: list[float] = []
    oos_sharpes: list[float] = []
    for row in results:
        tr = row.get("train_metrics", {})
        oos = row.get("oos_metrics", {})
        tr_ret = float(tr.get("total_return", 0.0))
        oos_ret = float(oos.get("total_return", 0.0))
        tr_sh = float(tr.get("sharpe", 0.0))
        oos_sh = float(oos.get("sharpe", 0.0))
        oos_sharpes.append(oos_sh)
        if (tr_ret > 0 and oos_ret < 0) or (tr_sh > 0 and oos_sh < 0):
            overfit_hits += 1
        gap = abs(tr_sh - oos_sh)
        stability_scores.append(max(0.0, 1.0 - min(1.0, gap / 5.0)))
    pbo = overfit_hits / max(len(results), 1)
    regime_stability = sum(stability_scores) / max(len(stability_scores), 1)
    avg_oos_sharpe = sum(oos_sharpes) / max(len(oos_sharpes), 1)
    # Conservative proxy of deflated Sharpe: penalize by overfitting odds and split count complexity.
    deflated_sharpe = avg_oos_sharpe * (1.0 - pbo) - (len(results) ** 0.5) * 0.05
    return {"pbo": pbo, "deflated_sharpe": deflated_sharpe, "regime_stability": regime_stability}


def walk_forward_quality_gate(
    summary: dict[str, float],
    penalty: dict[str, float],
    *,
    min_oos_return: float = -0.005,
    min_deflated_sharpe: float = 0.0,
    max_pbo: float = 0.55,
    min_regime_stability: float = 0.35,
) -> dict[str, object]:
    avg_oos_return = float(summary.get("avg_oos_return", 0.0))
    ds = float(penalty.get("deflated_sharpe", -1.0))
    pbo = float(penalty.get("pbo", 1.0))
    stability = float(penalty.get("regime_stability", 0.0))
    if avg_oos_return < min_oos_return:
        return {"allowed": False, "reason": "oos_return_too_low"}
    if ds < min_deflated_sharpe:
        return {"allowed": False, "reason": "deflated_sharpe_too_low"}
    if pbo > max_pbo:
        return {"allowed": False, "reason": "pbo_too_high"}
    if stability < min_regime_stability:
        return {"allowed": False, "reason": "regime_stability_too_low"}
    return {"allowed": True, "reason": "walk_forward_pass"}
