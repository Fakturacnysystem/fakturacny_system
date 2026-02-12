from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from autonomous_investment_robot.config.settings import ExecutionMode, ExecutionSettings
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
        self.live_service = None

    def attach_live_service(self, live_service: object) -> None:
        self.live_service = live_service

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
        regime: str,
        liquidity_regime: str,
    ) -> list[Fill]:
        if anti_toxic_block(oi_spike_pct, liquidations, funding_rate, spread_bps):
            return []

        slices = slice_notional(intent.target_notional, self.settings.slicing_parts, self.settings.max_participation_rate, depth_notional)
        fills = []
        for i, sl in enumerate(slices):
            partial = max(0.0, min(1.0, self.settings.partial_fill_ratio))
            maker_ok = self.settings.maker_preference and regime != "PANIC" and liquidity_regime == "GOOD" and spread_bps <= 15
            if maker_ok:
                fill_mode = "maker"
                fee_bps = self.settings.fee_bps * 0.6
                slippage_bps = self.settings.slippage_bps * 0.5
            else:
                # maker timeout fallback to taker (deterministic)
                fill_mode = "taker_timeout"
                fee_bps = self.settings.fee_bps
                slippage_bps = self.settings.slippage_bps * 1.5

            filled_notional = sl * partial
            fee = filled_notional * (fee_bps / 10000)
            spread_slip = filled_notional * (slippage_bps / 10000)
            fill_id = sha256(f"{order_id}:{i}:{filled_notional}:{fill_mode}".encode()).hexdigest()[:16]
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
                    status=f"filled_partial_{fill_mode}" if partial < 1.0 else f"filled_{fill_mode}",
                )
            )
        return fills

    def execute_live(self, intent: OrderIntent):
        mode = ExecutionMode(self.settings.mode)
        if self.live_service is None:
            raise RuntimeError("live_service_not_configured")
        if mode == ExecutionMode.LIVE_READONLY:
            return self.live_service.execute_readonly(intent)
        if mode in {ExecutionMode.LIVE_TESTNET, ExecutionMode.LIVE}:
            return self.live_service.execute_intent(intent)
        raise RuntimeError("execute_live_called_in_paper_mode")

    def flatten_worst_case(self, symbol: str, exposure_notional: float) -> Fill:
        fee = abs(exposure_notional) * (self.settings.fee_bps / 10000)
        slippage = abs(exposure_notional) * max(self.settings.slippage_bps, 40) / 10000
        return Fill("paper", "flatten-order", "flatten-fill", symbol, "sell" if exposure_notional > 0 else "buy", abs(exposure_notional), fee, slippage, 250, "flattened")
