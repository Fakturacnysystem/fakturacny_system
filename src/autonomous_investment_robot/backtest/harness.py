from __future__ import annotations

from autonomous_investment_robot.services.feature_store.service import FeatureStoreService
from autonomous_investment_robot.services.models.service import ModelsService
from autonomous_investment_robot.services.policy.service import PolicyService


def run_backtest_from_features(feature_vectors: list, policy_settings) -> dict:
    models = ModelsService()
    policy = PolicyService(policy_settings)
    trades = 0
    for fv in feature_vectors:
        fc = models.forecast(fv)
        intent = policy.make_intent(fc)
        if intent is not None:
            trades += 1
    return {"trades": trades}


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
