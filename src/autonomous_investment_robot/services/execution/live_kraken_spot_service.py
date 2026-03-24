from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector, KrakenSpotTradeRow
from autonomous_investment_robot.services.live_runtime.ledger import (
    NormalizedLiveFillRecord,
    _build_normalized_fill,
)
from autonomous_investment_robot.services.live_runtime.order_lifecycle import OrderLifecycleMirror
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.reconciliation.service import ReconciliationService


@dataclass
class LiveExecutionResult:
    status: str
    reason: str = ""
    order: dict[str, Any] | None = None
    ledger_records: list[NormalizedLiveFillRecord] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


@dataclass
class RejectTracker:
    timestamps: list[float] = field(default_factory=list)

    def add_reject(self, ts: float) -> None:
        self.timestamps.append(ts)
        self.timestamps = [x for x in self.timestamps if (ts - x) <= 60.0]

    def reject_storm(self, max_rejects: int) -> bool:
        return len(self.timestamps) > max_rejects


@dataclass
class RateLimitTracker:
    timestamps: list[float] = field(default_factory=list)

    def add_hit(self, ts: float) -> None:
        self.timestamps.append(ts)
        self.timestamps = [x for x in self.timestamps if (ts - x) <= 60.0]

    def storm(self, max_hits: int) -> bool:
        return len(self.timestamps) > max_hits


class LiveKrakenSpotService:
    def __init__(self, settings: RobotSettings, run_id: str, connector: KrakenSpotConnector | None = None) -> None:
        self.settings = settings
        self.run_id = run_id
        self.connector = connector or KrakenSpotConnector(settings.execution.kraken_spot)
        self.recon = ReconciliationService()
        self.rejects = RejectTracker()
        self.rate_limits = RateLimitTracker()
        self.safe_mode = False
        self.flatten_only = False
        self.killed = False
        self.kill_reason = ""
        self.cooldown_until_s = 0.0
        self._recent_cids: dict[str, float] = {}
        self._recent_intents: dict[str, float] = {}
        self._dedupe_ttl_s = 600.0
        self._order_status_by_id: dict[str, str] = {}
        self._fill_ids_seen: set[str] = set()
        self._lifecycle = OrderLifecycleMirror(venue="kraken_spot")
        self._market_integrity_state: dict[str, Any] = {
            "ts": None,
            "sequence_ok": True,
            "checksum_ok": True,
            "gap_count": 0,
            "checksum_mismatch_count": 0,
        }
        self._last_book_signature = ""
        self._last_book_change_ts: float | None = None
        self._book_repeat_count = 0
        self._auth_validated = False
        self._private_api_healthy = True
        self.user_stream_connected = False
        self.supports_replace = False
        self.supports_expire = True

    def _doctrine(self) -> dict[str, Any]:
        doctrine = getattr(self.settings, "doctrine", None)
        return {
            "target_provider": str(getattr(doctrine, "target_provider", "") or self.settings.execution.provider_id),
            "product_target": str(getattr(doctrine, "product_target", "") or "spot"),
            "long_only": bool(getattr(doctrine, "long_only", False)),
            "never_open_new_short_exposure": bool(getattr(doctrine, "never_open_new_short_exposure", False)),
            "minimum_sell_net_profit_bps": float(getattr(doctrine, "minimum_sell_net_profit_bps", 120.0) or 120.0),
            "enforce_cost_basis_sell_block": bool(getattr(doctrine, "enforce_cost_basis_sell_block", False)),
            "enforce_net_profit_sell_block": bool(getattr(doctrine, "enforce_net_profit_sell_block", False)),
            "block_non_reduce_only_sells": bool(getattr(doctrine, "block_non_reduce_only_sells", False)),
        }

    def _doctrine_ready(self) -> tuple[bool, str]:
        doctrine = self._doctrine()
        if doctrine["target_provider"] != "kraken_spot":
            return False, "doctrine_target_provider_not_kraken_spot"
        if doctrine["product_target"] != "spot":
            return False, "doctrine_product_target_not_spot"
        if not doctrine["long_only"]:
            return False, "doctrine_long_only_disabled"
        if not doctrine["never_open_new_short_exposure"]:
            return False, "doctrine_short_exposure_lock_disabled"
        if not doctrine["enforce_cost_basis_sell_block"]:
            return False, "doctrine_cost_basis_sell_block_disabled"
        if not doctrine["enforce_net_profit_sell_block"]:
            return False, "doctrine_net_profit_sell_block_disabled"
        if not doctrine["block_non_reduce_only_sells"]:
            return False, "doctrine_non_reduce_sell_block_disabled"
        if float(doctrine["minimum_sell_net_profit_bps"]) < 120.0:
            return False, "doctrine_minimum_sell_profit_floor_below_120bps"
        if not bool(getattr(self.settings.harmony, "enabled", False)):
            return False, "harmony_disabled"
        if not bool(getattr(self.settings.market_watch, "enabled", False)):
            return False, "market_watch_disabled"
        return True, "ok"

    def preflight(self) -> tuple[bool, str]:
        if "kraken_spot" not in self.settings.provider_whitelist:
            return False, "provider_not_whitelisted"
        doctrine_ok, doctrine_reason = self._doctrine_ready()
        if not doctrine_ok:
            return False, doctrine_reason
        mode = self.settings.execution_mode_enum()
        if mode == ExecutionMode.LIVE_READONLY:
            return True, "readonly"
        if not self.connector.has_credentials:
            return False, "missing_credentials"
        ok_perm, reason_perm = self.connector.verify_live_permissions()
        if not ok_perm:
            return False, reason_perm
        self._auth_validated = True
        if self.settings.risk.leverage != 0:
            return False, "risk_leverage_must_be_zero"
        info = self.connector.exchange_info()
        symbol_rows = {
            str(s.get("symbol", "")): s
            for s in info.get("symbols", [])
            if isinstance(s, dict)
        }
        for symbol in self.settings.universe:
            row = symbol_rows.get(symbol)
            if row is None:
                return False, f"symbol_missing:{symbol}"
            if not bool(row.get("active", False)) or not bool(row.get("spot", False)):
                return False, f"symbol_not_active_spot:{symbol}"
            constraints = self.connector.market_constraints(symbol)
            if not bool(constraints.get("active", False)) or not bool(constraints.get("spot", False)):
                return False, f"symbol_constraints_invalid:{symbol}"
            bal = self.connector.base_balance(symbol)
            if float(bal.get("total", 0.0) or 0.0) > max(1e-9, float(constraints.get("min_order_size", 0.0) or 0.0)):
                inventory = self._authoritative_inventory_state(symbol)
                if not inventory["ok"]:
                    return False, f"inventory_truth_invalid:{symbol}:{inventory['reason']}"
        return True, "ok"

    def _client_order_id(self, symbol: str, side: str, ts: float, slice_idx: int = 0) -> str:
        base = f"{self.run_id}|kraken_spot|{symbol}|{side}|{int(ts)}|{slice_idx}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]

    def _evict_dedupes(self, now: float) -> None:
        for store in (self._recent_cids, self._recent_intents):
            for k, t in list(store.items()):
                if now - t > self._dedupe_ttl_s:
                    del store[k]

    def _is_rate_limit_error(self, reason: str) -> bool:
        msg = reason.lower()
        return "429" in msg or "too many" in msg or "rate limit" in msg

    def _rate_limit_guard(self, reason: str, cid: str | None = None) -> LiveExecutionResult:
        now = time.time()
        self.rate_limits.add_hit(now)
        self._private_api_healthy = False
        if self.rate_limits.storm(max_hits=3):
            self.request_kill("rate_limit_storm")
            return LiveExecutionResult(status="killed", reason="rate_limit_storm", order={"clientOrderId": cid} if cid else None)
        return LiveExecutionResult(status="rejected", reason=reason, order={"clientOrderId": cid} if cid else None)

    def _reject_guard(self, reason: str, cid: str | None = None) -> LiveExecutionResult:
        if self._is_rate_limit_error(reason):
            return self._rate_limit_guard(reason, cid=cid)
        now = time.time()
        self.rejects.add_reject(now)
        if self.rejects.reject_storm(max_rejects=5):
            self.request_kill("reject_storm")
            return LiveExecutionResult(status="killed", reason="reject_storm", order={"clientOrderId": cid} if cid else None)
        return LiveExecutionResult(status="rejected", reason=reason, order={"clientOrderId": cid} if cid else None)

    def request_kill(self, reason: str = "operator_kill") -> None:
        self.killed = True
        self.safe_mode = True
        self.kill_reason = reason
        self.cooldown_until_s = max(self.cooldown_until_s, time.time() + 300)

    def enter_flatten_only(self, reason: str = "flatten_only") -> None:
        self.flatten_only = True
        self.safe_mode = True
        self.kill_reason = reason

    def _status_rank(self, status: str) -> int:
        ranks = {
            "NEW": 1,
            "PARTIALLY_FILLED": 2,
            "FILLED": 3,
            "CANCELED": 3,
            "REJECTED": 3,
            "EXECUTED": 3,
            "CLOSED": 3,
        }
        return ranks.get(str(status).upper(), 0)

    def _normalize_order_update(self, order: dict[str, Any]) -> dict[str, Any]:
        return {
            "clientOrderId": str(order.get("clientOrderId", order.get("cliOrdId", order.get("clOrdId", "")))),
            "orderId": str(order.get("orderId", order.get("order_id", ""))),
            "status": str(order.get("status", "NEW")).upper(),
            "symbol": str(order.get("symbol", "")),
            "raw": order,
        }

    def capture_market_integrity_evidence(self, book: dict[str, Any], now_dt: Any) -> None:
        prior = dict(self._market_integrity_state)
        ts = book.get("ts", book.get("timestamp", book.get("event_time", now_dt)))
        bid = str(book.get("bidPrice", ""))
        ask = str(book.get("askPrice", ""))
        bid_qty = str(book.get("bidQty", ""))
        ask_qty = str(book.get("askQty", ""))
        signature = f"{bid}|{ask}|{bid_qty}|{ask_qty}"
        capture_ts = float(now_dt.timestamp()) if hasattr(now_dt, "timestamp") else float(now_dt if isinstance(now_dt, (int, float)) else time.time())
        if signature == self._last_book_signature:
            self._book_repeat_count += 1
        else:
            self._book_repeat_count = 0
            self._last_book_signature = signature
            self._last_book_change_ts = capture_ts
        sequence_ok = bool(book.get("sequence_ok", book.get("sequenceOk", True)))
        checksum_ok = bool(book.get("checksum_ok", book.get("checksumOk", True)))
        gap_count = int(book.get("gap_count", 0) or 0)
        checksum_mismatch_count = int(book.get("checksum_mismatch_count", 0) or 0)
        if not sequence_ok:
            gap_count = max(gap_count, int(prior.get("gap_count", 0) or 0) + 1)
        if not checksum_ok:
            checksum_mismatch_count = max(checksum_mismatch_count, int(prior.get("checksum_mismatch_count", 0) or 0) + 1)
        self._market_integrity_state = {
            "ts": ts,
            "sequence_ok": sequence_ok,
            "checksum_ok": checksum_ok,
            "gap_count": gap_count,
            "checksum_mismatch_count": checksum_mismatch_count,
        }

    def market_integrity_evidence(self, now_dt: Any | None = None) -> dict[str, Any]:
        if hasattr(now_dt, "timestamp"):
            now_ts = float(now_dt.timestamp())
        else:
            now_ts = float(now_dt if isinstance(now_dt, (int, float)) else time.time())
        return {
            **dict(self._market_integrity_state),
            "user_stream_connected": self.user_stream_connected,
            "supports_replace": self.supports_replace,
            "supports_expire": self.supports_expire,
            "public_market_data_connected": bool(self._market_integrity_state.get("ts") is not None),
            "private_api_healthy": self._private_api_healthy,
            "auth_validated": self._auth_validated,
            "book_repeat_count": self._book_repeat_count,
            "seconds_since_distinct_book_change": 0.0
            if self._last_book_change_ts is None
            else max(0.0, now_ts - self._last_book_change_ts),
        }

    def capability_evidence(self, now_dt: Any | None = None) -> dict[str, Any]:
        evidence = self.market_integrity_evidence(now_dt=now_dt)
        return {
            "ts": evidence.get("ts"),
            "user_stream_connected": self.user_stream_connected,
            "lifecycle_snapshot_count": len(self.lifecycle_snapshot()),
            "sequence_ok": bool(evidence.get("sequence_ok", True)),
            "checksum_ok": bool(evidence.get("checksum_ok", True)),
            "replace_support_evidence": "dynamic",
            "expire_support_evidence": "dynamic",
            "auth_validated": self._auth_validated,
            "private_api_healthy": self._private_api_healthy,
            "public_market_data_connected": bool(evidence.get("public_market_data_connected", False)),
            "book_repeat_count": int(evidence.get("book_repeat_count", 0) or 0),
            "seconds_since_distinct_book_change": float(evidence.get("seconds_since_distinct_book_change", 0.0) or 0.0),
            "has_credentials": bool(self.connector.has_credentials),
            "supports_live_trading": bool(getattr(self.connector, "supports_live_trading", False)),
        }

    def apply_order_update(self, order: dict[str, Any]) -> tuple[bool, str]:
        normalized = self._normalize_order_update(order)
        key = normalized["clientOrderId"] or normalized["orderId"]
        if not key:
            return False, "missing_order_id"
        prior = self._order_status_by_id.get(key)
        if prior is not None and self._status_rank(normalized["status"]) < self._status_rank(prior):
            return False, "out_of_order_order_update"
        self._order_status_by_id[key] = normalized["status"]
        lifecycle_ok, lifecycle_reason = self._lifecycle.apply_exchange_update(normalized)
        return (True, "ok") if lifecycle_ok else (False, "out_of_order_order_update" if lifecycle_reason == "out_of_order_lifecycle_event" else lifecycle_reason)

    def apply_fill_update(self, fill: dict[str, Any]) -> tuple[bool, str]:
        fill_id = str(fill.get("fill_id", fill.get("fillId", fill.get("id", ""))))
        if not fill_id:
            return False, "missing_fill_id"
        if fill_id in self._fill_ids_seen:
            return False, "duplicate_fill_update"
        notional = float(fill.get("notional", fill.get("filledNotional", fill.get("quoteQty", 0.0))))
        if notional <= 0.0:
            return False, "non_positive_fill_notional"
        self._fill_ids_seen.add(fill_id)
        order_key = str(fill.get("order_id", fill.get("orderId", "")))
        if order_key:
            self._lifecycle.note_fill(order_key=order_key)
        return True, "ok"

    def rehydrate_state(self, order_events: list[dict[str, Any]], fill_events: list[dict[str, Any]]) -> dict[str, int]:
        self._order_status_by_id = {}
        self._fill_ids_seen = set()
        self._lifecycle.reset()
        order_count = 0
        fill_count = 0
        for event in order_events:
            payload = event.get("payload", event) if isinstance(event, dict) else {}
            if isinstance(payload, dict):
                ok, _ = self.apply_order_update(payload)
                if ok:
                    order_count += 1
        for event in fill_events:
            payload = event.get("payload", event) if isinstance(event, dict) else {}
            if isinstance(payload, dict):
                ok, _ = self.apply_fill_update(payload)
                if ok:
                    fill_count += 1
        return {"orders": order_count, "fills": fill_count}

    def drain_lifecycle_transitions(self) -> list[dict[str, Any]]:
        return self._lifecycle.drain_transitions()

    def lifecycle_snapshot(self) -> list[dict[str, Any]]:
        return self._lifecycle.snapshot()

    def _all_trade_history(self, symbol: str, *, limit: int = 50, max_pages: int = 20) -> list[KrakenSpotTradeRow]:
        rows: list[KrakenSpotTradeRow] = []
        seen: set[str] = set()
        offset = 0
        for _ in range(max_pages):
            page = self.connector.trade_history(symbol, offset=offset, limit=limit)
            if not page:
                break
            new_rows = [row for row in page if row.trade_id not in seen]
            if not new_rows:
                break
            rows.extend(new_rows)
            for row in new_rows:
                seen.add(row.trade_id)
            if len(page) < limit:
                break
            offset += len(page)
        rows.sort(key=lambda item: (item.timestamp_ms, item.trade_id))
        return rows

    def _reconstruct_inventory_state(self, symbol: str) -> dict[str, Any]:
        rows = self._all_trade_history(symbol)
        lots: list[dict[str, float]] = []
        realized_total = 0.0
        for row in rows:
            qty = float(row.base_qty or 0.0)
            if qty <= 0.0:
                continue
            if row.side == "buy":
                unit_cost = (float(row.quote_cost) + float(row.fee_quote)) / max(qty, 1e-12)
                lots.append({"qty": qty, "unit_cost": unit_cost})
                continue
            if row.side != "sell":
                continue
            remaining = qty
            basis_quote = 0.0
            while remaining > 1e-12 and lots:
                head = lots[0]
                consume = min(remaining, head["qty"])
                basis_quote += consume * head["unit_cost"]
                head["qty"] -= consume
                remaining -= consume
                if head["qty"] <= 1e-12:
                    lots.pop(0)
            if remaining > 1e-9:
                return {
                    "ok": False,
                    "reason": "trade_history_sell_exceeds_buys",
                    "lots": [],
                    "remaining_qty": 0.0,
                    "remaining_basis_quote": 0.0,
                    "avg_cost_quote": None,
                }
            realized_total += float(row.quote_cost) - float(row.fee_quote) - basis_quote
        remaining_qty = sum(float(lot["qty"]) for lot in lots)
        remaining_basis_quote = sum(float(lot["qty"]) * float(lot["unit_cost"]) for lot in lots)
        avg_cost = None if remaining_qty <= 1e-12 else remaining_basis_quote / remaining_qty
        return {
            "ok": True,
            "reason": "ok",
            "lots": lots,
            "remaining_qty": remaining_qty,
            "remaining_basis_quote": remaining_basis_quote,
            "avg_cost_quote": avg_cost,
            "realized_total_quote": realized_total,
            "trade_count": len(rows),
            "history_rows": rows,
        }

    def _authoritative_inventory_state(self, symbol: str) -> dict[str, Any]:
        state = self._reconstruct_inventory_state(symbol)
        if not state["ok"]:
            return state
        try:
            balance = self.connector.base_balance(symbol)
            constraints = self.connector.market_constraints(symbol)
        except Exception as exc:
            return {**state, "ok": False, "reason": f"balance_or_constraints_error:{exc}"}
        total_qty = float(balance.get("total", 0.0) or 0.0)
        min_qty = float(constraints.get("min_order_size", 0.0) or 0.0)
        tolerance = max(1e-8, min_qty, total_qty * 0.02)
        if abs(total_qty - float(state["remaining_qty"])) > tolerance:
            return {
                **state,
                "ok": False,
                "reason": "inventory_balance_history_mismatch",
                "balance_total_qty": total_qty,
                "balance_free_qty": float(balance.get("free", 0.0) or 0.0),
                "tolerance_qty": tolerance,
            }
        return {
            **state,
            "balance_total_qty": total_qty,
            "balance_free_qty": float(balance.get("free", 0.0) or 0.0),
        }

    def _basis_quote_for_qty(self, symbol: str, qty: float) -> tuple[float | None, list[str]]:
        state = self._authoritative_inventory_state(symbol)
        if not state["ok"]:
            return None, [str(state["reason"])]
        remaining = qty
        total_basis = 0.0
        for lot in state["lots"]:
            if remaining <= 1e-12:
                break
            consume = min(remaining, float(lot["qty"]))
            total_basis += consume * float(lot["unit_cost"])
            remaining -= consume
        if remaining > 1e-9:
            return None, ["requested_sell_qty_exceeds_authoritative_inventory"]
        return total_basis, []

    def authoritative_fill_history(
        self,
        symbol: str,
        *,
        side: str,
        order_id: str | None = None,
        client_order_id: str | None = None,  # noqa: ARG002
        since_ms: int | None = None,
    ) -> tuple[list[NormalizedLiveFillRecord], list[str]]:
        state = self._reconstruct_inventory_state(symbol)
        if not state["ok"]:
            return [], [str(state["reason"])]
        records: list[NormalizedLiveFillRecord] = []
        gaps: list[str] = []
        lots: list[dict[str, float]] = []
        for row in state["history_rows"]:
            qty = float(row.base_qty or 0.0)
            if qty <= 0.0:
                continue
            if row.side == "buy":
                unit_cost = (float(row.quote_cost) + float(row.fee_quote)) / max(qty, 1e-12)
                lots.append({"qty": qty, "unit_cost": unit_cost})
            elif row.side == "sell":
                remaining = qty
                basis_quote = 0.0
                while remaining > 1e-12 and lots:
                    head = lots[0]
                    consume = min(remaining, head["qty"])
                    basis_quote += consume * head["unit_cost"]
                    head["qty"] -= consume
                    remaining -= consume
                    if head["qty"] <= 1e-12:
                        lots.pop(0)
                if remaining > 1e-9:
                    gaps.append("trade_history_sell_exceeds_buys")
                    break
            else:
                continue
            if since_ms is not None and int(row.timestamp_ms) < int(since_ms):
                continue
            if order_id is not None and str(row.order_id) != str(order_id):
                continue
            if str(row.side).lower() != str(side).lower():
                continue
            realized_pnl = 0.0
            realized_authoritative = False
            if row.side == "sell":
                realized_pnl = float(row.quote_cost) - float(row.fee_quote) - basis_quote
                realized_authoritative = True
            records.append(
                _build_normalized_fill(
                    venue="kraken_spot",
                    symbol=symbol,
                    side=row.side,
                    order_id=str(row.order_id),
                    fill_id=str(row.trade_id),
                    notional=float(row.quote_cost),
                    fee=float(row.fee_quote),
                    latency_ms=0,
                    status="FILLED",
                    realized_pnl=realized_pnl,
                    fee_authoritative=True,
                    realized_pnl_authoritative=realized_authoritative,
                    metadata={
                        "timestamp_ms": int(row.timestamp_ms),
                        "price": float(row.price),
                        "base_qty": float(row.base_qty),
                    },
                    truth_evidence={"source": "kraken_spot_trade_history"},
                )
            )
        if not records:
            return [], list(sorted(set(gaps or ["execution_history_empty"])))
        return records, sorted(set(gaps))

    def authoritative_realized_pnl(self, symbol: str, *, since_ms: int | None = None) -> tuple[float | None, list[str]]:
        records, gaps = self.authoritative_fill_history(symbol, side="sell", since_ms=since_ms)
        if not records:
            return None, gaps
        return sum(float(record.realized_pnl) for record in records), gaps

    def authoritative_unrealized_pnl(self, symbol: str):
        state = self._authoritative_inventory_state(symbol)
        if not state["ok"]:
            return None, [str(state["reason"])]
        qty = float(state.get("balance_total_qty", 0.0) or 0.0)
        if qty <= 1e-12:
            return type("SpotTruth", (), {
                "symbol": symbol,
                "ts": datetime.now(timezone.utc),
                "source": "spot_inventory_empty",
                "confidence": "authoritative",
                "venue_value": 0.0,
                "reason": "no_open_spot_inventory",
                "evidence": {"remaining_qty": 0.0},
            })(), []
        book = self.connector.book_ticker(symbol)
        bid = float(book.get("bidPrice", 0.0) or 0.0)
        if not math.isfinite(bid) or bid <= 0.0:
            return None, ["book_invalid_for_unrealized_pnl"]
        venue_value = qty * bid - float(state.get("remaining_basis_quote", 0.0) or 0.0)
        return type("SpotTruth", (), {
            "symbol": symbol,
            "ts": datetime.now(timezone.utc),
            "source": "spot_trade_history_and_balance",
            "confidence": "authoritative",
            "venue_value": venue_value,
            "reason": "fifo_cost_basis_and_live_bid",
            "evidence": {
                "remaining_qty": qty,
                "remaining_basis_quote": float(state.get("remaining_basis_quote", 0.0) or 0.0),
                "bid": bid,
            },
        })(), []

    def _ledger_records_from_order(self, order: dict[str, Any], intent: OrderIntent) -> tuple[list[NormalizedLiveFillRecord], list[str]]:
        if not self._is_filled(order):
            return [], []
        order_id = str(order.get("orderId", order.get("order_id", order.get("raw", {}).get("order_id", ""))))
        records, gaps = self.authoritative_fill_history(
            intent.symbol,
            side=intent.side,
            order_id=order_id or None,
        )
        accepted_records: list[NormalizedLiveFillRecord] = []
        accepted_gaps = list(gaps)
        for record in records:
            accepted, accepted_reason = self.apply_fill_update({"fill_id": record.fill.fill_id, "notional": record.fill.notional, "order_id": record.fill.order_id})
            if not accepted:
                accepted_gaps.append(accepted_reason)
                continue
            accepted_records.append(record)
        return accepted_records, sorted(set(accepted_gaps))

    def _taker_fallback_edge_ok(self, intent: OrderIntent) -> bool:
        profitability = intent.why.get("profitability", {}) if isinstance(intent.why, dict) and isinstance(intent.why.get("profitability", {}), dict) else {}
        return float(profitability.get("net_edge_bps", 0.0) or 0.0) > 0.0

    def _intent_fingerprint(self, intent: OrderIntent) -> str:
        bucket = int(time.time() // 5)
        payload = f"{intent.symbol}|{intent.side}|{round(intent.target_notional, 6)}|{bucket}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def _book_prices(self, symbol: str) -> tuple[float, float]:
        book = self.connector.book_ticker(symbol)
        bid = float(book.get("bidPrice", 0.0) or 0.0)
        ask = float(book.get("askPrice", 0.0) or 0.0)
        if not math.isfinite(bid) or not math.isfinite(ask) or bid <= 0.0 or ask <= 0.0:
            raise ValueError(f"book_invalid:{bid}:{ask}")
        return bid, ask

    def _reduce_only(self, intent: OrderIntent) -> bool:
        if not isinstance(intent.why, dict):
            return False
        return bool(intent.why.get("reduce_only", False))

    def _market_watch_action(self, intent: OrderIntent) -> str:
        if not isinstance(intent.why, dict):
            return "continue"
        market_watch = intent.why.get("market_watch", {})
        if not isinstance(market_watch, dict):
            return "continue"
        return str(market_watch.get("action", "continue") or "continue")

    def _market_integrity_action(self, intent: OrderIntent) -> str:
        if not isinstance(intent.why, dict):
            return "continue"
        integrity = intent.why.get("market_integrity", {})
        if not isinstance(integrity, dict):
            return "continue"
        return str(integrity.get("action", "continue") or "continue")

    def _execution_plan_payload(self, intent: OrderIntent) -> dict[str, Any]:
        if not isinstance(intent.why, dict):
            return {}
        payload = intent.why.get("execution_plan", {})
        return payload if isinstance(payload, dict) else {}

    def _requested_order_style(self, intent: OrderIntent) -> str:
        style = str(self._execution_plan_payload(intent).get("order_style", "passive_limit") or "passive_limit")
        if style not in {"limit", "passive_limit", "marketable_limit"}:
            return "passive_limit"
        return style

    def _doctrine_target_ok(self, intent: OrderIntent) -> tuple[bool, str]:
        payload = intent.why if isinstance(intent.why, dict) else {}
        target = payload.get("doctrine_target", {})
        if not isinstance(target, dict):
            target = {}
        provider = str(target.get("provider", self.settings.execution.provider_id) or self.settings.execution.provider_id)
        product = str(target.get("product", "spot") or "spot")
        if provider != "kraken_spot":
            return False, f"doctrine_target_provider_invalid:{provider}"
        if product != "spot":
            return False, f"doctrine_target_product_invalid:{product}"
        return True, "ok"

    def _ordering_authorized(self) -> tuple[bool, str]:
        if self.settings.execution_mode_enum() != ExecutionMode.LIVE:
            return False, f"ordering_not_allowed_in_mode:{self.settings.execution_mode_enum().value}"
        doctrine_ok, doctrine_reason = self._doctrine_ready()
        if not doctrine_ok:
            return False, doctrine_reason
        if not self._auth_validated:
            return False, "preflight_not_completed"
        return True, "ok"

    def _sell_profit_guard(self, intent: OrderIntent, qty: float, bid: float, ask: float) -> str | None:
        doctrine = self._doctrine()
        if not doctrine["block_non_reduce_only_sells"] or not doctrine["enforce_cost_basis_sell_block"] or not doctrine["enforce_net_profit_sell_block"]:
            return "sell_doctrine_guards_disabled"
        inventory = self._authoritative_inventory_state(intent.symbol)
        if not inventory["ok"]:
            return f"inventory_truth_missing:{inventory['reason']}"
        free_qty = float(inventory.get("balance_free_qty", 0.0) or 0.0)
        tolerance = max(1e-8, qty * 0.02)
        if qty > free_qty + tolerance:
            return f"insufficient_spot_inventory:{qty:.8f}>{free_qty:.8f}"
        basis_quote, gaps = self._basis_quote_for_qty(intent.symbol, qty)
        if basis_quote is None:
            return f"cost_basis_truth_missing:{','.join(gaps) if gaps else 'unknown'}"
        sell_quote = qty * bid
        if sell_quote <= basis_quote:
            return f"sell_below_cost_basis:{sell_quote:.8f}<={basis_quote:.8f}"
        spread_bps = ((ask - bid) / max((ask + bid) / 2.0, 1e-9)) * 10000.0
        modeled_cost_bps = float(self.settings.execution.fee_bps) + float(self.settings.execution.slippage_bps) + max(0.0, spread_bps)
        modeled_exit_cost_quote = sell_quote * modeled_cost_bps / 10000.0
        net_profit_quote = sell_quote - modeled_exit_cost_quote - basis_quote
        if net_profit_quote <= 0.0:
            return f"sell_net_profit_non_positive:{net_profit_quote:.8f}"
        net_profit_bps = (net_profit_quote / max(basis_quote, 1e-9)) * 10000.0
        if net_profit_bps < max(120.0, float(doctrine["minimum_sell_net_profit_bps"])):
            return f"sell_net_profit_floor_breach:{net_profit_bps:.4f}"
        return None

    def _pre_submit_validate_intent(self, intent: OrderIntent) -> tuple[str | None, dict[str, Any]]:
        ok_target, target_reason = self._doctrine_target_ok(intent)
        if not ok_target:
            return target_reason, {}
        side = str(intent.side).lower()
        if side not in {"buy", "sell"}:
            return f"invalid_order_side:{intent.side}", {}
        try:
            target_notional = float(intent.target_notional)
        except Exception:
            return "invalid_target_notional:non_numeric", {}
        if not math.isfinite(target_notional) or target_notional <= 0.0:
            return f"invalid_target_notional:{target_notional}", {}
        if self._market_watch_action(intent) == "block_entries" and not self._reduce_only(intent):
            return "market_watch_blocks_entries", {}
        if self._market_integrity_action(intent) in {"flatten_only", "halt"} and not self._reduce_only(intent):
            return "market_integrity_blocks_entries", {}
        try:
            constraints = self.connector.market_constraints(intent.symbol)
            bid, ask = self._book_prices(intent.symbol)
        except Exception as exc:
            return str(exc), {}
        if not bool(constraints.get("active", False)) or not bool(constraints.get("spot", False)):
            return f"invalid_spot_symbol_constraints:{intent.symbol}", {}
        maker_price = bid if side == "buy" else ask
        conservative_price = ask if side == "buy" else bid
        try:
            raw_qty = target_notional / max(conservative_price, 1e-12)
            qty = self.connector.normalize_amount(intent.symbol, raw_qty)
            price = self.connector.normalize_price(intent.symbol, maker_price)
        except Exception as exc:
            return str(exc), {}
        if not math.isfinite(qty) or qty <= 0.0:
            return f"invalid_quantity:{qty}", {}
        if not math.isfinite(price) or price <= 0.0:
            return f"invalid_price:{price}", {}
        min_qty = float(constraints.get("min_order_size", 0.0) or 0.0)
        min_notional = float(constraints.get("min_notional", 0.0) or 0.0)
        executable_notional = qty * conservative_price
        if qty < min_qty:
            return f"below_min_order_size:{qty:.8f}", {}
        if executable_notional < min_notional:
            return f"below_min_notional:{executable_notional:.8f}", {}
        if side == "sell":
            if not self._reduce_only(intent):
                return "long_only_non_reduce_sell_block", {}
            sell_guard = self._sell_profit_guard(intent, qty, bid, ask)
            if sell_guard is not None:
                return sell_guard, {}
        return None, {
            "qty": qty,
            "maker_price": price,
            "conservative_price": conservative_price,
            "constraints": constraints,
        }

    def _submit_limit_order(
        self,
        *,
        intent: OrderIntent,
        cid: str,
        now: float,
        fp: str,
        qty: float,
        price: float,
        post_only: bool,
        success_status: str,
        timeout_reason: str,
    ) -> LiveExecutionResult:
        preview_ok, preview_reason = self.connector.validate_order_preview(
            symbol=intent.symbol,
            side=str(intent.side),
            amount=qty,
            price=price,
            post_only=post_only,
        )
        if not preview_ok:
            self._lifecycle.rejected(symbol=intent.symbol, order_key=cid, error=preview_reason)
            self.request_kill(f"order_preview_failed:{preview_reason}")
            return LiveExecutionResult(status="killed", reason=f"order_preview_failed:{preview_reason}")

        payload = {
            "symbol": intent.symbol,
            "side": str(intent.side).upper(),
            "quantity": f"{qty:.8f}",
            "newClientOrderId": cid,
            "type": "LIMIT",
            "price": f"{price:.8f}",
        }
        if post_only:
            payload["postOnly"] = True
        try:
            placed = self.connector.place_order(payload)
            self.apply_order_update(placed)
            self._recent_cids[cid] = now
            self._recent_intents[fp] = now
        except Exception as exc:
            self._lifecycle.rejected(symbol=intent.symbol, order_key=cid, error=str(exc))
            return self._reject_guard(f"{'maker' if post_only else 'marketable_limit'}_reject:{exc}", cid=cid)

        if self._is_filled(placed):
            ledger_records, gaps = self._ledger_records_from_order(placed, intent)
            return LiveExecutionResult(status=success_status, order=placed, ledger_records=ledger_records, gaps=gaps)

        timeout_s = max(0, int(self.settings.execution.maker_timeout_s))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            current = self._query_existing(intent.symbol, cid)
            if current and self._is_filled(current):
                self.apply_order_update(current)
                ledger_records, gaps = self._ledger_records_from_order(current, intent)
                return LiveExecutionResult(status=success_status, order=current, ledger_records=ledger_records, gaps=gaps)
            time.sleep(0.25)

        try:
            self._lifecycle.cancel_requested(symbol=intent.symbol, order_key=cid)
            self.connector.cancel_order(intent.symbol, cid)
            self.apply_order_update({"clientOrderId": cid, "symbol": intent.symbol, "status": "CANCELED"})
        except Exception as exc:
            self._lifecycle.cancel_rejected(symbol=intent.symbol, order_key=cid, error=str(exc))
            if self._is_rate_limit_error(str(exc)):
                return self._rate_limit_guard(f"cancel_rate_limit:{exc}", cid=cid)
        self._lifecycle.timed_out(symbol=intent.symbol, order_key=cid)
        return LiveExecutionResult(status="timeout", reason=timeout_reason, order={"clientOrderId": cid, "symbol": intent.symbol})

    def _query_existing(self, symbol: str, client_order_id: str):
        try:
            return self.connector.query_order(symbol, client_order_id)
        except Exception as exc:
            msg = str(exc).lower()
            if "not found" in msg or "unknown" in msg:
                return None
            raise

    def execute_readonly(self, intent: OrderIntent) -> LiveExecutionResult:
        if self.settings.execution_mode_enum() != ExecutionMode.LIVE_READONLY:
            return LiveExecutionResult(status="error", reason="not_readonly_mode")
        preview_error, preview_meta = self._pre_submit_validate_intent(intent)
        preview = {
            "symbol": intent.symbol,
            "side": intent.side,
            "target_notional": intent.target_notional,
            "book": self.connector.book_ticker(intent.symbol),
            "validation_error": preview_error,
            "validation": preview_meta,
        }
        return LiveExecutionResult(status="readonly_preview", order=preview)

    def _is_filled(self, order: dict[str, Any]) -> bool:
        return str(order.get("status", "")).upper() in {"FILLED", "PARTIALLY_FILLED", "EXECUTED", "CLOSED"}

    def execute_intent(self, intent: OrderIntent) -> LiveExecutionResult:
        now = time.time()
        if self.killed:
            return LiveExecutionResult(status="killed", reason=self.kill_reason or "kill_switch_active")
        if self.flatten_only and not self._reduce_only(intent):
            return LiveExecutionResult(status="blocked", reason="flatten_only")
        if self.safe_mode and not self._reduce_only(intent):
            return LiveExecutionResult(status="blocked", reason="safe_mode")
        if now < self.cooldown_until_s:
            return LiveExecutionResult(status="blocked", reason="cooldown")
        ordering_ok, ordering_reason = self._ordering_authorized()
        if not ordering_ok:
            self.request_kill(ordering_reason)
            return LiveExecutionResult(status="killed", reason=ordering_reason)

        pre_submit_error, validation = self._pre_submit_validate_intent(intent)
        if pre_submit_error is not None:
            self.request_kill(pre_submit_error)
            return LiveExecutionResult(status="killed", reason=pre_submit_error)

        cid = self._client_order_id(intent.symbol, intent.side, now, 0)
        self._evict_dedupes(now)
        fp = self._intent_fingerprint(intent)
        if fp in self._recent_intents:
            return LiveExecutionResult(status="deduped", reason="intent_fingerprint_dedupe", order={"fingerprint": fp})
        if cid in self._recent_cids:
            return LiveExecutionResult(status="deduped", reason="local_dedupe", order={"clientOrderId": cid})

        existing = self._query_existing(intent.symbol, cid)
        if existing is not None:
            self.apply_order_update(existing)
            self._recent_cids[cid] = now
            self._recent_intents[fp] = now
            ledger_records, gaps = self._ledger_records_from_order(existing, intent)
            return LiveExecutionResult(status="deduped", order=existing, ledger_records=ledger_records, gaps=gaps)
        qty = float(validation["qty"])
        maker_price = float(validation["maker_price"])
        self._lifecycle.submit(symbol=intent.symbol, order_key=cid, metadata={"side": intent.side, "requested_order_style": self._requested_order_style(intent)})
        requested_order_style = self._requested_order_style(intent)
        if requested_order_style == "marketable_limit":
            return self._submit_limit_order(
                intent=intent,
                cid=cid,
                now=now,
                fp=fp,
                qty=qty,
                price=float(validation["conservative_price"]),
                post_only=False,
                success_status="filled_marketable_limit",
                timeout_reason="marketable_limit_timeout",
            )

        maker_result = self._submit_limit_order(
            intent=intent,
            cid=cid,
            now=now,
            fp=fp,
            qty=qty,
            price=maker_price,
            post_only=True,
            success_status="filled_maker",
            timeout_reason="maker_timeout",
        )
        if maker_result.status != "timeout":
            return maker_result

        if str(intent.side).lower() == "sell":
            refreshed_error, refreshed_validation = self._pre_submit_validate_intent(intent)
            if refreshed_error is not None:
                self.request_kill(refreshed_error)
                return LiveExecutionResult(status="killed", reason=refreshed_error)
            taker_cid = self._client_order_id(intent.symbol, intent.side, now, 1)
            self._lifecycle.submit(symbol=intent.symbol, order_key=taker_cid, metadata={"side": intent.side, "fallback": True, "requested_order_style": "marketable_limit"})
            return self._submit_limit_order(
                intent=intent,
                cid=taker_cid,
                now=now,
                fp=fp,
                qty=float(refreshed_validation["qty"]),
                price=float(refreshed_validation["conservative_price"]),
                post_only=False,
                success_status="filled_marketable_limit",
                timeout_reason="sell_marketable_limit_timeout",
            )

        if not self._taker_fallback_edge_ok(intent):
            return LiveExecutionResult(status="timeout", reason="maker_timeout_edge_le_cost", order=maker_result.order)

        taker_cid = self._client_order_id(intent.symbol, intent.side, now, 1)
        fallback_order = {
            "symbol": intent.symbol,
            "side": str(intent.side).upper(),
            "quantity": f"{qty:.8f}",
            "newClientOrderId": taker_cid,
            "type": "MARKET",
        }
        try:
            self._lifecycle.submit(symbol=intent.symbol, order_key=taker_cid, metadata={"side": intent.side, "fallback": True})
            out = self.connector.place_order(fallback_order)
            self.apply_order_update(out)
            self._recent_cids[taker_cid] = now
            self._recent_intents[fp] = now
            ledger_records, gaps = self._ledger_records_from_order(out, intent)
            return LiveExecutionResult(status="filled_taker_fallback", order=out, ledger_records=ledger_records, gaps=gaps)
        except Exception as exc:
            self._lifecycle.rejected(symbol=intent.symbol, order_key=taker_cid, error=str(exc))
            return self._reject_guard(f"taker_reject:{exc}", cid=taker_cid)

    def _cancel_open_orders_best_effort(self) -> None:
        try:
            orders = self.connector.open_orders()
        except Exception:
            return
        if not isinstance(orders, list):
            return
        for o in orders:
            symbol = str(o.get("symbol", ""))
            cid = str(o.get("clientOrderId", o.get("clOrdId", o.get("orderId", ""))))
            if not symbol or not cid:
                continue
            try:
                self.connector.cancel_order(symbol, cid)
            except Exception:
                continue

    def flatten_all_positions(self, max_attempts: int = 3) -> tuple[bool, str]:
        ordering_ok, ordering_reason = self._ordering_authorized()
        if not ordering_ok:
            return False, ordering_reason
        self._cancel_open_orders_best_effort()
        for _ in range(max_attempts):
            non_zero: list[tuple[str, float]] = []
            for symbol in self.settings.universe:
                try:
                    bal = self.connector.base_balance(symbol)
                except Exception:
                    continue
                free_qty = float(bal.get("free", 0.0) or 0.0)
                if free_qty > 1e-9:
                    non_zero.append((symbol, free_qty))
            if not non_zero:
                return True, "flat"
            for symbol, qty in non_zero:
                try:
                    qty_norm = self.connector.normalize_amount(symbol, qty)
                    if qty_norm <= 0.0:
                        continue
                    self.connector.place_order(
                        {
                            "symbol": symbol,
                            "side": "SELL",
                            "type": "MARKET",
                            "quantity": f"{qty_norm:.8f}",
                            "newClientOrderId": self._client_order_id(symbol, "sell", time.time(), 999),
                        }
                    )
                except Exception:
                    continue
            time.sleep(0.5)
        for symbol in self.settings.universe:
            try:
                bal = self.connector.base_balance(symbol)
            except Exception:
                continue
            if float(bal.get("free", 0.0) or 0.0) > 1e-9:
                return False, "flatten_failed"
        return True, "flat"

    def emergency_kill_and_flatten(self, max_attempts: int = 3) -> tuple[bool, str]:
        self.request_kill("emergency")
        return self.flatten_all_positions(max_attempts=max_attempts)

    def reconcile_live_state(
        self,
        internal_exposure: float,
        open_orders_state_ok: bool = True,
        cash_ok: bool = True,
    ) -> tuple[bool, str]:
        balance_ok, balance_reason = self._balance_state_ok()
        effective_cash_ok = bool(cash_ok and balance_ok)
        positions = self.connector.position_risk()
        exchange_exposure = 0.0
        for p in positions:
            amt = abs(float(p.get("positionAmt", p.get("size", p.get("qty", 0.0)))))
            mark = abs(float(p.get("markPrice", p.get("mark", p.get("price", 0.0)))))
            exchange_exposure += amt * mark
        report = self.recon.reconcile_live_report(
            exchange_exposure=exchange_exposure,
            internal_exposure=internal_exposure,
            open_orders_state_ok=open_orders_state_ok,
            cash_ok=effective_cash_ok,
        )
        reason = report.code
        if report.code == "live_cash_mismatch" and not balance_ok:
            reason = f"{reason}:{balance_reason}"
        if not report.ok:
            self.request_kill("reconciliation_mismatch")
        return report.ok, reason

    def _balance_state_ok(self) -> tuple[bool, str]:
        try:
            rows = self.connector.balances()
        except Exception as exc:
            return False, f"balance_fetch_error:{exc}"
        if not isinstance(rows, list) or not rows:
            return False, "balance_empty"
        total = 0.0
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("balance", "equity", "availableBalance"):
                if key not in row:
                    continue
                try:
                    total += max(0.0, float(row.get(key, 0.0)))
                    break
                except Exception:
                    continue
        if total <= 0.0:
            return False, "balance_non_positive"
        return True, "ok"

    def reconcile_and_flatten_on_mismatch(
        self,
        internal_exposure: float,
        open_orders_state_ok: bool = True,
        cash_ok: bool = True,
        max_flatten_attempts: int = 3,
    ) -> tuple[bool, str]:
        ok, reason = self.reconcile_live_state(
            internal_exposure=internal_exposure,
            open_orders_state_ok=open_orders_state_ok,
            cash_ok=cash_ok,
        )
        if ok:
            return True, reason
        closed, flat_reason = self.flatten_all_positions(max_attempts=max_flatten_attempts)
        if closed:
            return False, f"{reason};flattened"
        return False, f"{reason};{flat_reason}"
