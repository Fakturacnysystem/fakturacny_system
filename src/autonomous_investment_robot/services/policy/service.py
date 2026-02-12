from autonomous_investment_robot.core.contracts import OrderIntent


class PolicyService:
    def make_intent(self, snapshot: dict) -> OrderIntent:
        forecast = snapshot["forecast"]
        sigma = max(forecast.sigma, 1e-6)
        risk_budget = 0.001  # safe MVP default placeholder
        qty = risk_budget / sigma  # position_size proportionality
        side = "buy" if forecast.mu > 0 else "sell"
        return OrderIntent(symbol=forecast.symbol, side=side, qty=qty, reason="policy_optimization", max_slippage_bps=10.0)
