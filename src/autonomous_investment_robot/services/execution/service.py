from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from autonomous_investment_robot.config.settings import ExecutionSettings
from autonomous_investment_robot.services.policy.service import OrderIntent


@dataclass
class Fill:
    venue: str
    order_id: str
    fill_id: str
    symbol: str
    side: str
    notional: float
    fee: float
    slippage_cost: float
    latency_ms: int
    status: str


class ExecutionService:
    def __init__(self, settings: ExecutionSettings) -> None:
        self.settings = settings
        self.fill_seen: set[tuple[str, str, str]] = set()

    def execute_paper(self, order_id: str, intent: OrderIntent, mid_price: float) -> list[Fill]:
        partial = max(0.0, min(1.0, self.settings.partial_fill_ratio))
        filled_notional = intent.target_notional * partial
        fee = filled_notional * (self.settings.fee_bps / 10000)
        spread_slip = filled_notional * (self.settings.slippage_bps / 10000)
        fill_id = sha256(f"{order_id}:{filled_notional}".encode()).hexdigest()[:16]
        dedupe_key = ("paper", order_id, fill_id)
        if dedupe_key in self.fill_seen:
            return []
        self.fill_seen.add(dedupe_key)
        return [
            Fill(
                venue="paper",
                order_id=order_id,
                fill_id=fill_id,
                symbol=intent.symbol,
                side=intent.side,
                notional=filled_notional,
                fee=fee,
                slippage_cost=spread_slip,
                latency_ms=100,
                status="filled_partial" if partial < 1.0 else "filled",
            )
        ]

    def flatten_worst_case(self, symbol: str, exposure_notional: float) -> Fill:
        fee = abs(exposure_notional) * (self.settings.fee_bps / 10000)
        slippage = abs(exposure_notional) * max(self.settings.slippage_bps, 25) / 10000
        return Fill(
            venue="paper",
            order_id="flatten-order",
            fill_id="flatten-fill",
            symbol=symbol,
            side="sell" if exposure_notional > 0 else "buy",
            notional=abs(exposure_notional),
            fee=fee,
            slippage_cost=slippage,
            latency_ms=200,
            status="flattened",
        )
