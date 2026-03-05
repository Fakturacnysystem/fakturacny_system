from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TreasuryDecision:
    allowed: bool
    throttle_scale: float
    reason: str
    reserve_ratio: float
    margin_buffer: float
    actions: list[str]


class TreasuryService:
    def __init__(self, reserve_cash_ratio: float = 0.12, min_margin_buffer: float = 1.4) -> None:
        self.reserve_cash_ratio = max(0.0, float(reserve_cash_ratio))
        self.min_margin_buffer = max(0.1, float(min_margin_buffer))

    def evaluate(
        self,
        *,
        quote_free: float,
        quote_total: float,
        margin_used: float,
        open_notional: float,
        drawdown_pct: float,
    ) -> TreasuryDecision:
        free = max(0.0, float(quote_free))
        total = max(free, float(quote_total))
        reserve_ratio = 0.0 if total <= 0 else free / total
        buffer_denom = max(1.0, float(margin_used))
        margin_buffer = max(0.0, (total - margin_used) / buffer_denom)

        throttle = 1.0
        actions: list[str] = []
        if reserve_ratio < self.reserve_cash_ratio:
            shortage = max(0.0, self.reserve_cash_ratio - reserve_ratio)
            throttle *= max(0.1, 1.0 - shortage * 3.0)
            actions.append("increase_cash_reserve")
        if margin_buffer < self.min_margin_buffer:
            deficit = max(0.0, self.min_margin_buffer - margin_buffer)
            throttle *= max(0.1, 1.0 - deficit * 0.5)
            actions.append("reduce_open_exposure")
        if drawdown_pct <= -3.0:
            throttle *= 0.7
            actions.append("drawdown_treasury_de_risk")
        if open_notional > total * 1.2:
            throttle *= 0.65
            actions.append("inventory_too_large")

        throttle = max(0.05, min(1.0, throttle))
        allowed = throttle > 0.08
        reason = "ok" if allowed else "treasury_block"
        return TreasuryDecision(
            allowed=allowed,
            throttle_scale=throttle,
            reason=reason,
            reserve_ratio=reserve_ratio,
            margin_buffer=margin_buffer,
            actions=actions,
        )
