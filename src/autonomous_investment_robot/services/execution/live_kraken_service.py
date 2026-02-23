from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.kraken_derivatives import KrakenDerivativesConnector
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.reconciliation.service import ReconciliationService


@dataclass
class LiveExecutionResult:
    status: str
    reason: str = ""
    order: dict[str, Any] | None = None


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
        self.killed = False
        self.kill_reason = ""
        self.cooldown_until_s = 0.0
        self._recent_cids: dict[str, float] = {}
        self._recent_intents: dict[str, float] = {}
        self._dedupe_ttl_s = 600.0

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
        if self.settings.risk.leverage != 0:
            return False, "risk_leverage_must_be_zero"
        info = self.connector.exchange_info() if hasattr(self.connector, "exchange_info") else {}
        symbols = {str(s.get("symbol", "")).upper() for s in info.get("symbols", []) if isinstance(s, dict)}
        for symbol in self.settings.universe:
            if symbols and symbol.upper() not in symbols:
                return False, f"symbol_missing:{symbol}"
        if not bool(getattr(self.connector, "supports_live_trading", False)):
            return False, "kraken_live_trading_not_implemented"
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

    def _is_filled(self, order: dict[str, Any]) -> bool:
        return str(order.get("status", "")).upper() in {"FILLED", "PARTIALLY_FILLED", "EXECUTED", "CLOSED"}

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
        if side == "buy":
            return bid if bid > 0 else ask
        return ask if ask > 0 else bid

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
        if self.safe_mode:
            return LiveExecutionResult(status="blocked", reason="safe_mode")
        if now < self.cooldown_until_s:
            return LiveExecutionResult(status="blocked", reason="cooldown")

        cid = self._client_order_id(intent.symbol, intent.side, now, 0)
        self._evict_dedupes(now)
        fp = self._intent_fingerprint(intent)
        if fp in self._recent_intents:
            return LiveExecutionResult(status="deduped", reason="intent_fingerprint_dedupe", order={"fingerprint": fp})
        if cid in self._recent_cids:
            return LiveExecutionResult(status="deduped", reason="local_dedupe", order={"clientOrderId": cid})

        existing = self._query_existing(intent.symbol, cid)
        if existing is not None:
            self._recent_cids[cid] = now
            self._recent_intents[fp] = now
            return LiveExecutionResult(status="deduped", order=existing)

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
            self._recent_cids[cid] = now
            self._recent_intents[fp] = now
        except Exception as exc:
            return self._reject_guard(f"maker_reject:{exc}", cid=cid)

        timeout_s = max(0, int(self.settings.execution.maker_timeout_s))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            current = self._query_existing(intent.symbol, cid)
            if current and self._is_filled(current):
                return LiveExecutionResult(status="filled_maker", order=current)
            time.sleep(0.25)

        try:
            self.connector.cancel_order(intent.symbol, cid)
        except Exception as exc:
            if self._is_rate_limit_error(str(exc)):
                return self._rate_limit_guard(f"cancel_rate_limit:{exc}", cid=cid)

        if not self._taker_fallback_edge_ok(intent):
            return LiveExecutionResult(status="timeout", reason="maker_timeout_edge_le_cost")

        taker_cid = self._client_order_id(intent.symbol, intent.side, now, 1)
        fallback_order = {
            **base_order,
            "newClientOrderId": taker_cid,
            "type": "MARKET",
        }
        try:
            out = self.connector.place_order(fallback_order)
            self._recent_cids[taker_cid] = now
            self._recent_intents[fp] = now
            return LiveExecutionResult(status="filled_taker_fallback", order=out)
        except Exception as exc:
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
        positions = self.connector.position_risk()
        exchange_exposure = 0.0
        for p in positions:
            amt = abs(float(p.get("positionAmt", p.get("size", p.get("qty", 0.0)))))
            mark = abs(float(p.get("markPrice", p.get("mark", p.get("price", 0.0)))))
            exchange_exposure += amt * mark
        rec_ok, reason = self.recon.reconcile_live(
            exchange_exposure=exchange_exposure,
            internal_exposure=internal_exposure,
            open_orders_state_ok=open_orders_state_ok,
            cash_ok=cash_ok,
        )
        if not rec_ok:
            self.request_kill("reconciliation_mismatch")
        return rec_ok, reason

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
