from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from autonomous_investment_robot.core.contracts import UnrealizedPnlTruth
from autonomous_investment_robot.services.execution.service import Fill


@dataclass
class NormalizedLiveFillRecord:
    fill: Fill
    realized_pnl: float = 0.0
    fee_authoritative: bool = False
    realized_pnl_authoritative: bool = False
    gaps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    truth_evidence: dict[str, Any] = field(default_factory=dict)


def _first_string(candidates: list[dict[str, Any]], *keys: str) -> str:
    for candidate in candidates:
        for key in keys:
            value = candidate.get(key)
            if value is None:
                continue
            if isinstance(value, (dict, list, tuple, set)):
                continue
            text = str(value).strip()
            if text:
                return text
    return ""


def _first_float(candidates: list[dict[str, Any]], *keys: str) -> tuple[float | None, bool]:
    for candidate in candidates:
        for key in keys:
            if key not in candidate:
                continue
            value = candidate.get(key)
            try:
                return float(value), True
            except Exception:
                continue
    return None, False


def _extract_fee(candidates: list[dict[str, Any]]) -> tuple[float, bool]:
    fee, found = _first_float(candidates, "commission", "fee", "cumCommission", "fees", "fillFee", "fee_usd_equiv")
    if found and fee is not None:
        return abs(fee), True
    for candidate in candidates:
        fees = candidate.get("fees")
        if not isinstance(fees, list):
            continue
        total = 0.0
        matched = False
        for row in fees:
            if not isinstance(row, dict):
                continue
            amount, ok = _first_float([row], "amount", "fee", "commission", "qty")
            if ok and amount is not None:
                total += abs(amount)
                matched = True
        if matched:
            return total, True
    return 0.0, False


def _build_normalized_fill(
    *,
    venue: str,
    symbol: str,
    side: str,
    order_id: str,
    fill_id: str,
    notional: float,
    fee: float,
    latency_ms: int = 0,
    status: str = "filled",
    realized_pnl: float = 0.0,
    fee_authoritative: bool = False,
    realized_pnl_authoritative: bool = False,
    metadata: dict[str, Any] | None = None,
    truth_evidence: dict[str, Any] | None = None,
) -> NormalizedLiveFillRecord:
    gaps: list[str] = []
    if not fee_authoritative:
        gaps.append("fee_truth_gap")
    if not realized_pnl_authoritative:
        gaps.append("realized_pnl_truth_gap")
    payload = {} if metadata is None else dict(metadata)
    fill = Fill(
        venue=venue,
        order_id=order_id,
        fill_id=fill_id,
        symbol=symbol,
        side=side,
        notional=abs(notional),
        fee=abs(fee),
        slippage_cost=0.0,
        latency_ms=int(latency_ms),
        status=status,
        metadata=payload,
    )
    return NormalizedLiveFillRecord(
        fill=fill,
        realized_pnl=realized_pnl,
        fee_authoritative=fee_authoritative,
        realized_pnl_authoritative=realized_pnl_authoritative,
        gaps=gaps,
        metadata=payload,
        truth_evidence={} if truth_evidence is None else dict(truth_evidence),
    )


def extract_exchange_balance_total(rows: list[dict[str, Any]] | None) -> float | None:
    if not isinstance(rows, list) or not rows:
        return None
    total = 0.0
    matched = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        amount, ok = _first_float([row], "equity", "walletBalance", "balance", "availableBalance")
        if ok and amount is not None:
            total += max(0.0, amount)
            matched = True
    return total if matched else None


def extract_exchange_unrealized_pnl(rows: list[dict[str, Any]] | None) -> float:
    if not isinstance(rows, list):
        return 0.0
    total = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        amount, ok = _first_float([row], "unRealizedProfit", "unrealizedPnl", "unrealisedPnl", "floatingPnl")
        if ok and amount is not None:
            total += amount
            continue
        raw = row.get("raw")
        if isinstance(raw, dict):
            amount, ok = _first_float([raw], "unRealizedProfit", "unrealizedPnl", "unrealisedPnl", "floatingPnl")
            if ok and amount is not None:
                total += amount
    return total


def extract_exchange_unrealized_pnl_truth(rows: list[dict[str, Any]] | None, *, symbol: str) -> UnrealizedPnlTruth:
    ts = datetime.now(timezone.utc)
    if not isinstance(rows, list):
        return UnrealizedPnlTruth(
            symbol=symbol,
            ts=ts,
            source="position_snapshot_missing",
            confidence="unavailable",
            venue_value=None,
            reason="position_snapshot_missing",
        )

    authoritative_total = 0.0
    authoritative_count = 0
    derived_total = 0.0
    derived_count = 0
    position_count = 0
    evidence_rows: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        qty, qty_ok = _first_float([row, row.get("raw", {}) if isinstance(row.get("raw"), dict) else {}], "positionAmt", "size", "qty")
        if qty_ok and qty is not None and abs(qty) > 0.0:
            position_count += 1
        amount, ok = _first_float([row], "unRealizedProfit", "unrealizedPnl", "unrealisedPnl", "floatingPnl")
        if not ok or amount is None:
            raw = row.get("raw")
            if isinstance(raw, dict):
                amount, ok = _first_float([raw], "unRealizedProfit", "unrealizedPnl", "unrealisedPnl", "floatingPnl")
        if ok and amount is not None:
            authoritative_total += amount
            authoritative_count += 1
            evidence_rows.append({"symbol": row.get("symbol", symbol), "source": "venue_field"})
            continue

        candidates = [row]
        raw = row.get("raw")
        if isinstance(raw, dict):
            candidates.append(raw)
        entry_price, entry_ok = _first_float(candidates, "entryPrice", "avgEntryPrice", "avgPrice")
        mark_price, mark_ok = _first_float(candidates, "markPrice", "mark", "mark_value")
        qty_value, qty_value_ok = _first_float(candidates, "positionAmt", "size", "qty")
        if entry_ok and mark_ok and qty_value_ok and entry_price is not None and mark_price is not None and qty_value is not None:
            derived_total += (mark_price - entry_price) * qty_value
            derived_count += 1
            evidence_rows.append({"symbol": row.get("symbol", symbol), "source": "entry_mark_derivation"})

    if authoritative_count:
        return UnrealizedPnlTruth(
            symbol=symbol,
            ts=ts,
            source="venue_position_field",
            confidence="authoritative",
            venue_value=authoritative_total,
            reason="venue_unrealized_fields_present",
            evidence={
                "authoritative_positions": authoritative_count,
                "position_count": position_count,
                "rows": evidence_rows[:10],
            },
        )

    if position_count == 0:
        return UnrealizedPnlTruth(
            symbol=symbol,
            ts=ts,
            source="venue_position_field",
            confidence="authoritative",
            venue_value=0.0,
            reason="no_open_positions",
            evidence={"position_count": 0},
        )

    if derived_count == position_count and derived_count > 0:
        return UnrealizedPnlTruth(
            symbol=symbol,
            ts=ts,
            source="position_mark_entry_derivation",
            confidence="proxy",
            venue_value=derived_total,
            reason="derived_from_position_mark_and_entry",
            evidence={
                "derived_positions": derived_count,
                "position_count": position_count,
                "rows": evidence_rows[:10],
            },
        )

    return UnrealizedPnlTruth(
        symbol=symbol,
        ts=ts,
        source="position_snapshot_incomplete",
        confidence="unavailable",
        venue_value=None,
        reason="venue_unrealized_fields_missing",
        evidence={
            "position_count": position_count,
            "derived_positions": derived_count,
            "rows": evidence_rows[:10],
        },
    )


def normalize_live_fill(
    order: dict[str, Any],
    *,
    venue: str,
    fallback_symbol: str,
    fallback_side: str,
) -> tuple[NormalizedLiveFillRecord | None, str]:
    raw = order.get("raw") if isinstance(order.get("raw"), dict) else {}
    candidates = [order]
    if isinstance(raw, dict):
        candidates.append(raw)

    symbol = _first_string(candidates, "symbol", "instrument") or fallback_symbol
    side = (_first_string(candidates, "side", "direction") or fallback_side).lower()
    order_id = _first_string(candidates, "clientOrderId", "origClientOrderId", "cliOrdId", "clOrdId", "orderId", "order_id")
    status = (_first_string(candidates, "status") or "FILLED").upper()
    executed_qty, qty_found = _first_float(candidates, "executedQty", "cumQty", "filled", "filledQty", "filledSize", "sizeFilled", "lastQty")
    average_price, price_found = _first_float(candidates, "avgPrice", "averagePrice", "avgFillPrice", "fillPrice", "lastPx", "price", "limitPrice")
    notional, notional_found = _first_float(candidates, "cumQuote", "filledNotional", "quoteQty", "notional", "cost", "value")
    if (notional is None or notional <= 0.0) and qty_found and price_found and executed_qty is not None and average_price is not None:
        notional = abs(executed_qty * average_price)
        notional_found = True
    if not notional_found or notional is None or notional <= 0.0:
        return None, "insufficient_fill_notional"

    fee, fee_authoritative = _extract_fee(candidates)
    realized_pnl, realized_authoritative = _first_float(
        candidates,
        "realizedPnl",
        "realizedPNL",
        "realisedPnl",
        "closedPnl",
        "closedProfit",
        "rp",
    )
    latency_ms, _ = _first_float(candidates, "latency_ms", "latencyMs")
    fill_id = _first_string(candidates, "fill_id", "fillId", "tradeId", "lastTradeId", "id")
    if not fill_id:
        fill_id = sha256(
            f"{venue}|{order_id}|{symbol}|{side}|{status}|{round(notional, 8)}|{round(executed_qty or 0.0, 8)}".encode("utf-8")
        ).hexdigest()[:24]

    metadata = {
        "normalized_status": status,
        "executed_qty": 0.0 if executed_qty is None else executed_qty,
        "average_price": 0.0 if average_price is None else average_price,
        "fee_authoritative": fee_authoritative,
        "realized_pnl_authoritative": realized_authoritative,
    }
    truth_evidence = {
        "source": "order_payload_proxy",
        "history_window_covered": False,
        "venue_event_ids": [fill_id],
        "duplicate_suppression": False,
        "out_of_order_repair_applied": False,
        "fee_present": fee_authoritative,
        "realized_pnl_present": realized_authoritative,
    }
    return (
        _build_normalized_fill(
            venue=venue,
            symbol=symbol,
            side=side,
            order_id=order_id or fill_id,
            fill_id=fill_id,
            notional=notional,
            fee=fee,
            latency_ms=int(latency_ms or 0.0),
            status=status.lower(),
            realized_pnl=0.0 if realized_pnl is None else realized_pnl,
            fee_authoritative=fee_authoritative,
            realized_pnl_authoritative=realized_authoritative,
            metadata=metadata,
            truth_evidence=truth_evidence,
        ),
        "ok",
    )


def normalize_binance_user_trades(
    trades: list[dict[str, Any]] | None,
    *,
    symbol: str,
    side: str,
    order_id: str | None = None,
) -> list[NormalizedLiveFillRecord]:
    records: list[NormalizedLiveFillRecord] = []
    for row in trades or []:
        if not isinstance(row, dict):
            continue
        current_order_id = _first_string([row], "orderId")
        if order_id and current_order_id and current_order_id != str(order_id):
            continue
        trade_symbol = _first_string([row], "symbol") or symbol
        trade_side = (_first_string([row], "side") or side).lower()
        notional, notional_found = _first_float([row], "quoteQty")
        qty, qty_found = _first_float([row], "qty")
        price, price_found = _first_float([row], "price")
        if (notional is None or notional <= 0.0) and qty_found and price_found and qty is not None and price is not None:
            notional = abs(qty * price)
            notional_found = True
        if not notional_found or notional is None or notional <= 0.0:
            continue
        fee, fee_found = _first_float([row], "commission")
        realized_pnl, realized_found = _first_float([row], "realizedPnl", "realizedPNL")
        fill_id = _first_string([row], "id", "tradeId") or sha256(
            f"binance_um_perps|{current_order_id}|{trade_symbol}|{trade_side}|{round(notional, 8)}".encode("utf-8")
        ).hexdigest()[:24]
        metadata = {
            "source": "user_trades",
            "maker": bool(row.get("maker", False)),
            "buyer": bool(row.get("buyer", False)),
            "trade_time_ms": int(row.get("time", 0) or 0),
        }
        truth_evidence = {
            "source": "user_trades",
            "history_window_covered": True,
            "venue_event_ids": [fill_id],
            "duplicate_suppression": False,
            "out_of_order_repair_applied": False,
            "fee_present": fee_found,
            "realized_pnl_present": realized_found,
            "order_id": current_order_id,
        }
        records.append(
            _build_normalized_fill(
                venue="binance_um_perps",
                symbol=trade_symbol,
                side=trade_side,
                order_id=current_order_id or fill_id,
                fill_id=fill_id,
                notional=notional,
                fee=0.0 if fee is None else fee,
                status="filled",
                realized_pnl=0.0 if realized_pnl is None else realized_pnl,
                fee_authoritative=fee_found,
                realized_pnl_authoritative=realized_found,
                metadata=metadata,
                truth_evidence=truth_evidence,
            )
        )
    return records


def sum_binance_income_realized_pnl(rows: list[dict[str, Any]] | None, *, symbol: str | None = None) -> float | None:
    if not isinstance(rows, list):
        return None
    total = 0.0
    matched = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("incomeType", "")).upper() != "REALIZED_PNL":
            continue
        if symbol and str(row.get("symbol", "")).upper() not in {"", symbol.upper()}:
            continue
        amount, ok = _first_float([row], "income")
        if ok and amount is not None:
            total += amount
            matched = True
    return total if matched else None


def _flatten_kraken_execution_rows(payload: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key in ("elements", "events", "executions", "history"):
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
    if rows:
        return rows
    if any(key in payload for key in ("event", "execution", "exec_id", "trade_id")):
        return [payload]
    return []


def _execution_candidate_dicts(row: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [row]
    event = row.get("event")
    if isinstance(event, dict):
        candidates.append(event)
        execution_wrapper = event.get("Execution")
        if isinstance(execution_wrapper, dict):
            candidates.append(execution_wrapper)
            execution = execution_wrapper.get("execution")
            if isinstance(execution, dict):
                candidates.append(execution)
                for key in ("makerOrder", "takerOrder", "oldTakerOrder", "makerOrderData", "takerOrderData"):
                    nested = execution.get(key)
                    if isinstance(nested, dict):
                        candidates.append(nested)
    execution = row.get("execution")
    if isinstance(execution, dict):
        candidates.append(execution)
        for key in ("makerOrder", "takerOrder", "oldTakerOrder", "makerOrderData", "takerOrderData"):
            nested = execution.get(key)
            if isinstance(nested, dict):
                candidates.append(nested)
    raw = row.get("raw")
    if isinstance(raw, dict):
        candidates.append(raw)
    return candidates


def _index_kraken_account_logs(logs: list[dict[str, Any]] | None) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for row in logs or []:
        if not isinstance(row, dict):
            continue
        key = _first_string([row], "execution", "booking_uid", "uid")
        if not key:
            continue
        indexed.setdefault(key, []).append(row)
    return indexed


def normalize_kraken_execution_history(
    payload: dict[str, Any] | list[dict[str, Any]] | None,
    *,
    symbol: str,
    side: str,
    order_id: str | None = None,
    client_order_id: str | None = None,
    account_logs: list[dict[str, Any]] | None = None,
) -> list[NormalizedLiveFillRecord]:
    records: list[NormalizedLiveFillRecord] = []
    log_index = _index_kraken_account_logs(account_logs)
    for row in _flatten_kraken_execution_rows(payload):
        candidates = _execution_candidate_dicts(row)
        trade_symbol = _first_string(candidates, "symbol", "tradeable", "contract", "instrument") or symbol
        current_order_id = _first_string(candidates, "order_id", "orderId", "uid")
        current_client_order_id = _first_string(candidates, "clientId", "clientOrderId", "cliOrdId", "clOrdId")
        if order_id and current_order_id and current_order_id != str(order_id):
            continue
        if client_order_id and current_client_order_id and current_client_order_id != str(client_order_id):
            continue
        trade_side = (_first_string(candidates, "side", "direction") or side).lower()
        if trade_side in {"buy", "sell"}:
            pass
        elif trade_side in {"bid", "ask"}:
            trade_side = "buy" if trade_side == "bid" else "sell"
        else:
            trade_side = side.lower()
        notional, notional_found = _first_float(candidates, "cost", "notional_amount", "cum_cost", "quoteQty")
        qty, qty_found = _first_float(candidates, "last_qty", "filled", "quantity", "size")
        price, price_found = _first_float(candidates, "last_price", "price", "trade_price", "limitPrice", "limit_price")
        if (notional is None or notional <= 0.0) and qty_found and price_found and qty is not None and price is not None:
            notional = abs(qty * price)
            notional_found = True
        if not notional_found or notional is None or notional <= 0.0:
            continue
        fee, fee_found = _extract_fee(candidates)
        execution_id = _first_string(candidates, "exec_id", "execution", "trade_id", "tradeId", "fill_id")
        matched_logs = log_index.get(execution_id, []) if execution_id else []
        realized_pnl = 0.0
        realized_found = False
        for log in matched_logs:
            amount, ok = _first_float([log], "realized_pnl")
            if ok and amount is not None:
                realized_pnl += amount
                realized_found = True
            if not fee_found:
                fee_amount, fee_ok = _first_float([log], "fee", "liquidation_fee")
                if fee_ok and fee_amount is not None:
                    fee = abs(fee_amount)
                    fee_found = True
        fill_id = execution_id or sha256(
            f"kraken_derivatives|{current_order_id}|{trade_symbol}|{trade_side}|{round(notional, 8)}".encode("utf-8")
        ).hexdigest()[:24]
        metadata = {
            "source": "execution_events",
            "client_order_id": current_client_order_id,
            "trade_time": _first_string(candidates, "timestamp", "time"),
            "execution_id": execution_id,
        }
        truth_evidence = {
            "source": "execution_events",
            "history_window_covered": True,
            "venue_event_ids": [fill_id],
            "duplicate_suppression": False,
            "out_of_order_repair_applied": False,
            "fee_present": fee_found,
            "realized_pnl_present": realized_found,
            "matched_account_log_rows": len(matched_logs),
        }
        records.append(
            _build_normalized_fill(
                venue="kraken_derivatives",
                symbol=trade_symbol,
                side=trade_side,
                order_id=current_order_id or fill_id,
                fill_id=fill_id,
                notional=notional,
                fee=fee,
                status="filled",
                realized_pnl=realized_pnl,
                fee_authoritative=fee_found,
                realized_pnl_authoritative=realized_found,
                metadata=metadata,
                truth_evidence=truth_evidence,
            )
        )
    return records


def sum_kraken_account_log_realized_pnl(
    logs: list[dict[str, Any]] | None,
    *,
    symbol: str | None = None,
) -> float | None:
    if not isinstance(logs, list):
        return None
    total = 0.0
    matched = False
    for row in logs:
        if not isinstance(row, dict):
            continue
        contract = str(row.get("contract", row.get("symbol", ""))).upper()
        if symbol and contract and contract != symbol.upper():
            continue
        amount, ok = _first_float([row], "realized_pnl")
        if ok and amount is not None:
            total += amount
            matched = True
    return total if matched else None
