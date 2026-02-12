from __future__ import annotations

from dataclasses import dataclass

from autonomous_investment_robot.config.settings import ExecutionSettings
from autonomous_investment_robot.services.policy.service import OrderIntent


@dataclass
class Fill:
    symbol: str
    side: str
    notional: float
    fee: float
    slippage_cost: float
    status: str


class ExecutionService:
    def __init__(self, settings: ExecutionSettings) -> None:
        self.settings = settings

    def execute_paper(self, intent: OrderIntent, mid_price: float) -> list[Fill]:
        partial = max(0.0, min(1.0, self.settings.partial_fill_ratio))
        filled_notional = intent.target_notional * partial
        fee = filled_notional * (self.settings.fee_bps / 10000)
        slip = filled_notional * (self.settings.slippage_bps / 10000)
        return [
            Fill(
                symbol=intent.symbol,
                side=intent.side,
                notional=filled_notional,
                fee=fee,
                slippage_cost=slip,
                status="filled_partial" if partial < 1.0 else "filled",
            )
        ]
