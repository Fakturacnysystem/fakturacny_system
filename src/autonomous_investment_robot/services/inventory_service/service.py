from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import InventoryLot, InventoryState, ReserveState
from autonomous_investment_robot.services.execution.service import Fill


class InventoryService:
    def __init__(self) -> None:
        self._lots: dict[str, list[InventoryLot]] = {}

    def clear(self) -> None:
        self._lots = {}

    def lots(self, symbol: str) -> list[InventoryLot]:
        return [InventoryLot(**asdict(lot)) for lot in self._lots.get(symbol, [])]

    def update_from_fill(
        self,
        fill: Fill,
        *,
        ts: datetime | None = None,
        expected_exit_cost_bps: float = 0.0,
        reserve_quote: float = 0.0,
    ) -> list[InventoryLot]:
        ts = ts or datetime.now(timezone.utc)
        lots = self._lots.setdefault(fill.symbol, [])
        remaining = float(fill.notional)
        if fill.side == "buy":
            lots.append(
                InventoryLot(
                    symbol=fill.symbol,
                    venue=fill.venue,
                    side="buy",
                    opened_ts=ts,
                    remaining_notional=remaining,
                    entry_notional=fill.notional,
                    fees_paid=fill.fee + fill.slippage_cost,
                    expected_exit_cost_bps=expected_exit_cost_bps,
                    reserved_quote=reserve_quote,
                    source_fill_id=fill.fill_id,
                    source_order_id=fill.order_id,
                    metadata=dict(fill.metadata),
                )
            )
        else:
            for lot in lots:
                if remaining <= 0.0:
                    break
                if lot.remaining_notional <= 0.0 or lot.side != "buy":
                    continue
                reduce_by = min(lot.remaining_notional, remaining)
                lot.remaining_notional -= reduce_by
                remaining -= reduce_by
            if remaining > 0.0:
                lots.append(
                    InventoryLot(
                        symbol=fill.symbol,
                        venue=fill.venue,
                        side="sell",
                        opened_ts=ts,
                        remaining_notional=remaining,
                        entry_notional=remaining,
                        fees_paid=fill.fee + fill.slippage_cost,
                        expected_exit_cost_bps=expected_exit_cost_bps,
                        reserved_quote=0.0,
                        source_fill_id=fill.fill_id,
                        source_order_id=fill.order_id,
                        metadata={**dict(fill.metadata), "synthetic_short_lot": True},
                    )
                )
        self._lots[fill.symbol] = [lot for lot in lots if lot.remaining_notional > 1e-9]
        return self.lots(fill.symbol)

    def rehydrate_from_events(self, fill_events: list[dict[str, Any]]) -> None:
        self.clear()
        for event in fill_events:
            payload = event.get("payload", event) if isinstance(event, dict) else {}
            if not isinstance(payload, dict):
                continue
            try:
                fill = Fill(
                    venue=str(payload.get("venue", "paper")),
                    order_id=str(payload.get("order_id", payload.get("orderId", ""))),
                    fill_id=str(payload.get("fill_id", payload.get("fillId", ""))),
                    symbol=str(payload.get("symbol", "")),
                    side=str(payload.get("side", "")),
                    notional=float(payload.get("notional", 0.0)),
                    fee=float(payload.get("fee", 0.0)),
                    slippage_cost=float(payload.get("slippage_cost", payload.get("slippageCost", 0.0))),
                    latency_ms=int(payload.get("latency_ms", payload.get("latencyMs", 0))),
                    status=str(payload.get("status", "")),
                    metadata=dict(payload.get("metadata", {})) if isinstance(payload.get("metadata", {}), dict) else {},
                )
            except Exception:
                continue
            if fill.notional <= 0.0 or not fill.symbol:
                continue
            expected_exit_cost_bps = float(payload.get("expected_exit_cost_bps", 0.0))
            reserve_quote = float(payload.get("reserved_quote", 0.0))
            self.update_from_fill(fill, expected_exit_cost_bps=expected_exit_cost_bps, reserve_quote=reserve_quote)

    def inventory_pressure(
        self,
        *,
        symbol: str,
        ts: datetime,
        opportunity_cost_score: float = 0.0,
        unrealized_pnl: float = 0.0,
        truth_pressure: float = 0.0,
        execution_fragility: float = 0.0,
    ) -> InventoryState:
        lots = [lot for lot in self._lots.get(symbol, []) if lot.remaining_notional > 1e-9]
        if not lots:
            return InventoryState(symbol=symbol, ts=ts)
        ages = [max(0.0, (ts - lot.opened_ts).total_seconds()) for lot in lots]
        gross = sum(abs(lot.remaining_notional) for lot in lots)
        oldest = max(ages)
        weighted_age = 0.0 if gross <= 0.0 else sum(age * abs(lot.remaining_notional) for age, lot in zip(ages, lots)) / gross
        age_pressure = max(0.0, min(1.0, weighted_age / 3600.0 / 12.0))
        unrealized_draw_pressure = max(0.0, min(1.0, abs(min(0.0, unrealized_pnl)) / max(gross, 1.0)))
        truth_fragility = max(0.0, min(1.0, truth_pressure))
        execution_pressure = max(0.0, min(1.0, execution_fragility))
        stale_score = max(
            age_pressure,
            min(
                1.0,
                age_pressure * 0.45
                + max(0.0, min(1.0, opportunity_cost_score)) * 0.2
                + unrealized_draw_pressure * 0.15
                + truth_fragility * 0.1
                + execution_pressure * 0.1,
            ),
        )
        return InventoryState(
            symbol=symbol,
            ts=ts,
            open_lots=self.lots(symbol),
            gross_open_notional=gross,
            stale_inventory_score=stale_score,
            oldest_age_seconds=oldest,
            weighted_age_seconds=weighted_age,
            opportunity_cost_pressure=max(0.0, min(1.0, opportunity_cost_score)),
            unrealized_draw_pressure=unrealized_draw_pressure,
            truth_fragility_pressure=truth_fragility,
            execution_fragility_pressure=execution_pressure,
            metadata={
                "age_pressure": age_pressure,
                "lot_count": len(lots),
            },
        )

    def reserve_state(
        self,
        *,
        ts: datetime,
        exchange_balance: float,
        local_cash_delta: float,
        gross_exposure_notional: float,
        minimum_reserve_pct: float,
        capital_floor: float = 0.0,
    ) -> ReserveState:
        total_capital = max(exchange_balance, capital_floor, abs(local_cash_delta) + gross_exposure_notional, 1.0)
        free_quote = max(0.0, total_capital - gross_exposure_notional)
        reserve_pct = free_quote / max(total_capital, 1.0)
        reasons: list[str] = []
        breached = reserve_pct < minimum_reserve_pct
        if breached:
            reasons.append("free_quote_reserve_breached")
        return ReserveState(
            ts=ts,
            total_capital=total_capital,
            free_quote=free_quote,
            free_quote_reserve_pct=reserve_pct,
            minimum_reserve_pct=minimum_reserve_pct,
            reserve_breached=breached,
            reasons=reasons,
        )
