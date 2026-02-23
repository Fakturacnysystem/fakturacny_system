from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.kraken_spot import (
    KrakenConnectorError,
    KrakenInsufficientFundsError,
    KrakenRateLimitError,
    KrakenSpotConnector,
)


@dataclass
class LiveExecutionResult:
    status: str
    reason: str = ""
    order: dict[str, Any] | None = None


@dataclass
class RejectTracker:
    timestamps: list[float] = field(default_factory=list)

    def add(self, ts: float) -> None:
        self.timestamps.append(ts)
        self.timestamps = [x for x in self.timestamps if ts - x <= 60.0]

    def storm(self, max_rejects: int) -> bool:
        return len(self.timestamps) > max_rejects


@dataclass
class RateLimitTracker:
    timestamps: list[float] = field(default_factory=list)

    def add(self, ts: float) -> None:
        self.timestamps.append(ts)
        self.timestamps = [x for x in self.timestamps if ts - x <= 60.0]

    def storm(self, max_hits: int) -> bool:
        return len(self.timestamps) > max_hits


class KrakenMinOrderGuard:
    def __init__(self, connector: KrakenSpotConnector) -> None:
        self.connector = connector
        self._cache: dict[str, dict[str, Any]] = {}

    def load_pairs(self) -> dict[str, dict[str, Any]]:
        if self._cache:
            return self._cache
        raw = self.connector.asset_pairs()
        self._cache = raw if isinstance(raw, dict) else {}
        return self._cache

    def pair_meta(self, pair: str) -> dict[str, Any]:
        return self.load_pairs().get(pair, {})

    def round_volume(self, pair: str, volume: float) -> float:
        meta = self.pair_meta(pair)
        lot_decimals = int(meta.get("lot_decimals", 8) or 8)
        return round(max(0.0, volume), lot_decimals)

    def round_price(self, pair: str, price: float) -> float:
        meta = self.pair_meta(pair)
        pair_decimals = int(meta.get("pair_decimals", 8) or 8)
        return round(max(0.0, price), pair_decimals)

    def validate(self, pair: str, volume: float, price: float, available_quote: float) -> tuple[bool, str]:
        pairs = self.load_pairs()
        meta = pairs.get(pair, {})
        ordermin = float(meta.get("ordermin", 0.0) or 0.0)
        pair_decimals = int(meta.get("pair_decimals", 8) or 8)
        lot_decimals = int(meta.get("lot_decimals", 8) or 8)
        if volume < ordermin:
            return False, "min_order_block"
        if round(volume, lot_decimals) != volume:
            return False, "qty_precision_block"
        if round(price, pair_decimals) != price:
            return False, "price_precision_block"
        if volume * price > available_quote:
            return False, "insufficient_balance_block"
        return True, "ok"


class LiveKrakenSpotService:
    def __init__(self, settings: RobotSettings, run_id: str, connector: KrakenSpotConnector | None = None) -> None:
        self.settings = settings
        self.run_id = run_id
        self.connector = connector or KrakenSpotConnector(settings.execution.kraken_spot)
        self.safe_mode = False
        self.killed = False
        self.kill_reason = ""
        self.min_guard = KrakenMinOrderGuard(self.connector)
        self.rejects = RejectTracker()
        self.rate_limits = RateLimitTracker()
        self.cooldown_until_s = 0.0
        self._recent_ids: dict[str, float] = {}
        self._recent_ttl_s = 600.0

    def _taker_fallback_edge_ok(self, intent) -> bool:
        comps = intent.why.get("components", []) if isinstance(intent.why, dict) else []
        if not comps:
            return True
        for c in comps:
            edge = float(c.get("final_edge_bps", c.get("edge_bps", 0.0)))
            cost = float(c.get("cost_total_bps", 0.0))
            if edge > cost:
                return True
        return False

    def _evict_recent(self, now: float) -> None:
        for k, t in list(self._recent_ids.items()):
            if now - t > self._recent_ttl_s:
                del self._recent_ids[k]

    def _intent_key(self, intent) -> str:
        payload = f"{self.run_id}|{intent.symbol}|{intent.side}|{round(float(intent.target_notional), 6)}|{int(time.time()//5)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _is_rate_limit_err(self, exc: Exception) -> bool:
        return isinstance(exc, KrakenRateLimitError) or "rate limit" in str(exc).lower() or "429" in str(exc)

    def _reject_guard(self, exc: Exception, order_meta: dict[str, Any] | None = None) -> LiveExecutionResult:
        now = time.time()
        if self._is_rate_limit_err(exc):
            self.rate_limits.add(now)
            if self.rate_limits.storm(3):
                self.request_kill("rate_limit_storm")
                return LiveExecutionResult(status="killed", reason="rate_limit_storm", order=order_meta)
            return LiveExecutionResult(status="rejected", reason=f"rate_limit:{exc}", order=order_meta)
        self.rejects.add(now)
        if self.rejects.storm(5):
            self.request_kill("reject_storm")
            return LiveExecutionResult(status="killed", reason="reject_storm", order=order_meta)
        return LiveExecutionResult(status="rejected", reason=str(exc), order=order_meta)

    def _ticker_row(self, symbol: str) -> dict[str, Any]:
        t = self.connector.ticker(symbol)
        if isinstance(t, dict) and symbol in t and isinstance(t[symbol], dict):
            return t[symbol]
        if isinstance(t, dict) and t:
            first = next(iter(t.values()))
            if isinstance(first, dict):
                return first
        raise KrakenConnectorError(f"ticker_missing:{symbol}")

    def _best_ask(self, symbol: str) -> float:
        row = self._ticker_row(symbol)
        ask = row.get("a", 0.0)
        if isinstance(ask, list):
            ask = ask[0] if ask else 0.0
        return float(ask or 0.0)

    def _best_bid(self, symbol: str) -> float:
        row = self._ticker_row(symbol)
        bid = row.get("b", 0.0)
        if isinstance(bid, list):
            bid = bid[0] if bid else 0.0
        return float(bid or 0.0)

    def _available_quote_balance(self) -> tuple[str, float]:
        bal = self.connector.balance()
        if not isinstance(bal, dict):
            return ("ZUSD", 0.0)
        for k in ("ZUSD", "USD", "USDT", "ZEUR", "EUR"):
            if k in bal:
                try:
                    return (k, float(bal.get(k) or 0.0))
                except Exception:
                    return (k, 0.0)
        return ("ZUSD", 0.0)

    def _available_base_balance(self, pair: str) -> tuple[str, float]:
        bal = self.connector.balance()
        if not isinstance(bal, dict):
            return ("", 0.0)
        meta = self.min_guard.pair_meta(pair)
        base = str(meta.get("base", ""))
        candidates = [base]
        if base.startswith("X") or base.startswith("Z"):
            candidates.append(base[1:])
        for k in candidates:
            if not k:
                continue
            if k in bal:
                return (k, float(bal.get(k) or 0.0))
        return (base, 0.0)

    def preflight(self) -> tuple[bool, str]:
        if self.settings.execution_mode_enum() == ExecutionMode.LIVE_READONLY:
            return True, "readonly"
        ok_perm, reason_perm = self.connector.verify_live_permissions()
        if not ok_perm:
            return False, reason_perm
        if "kraken_spot" not in self.settings.provider_whitelist:
            return False, "provider_not_whitelisted"
        if not self.connector.has_credentials:
            return False, "missing_credentials"
        return True, "ok"

    def execute_readonly(self, intent) -> LiveExecutionResult:
        symbol = intent.symbol
        t = self.connector.ticker(symbol)
        return LiveExecutionResult(status="readonly_preview", order={"symbol": symbol, "ticker": t.get(symbol, t), "target_notional": getattr(intent, "target_notional", 0.0)})

    def execute_intent(self, intent) -> LiveExecutionResult:
        now = time.time()
        if self.killed:
            return LiveExecutionResult(status="killed", reason=self.kill_reason or "kill_switch_active")
        if self.safe_mode:
            return LiveExecutionResult(status="blocked", reason="safe_mode")
        if now < self.cooldown_until_s:
            return LiveExecutionResult(status="blocked", reason="cooldown")

        side = str(intent.side).lower()
        if side not in {"buy", "sell"}:
            return LiveExecutionResult(status="blocked", reason="invalid_side")
        if side != "buy":
            # Only risk exits/sells are allowed, not directional shorting.
            return LiveExecutionResult(status="blocked", reason="long_only_mode")

        dedupe = self._intent_key(intent)
        self._evict_recent(now)
        if dedupe in self._recent_ids:
            return LiveExecutionResult(status="deduped", reason="intent_dedupe", order={"intent_id": dedupe})

        pair = intent.symbol
        try:
            ask = self._best_ask(pair)
            bid = self._best_bid(pair)
            if ask <= 0 or bid <= 0:
                return LiveExecutionResult(status="blocked", reason="invalid_book")
            quote_ccy, available_quote = self._available_quote_balance()
        except Exception as exc:
            return self._reject_guard(exc)

        target_notional = max(0.0, float(intent.target_notional))
        raw_vol = target_notional / max(ask, 1e-9)
        price = self.min_guard.round_price(pair, ask)
        vol = self.min_guard.round_volume(pair, raw_vol)
        ok, guard_reason = self.min_guard.validate(pair, vol, price, available_quote)
        if not ok:
            return LiveExecutionResult(
                status="blocked",
                reason=guard_reason,
                order={"pair": pair, "volume": vol, "price": price, "available_quote": available_quote, "quote_ccy": quote_ccy},
            )

        if self.settings.execution.kraken_spot.dry_run_long_only:
            self._recent_ids[dedupe] = now
            return LiveExecutionResult(
                status="blocked",
                reason="spot_live_execution_dry_run",
                order={"pair": pair, "side": side, "volume": vol, "price": price, "notional": vol * price, "quote_ccy": quote_ccy},
            )

        userref = int(hashlib.sha256(f"{self.run_id}|{pair}|{side}|{int(now)}".encode("utf-8")).hexdigest()[:8], 16)
        maker_preference = bool(self.settings.execution.maker_preference)
        timeout_s = max(1, int(self.settings.execution.maker_timeout_s))
        maker_price = self.min_guard.round_price(pair, max(bid, 0.0))
        base_order = {
            "pair": pair,
            "type": side,
            "volume": f"{vol:.8f}",
            "userref": str(userref),
        }

        # Maker-first spot execution reduces modeled TCO. We only taker-fallback if edge still beats cost.
        if maker_preference and maker_price > 0:
            maker_params = {
                **base_order,
                "ordertype": "limit",
                "price": f"{maker_price:.8f}",
                "oflags": "post",
            }
            try:
                out = self.connector.add_order(maker_params)
            except (KrakenInsufficientFundsError, KrakenConnectorError) as exc:
                return self._reject_guard(exc, {"pair": pair, "volume": vol, "price": maker_price, "stage": "maker_submit"})

            txids = out.get("txid", []) if isinstance(out, dict) else []
            txid = txids[0] if isinstance(txids, list) and txids else ""
            deadline = time.time() + timeout_s
            while txid and time.time() < deadline:
                try:
                    q = self.connector.query_orders(txid)
                    row = q.get(txid, {}) if isinstance(q, dict) else {}
                    status = str(row.get("status", "")).lower()
                    vol_exec = float(row.get("vol_exec", 0.0) or 0.0)
                    if status == "closed" and vol_exec > 0:
                        self._recent_ids[dedupe] = now
                        return LiveExecutionResult(
                            status="filled_maker",
                            reason="spot_order_filled_maker",
                            order={"pair": pair, "side": side, "volume": vol, "price": maker_price, "notional": vol * maker_price, "txid": txid, "userref": userref, "raw": out},
                        )
                except KrakenConnectorError:
                    break
                time.sleep(0.25)
            if txid:
                try:
                    self.connector.cancel_order(txid)
                except Exception as exc:
                    if self._is_rate_limit_err(exc):
                        return self._reject_guard(exc, {"pair": pair, "volume": vol, "price": maker_price, "stage": "maker_cancel"})
            if not self._taker_fallback_edge_ok(intent):
                return LiveExecutionResult(status="timeout", reason="maker_timeout_edge_le_cost", order={"pair": pair, "volume": vol, "price": maker_price, "txid": txid})

        params = {**base_order, "ordertype": "market"}
        try:
            out = self.connector.add_order(params)
        except (KrakenInsufficientFundsError, KrakenConnectorError) as exc:
            return self._reject_guard(exc, {"pair": pair, "volume": vol, "price": price, "stage": "taker_submit"})

        self._recent_ids[dedupe] = now
        txids = out.get("txid", []) if isinstance(out, dict) else []
        txid = txids[0] if isinstance(txids, list) and txids else ""
        return LiveExecutionResult(
            status="filled_taker_fallback" if maker_preference else "submitted",
            reason="spot_order_taker_fallback" if maker_preference else "spot_order_submitted",
            order={
                "pair": pair,
                "side": side,
                "volume": vol,
                "price": price,
                "notional": vol * price,
                "txid": txid,
                "userref": userref,
                "raw": out if isinstance(out, dict) else {"result": out},
            },
        )

    def request_kill(self, reason: str = "operator_kill") -> None:
        self.killed = True
        self.safe_mode = True
        self.kill_reason = reason
        self.cooldown_until_s = max(self.cooldown_until_s, time.time() + 300)

    def flatten_all_positions(self) -> tuple[bool, str]:
        if self.killed is False:
            self.request_kill("emergency")
        try:
            self.connector.cancel_all()
        except Exception:
            pass
        bal = self.connector.balance()
        pairs = self.min_guard.load_pairs()
        quote_ccys = {"ZUSD", "USD", "USDT", "ZEUR", "EUR"}
        for asset, amount in bal.items() if isinstance(bal, dict) else []:
            if asset in quote_ccys:
                continue
            qty = float(amount or 0.0)
            if qty <= 0:
                continue
            pair = next((p for p, m in pairs.items() if m.get("base") == asset and m.get("quote") in quote_ccys), "")
            if not pair:
                continue
            vol = self.min_guard.round_volume(pair, qty)
            if vol <= 0:
                continue
            try:
                self.connector.add_order({"pair": pair, "type": "sell", "ordertype": "market", "volume": f"{vol:.8f}"})
                time.sleep(0.2)
            except KrakenConnectorError:
                continue
        return True, "flatten_best_effort"
