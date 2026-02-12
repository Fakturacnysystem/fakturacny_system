from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from autonomous_investment_robot.config.settings import ExecutionSettings
from autonomous_investment_robot.services.execution.tco import anti_toxic_block, slice_notional
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

    def execute_paper(
        self,
        order_id: str,
        intent: OrderIntent,
        mid_price: float,
        depth_notional: float,
        oi_spike_pct: float,
        liquidations: float,
        funding_rate: float,
        spread_bps: float,
    ) -> list[Fill]:
        if anti_toxic_block(oi_spike_pct, liquidations, funding_rate, spread_bps):
            return []

        slices = slice_notional(intent.target_notional, self.settings.slicing_parts, self.settings.max_participation_rate, depth_notional)
        fills = []
        for i, sl in enumerate(slices):
            partial = max(0.0, min(1.0, self.settings.partial_fill_ratio))
            filled_notional = sl * partial
            fee = filled_notional * (self.settings.fee_bps / 10000)
            spread_slip = filled_notional * (self.settings.slippage_bps / 10000)
            fill_id = sha256(f"{order_id}:{i}:{filled_notional}".encode()).hexdigest()[:16]
            dedupe_key = ("paper", order_id, fill_id)
            if dedupe_key in self.fill_seen:
                continue
            self.fill_seen.add(dedupe_key)
            fills.append(
                Fill(
                    venue="paper",
                    order_id=order_id,
                    fill_id=fill_id,
                    symbol=intent.symbol,
                    side=intent.side,
                    notional=filled_notional,
                    fee=fee,
                    slippage_cost=spread_slip,
                    latency_ms=100 + i * 20,
                    status="filled_partial" if partial < 1.0 else "filled",
                )
            )
        return fills

    def flatten_worst_case(self, symbol: str, exposure_notional: float) -> Fill:
        fee = abs(exposure_notional) * (self.settings.fee_bps / 10000)
        slippage = abs(exposure_notional) * max(self.settings.slippage_bps, 40) / 10000
        return Fill("paper", "flatten-order", "flatten-fill", symbol, "sell" if exposure_notional > 0 else "buy", abs(exposure_notional), fee, slippage, 250, "flattened")
