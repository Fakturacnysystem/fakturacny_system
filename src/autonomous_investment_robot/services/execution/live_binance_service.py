from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.binance_um_perps import BinanceConnectorError, BinanceUMPerpsConnector
from autonomous_investment_robot.services.execution.binance_user_stream import BinanceUserStream
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


class LiveBinanceService:
    def __init__(self, settings: RobotSettings, run_id: str, connector: BinanceUMPerpsConnector | None = None) -> None:
        self.settings = settings
        self.run_id = run_id
        self.connector = connector or BinanceUMPerpsConnector(settings.execution.binance)
        self.recon = ReconciliationService()
        self.rejects = RejectTracker()
        self.safe_mode = False
        self.killed = False
        self.cooldown_until_s = 0.0
        self._recent_cids: dict[str, float] = {}
        self._dedupe_ttl_s = 600.0  # 10 min

    def preflight(self) -> tuple[bool, str]:
        if self.settings.execution_mode_enum() == ExecutionMode.LIVE_READONLY:
            return True, "readonly"

        ok_perm, reason_perm = self.connector.verify_live_permissions()
        if not ok_perm:
            return False, reason_perm

        if "binance_um_perps" not in self.settings.provider_whitelist:
            return False, "provider_not_whitelisted"

        if not self.connector.has_credentials:
            return False, "missing_credentials"

        info = self.connector.exchange_info()
        symbols = {s.get("symbol") for s in info.get("symbols", [])}
        for symbol in self.settings.universe:
            if symbol not in symbols:
                return False, f"symbol_missing:{symbol}"

        for symbol in self.settings.universe:
            self.connector.set_leverage(symbol, self.settings.execution.binance.leverage_target)

        return True, "ok"

    def _client_order_id(self, symbol: str, side: str, ts: float, slice_idx: int = 0) -> str:
        salt = os.getenv(self.settings.execution.binance.idempotency_salt_env or "", "")
        # DÔLEŽITÉ: int(ts) aby 2 volania v tej istej sekunde dali rovnaký CID
        base = f"{self.run_id}|{symbol}|{side}|{int(ts)}|{slice_idx}|{salt}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]

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
        except Exception as e:
            msg = str(e).lower()
            # "not found" / "unknown order" je normálne pri idempotency checku
            if "not found" in msg or "unknown" in msg or "order does not exist" in msg:
                return None
            raise

    def _is_filled(self, order: dict[str, Any]) -> bool:
        return order.get("status") in {"FILLED", "PARTIALLY_FILLED"}

    def _reject_guard(self, reason: str, cid: str | None = None) -> LiveExecutionResult:
        now = time.time()
        self.rejects.add_reject(now)
        if self.rejects.reject_storm(max_rejects=5):
            self.safe_mode = True
            self.killed = True
            self.cooldown_until_s = now + 300
            return LiveExecutionResult(
                status="killed",
                reason="reject_storm",
                order={"clientOrderId": cid} if cid else None,
            )
        return LiveExecutionResult(status="rejected", reason=reason)

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

    def execute_intent(self, intent: OrderIntent, user_stream: BinanceUserStream | None = None) -> LiveExecutionResult:
        now = time.time()
        if self.killed:
            return LiveExecutionResult(status="killed", reason="kill_switch_active")
        if self.safe_mode:
            return LiveExecutionResult(status="blocked", reason="safe_mode")
        if now < self.cooldown_until_s:
            return LiveExecutionResult(status="blocked", reason="cooldown")

        cid = self._client_order_id(intent.symbol, intent.side, now, 0)
        for k, t in list(self._recent_cids.items()):
            if now - t > self._dedupe_ttl_s:
                del self._recent_cids[k]
        if cid in self._recent_cids:
            return LiveExecutionResult(
                status="deduped",
                reason="local_dedupe",
                order={"clientOrderId": cid},
            )

        existing = self._query_existing(intent.symbol, cid)
        if existing is not None:
            self._recent_cids[cid] = now
            return LiveExecutionResult(status="deduped", order=existing)

        price = self._price_from_book(intent.symbol, intent.side)
        qty = max(0.001, intent.target_notional / max(price, 1e-9))

        base_order = {
            "symbol": intent.symbol,
            "side": intent.side.upper(),
            "quantity": f"{qty:.6f}",
            "newClientOrderId": cid,
            "newOrderRespType": "RESULT",
        }

        maker_order = {
            **base_order,
            "type": "LIMIT",
            "timeInForce": "GTX",
            "price": f"{price:.2f}",
        }

        try:
            placed = self.connector.place_order(maker_order)
            self._recent_cids[cid] = now
        except Exception as exc:
            return self._reject_guard(f"maker_reject:{exc}", cid=cid)

        timeout_s = int(self.settings.execution.binance.maker_timeout_s)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if user_stream is not None:
                user_stream.maybe_keepalive()
            current = self._query_existing(intent.symbol, cid)
            if current and self._is_filled(current):
                return LiveExecutionResult(status="filled_maker", order=current)
            time.sleep(0.25)

        try:
            self.connector.cancel_order(intent.symbol, cid)
        except BinanceConnectorError:
            pass

        if not self.settings.execution.binance.taker_fallback:
            return LiveExecutionResult(status="timeout", reason="maker_timeout_no_fallback")

        taker_cid = self._client_order_id(intent.symbol, intent.side, now, 1)
        fallback_order = {
            **base_order,
            "newClientOrderId": taker_cid,
            "type": "MARKET",
        }
        try:
            result = self.connector.place_order(fallback_order)
            self._recent_cids[taker_cid] = now
            return LiveExecutionResult(status="filled_taker_fallback", order=result)
        except Exception as exc:
            return self._reject_guard(f"taker_reject:{exc}", cid=taker_cid)

    def flatten_all_positions(self, max_attempts: int = 3) -> tuple[bool, str]:
        if not self.settings.execution.binance.reduce_only_on_flatten:
            return False, "flatten_disabled"

        for _ in range(max_attempts):
            positions = self.connector.position_risk()
            non_zero = []
            for p in positions:
                amt = float(p.get("positionAmt", 0.0))
                if abs(amt) < 1e-9:
                    continue
                non_zero.append((p.get("symbol", ""), amt))

            if not non_zero:
                return True, "flat"

            for symbol, amt in non_zero:
                side = "SELL" if amt > 0 else "BUY"
                params = {
                    "symbol": symbol,
                    "side": side,
                    "type": "MARKET",
                    "reduceOnly": "true",
                    "quantity": f"{abs(amt):.6f}",
                    "newClientOrderId": self._client_order_id(symbol, side.lower(), time.time(), 999),
                }
                self.connector.place_order(params)

            time.sleep(0.5)

        final_positions = self.connector.position_risk()
        still_open = [p for p in final_positions if abs(float(p.get("positionAmt", 0.0))) > 1e-9]
        if still_open:
            return False, "flatten_failed"
        return True, "flat"

    def reconcile_live_state(
        self,
        internal_exposure: float,
        open_orders_state_ok: bool = True,
        cash_ok: bool = True,
    ) -> tuple[bool, str]:
        positions = self.connector.position_risk()
        exchange_exposure = 0.0
        for p in positions:
            amt = abs(float(p.get("positionAmt", 0.0)))
            mark = abs(float(p.get("markPrice", 0.0)))
            exchange_exposure += amt * mark

        rec_ok, reason = self.recon.reconcile_live(
            exchange_exposure=exchange_exposure,
            internal_exposure=internal_exposure,
            open_orders_state_ok=open_orders_state_ok,
            cash_ok=cash_ok,
        )
        if not rec_ok:
            self.safe_mode = True
            self.killed = True
        return rec_ok, reason
