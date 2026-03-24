from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from autonomous_investment_robot.core.contracts import AccountStateSnapshot, PortfolioAllocation, PortfolioLedgerEntry, PortfolioStateSnapshot
from autonomous_investment_robot.services.execution.service import Fill


class PortfolioService:
    def __init__(self) -> None:
        self._ledger: list[PortfolioLedgerEntry] = []
        self._state: dict[str, PortfolioStateSnapshot] = {}
        self._baseline_balance: float | None = None
        self._exchange_balance: float | None = None

    def recommend_allocation(
        self,
        *,
        symbol: str,
        ts: datetime,
        base_budget: float,
        expected_edge_bps: float,
        confidence: float,
        uncertainty: float,
        realized_vol: float,
        depth_notional: float,
        current_exposure: float,
        drawdown_pct: float,
        regime_fit: float,
    ) -> PortfolioAllocation:
        volatility_scalar = max(0.2, min(1.0, 0.02 / max(realized_vol, 0.0001)))
        liquidity_scalar = max(0.2, min(1.0, depth_notional / max(base_budget * 10.0, 1.0)))
        concentration_score = min(1.0, current_exposure / max(base_budget, 1.0))
        drawdown_scalar = max(0.2, min(1.0, 1.0 + min(0.0, drawdown_pct) / 20.0))
        confidence_scalar = max(0.2, min(1.0, confidence))
        uncertainty_scalar = max(0.2, 1.0 - min(1.0, uncertainty))
        regime_scalar = max(0.25, min(1.0, regime_fit))
        opportunity_cost = max(0.0, min(1.0, concentration_score * 0.5 + uncertainty * 0.5))
        edge_scalar = max(0.2, min(1.0, expected_edge_bps / 20.0 if expected_edge_bps > 0 else 0.2))
        recommended = base_budget * volatility_scalar * liquidity_scalar * drawdown_scalar * confidence_scalar * uncertainty_scalar * regime_scalar * edge_scalar
        return PortfolioAllocation(
            symbol=symbol,
            ts=ts,
            recommended_notional=max(0.0, recommended),
            concentration_score=concentration_score,
            opportunity_cost_score=opportunity_cost,
            volatility_scalar=volatility_scalar,
            liquidity_scalar=liquidity_scalar,
            drawdown_scalar=drawdown_scalar,
            regime_scalar=regime_scalar,
            confidence_scalar=confidence_scalar,
            uncertainty_scalar=uncertainty_scalar,
            reasons={
                "base_budget": base_budget,
                "expected_edge_bps": expected_edge_bps,
                "current_exposure": current_exposure,
            },
        )

    def record_fill(
        self,
        fill: Fill,
        *,
        realized_pnl: float = 0.0,
        venue: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> PortfolioStateSnapshot:
        ts = datetime.now(timezone.utc)
        signed_notional = fill.notional if fill.side == "buy" else -fill.notional
        combined_metadata = {"order_id": fill.order_id, "status": fill.status, **fill.metadata}
        if metadata:
            combined_metadata.update(metadata)
        entry = PortfolioLedgerEntry(
            ts=ts,
            symbol=fill.symbol,
            entry_type="fill",
            quantity=signed_notional,
            notional=fill.notional,
            fee=fill.fee,
            slippage_cost=fill.slippage_cost,
            realized_pnl=realized_pnl,
            venue=venue or fill.venue,
            reference_id=fill.fill_id,
            metadata=combined_metadata,
        )
        self._ledger.append(entry)
        prior = self._state.get(fill.symbol)
        exposure = (prior.exposure_notional if prior else 0.0) + signed_notional
        state = PortfolioStateSnapshot(
            ts=ts,
            symbol=fill.symbol,
            exposure_notional=exposure,
            net_quantity=exposure,
            cash_balance=(prior.cash_balance if prior else 0.0) - fill.fee - fill.slippage_cost + realized_pnl,
            realized_pnl=(prior.realized_pnl if prior else 0.0) + realized_pnl,
            unrealized_pnl=prior.unrealized_pnl if prior else 0.0,
            cumulative_fees=(prior.cumulative_fees if prior else 0.0) + fill.fee,
            cumulative_slippage=(prior.cumulative_slippage if prior else 0.0) + fill.slippage_cost,
            fill_count=(prior.fill_count if prior else 0) + 1,
            metadata={"last_fill_status": fill.status, **({} if metadata is None else metadata)},
        )
        self._state[fill.symbol] = state
        return state

    def seed_account_balance(self, balance_total: float) -> None:
        if balance_total <= 0.0:
            return
        if self._baseline_balance is None:
            self._baseline_balance = balance_total
        self._exchange_balance = balance_total

    def account_snapshot(
        self,
        *,
        venue: str = "paper",
        exchange_balance: float | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AccountStateSnapshot:
        if exchange_balance is not None and exchange_balance > 0.0:
            self.seed_account_balance(exchange_balance)
        local_cash_delta = sum(state.cash_balance for state in self._state.values())
        realized_pnl = sum(state.realized_pnl for state in self._state.values())
        unrealized_pnl = sum(state.unrealized_pnl for state in self._state.values())
        gross_exposure = sum(abs(state.exposure_notional) for state in self._state.values())
        cumulative_fees = sum(state.cumulative_fees for state in self._state.values())
        cumulative_slippage = sum(state.cumulative_slippage for state in self._state.values())
        fill_count = sum(state.fill_count for state in self._state.values())
        snapshot = AccountStateSnapshot(
            ts=datetime.now(timezone.utc),
            venue=venue,
            baseline_balance=self._baseline_balance or 0.0,
            exchange_balance=self._exchange_balance or 0.0,
            local_cash_delta=local_cash_delta,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            gross_exposure_notional=gross_exposure,
            cumulative_fees=cumulative_fees,
            cumulative_slippage=cumulative_slippage,
            fill_count=fill_count,
            metadata={} if metadata is None else dict(metadata),
        )
        return snapshot

    def mark_to_market(self, symbol: str, unrealized_pnl: float) -> PortfolioStateSnapshot:
        ts = datetime.now(timezone.utc)
        prior = self._state.get(symbol)
        if prior is None:
            state = PortfolioStateSnapshot(ts=ts, symbol=symbol, exposure_notional=0.0, net_quantity=0.0, cash_balance=0.0, realized_pnl=0.0, unrealized_pnl=unrealized_pnl, cumulative_fees=0.0, cumulative_slippage=0.0, fill_count=0)
        else:
            state = PortfolioStateSnapshot(
                ts=ts,
                symbol=symbol,
                exposure_notional=prior.exposure_notional,
                net_quantity=prior.net_quantity,
                cash_balance=prior.cash_balance,
                realized_pnl=prior.realized_pnl,
                unrealized_pnl=unrealized_pnl,
                cumulative_fees=prior.cumulative_fees,
                cumulative_slippage=prior.cumulative_slippage,
                fill_count=prior.fill_count,
                metadata=dict(prior.metadata),
            )
        self._state[symbol] = state
        return state

    def snapshot(self, symbol: str) -> PortfolioStateSnapshot:
        return self._state.get(
            symbol,
            PortfolioStateSnapshot(
                ts=datetime.now(timezone.utc),
                symbol=symbol,
                exposure_notional=0.0,
                net_quantity=0.0,
                cash_balance=0.0,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
                cumulative_fees=0.0,
                cumulative_slippage=0.0,
                fill_count=0,
            ),
        )

    def rehydrate_from_events(
        self,
        *,
        fill_events: list[dict[str, object]] | None = None,
        position_events: list[dict[str, object]] | None = None,
        account_events: list[dict[str, object]] | None = None,
    ) -> dict[str, PortfolioStateSnapshot]:
        self._ledger = []
        self._state = {}
        self._baseline_balance = None
        self._exchange_balance = None

        for event in fill_events or []:
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
            if fill.notional <= 0.0 or not fill.symbol or not fill.fill_id:
                continue
            realized_pnl = float(payload.get("realized_pnl", payload.get("realizedPnl", 0.0)))
            extra_metadata = {
                "fee_authoritative": bool(payload.get("fee_authoritative", payload.get("feeAuthoritative", False))),
                "realized_pnl_authoritative": bool(payload.get("realized_pnl_authoritative", payload.get("realizedPnlAuthoritative", False))),
            }
            self.record_fill(fill, realized_pnl=realized_pnl, venue=fill.venue, metadata=extra_metadata)

        for event in position_events or []:
            payload = event.get("payload", event) if isinstance(event, dict) else {}
            if not isinstance(payload, dict):
                continue
            symbol = str(payload.get("symbol", ""))
            if not symbol:
                continue
            exposure = float(payload.get("exposure_notional", payload.get("exposureNotional", 0.0)))
            prior = self.snapshot(symbol)
            self._state[symbol] = PortfolioStateSnapshot(
                ts=datetime.now(timezone.utc),
                symbol=symbol,
                exposure_notional=exposure,
                net_quantity=exposure,
                cash_balance=prior.cash_balance,
                realized_pnl=prior.realized_pnl,
                unrealized_pnl=prior.unrealized_pnl,
                cumulative_fees=prior.cumulative_fees,
                cumulative_slippage=prior.cumulative_slippage,
                fill_count=prior.fill_count,
                metadata={**prior.metadata, "rehydrated_position_snapshot": True},
            )
        latest_account_payload: dict[str, object] | None = None
        for event in account_events or []:
            payload = event.get("payload", event) if isinstance(event, dict) else {}
            if isinstance(payload, dict):
                latest_account_payload = payload
        if latest_account_payload:
            baseline_balance = float(latest_account_payload.get("baseline_balance", latest_account_payload.get("baselineBalance", 0.0)))
            exchange_balance = float(latest_account_payload.get("exchange_balance", latest_account_payload.get("exchangeBalance", 0.0)))
            if baseline_balance > 0.0:
                self._baseline_balance = baseline_balance
            if exchange_balance > 0.0:
                self._exchange_balance = exchange_balance
        return dict(self._state)

    def ledger_rows(self) -> list[dict[str, object]]:
        return [asdict(entry) for entry in self._ledger]

    def state_rows(self) -> list[dict[str, object]]:
        return [asdict(state) for state in self._state.values()]

    def account_row(self, *, venue: str = "paper", exchange_balance: float | None = None, metadata: dict[str, object] | None = None) -> dict[str, object]:
        return asdict(self.account_snapshot(venue=venue, exchange_balance=exchange_balance, metadata=metadata))
