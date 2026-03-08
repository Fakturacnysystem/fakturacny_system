from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SizingDecision:
    allowed: bool
    reason: str
    trade_notional_quote: float
    risk_budget_quote: float
    effective_min_quote: float


class SizingService:
    def __init__(
        self,
        *,
        reserve_ratio: float = 0.15,
        sizing_fraction: float = 0.25,
        per_symbol_cap_ratio: float = 0.5,
    ) -> None:
        self.reserve_ratio = max(0.0, min(0.95, float(reserve_ratio)))
        self.sizing_fraction = max(0.01, min(1.0, float(sizing_fraction)))
        self.per_symbol_cap_ratio = max(0.01, min(1.0, float(per_symbol_cap_ratio)))

    def decide(
        self,
        *,
        free_quote: float,
        effective_min_quote: float,
        explicit_cap_quote: float | None = None,
    ) -> SizingDecision:
        free = max(0.0, float(free_quote))
        eff_min = max(0.0, float(effective_min_quote))
        risk_budget = free * (1.0 - self.reserve_ratio)
        if risk_budget <= 0.0:
            return SizingDecision(
                allowed=False,
                reason="insufficient_quote_for_min_order",
                trade_notional_quote=0.0,
                risk_budget_quote=float(risk_budget),
                effective_min_quote=float(eff_min),
            )
        cap = risk_budget * self.per_symbol_cap_ratio
        if explicit_cap_quote is not None and explicit_cap_quote > 0.0:
            cap = min(cap, float(explicit_cap_quote))
        target = risk_budget * self.sizing_fraction
        target = min(max(target, eff_min), max(0.0, cap))
        if target + 1e-12 < eff_min:
            return SizingDecision(
                allowed=False,
                reason="insufficient_quote_for_min_order",
                trade_notional_quote=float(target),
                risk_budget_quote=float(risk_budget),
                effective_min_quote=float(eff_min),
            )
        return SizingDecision(
            allowed=True,
            reason="ok",
            trade_notional_quote=float(target),
            risk_budget_quote=float(risk_budget),
            effective_min_quote=float(eff_min),
        )

