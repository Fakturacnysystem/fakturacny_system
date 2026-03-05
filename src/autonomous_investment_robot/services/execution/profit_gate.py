from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal


AccountingMethod = Literal["fifo", "average"]


@dataclass
class PositionLot:
    qty: float
    entry_price: float
    entry_fee_quote: float = 0.0
    funding_quote: float = 0.0
    interest_quote: float = 0.0
    opened_ts: float | None = None


@dataclass
class ProfitGateConfig:
    min_net_profit_ratio: float = 0.02
    default_entry_fee_bps: float = 0.0
    default_exit_fee_bps: float = 0.0
    default_slippage_bps: float = 1.0
    default_funding_bps: float = 0.0
    default_margin_interest_bps: float = 0.0
    accounting_method: AccountingMethod = "fifo"

    def __post_init__(self) -> None:
        # Hard global floor: do not allow lowering below +2% net target.
        self.min_net_profit_ratio = max(0.02, float(self.min_net_profit_ratio))
        method = str(self.accounting_method).strip().lower()
        self.accounting_method = "average" if method == "average" else "fifo"


@dataclass
class ProfitGateDecision:
    allowed: bool
    reason: str
    required_exit_price: float
    matched_qty: float
    eligible_qty: float
    min_profit_ratio: float


@dataclass
class _MatchedLot:
    qty: float
    entry_price: float
    entry_fee_quote: float
    funding_quote: float
    interest_quote: float


def _round_up_to_tick(value: float, tick_size: float) -> float:
    if tick_size <= 0.0:
        return float(value)
    return math.ceil(float(value) / tick_size) * tick_size


def _round_down_to_tick(value: float, tick_size: float) -> float:
    if tick_size <= 0.0:
        return float(value)
    return math.floor(float(value) / tick_size) * tick_size


class ProfitGate:
    def __init__(self, config: ProfitGateConfig | None = None) -> None:
        self.config = config or ProfitGateConfig()

    def _rates(
        self,
        *,
        entry_fee_bps: float | None = None,
        exit_fee_bps: float | None = None,
        slippage_bps: float | None = None,
        funding_bps: float | None = None,
        interest_bps: float | None = None,
    ) -> tuple[float, float]:
        e_fee = self.config.default_entry_fee_bps if entry_fee_bps is None else float(entry_fee_bps)
        x_fee = self.config.default_exit_fee_bps if exit_fee_bps is None else float(exit_fee_bps)
        slip = self.config.default_slippage_bps if slippage_bps is None else float(slippage_bps)
        fund = self.config.default_funding_bps if funding_bps is None else float(funding_bps)
        intr = self.config.default_margin_interest_bps if interest_bps is None else float(interest_bps)
        entry_rate = max(0.0, e_fee + slip) / 10000.0
        exit_rate = max(0.0, x_fee + slip + fund + intr) / 10000.0
        return entry_rate, exit_rate

    def _sanitize_lots(self, lots: list[PositionLot]) -> list[PositionLot]:
        out: list[PositionLot] = []
        for lot in lots:
            qty = max(0.0, float(lot.qty))
            px = max(0.0, float(lot.entry_price))
            if qty <= 0.0 or px <= 0.0:
                continue
            out.append(
                PositionLot(
                    qty=qty,
                    entry_price=px,
                    entry_fee_quote=max(0.0, float(lot.entry_fee_quote)),
                    funding_quote=float(lot.funding_quote),
                    interest_quote=float(lot.interest_quote),
                    opened_ts=lot.opened_ts,
                )
            )
        return out

    def _match_lots(self, lots: list[PositionLot], qty: float, method: AccountingMethod) -> tuple[list[_MatchedLot], float]:
        q = max(0.0, float(qty))
        if q <= 0.0:
            return [], 0.0
        lots_s = self._sanitize_lots(lots)
        if not lots_s:
            return [], 0.0

        if method == "average":
            total_qty = sum(x.qty for x in lots_s)
            if total_qty <= 0.0:
                return [], 0.0
            matched_qty = min(q, total_qty)
            avg_entry = sum(x.entry_price * x.qty for x in lots_s) / total_qty
            avg_fee_q = sum(x.entry_fee_quote for x in lots_s) * (matched_qty / total_qty)
            avg_funding_q = sum(x.funding_quote for x in lots_s) * (matched_qty / total_qty)
            avg_interest_q = sum(x.interest_quote for x in lots_s) * (matched_qty / total_qty)
            return [
                _MatchedLot(
                    qty=matched_qty,
                    entry_price=avg_entry,
                    entry_fee_quote=avg_fee_q,
                    funding_quote=avg_funding_q,
                    interest_quote=avg_interest_q,
                )
            ], matched_qty

        rem = q
        out: list[_MatchedLot] = []
        for lot in lots_s:
            if rem <= 1e-12:
                break
            take = min(rem, lot.qty)
            ratio = take / lot.qty
            out.append(
                _MatchedLot(
                    qty=take,
                    entry_price=lot.entry_price,
                    entry_fee_quote=lot.entry_fee_quote * ratio,
                    funding_quote=lot.funding_quote * ratio,
                    interest_quote=lot.interest_quote * ratio,
                )
            )
            rem -= take
        return out, q - rem

    def required_exit_price_long(
        self,
        *,
        lots: list[PositionLot],
        exit_qty: float,
        tick_size: float = 0.0,
        min_profit_ratio: float | None = None,
        entry_fee_bps: float | None = None,
        exit_fee_bps: float | None = None,
        slippage_bps: float | None = None,
        funding_bps: float | None = None,
        interest_bps: float | None = None,
        extra_exit_cost_quote: float = 0.0,
        accounting_method: AccountingMethod | None = None,
    ) -> tuple[float, float]:
        method = self.config.accounting_method if accounting_method is None else accounting_method
        target = self.config.min_net_profit_ratio if min_profit_ratio is None else max(0.02, float(min_profit_ratio))
        matched, matched_qty = self._match_lots(lots, exit_qty, method)
        if matched_qty <= 0.0:
            return float("inf"), 0.0
        entry_rate, exit_rate = self._rates(
            entry_fee_bps=entry_fee_bps,
            exit_fee_bps=exit_fee_bps,
            slippage_bps=slippage_bps,
            funding_bps=funding_bps,
            interest_bps=interest_bps,
        )
        den = max(1e-9, 1.0 - exit_rate)
        req = 0.0
        for lot in matched:
            unit_entry_fee = lot.entry_fee_quote / max(lot.qty, 1e-9)
            unit_carry = (lot.funding_quote + lot.interest_quote) / max(lot.qty, 1e-9)
            unit_entry_cost = (lot.entry_price * (1.0 + entry_rate)) + unit_entry_fee + unit_carry
            lot_req = (unit_entry_cost * (1.0 + target)) / den
            req = max(req, lot_req)
        if extra_exit_cost_quote > 0.0:
            req += (float(extra_exit_cost_quote) / max(matched_qty, 1e-9)) / den
        req = _round_up_to_tick(req, max(0.0, float(tick_size)))
        return req, matched_qty

    def required_exit_price_short(
        self,
        *,
        lots: list[PositionLot],
        close_qty: float,
        tick_size: float = 0.0,
        min_profit_ratio: float | None = None,
        entry_fee_bps: float | None = None,
        exit_fee_bps: float | None = None,
        slippage_bps: float | None = None,
        funding_bps: float | None = None,
        interest_bps: float | None = None,
        extra_exit_cost_quote: float = 0.0,
        accounting_method: AccountingMethod | None = None,
    ) -> tuple[float, float]:
        method = self.config.accounting_method if accounting_method is None else accounting_method
        target = self.config.min_net_profit_ratio if min_profit_ratio is None else max(0.02, float(min_profit_ratio))
        matched, matched_qty = self._match_lots(lots, close_qty, method)
        if matched_qty <= 0.0:
            return 0.0, 0.0
        entry_rate, exit_rate = self._rates(
            entry_fee_bps=entry_fee_bps,
            exit_fee_bps=exit_fee_bps,
            slippage_bps=slippage_bps,
            funding_bps=funding_bps,
            interest_bps=interest_bps,
        )
        den = max(1e-9, 1.0 + exit_rate)
        max_exit = float("inf")
        for lot in matched:
            unit_entry_fee = lot.entry_fee_quote / max(lot.qty, 1e-9)
            unit_carry = (lot.funding_quote + lot.interest_quote) / max(lot.qty, 1e-9)
            unit_entry_net = (lot.entry_price * (1.0 - entry_rate)) - unit_entry_fee - unit_carry
            min_pnl = lot.entry_price * target
            lot_max_exit = (unit_entry_net - min_pnl) / den
            max_exit = min(max_exit, lot_max_exit)
        if extra_exit_cost_quote > 0.0:
            max_exit -= (float(extra_exit_cost_quote) / max(matched_qty, 1e-9)) / den
        max_exit = max(0.0, _round_down_to_tick(max_exit, max(0.0, float(tick_size))))
        return max_exit, matched_qty

    def max_closable_qty_long(
        self,
        *,
        lots: list[PositionLot],
        exit_price: float,
        tick_size: float = 0.0,
        min_profit_ratio: float | None = None,
        entry_fee_bps: float | None = None,
        exit_fee_bps: float | None = None,
        slippage_bps: float | None = None,
        funding_bps: float | None = None,
        interest_bps: float | None = None,
        accounting_method: AccountingMethod | None = None,
    ) -> float:
        px = max(0.0, float(exit_price))
        method = self.config.accounting_method if accounting_method is None else accounting_method
        lots_s = self._sanitize_lots(lots)
        if not lots_s or px <= 0.0:
            return 0.0

        if method == "average":
            total_qty = sum(l.qty for l in lots_s)
            required, matched = self.required_exit_price_long(
                lots=lots_s,
                exit_qty=total_qty,
                tick_size=tick_size,
                min_profit_ratio=min_profit_ratio,
                entry_fee_bps=entry_fee_bps,
                exit_fee_bps=exit_fee_bps,
                slippage_bps=slippage_bps,
                funding_bps=funding_bps,
                interest_bps=interest_bps,
                accounting_method="average",
            )
            return matched if px + 1e-12 >= required else 0.0

        closable = 0.0
        for lot in lots_s:
            req, matched = self.required_exit_price_long(
                lots=[lot],
                exit_qty=lot.qty,
                tick_size=tick_size,
                min_profit_ratio=min_profit_ratio,
                entry_fee_bps=entry_fee_bps,
                exit_fee_bps=exit_fee_bps,
                slippage_bps=slippage_bps,
                funding_bps=funding_bps,
                interest_bps=interest_bps,
                accounting_method="fifo",
            )
            if matched <= 0.0:
                continue
            if px + 1e-12 < req:
                break
            closable += matched
        return max(0.0, closable)

    def max_closable_qty_short(
        self,
        *,
        lots: list[PositionLot],
        exit_price: float,
        tick_size: float = 0.0,
        min_profit_ratio: float | None = None,
        entry_fee_bps: float | None = None,
        exit_fee_bps: float | None = None,
        slippage_bps: float | None = None,
        funding_bps: float | None = None,
        interest_bps: float | None = None,
        accounting_method: AccountingMethod | None = None,
    ) -> float:
        px = max(0.0, float(exit_price))
        method = self.config.accounting_method if accounting_method is None else accounting_method
        lots_s = self._sanitize_lots(lots)
        if not lots_s or px <= 0.0:
            return 0.0

        if method == "average":
            total_qty = sum(l.qty for l in lots_s)
            max_exit, matched = self.required_exit_price_short(
                lots=lots_s,
                close_qty=total_qty,
                tick_size=tick_size,
                min_profit_ratio=min_profit_ratio,
                entry_fee_bps=entry_fee_bps,
                exit_fee_bps=exit_fee_bps,
                slippage_bps=slippage_bps,
                funding_bps=funding_bps,
                interest_bps=interest_bps,
                accounting_method="average",
            )
            return matched if px <= max_exit + 1e-12 else 0.0

        closable = 0.0
        for lot in lots_s:
            max_exit, matched = self.required_exit_price_short(
                lots=[lot],
                close_qty=lot.qty,
                tick_size=tick_size,
                min_profit_ratio=min_profit_ratio,
                entry_fee_bps=entry_fee_bps,
                exit_fee_bps=exit_fee_bps,
                slippage_bps=slippage_bps,
                funding_bps=funding_bps,
                interest_bps=interest_bps,
                accounting_method="fifo",
            )
            if matched <= 0.0:
                continue
            if px > (max_exit + 1e-12):
                break
            closable += matched
        return max(0.0, closable)

    def can_close_long(
        self,
        *,
        lots: list[PositionLot],
        exit_price: float,
        exit_qty: float,
        tick_size: float = 0.0,
        min_profit_ratio: float | None = None,
        entry_fee_bps: float | None = None,
        exit_fee_bps: float | None = None,
        slippage_bps: float | None = None,
        funding_bps: float | None = None,
        interest_bps: float | None = None,
        extra_exit_cost_quote: float = 0.0,
        accounting_method: AccountingMethod | None = None,
    ) -> ProfitGateDecision:
        required, matched_qty = self.required_exit_price_long(
            lots=lots,
            exit_qty=exit_qty,
            tick_size=tick_size,
            min_profit_ratio=min_profit_ratio,
            entry_fee_bps=entry_fee_bps,
            exit_fee_bps=exit_fee_bps,
            slippage_bps=slippage_bps,
            funding_bps=funding_bps,
            interest_bps=interest_bps,
            extra_exit_cost_quote=extra_exit_cost_quote,
            accounting_method=accounting_method,
        )
        px = max(0.0, float(exit_price))
        target = self.config.min_net_profit_ratio if min_profit_ratio is None else max(0.02, float(min_profit_ratio))
        if matched_qty <= 0.0 or not math.isfinite(required):
            return ProfitGateDecision(
                allowed=False,
                reason="missing_cost_basis",
                required_exit_price=required,
                matched_qty=matched_qty,
                eligible_qty=0.0,
                min_profit_ratio=target,
            )
        if px + 1e-12 >= required:
            return ProfitGateDecision(
                allowed=True,
                reason="ok",
                required_exit_price=required,
                matched_qty=matched_qty,
                eligible_qty=matched_qty,
                min_profit_ratio=target,
            )
        eligible = self.max_closable_qty_long(
            lots=lots,
            exit_price=px,
            tick_size=tick_size,
            min_profit_ratio=target,
            entry_fee_bps=entry_fee_bps,
            exit_fee_bps=exit_fee_bps,
            slippage_bps=slippage_bps,
            funding_bps=funding_bps,
            interest_bps=interest_bps,
            accounting_method=accounting_method,
        )
        return ProfitGateDecision(
            allowed=False,
            reason="profit_gate_block",
            required_exit_price=required,
            matched_qty=matched_qty,
            eligible_qty=eligible,
            min_profit_ratio=target,
        )

    def can_close_short(
        self,
        *,
        lots: list[PositionLot],
        exit_price: float,
        close_qty: float,
        tick_size: float = 0.0,
        min_profit_ratio: float | None = None,
        entry_fee_bps: float | None = None,
        exit_fee_bps: float | None = None,
        slippage_bps: float | None = None,
        funding_bps: float | None = None,
        interest_bps: float | None = None,
        extra_exit_cost_quote: float = 0.0,
        accounting_method: AccountingMethod | None = None,
    ) -> ProfitGateDecision:
        max_exit, matched_qty = self.required_exit_price_short(
            lots=lots,
            close_qty=close_qty,
            tick_size=tick_size,
            min_profit_ratio=min_profit_ratio,
            entry_fee_bps=entry_fee_bps,
            exit_fee_bps=exit_fee_bps,
            slippage_bps=slippage_bps,
            funding_bps=funding_bps,
            interest_bps=interest_bps,
            extra_exit_cost_quote=extra_exit_cost_quote,
            accounting_method=accounting_method,
        )
        px = max(0.0, float(exit_price))
        target = self.config.min_net_profit_ratio if min_profit_ratio is None else max(0.02, float(min_profit_ratio))
        if matched_qty <= 0.0 or not math.isfinite(max_exit):
            return ProfitGateDecision(
                allowed=False,
                reason="missing_cost_basis",
                required_exit_price=max_exit,
                matched_qty=matched_qty,
                eligible_qty=0.0,
                min_profit_ratio=target,
            )
        if px <= max_exit + 1e-12:
            return ProfitGateDecision(
                allowed=True,
                reason="ok",
                required_exit_price=max_exit,
                matched_qty=matched_qty,
                eligible_qty=matched_qty,
                min_profit_ratio=target,
            )
        eligible = self.max_closable_qty_short(
            lots=lots,
            exit_price=px,
            tick_size=tick_size,
            min_profit_ratio=target,
            entry_fee_bps=entry_fee_bps,
            exit_fee_bps=exit_fee_bps,
            slippage_bps=slippage_bps,
            funding_bps=funding_bps,
            interest_bps=interest_bps,
            accounting_method=accounting_method,
        )
        return ProfitGateDecision(
            allowed=False,
            reason="profit_gate_block",
            required_exit_price=max_exit,
            matched_qty=matched_qty,
            eligible_qty=eligible,
            min_profit_ratio=target,
        )
