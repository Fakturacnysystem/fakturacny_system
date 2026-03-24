from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.kraken_derivatives import KrakenDerivativesConnector
from autonomous_investment_robot.services.live_runtime.ledger import (
    NormalizedLiveFillRecord,
    extract_exchange_unrealized_pnl_truth,
    normalize_kraken_execution_history,
    normalize_live_fill,
    sum_kraken_account_log_realized_pnl,
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


class LiveKrakenService:
    def __init__(self, settings: RobotSettings, run_id: str, connector: KrakenDerivativesConnector | None = None) -> None:
        self.settings = settings
        self.run_id = run_id
        self.connector = connector or KrakenDerivativesConnector(settings.execution.kraken)
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
        self._lifecycle = OrderLifecycleMirror(venue="kraken_derivatives")
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

    def preflight(self) -> tuple[bool, str]:
        if "kraken_derivatives" not in self.settings.provider_whitelist:
            return False, "provider_not_whitelisted"
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
        info = self.connector.exchange_info() if hasattr(self.connector, "exchange_info") else {}
        symbols = {str(s.get("symbol", "")).upper() for s in info.get("symbols", []) if isinstance(s, dict)}
        for symbol in self.settings.universe:
            if symbols and symbol.upper() not in symbols:
                return False, f"symbol_missing:{symbol}"
        if not bool(getattr(self.connector, "supports_live_trading", False)):
            return False, "kraken_live_trading_not_implemented"
        balance_ok, balance_reason = self._balance_state_ok()
        if not balance_ok:
            return False, f"balance_state_invalid:{balance_reason}"
        return True, "ok"

    def _client_order_id(self, symbol: str, side: str, ts: float, slice_idx: int = 0) -> str:
        base = f"{self.run_id}|kraken|{symbol}|{side}|{int(ts)}|{slice_idx}"
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

    def mark_orphan_order(self, order: dict[str, Any]) -> None:
        key = str(order.get("clientOrderId", order.get("origClientOrderId", order.get("orderId", ""))))
        symbol = str(order.get("symbol", ""))
        status = str(order.get("status", "NEW")).upper()
        if key:
            self._lifecycle.orphaned(symbol=symbol, order_key=key, exchange_status=status)

    def _is_filled(self, order: dict[str, Any]) -> bool:
        return str(order.get("status", "")).upper() in {"FILLED", "PARTIALLY_FILLED", "EXECUTED", "CLOSED"}

    def authoritative_fill_history(
        self,
        symbol: str,
        *,
        side: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
        since_ms: int | None = None,
    ) -> tuple[list[NormalizedLiveFillRecord], list[str]]:
        try:
            executions = self.connector.execution_events(since=since_ms, count=200, sort="desc")
        except Exception as exc:
            return [], [f"execution_events_error:{exc}"]
        try:
            account_logs = self.connector.account_log(since=since_ms, sort="desc")
        except Exception as exc:
            return [], [f"account_log_error:{exc}"]
        records = normalize_kraken_execution_history(
            executions,
            symbol=symbol,
            side=side,
            order_id=order_id,
            client_order_id=client_order_id,
            account_logs=account_logs,
        )
        if not records:
            return [], ["execution_history_empty"]
        gaps: list[str] = []
        for record in records:
            gaps.extend(record.gaps)
        return records, gaps

    def authoritative_realized_pnl(self, symbol: str, *, since_ms: int | None = None) -> tuple[float | None, list[str]]:
        try:
            logs = self.connector.account_log(since=since_ms, sort="desc")
        except Exception as exc:
            return None, [f"account_log_error:{exc}"]
        realized = sum_kraken_account_log_realized_pnl(logs, symbol=symbol)
        if realized is None:
            return None, ["account_log_realized_pnl_empty"]
        return realized, []

    def authoritative_unrealized_pnl(self, symbol: str):
        try:
            rows = self.connector.position_risk(symbol)
        except Exception as exc:
            return None, [f"position_risk_error:{exc}"]
        truth = extract_exchange_unrealized_pnl_truth(rows, symbol=symbol)
        gaps: list[str] = []
        if truth.confidence != "authoritative":
            gaps.append(truth.reason or "unrealized_pnl_truth_gap")
        return truth, gaps

    def _ledger_records_from_order(self, order: dict[str, Any], intent: OrderIntent) -> tuple[list[NormalizedLiveFillRecord], list[str]]:
        if not self._is_filled(order):
            return [], []
        order_id = str(order.get("orderId", order.get("order_id", order.get("raw", {}).get("order_id", ""))))
        client_order_id = str(order.get("clientOrderId", order.get("cliOrdId", order.get("clOrdId", ""))))
        records, gaps = self.authoritative_fill_history(
            intent.symbol,
            side=intent.side,
            order_id=order_id or None,
            client_order_id=client_order_id or None,
        )
        if not records:
            fallback_record, fallback_reason = normalize_live_fill(
                order,
                venue="kraken_derivatives",
                fallback_symbol=intent.symbol,
                fallback_side=intent.side,
            )
            if fallback_record is not None:
                gaps = list(gaps) + ["native_fill_history_unavailable"]
            return [], list(gaps or [fallback_reason])
        accepted_records: list[NormalizedLiveFillRecord] = []
        accepted_gaps = list(gaps)
        for record in records:
            accepted, accepted_reason = self.apply_fill_update({"fill_id": record.fill.fill_id, "notional": record.fill.notional})
            if not accepted:
                accepted_gaps.append(accepted_reason)
                continue
            accepted_records.append(record)
        return accepted_records, accepted_gaps

    def _taker_fallback_edge_ok(self, intent: OrderIntent) -> bool:
        comps = intent.why.get("components", []) if isinstance(intent.why, dict) else []
        if not comps:
            return True
        return any(float(c.get("final_edge_bps", c.get("edge_bps", 0.0))) > float(c.get("cost_total_bps", 0.0)) for c in comps)

    def _intent_fingerprint(self, intent: OrderIntent) -> str:
        bucket = int(time.time() // 5)
        payload = f"{intent.symbol}|{intent.side}|{round(intent.target_notional, 6)}|{bucket}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def _price_from_book(self, symbol: str, side: str) -> float:
        book = self.connector.book_ticker(symbol)
        bid = float(book.get("bidPrice", 0.0))
        ask = float(book.get("askPrice", 0.0))
        if not math.isfinite(bid) or not math.isfinite(ask) or bid <= 0.0 or ask <= 0.0:
            raise ValueError(f"book_invalid:{bid}:{ask}")
        if side == "buy":
            return bid if bid > 0 else ask
        return ask if ask > 0 else bid

    def _pre_submit_validate_intent(self, intent: OrderIntent) -> str | None:
        if str(intent.side).lower() not in {"buy", "sell"}:
            return f"invalid_order_side:{intent.side}"
        try:
            target_notional = float(intent.target_notional)
        except Exception:
            return "invalid_target_notional:non_numeric"
        if not math.isfinite(target_notional) or target_notional <= 0.0:
            return f"invalid_target_notional:{target_notional}"
        try:
            self._price_from_book(intent.symbol, intent.side)
        except Exception as exc:
            return str(exc)
        return None

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
        preview = {
            "symbol": intent.symbol,
            "side": intent.side,
            "target_notional": intent.target_notional,
            "book": self.connector.book_ticker(intent.symbol),
        }
        return LiveExecutionResult(status="readonly_preview", order=preview)

    def execute_intent(self, intent: OrderIntent) -> LiveExecutionResult:
        now = time.time()
        if self.killed:
            return LiveExecutionResult(status="killed", reason=self.kill_reason or "kill_switch_active")
        if self.flatten_only:
            return LiveExecutionResult(status="blocked", reason="flatten_only")
        if self.safe_mode:
            return LiveExecutionResult(status="blocked", reason="safe_mode")
        if now < self.cooldown_until_s:
            return LiveExecutionResult(status="blocked", reason="cooldown")

        pre_submit_error = self._pre_submit_validate_intent(intent)
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

        self._lifecycle.submit(symbol=intent.symbol, order_key=cid, metadata={"side": intent.side})

        price = self._price_from_book(intent.symbol, intent.side)
        qty = max(0.001, intent.target_notional / max(price, 1e-9))
        base_order = {
            "symbol": intent.symbol,
            "side": intent.side.upper(),
            "quantity": f"{qty:.6f}",
            "newClientOrderId": cid,
        }
        maker_order = {
            **base_order,
            "type": "LIMIT",
            "postOnly": True,
            "price": f"{price:.2f}",
        }

        try:
            placed = self.connector.place_order(maker_order)
            self.apply_order_update(placed)
            self._recent_cids[cid] = now
            self._recent_intents[fp] = now
        except Exception as exc:
            self._lifecycle.rejected(symbol=intent.symbol, order_key=cid, error=str(exc))
            return self._reject_guard(f"maker_reject:{exc}", cid=cid)

        timeout_s = max(0, int(self.settings.execution.maker_timeout_s))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            current = self._query_existing(intent.symbol, cid)
            if current and self._is_filled(current):
                self.apply_order_update(current)
                ledger_records, gaps = self._ledger_records_from_order(current, intent)
                return LiveExecutionResult(status="filled_maker", order=current, ledger_records=ledger_records, gaps=gaps)
            time.sleep(0.25)

        try:
            self._lifecycle.cancel_requested(symbol=intent.symbol, order_key=cid)
            self.connector.cancel_order(intent.symbol, cid)
            self.apply_order_update({"clientOrderId": cid, "symbol": intent.symbol, "status": "CANCELED"})
        except Exception as exc:
            self._lifecycle.cancel_rejected(symbol=intent.symbol, order_key=cid, error=str(exc))
            if self._is_rate_limit_error(str(exc)):
                return self._rate_limit_guard(f"cancel_rate_limit:{exc}", cid=cid)

        if not self._taker_fallback_edge_ok(intent):
            self._lifecycle.timed_out(symbol=intent.symbol, order_key=cid)
            return LiveExecutionResult(status="timeout", reason="maker_timeout_edge_le_cost")

        taker_cid = self._client_order_id(intent.symbol, intent.side, now, 1)
        fallback_order = {
            **base_order,
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
            cid = str(o.get("clientOrderId", o.get("clOrdId", o.get("order_id", ""))))
            if not symbol or not cid:
                continue
            try:
                self.connector.cancel_order(symbol, cid)
            except Exception:
                continue

    def flatten_all_positions(self, max_attempts: int = 3) -> tuple[bool, str]:
        if not self.settings.execution.kraken.reduce_only_on_flatten:
            return False, "flatten_disabled"
        self._cancel_open_orders_best_effort()
        for _ in range(max_attempts):
            positions = self.connector.position_risk()
            non_zero: list[tuple[str, float]] = []
            for p in positions:
                amt = float(p.get("positionAmt", p.get("size", p.get("qty", 0.0))))
                if abs(amt) < 1e-9:
                    continue
                symbol = str(p.get("symbol", p.get("instrument", "")))
                non_zero.append((symbol, amt))

            if not non_zero:
                return True, "flat"

            for symbol, amt in non_zero:
                side = "SELL" if amt > 0 else "BUY"
                self.connector.place_order(
                    {
                        "symbol": symbol,
                        "side": side,
                        "type": "MARKET",
                        "reduceOnly": True,
                        "quantity": f"{abs(amt):.6f}",
                        "newClientOrderId": self._client_order_id(symbol, side.lower(), time.time(), 999),
                    }
                )
            time.sleep(0.5)

        final_positions = self.connector.position_risk()
        still_open = []
        for p in final_positions:
            amt = float(p.get("positionAmt", p.get("size", p.get("qty", 0.0))))
            if abs(amt) > 1e-9:
                still_open.append(p)
        if still_open:
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
        if not hasattr(self.connector, "balances"):
            return True, "balance_check_not_supported"
        try:
            rows = self.connector.balances()  # type: ignore[attr-defined]
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
