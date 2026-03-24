from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import AccountStateSnapshot, RecoveryDecision, TradeForensicsContext, TruthConfidence, TruthConfidenceLevel, TruthConfidenceSnapshot, UnrealizedPnlTruth
from autonomous_investment_robot.services.event_store.service import EventStore
from autonomous_investment_robot.services.live_runtime.ledger import (
    NormalizedLiveFillRecord,
    extract_exchange_balance_total,
    extract_exchange_unrealized_pnl_truth,
)
from autonomous_investment_robot.services.portfolio_service.service import PortfolioService
from autonomous_investment_robot.services.reconciliation.service import ReconciliationOutcome, ReconciliationService
from autonomous_investment_robot.services.replay.events import AccountEvent, FillEvent, OrderEvent, PositionEvent, RecoveryEvent, RiskEvent, TruthEvent, make_event


@dataclass(frozen=True)
class LiveExchangeState:
    balance_total: float | None
    exposure_notional: float
    unrealized_pnl: float
    unrealized_pnl_truth: UnrealizedPnlTruth
    open_order_count: int
    position_count: int


@dataclass(frozen=True)
class LiveRehydrationResult:
    confidence: str
    details: dict[str, Any]


@dataclass(frozen=True)
class LiveLedgerApplyResult:
    exposure_notional: float
    account_snapshot: AccountStateSnapshot
    fill_truth_ok: bool
    gap_reasons: list[str]


def _confidence(
    domain: str,
    level: TruthConfidenceLevel,
    reason: str,
    **evidence: Any,
) -> TruthConfidence:
    return TruthConfidence(domain=domain, level=level, reason=reason, evidence=evidence)


def _truth_snapshot_dict(snapshot: TruthConfidenceSnapshot) -> dict[str, Any]:
    out = asdict(snapshot)
    for key in (
        "fill_truth_confidence",
        "fee_truth_confidence",
        "realized_pnl_confidence",
        "balance_truth_confidence",
        "exposure_truth_confidence",
        "market_data_truth_confidence",
        "unrealized_pnl_confidence",
    ):
        if key in out and isinstance(out[key], dict):
            raw = snapshot.__dict__.get(key)
            if raw is not None:
                out[key]["level"] = raw.level.value
    return out


class LiveStateCoordinator:
    def __init__(self, event_store: EventStore, portfolio: PortfolioService, recon: ReconciliationService, inventory: Any | None = None) -> None:
        self.event_store = event_store
        self.portfolio = portfolio
        self.recon = recon
        self.inventory = inventory

    def exchange_state(self, live: object, symbol: str) -> LiveExchangeState:
        positions = live.connector.position_risk(symbol)  # type: ignore[attr-defined]
        exposure = 0.0
        count = 0
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            amt = abs(float(pos.get("positionAmt", pos.get("size", pos.get("qty", 0.0)))))
            mark = abs(float(pos.get("markPrice", pos.get("mark", pos.get("price", 0.0)))))
            if amt <= 0.0:
                continue
            exposure += amt * mark
            count += 1
        if hasattr(live, "authoritative_unrealized_pnl"):
            unrealized_truth, gaps = live.authoritative_unrealized_pnl(symbol)  # type: ignore[attr-defined]
            if unrealized_truth is None:
                unrealized_truth = UnrealizedPnlTruth(
                    symbol=symbol,
                    ts=datetime.now(timezone.utc),
                    source="provider_hook_missing",
                    confidence="unavailable",
                    venue_value=None,
                    reason="provider_unrealized_hook_returned_none",
                    evidence={"gaps": list(gaps)},
                )
            elif gaps:
                unrealized_truth.evidence.setdefault("gaps", list(gaps))
        else:
            unrealized_truth = extract_exchange_unrealized_pnl_truth(positions, symbol=symbol)
        unrealized_pnl = float(unrealized_truth.venue_value or 0.0)
        try:
            open_orders = live.connector.open_orders(symbol)  # type: ignore[attr-defined]
        except Exception:
            open_orders = []
        open_order_count = len(open_orders) if isinstance(open_orders, list) else 0
        balance_total = None
        if hasattr(live.connector, "balances"):  # type: ignore[attr-defined]
            try:
                balance_total = extract_exchange_balance_total(live.connector.balances())  # type: ignore[attr-defined]
            except Exception:
                balance_total = None
        if balance_total is not None:
            self.portfolio.seed_account_balance(balance_total)
        return LiveExchangeState(
            balance_total=balance_total,
            exposure_notional=exposure,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_truth=unrealized_truth,
            open_order_count=open_order_count,
            position_count=count,
        )

    def _baseline_since_ms(self, account_events: list[dict[str, Any]]) -> int | None:
        for event in account_events:
            if not isinstance(event, dict):
                continue
            payload = event.get("payload", event)
            if not isinstance(payload, dict):
                continue
            metadata = payload.get("metadata", {})
            if isinstance(metadata, dict):
                raw = metadata.get("baseline_recorded_at_ms")
                if raw is not None:
                    try:
                        return int(raw)
                    except Exception:
                        pass
            ts = event.get("ts")
            if isinstance(ts, str):
                try:
                    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
                except Exception:
                    continue
        return None

    def _latest_event_ts_ms(self, events: list[dict[str, Any]]) -> int | None:
        latest: int | None = None
        for event in events:
            if not isinstance(event, dict):
                continue
            ts = event.get("ts")
            if not isinstance(ts, str):
                continue
            try:
                current = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
            except Exception:
                continue
            latest = current if latest is None else max(latest, current)
        return latest

    def _history_since_ms(
        self,
        account_events: list[dict[str, Any]],
        fill_events: list[dict[str, Any]],
    ) -> int | None:
        baseline = self._baseline_since_ms(account_events)
        if baseline is not None:
            return baseline
        account_ts = self._latest_event_ts_ms(account_events)
        fill_ts = self._latest_event_ts_ms(fill_events)
        if account_ts is None:
            return fill_ts
        if fill_ts is None:
            return account_ts
        return max(account_ts, fill_ts)

    def truth_confidence(
        self,
        *,
        exchange: LiveExchangeState,
        fill_history_gaps: list[str] | None = None,
        realized_pnl_gaps: list[str] | None = None,
        unrealized_truth: UnrealizedPnlTruth | None = None,
        market_health: Any | None = None,
        history_since_ms: int | None = None,
        history_recovered: int = 0,
    ) -> TruthConfidenceSnapshot:
        fill_history_gaps = list(fill_history_gaps or [])
        realized_pnl_gaps = list(realized_pnl_gaps or [])

        fill_level = TruthConfidenceLevel.AUTHORITATIVE
        fill_reason = "native_fill_history_verified"
        if any(gap for gap in fill_history_gaps if gap not in {"fee_truth_gap", "realized_pnl_truth_gap"}):
            fill_level = TruthConfidenceLevel.UNAVAILABLE
            fill_reason = "native_fill_history_gap"
        elif history_since_ms is None and (exchange.position_count > 0 or exchange.open_order_count > 0 or history_recovered > 0):
            fill_level = TruthConfidenceLevel.PROXY
            fill_reason = "history_window_baseline_missing"

        fee_level = TruthConfidenceLevel.AUTHORITATIVE
        fee_reason = "native_fee_history_verified"
        if "fee_truth_gap" in fill_history_gaps:
            fee_level = TruthConfidenceLevel.UNAVAILABLE
            fee_reason = "native_fee_history_gap"
        elif fill_level == TruthConfidenceLevel.PROXY:
            fee_level = TruthConfidenceLevel.PROXY
            fee_reason = "fee_history_window_proxy"

        realized_level = TruthConfidenceLevel.AUTHORITATIVE
        realized_reason = "native_realized_pnl_verified"
        if realized_pnl_gaps == ["realized_pnl_proxy_balance_delta"]:
            realized_level = TruthConfidenceLevel.PROXY
            realized_reason = "realized_pnl_balance_proxy"
        elif "realized_pnl_truth_gap" in fill_history_gaps or realized_pnl_gaps:
            realized_level = TruthConfidenceLevel.UNAVAILABLE
            realized_reason = "native_realized_pnl_gap"
        elif fill_level == TruthConfidenceLevel.PROXY:
            realized_level = TruthConfidenceLevel.PROXY
            realized_reason = "realized_pnl_window_proxy"

        if exchange.balance_total is not None and exchange.balance_total > 0.0:
            balance_conf = _confidence(
                "balance_truth_confidence",
                TruthConfidenceLevel.AUTHORITATIVE,
                "exchange_balance_snapshot_available",
                balance_total=exchange.balance_total,
            )
        else:
            balance_conf = _confidence(
                "balance_truth_confidence",
                TruthConfidenceLevel.UNAVAILABLE,
                "exchange_balance_snapshot_missing",
            )

        exposure_conf = _confidence(
            "exposure_truth_confidence",
            TruthConfidenceLevel.AUTHORITATIVE,
            "exchange_position_snapshot_available",
            exposure_notional=exchange.exposure_notional,
            position_count=exchange.position_count,
            open_order_count=exchange.open_order_count,
        )

        if market_health is None:
            market_conf = _confidence(
                "market_data_truth_confidence",
                TruthConfidenceLevel.PROXY,
                "market_health_not_provided",
            )
        elif getattr(market_health, "feed_stale", False):
            market_conf = _confidence(
                "market_data_truth_confidence",
                TruthConfidenceLevel.UNAVAILABLE,
                "market_data_stale",
                reasons=list(getattr(market_health, "reasons", [])),
            )
        elif not getattr(market_health, "sequence_ok", True) or not getattr(market_health, "checksum_ok", True):
            market_conf = _confidence(
                "market_data_truth_confidence",
                TruthConfidenceLevel.PROXY,
                "market_data_integrity_degraded",
                reasons=list(getattr(market_health, "reasons", [])),
            )
        else:
            market_conf = _confidence(
                "market_data_truth_confidence",
                TruthConfidenceLevel.AUTHORITATIVE,
                "market_data_integrity_ok",
                symbol_health_score=float(getattr(market_health, "symbol_health_score", 0.0)),
                exchange_health_score=float(getattr(market_health, "exchange_health_score", 0.0)),
            )
        if unrealized_truth is None:
            unrealized_conf = _confidence(
                "unrealized_pnl_confidence",
                TruthConfidenceLevel.UNAVAILABLE,
                "unrealized_pnl_truth_missing",
            )
        else:
            unrealized_level = TruthConfidenceLevel(unrealized_truth.confidence)
            unrealized_conf = _confidence(
                "unrealized_pnl_confidence",
                unrealized_level,
                unrealized_truth.reason or "unrealized_pnl_truth_available",
                source=unrealized_truth.source,
                venue_value=unrealized_truth.venue_value,
                evidence=unrealized_truth.evidence,
            )

        fill_conf = _confidence(
            "fill_truth_confidence",
            fill_level,
            fill_reason,
            gaps=fill_history_gaps,
            history_since_ms=history_since_ms,
            history_recovered=history_recovered,
        )
        fee_conf = _confidence(
            "fee_truth_confidence",
            fee_level,
            fee_reason,
            gaps=[gap for gap in fill_history_gaps if gap == "fee_truth_gap"],
            history_since_ms=history_since_ms,
        )
        realized_conf = _confidence(
            "realized_pnl_confidence",
            realized_level,
            realized_reason,
            gaps=[*realized_pnl_gaps, *[gap for gap in fill_history_gaps if gap == "realized_pnl_truth_gap"]],
            history_since_ms=history_since_ms,
        )

        action = "continue"
        reasons: list[str] = []
        levels = {
            "fill": fill_conf.level,
            "fee": fee_conf.level,
            "realized_pnl": realized_conf.level,
            "balance": balance_conf.level,
            "exposure": exposure_conf.level,
            "market_data": market_conf.level,
            "unrealized_pnl": unrealized_conf.level,
        }
        critical_levels = {k: v for k, v in levels.items() if k != "unrealized_pnl"}
        if any(level == TruthConfidenceLevel.UNAVAILABLE for level in critical_levels.values()):
            action = "flatten_only"
            reasons.extend([f"{name}_unavailable" for name, level in critical_levels.items() if level == TruthConfidenceLevel.UNAVAILABLE])
            if levels["unrealized_pnl"] == TruthConfidenceLevel.UNAVAILABLE:
                reasons.append("unrealized_pnl_unavailable")
        elif any(level == TruthConfidenceLevel.PROXY for level in levels.values()):
            action = "degrade"
            reasons.extend([f"{name}_proxy" for name, level in levels.items() if level == TruthConfidenceLevel.PROXY])
        elif levels["unrealized_pnl"] == TruthConfidenceLevel.UNAVAILABLE:
            action = "degrade"
            reasons.append("unrealized_pnl_unavailable")

        return TruthConfidenceSnapshot(
            ts=datetime.now(timezone.utc),
            fill_truth_confidence=fill_conf,
            fee_truth_confidence=fee_conf,
            realized_pnl_confidence=realized_conf,
            balance_truth_confidence=balance_conf,
            exposure_truth_confidence=exposure_conf,
            market_data_truth_confidence=market_conf,
            unrealized_pnl_confidence=unrealized_conf,
            overall_action=action,
            reasons=reasons,
            metadata={"history_since_ms": history_since_ms, "history_recovered": history_recovered},
        )

    def _order_recovery_state(self, status: str, *, seen_fill: bool, exchange_open: bool) -> str:
        normalized = str(status).upper()
        if normalized in {"FILLED", "EXECUTED", "CLOSED"}:
            return "filled"
        if normalized in {"CANCELED", "CANCELLED"}:
            return "cancelled"
        if normalized == "REJECTED":
            return "rejected"
        if normalized == "PARTIALLY_FILLED":
            return "partially_filled" if exchange_open else "recovered"
        if normalized in {"NEW", "ACK", "ACKNOWLEDGED"}:
            if exchange_open:
                return "acknowledged"
            if seen_fill:
                return "recovered"
            return "timed_out"
        return "recovered" if seen_fill else "stuck"

    def recover_inflight_state(
        self,
        live: object,
        symbol: str,
        *,
        restart_confidence: str = "trusted",
        safe_mode_requested: bool = False,
    ) -> RecoveryDecision:
        order_events = self.event_store.load("orders")
        fill_events = self.event_store.load("fills")
        provider_id = getattr(getattr(live, "connector", None), "provider_id", "live")
        local_orders: dict[str, dict[str, Any]] = {}
        local_fill_ids: list[str] = []
        local_filled_orders: set[str] = set()
        for event in fill_events:
            payload = event.get("payload", event) if isinstance(event, dict) else {}
            if not isinstance(payload, dict):
                continue
            fill_id = str(payload.get("fill_id", payload.get("fillId", "")))
            if fill_id:
                local_fill_ids.append(fill_id)
            order_id = str(payload.get("order_id", payload.get("orderId", "")))
            if order_id:
                local_filled_orders.add(order_id)
        for event in order_events:
            payload = event.get("payload", event) if isinstance(event, dict) else {}
            if not isinstance(payload, dict):
                continue
            key = str(payload.get("clientOrderId", payload.get("origClientOrderId", payload.get("orderId", payload.get("order_id", "")))))
            if not key:
                continue
            local_orders[key] = payload

        duplicate_repairs = max(0, len(local_fill_ids) - len(set(local_fill_ids)))
        out_of_order_repairs = 0
        recovered_orders = 0
        orphan_orders = 0
        reasons: list[str] = []
        swept_order_ids: list[str] = []
        order_states: list[dict[str, Any]] = []
        try:
            exchange_orders = live.connector.open_orders(symbol)  # type: ignore[attr-defined]
        except Exception as exc:
            exchange_orders = []
            reasons.append(f"open_orders_fetch_error:{exc}")
        if not isinstance(exchange_orders, list):
            exchange_orders = []

        exchange_keys: set[str] = set()
        for order in exchange_orders:
            if not isinstance(order, dict):
                continue
            key = str(order.get("clientOrderId", order.get("origClientOrderId", order.get("clOrdId", order.get("orderId", order.get("order_id", ""))))))
            if not key:
                continue
            exchange_keys.add(key)
            local = local_orders.get(key)
            status = str(order.get("status", "NEW")).upper()
            if hasattr(live, "apply_order_update"):
                ok, repair_reason = live.apply_order_update(order)
                if repair_reason == "out_of_order_order_update":
                    out_of_order_repairs += 1
            else:
                ok = True
            if local is None:
                orphan_orders += 1
                reasons.append("orphan_open_order")
                order_states.append({"order_key": key, "state": "orphaned", "exchange_status": status})
                if hasattr(live, "mark_orphan_order"):
                    live.mark_orphan_order(order)
                cancel_fn = getattr(live.connector, "cancel_order", None)  # type: ignore[attr-defined]
                if callable(cancel_fn):
                    symbol_value = str(order.get("symbol", symbol))
                    cancel_id = str(order.get("clientOrderId", order.get("origClientOrderId", key)))
                    try:
                        cancel_fn(symbol_value, cancel_id)
                        swept_order_ids.append(cancel_id)
                    except Exception as exc:
                        reasons.append(f"orphan_cancel_error:{exc}")
                continue
            local_status = str(local.get("status", "NEW"))
            state = self._order_recovery_state(local_status, seen_fill=bool(local_filled_orders), exchange_open=True)
            if ok:
                recovered_orders += 1
            order_states.append({"order_key": key, "state": state, "local_status": local_status, "exchange_status": status})

        for key, local in local_orders.items():
            if key in exchange_keys:
                continue
            local_status = str(local.get("status", "NEW"))
            seen_fill = str(local.get("orderId", local.get("order_id", ""))) in local_filled_orders
            state = self._order_recovery_state(local_status, seen_fill=seen_fill, exchange_open=False)
            if state in {"recovered", "timed_out", "stuck"}:
                recovered_orders += 1
                if hasattr(live, "lifecycle_snapshot"):
                    pass
            order_states.append({"order_key": key, "state": state, "local_status": local_status, "exchange_status": "missing"})

        if restart_confidence == "insufficient":
            outcome = "insufficient_confidence_boot"
            action = "flatten_only"
        elif orphan_orders:
            outcome = "warm_restart"
            action = "flatten_only"
        elif safe_mode_requested and (exchange_keys or local_orders):
            outcome = "safe_mode_boot"
            action = "degrade"
        elif exchange_keys or local_orders or local_fill_ids:
            outcome = "warm_restart"
            action = "degrade" if recovered_orders or duplicate_repairs or out_of_order_repairs else "continue"
        else:
            outcome = "cold_restart"
            action = "continue"

        decision = RecoveryDecision(
            symbol=symbol,
            ts=datetime.now(timezone.utc),
            outcome=outcome,
            action=action,
            confidence=restart_confidence,
            recovered_orders=recovered_orders,
            orphan_orders=orphan_orders,
            duplicate_repairs=duplicate_repairs,
            out_of_order_repairs=out_of_order_repairs,
            reasons=reasons,
            metadata={
                "swept_order_ids": swept_order_ids,
                "order_states": order_states,
                "lifecycle_snapshot": live.lifecycle_snapshot() if hasattr(live, "lifecycle_snapshot") else [],
            },
        )
        self.event_store.append(
            "recovery",
            make_event(
                RecoveryEvent,
                "RECOVERY_DECISION",
                symbol,
                provider_id,
                self.event_store.next_seq("recovery"),
                asdict(decision),
            ),
        )
        return decision

    def _exchange_history_rehydrate(
        self,
        *,
        live: object,
        symbol: str,
        provider_id: str,
        account_events: list[dict[str, Any]],
        fill_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not hasattr(live, "authoritative_fill_history"):
            return {"supported": False, "since_ms": None, "fetched": 0, "recovered": 0, "gaps": []}
        since_ms = self._history_since_ms(account_events, fill_events)
        records, gaps = live.authoritative_fill_history(symbol, side="buy", since_ms=since_ms)  # type: ignore[attr-defined]
        existing_fill_ids = {
            str(payload.get("fill_id", payload.get("fillId", "")))
            for event in fill_events
            if isinstance(event, dict)
            for payload in [event.get("payload", event)]
            if isinstance(payload, dict)
        }
        recovered = 0
        for record in records:
            if record.fill.fill_id in existing_fill_ids:
                continue
            payload = {
                "venue": record.fill.venue,
                "order_id": record.fill.order_id,
                "fill_id": record.fill.fill_id,
                "symbol": record.fill.symbol,
                "side": record.fill.side,
                "notional": record.fill.notional,
                "fee": record.fill.fee,
                "slippage_cost": record.fill.slippage_cost,
                "latency_ms": record.fill.latency_ms,
                "status": record.fill.status,
                "metadata": record.metadata,
                "truth_evidence": record.truth_evidence,
                "realized_pnl": record.realized_pnl,
                "fee_authoritative": record.fee_authoritative,
                "realized_pnl_authoritative": record.realized_pnl_authoritative,
            }
            self.event_store.append(
                "fills",
                make_event(
                    FillEvent,
                    "FILL_REHYDRATED_FROM_EXCHANGE",
                    symbol,
                    provider_id,
                    self.event_store.next_seq("fills"),
                    payload,
                    idempotency_key=record.fill.fill_id,
                ),
            )
            self.portfolio.record_fill(
                record.fill,
                realized_pnl=record.realized_pnl,
                venue=record.fill.venue,
                metadata={
                    "fee_authoritative": record.fee_authoritative,
                    "realized_pnl_authoritative": record.realized_pnl_authoritative,
                    "rehydrated_from_exchange": True,
                },
            )
            if self.inventory is not None:
                self.inventory.update_from_fill(record.fill)
            existing_fill_ids.add(record.fill.fill_id)
            recovered += 1
        if records:
            self.event_store.append(
                "account",
                make_event(
                    AccountEvent,
                    "ACCOUNT_REHYDRATED_FROM_EXCHANGE",
                    symbol,
                    provider_id,
                    self.event_store.next_seq("account"),
                    self.portfolio.account_row(
                        venue=provider_id,
                        metadata={
                            "exchange_history_supported": True,
                            "exchange_history_recovered_fills": recovered,
                        },
                    ),
                ),
            )
        return {
            "supported": True,
            "since_ms": since_ms,
            "fetched": len(records),
            "recovered": recovered,
            "gaps": list(gaps),
        }

    def rehydrate_state(self, live: object, symbol: str) -> LiveRehydrationResult:
        order_events = self.event_store.load("orders")
        fill_events = self.event_store.load("fills")
        position_events = self.event_store.load("positions")
        account_events = self.event_store.load("account")
        provider_id = getattr(getattr(live, "connector", None), "provider_id", "live")
        rehydrated: dict[str, Any] = {}
        if hasattr(live, "rehydrate_state"):
            rehydrated = live.rehydrate_state(order_events, fill_events)
        self.portfolio.rehydrate_from_events(fill_events=fill_events, position_events=position_events, account_events=account_events)
        if self.inventory is not None:
            self.inventory.rehydrate_from_events(fill_events)
        history_rehydrate = self._exchange_history_rehydrate(
            live=live,
            symbol=symbol,
            provider_id=provider_id,
            account_events=account_events,
            fill_events=fill_events,
        )
        local_state = self.portfolio.snapshot(symbol)
        account = self.portfolio.account_snapshot(venue=provider_id)
        exchange = self.exchange_state(live, symbol)
        truth_confidence = self.truth_confidence(
            exchange=exchange,
            fill_history_gaps=history_rehydrate["gaps"],
            unrealized_truth=exchange.unrealized_pnl_truth,
            history_since_ms=history_rehydrate["since_ms"],
            history_recovered=history_rehydrate["recovered"],
        )
        tolerance = max(2.0, abs(exchange.exposure_notional) * 0.1)
        delta = exchange.exposure_notional - abs(local_state.exposure_notional)

        confidence = "trusted"
        reason = "rehydrated"
        if abs(exchange.exposure_notional) <= tolerance and abs(local_state.exposure_notional) <= tolerance and exchange.open_order_count == 0:
            confidence = "trusted"
            reason = "flat_and_consistent"
        elif abs(exchange.exposure_notional) > tolerance and not fill_events and not position_events and history_rehydrate["recovered"] == 0:
            confidence = "insufficient"
            reason = "exchange_exposure_without_local_history"
        elif exchange.open_order_count > 0 and not order_events:
            confidence = "insufficient"
            reason = "exchange_open_orders_without_local_history"
        elif history_rehydrate["supported"] and history_rehydrate["recovered"] > 0:
            confidence = "degraded"
            reason = "rehydrated_from_exchange_history"
        elif abs(delta) > tolerance:
            confidence = "degraded"
            reason = "exchange_local_exposure_gap"
        if history_rehydrate["gaps"]:
            confidence = "degraded" if confidence == "trusted" else confidence
            reason = "exchange_history_truth_gap"

        details = {
            "confidence": confidence,
            "reason": reason,
            "exchange_exposure": exchange.exposure_notional,
            "local_exposure": local_state.exposure_notional,
            "delta": delta,
            "tolerance": tolerance,
            "exchange_positions": exchange.position_count,
            "open_order_count": exchange.open_order_count,
            "exchange_balance": exchange.balance_total,
            "local_cash_delta": account.local_cash_delta,
            "exchange_unrealized_pnl": exchange.unrealized_pnl,
            "exchange_unrealized_truth": asdict(exchange.unrealized_pnl_truth),
            "local_unrealized_pnl": local_state.unrealized_pnl,
            "rehydrated": rehydrated,
            "exchange_history_rehydrate": history_rehydrate,
            "truth_confidence": _truth_snapshot_dict(truth_confidence),
            "fill_event_count": len(fill_events),
            "position_event_count": len(position_events),
            "account_event_count": len(account_events),
        }
        self.event_store.append(
            "truth",
            make_event(
                TruthEvent,
                "TRUTH_CONFIDENCE_SNAPSHOT",
                symbol,
                provider_id,
                self.event_store.next_seq("truth"),
                _truth_snapshot_dict(truth_confidence),
            ),
        )
        return LiveRehydrationResult(confidence=confidence, details=details)

    def reconcile_state(self, live: object, symbol: str, internal_exposure: float, market_health: Any | None = None) -> ReconciliationOutcome:
        account_events = self.event_store.load("account")
        fill_events = self.event_store.load("fills")
        since_ms = self._history_since_ms(account_events, fill_events)
        exchange = self.exchange_state(live, symbol)
        account = self.portfolio.account_snapshot(
            venue=getattr(getattr(live, "connector", None), "provider_id", "live"),
            exchange_balance=exchange.balance_total,
        )
        local_state = self.portfolio.snapshot(symbol)
        exchange_realized_pnl = None
        realized_gaps: list[str] = []
        fill_history_gaps: list[str] = []
        if hasattr(live, "authoritative_realized_pnl"):
            exchange_realized_pnl, realized_gaps = live.authoritative_realized_pnl(symbol, since_ms=since_ms)  # type: ignore[attr-defined]
        elif account.baseline_balance > 0.0 and exchange.balance_total is not None:
            exchange_realized_pnl = (exchange.balance_total - account.baseline_balance) - exchange.unrealized_pnl
            realized_gaps = ["realized_pnl_proxy_balance_delta"]
        if hasattr(live, "authoritative_fill_history"):
            _, fill_history_gaps = live.authoritative_fill_history(symbol, side="buy", since_ms=since_ms)  # type: ignore[attr-defined]
        truth_confidence = self.truth_confidence(
            exchange=exchange,
            fill_history_gaps=fill_history_gaps,
            realized_pnl_gaps=realized_gaps,
            unrealized_truth=exchange.unrealized_pnl_truth,
            market_health=market_health,
            history_since_ms=since_ms,
            history_recovered=len(fill_events),
        )
        lifecycle_snapshot = live.lifecycle_snapshot() if hasattr(live, "lifecycle_snapshot") else []
        lifecycle_problem_states = {
            str(item.get("state", "")).lower()
            for item in lifecycle_snapshot
            if isinstance(item, dict)
        }
        if exchange.open_order_count > 0 and not lifecycle_snapshot:
            order_lifecycle_confidence = TruthConfidenceLevel.UNAVAILABLE.value
        elif lifecycle_problem_states & {"orphaned", "stuck", "unknown", "cancel_rejected"}:
            order_lifecycle_confidence = TruthConfidenceLevel.PROXY.value
        elif any(str(item.get("confidence", "")).lower() in {"recovery", "local"} for item in lifecycle_snapshot if isinstance(item, dict)):
            order_lifecycle_confidence = TruthConfidenceLevel.PROXY.value
        else:
            order_lifecycle_confidence = TruthConfidenceLevel.AUTHORITATIVE.value
        report = self.recon.reconcile_live_report(
            exchange_exposure=exchange.exposure_notional,
            internal_exposure=internal_exposure,
            open_orders_state_ok=exchange.open_order_count == 0,
            cash_ok=exchange.balance_total is not None and exchange.balance_total > 0.0,
            local_realized_pnl=account.realized_pnl,
            exchange_realized_pnl=exchange_realized_pnl,
            local_unrealized_pnl=local_state.unrealized_pnl,
            exchange_unrealized_pnl=exchange.unrealized_pnl,
            truth_confidence=truth_confidence,
            stale_account_snapshot=since_ms is None and (exchange.position_count > 0 or exchange.open_order_count > 0),
            stale_market_snapshot=bool(market_health is not None and getattr(market_health, "feed_stale", False)),
            lifecycle_snapshot=lifecycle_snapshot,
            order_lifecycle_confidence=order_lifecycle_confidence,
        )
        report.details.setdefault("exchange_balance", exchange.balance_total)
        report.details.setdefault("local_cash_delta", account.local_cash_delta)
        report.details.setdefault("local_realized_pnl", account.realized_pnl)
        report.details.setdefault("exchange_realized_pnl", exchange_realized_pnl)
        report.details.setdefault("exchange_realized_pnl_gaps", realized_gaps)
        report.details.setdefault("fill_truth_gaps", fill_history_gaps)
        report.details["truth_confidence"] = _truth_snapshot_dict(truth_confidence)
        report.details.setdefault("exchange_unrealized_pnl", exchange.unrealized_pnl)
        report.details.setdefault("exchange_unrealized_truth", asdict(exchange.unrealized_pnl_truth))
        report.details.setdefault("local_unrealized_pnl", local_state.unrealized_pnl)
        report.details.setdefault("order_lifecycle_confidence", order_lifecycle_confidence)
        report.details.setdefault("order_lifecycle_snapshot", lifecycle_snapshot)
        report.details.setdefault("reconciliation_since_ms", since_ms)
        self.event_store.append(
            "truth",
            make_event(
                TruthEvent,
                "TRUTH_CONFIDENCE_SNAPSHOT",
                symbol,
                getattr(getattr(live, "connector", None), "provider_id", "live"),
                self.event_store.next_seq("truth"),
                _truth_snapshot_dict(truth_confidence),
            ),
        )
        return report


class LiveLedgerCoordinator:
    def __init__(self, event_store: EventStore, portfolio: PortfolioService, observability: Any | None = None, forensics: Any | None = None, inventory: Any | None = None) -> None:
        self.event_store = event_store
        self.portfolio = portfolio
        self.observability = observability
        self.forensics = forensics
        self.inventory = inventory

    def apply_execution_result(
        self,
        *,
        symbol: str,
        provider_id: str,
        result: Any,
        fallback_intent_notional: float,
        fallback_side: str,
        current_exposure: float,
        live: object | None = None,
    ) -> LiveLedgerApplyResult:
        gap_reasons = list(getattr(result, "gaps", []))
        if result.order is not None:
            order_key = str(result.order.get("clientOrderId", result.order.get("orderId", symbol)))
            self.event_store.append(
                "orders",
                make_event(
                    OrderEvent,
                    "ORDER_UPDATE",
                    symbol,
                    provider_id,
                    self.event_store.next_seq("orders"),
                    result.order,
                    idempotency_key=order_key,
                ),
            )
        if live is not None and hasattr(live, "drain_lifecycle_transitions"):
            transitions = live.drain_lifecycle_transitions()
            for transition in transitions:
                order_key = str(transition.get("order_key", transition.get("orderId", symbol)))
                self.event_store.append(
                    "orders",
                    make_event(
                        OrderEvent,
                        "ORDER_LIFECYCLE_TRANSITION",
                        symbol,
                        provider_id,
                        self.event_store.next_seq("orders"),
                        transition,
                        idempotency_key=f"{order_key}:{transition.get('from_state')}:{transition.get('to_state')}:{transition.get('reason')}",
                    ),
                )
                if self.observability is not None:
                    self.observability.journal("lifecycle_journal", transition)

        new_exposure = current_exposure
        fill_truth_ok = True
        ledger_records = list(getattr(result, "ledger_records", []))
        if result.status in {"filled_maker", "filled_taker_fallback", "filled_marketable_limit"}:
            if not ledger_records:
                fill_truth_ok = False
                gap_reasons.append("normalized_fill_missing")
                self.event_store.append(
                    "risk",
                    make_event(
                        RiskEvent,
                        "LIVE_FILL_TRUTH_GAP",
                        symbol,
                        provider_id,
                        self.event_store.next_seq("risk"),
                        {"reason": "normalized_fill_missing", "result_status": result.status},
                    ),
                )
                if live is not None and hasattr(live, "enter_flatten_only"):
                    live.enter_flatten_only("live_fill_truth_gap")
                if self.forensics is not None:
                    self.forensics.record_runtime_anomaly(
                        symbol=symbol,
                        ts=datetime.now(timezone.utc),
                        venue=provider_id,
                        category="execution_truth_gap",
                        reason="normalized_fill_missing",
                        evidence={"result_status": result.status},
                    )
            for record in ledger_records:
                if record.gaps:
                    fill_truth_ok = False
                payload = {
                    "venue": record.fill.venue,
                    "order_id": record.fill.order_id,
                    "fill_id": record.fill.fill_id,
                    "symbol": record.fill.symbol,
                    "side": record.fill.side,
                    "notional": record.fill.notional,
                    "fee": record.fill.fee,
                    "slippage_cost": record.fill.slippage_cost,
                    "latency_ms": record.fill.latency_ms,
                    "status": record.fill.status,
                    "metadata": record.metadata,
                    "truth_evidence": record.truth_evidence,
                    "realized_pnl": record.realized_pnl,
                    "fee_authoritative": record.fee_authoritative,
                    "realized_pnl_authoritative": record.realized_pnl_authoritative,
                }
                self.event_store.append(
                    "fills",
                    make_event(
                        FillEvent,
                        "FILL_ACCEPTED",
                        symbol,
                        provider_id,
                        self.event_store.next_seq("fills"),
                        payload,
                        idempotency_key=record.fill.fill_id,
                    ),
                )
                if self.observability is not None:
                    self.observability.journal("fills_journal", payload)
                self.portfolio.record_fill(
                    record.fill,
                    realized_pnl=record.realized_pnl,
                    venue=record.fill.venue,
                    metadata={
                        "fee_authoritative": record.fee_authoritative,
                        "realized_pnl_authoritative": record.realized_pnl_authoritative,
                    },
                )
                if self.inventory is not None:
                    self.inventory.update_from_fill(
                        record.fill,
                        expected_exit_cost_bps=float(record.truth_evidence.get("expected_exit_cost_bps", 0.0) or 0.0),
                    )
                for gap in record.gaps:
                    gap_reasons.append(gap)
                    event_type = "LIVE_LEDGER_GAP"
                    if gap == "fee_truth_gap":
                        event_type = "LIVE_FEE_TRUTH_GAP"
                    elif gap == "realized_pnl_truth_gap":
                        event_type = "LIVE_REALIZED_PNL_TRUTH_GAP"
                    self.event_store.append(
                        "risk",
                        make_event(
                            RiskEvent,
                            event_type,
                            symbol,
                            provider_id,
                            self.event_store.next_seq("risk"),
                            {"fill_id": record.fill.fill_id, "reason": gap},
                        ),
                    )
                    if live is not None and hasattr(live, "enter_flatten_only") and gap in {"fee_truth_gap", "realized_pnl_truth_gap"}:
                        live.enter_flatten_only("live_account_truth_gap")
                if self.forensics is not None and (record.realized_pnl_authoritative or record.realized_pnl != 0.0 or record.gaps):
                    inventory_age = 0.0
                    if self.inventory is not None:
                        lots = self.inventory.lots(symbol)
                        if lots:
                            now_ts = datetime.now(timezone.utc)
                            inventory_age = max(0.0, max((now_ts - lot.opened_ts).total_seconds() for lot in lots))
                    self.forensics.analyze_trade(
                        context=TradeForensicsContext(
                            symbol=symbol,
                            ts=datetime.now(timezone.utc),
                            venue=provider_id,
                            order_id=record.fill.order_id,
                            side=record.fill.side,
                            unrealized_truth_source=str(record.truth_evidence.get("unrealized_pnl_source", "")),
                            inventory_age=inventory_age,
                            metadata={
                                "status": record.fill.status,
                                "truth_evidence": dict(record.truth_evidence),
                                "record_gaps": list(record.gaps),
                            },
                        ),
                        fills=[record.fill],
                        filled_notional=record.fill.notional,
                        realized_pnl=record.realized_pnl,
                        additional_metadata={"live_record": True},
                    )
            if ledger_records:
                new_exposure = self.portfolio.snapshot(symbol).exposure_notional
            else:
                new_exposure = current_exposure
            self.event_store.append(
                "positions",
                make_event(
                    PositionEvent,
                    "POSITION_SNAPSHOT",
                    symbol,
                    provider_id,
                    self.event_store.next_seq("positions"),
                    {"exposure_notional": new_exposure},
                ),
            )
        account_snapshot = self.portfolio.account_snapshot(venue=provider_id)
        self.event_store.append(
            "account",
            make_event(
                AccountEvent,
                "ACCOUNT_SNAPSHOT",
                symbol,
                provider_id,
                self.event_store.next_seq("account"),
                asdict(account_snapshot),
            ),
        )
        if self.observability is not None:
            self.observability.journal(
                "accounting_truth_journal",
                {
                    "symbol": symbol,
                    "provider_id": provider_id,
                    "fill_truth_ok": fill_truth_ok,
                    "gap_reasons": list(gap_reasons),
                    "fill_count": len(ledger_records),
                    "fee_authoritative_count": sum(1 for record in ledger_records if record.fee_authoritative),
                    "realized_pnl_authoritative_count": sum(1 for record in ledger_records if record.realized_pnl_authoritative),
                    "account_snapshot": asdict(account_snapshot),
                },
            )
        return LiveLedgerApplyResult(
            exposure_notional=new_exposure,
            account_snapshot=account_snapshot,
            fill_truth_ok=fill_truth_ok,
            gap_reasons=gap_reasons,
        )
