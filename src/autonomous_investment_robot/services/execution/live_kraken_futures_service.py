from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.kraken_futures import (
    KrakenFuturesAuthError,
    KrakenFuturesConnector,
    KrakenFuturesConnectorError,
    KrakenFuturesOrderError,
    KrakenFuturesRateLimitError,
)
from autonomous_investment_robot.services.execution.profit_gate import (
    AccountingMethod,
    PositionLot,
    ProfitGate,
    ProfitGateConfig,
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except Exception:
        return float(default)


@dataclass
class LiveExecutionResult:
    status: str
    reason: str = ""
    order: dict[str, Any] | None = None


@dataclass
class FuturesPositionLedger:
    position_qty: float = 0.0
    avg_entry_price: float = 0.0
    position_open_ts: float | None = None
    realized_quote: float = 0.0
    unrealized_quote: float = 0.0
    fees_quote: float = 0.0
    funding_quote: float = 0.0
    interest_quote: float = 0.0
    filled_notional_quote: float = 0.0
    lots: list[PositionLot] = field(default_factory=list)


class LiveKrakenFuturesService:
    def __init__(self, settings: RobotSettings, run_id: str, connector: KrakenFuturesConnector | None = None) -> None:
        self.settings = settings
        self.run_id = run_id
        self.connector = connector or KrakenFuturesConnector()
        self.safe_mode = False
        self.killed = False
        self.kill_reason = ""
        self.cooldown_until_s = 0.0
        self.rate_limit_cooldown_until_s = 0.0
        self._ticker_cache: dict[str, dict[str, Any]] = {}
        self._ticker_cache_ts: dict[str, float] = {}
        self._instruments: dict[str, dict[str, Any]] = {}
        self._instruments_ts: float = 0.0
        self._instrument_ttl_s = max(60.0, _env_float("AUTONOMOUS_FUTURES_INSTRUMENTS_TTL_S", 900.0))
        self._ticker_ttl_s = max(0.1, _env_float("AUTONOMOUS_FUTURES_TICKER_TTL_S", 1.0))
        self._recent_ids: dict[str, float] = {}
        self._recent_ttl_s = 600.0
        self._rate_limit_cooldown_s = max(0.25, _env_float("AUTONOMOUS_RATE_LIMIT_COOLDOWN_S", 4.0))
        self._position_accounting_method: AccountingMethod = "average" if str(os.getenv("AUTONOMOUS_POSITION_ACCOUNTING", "fifo")).strip().lower() == "average" else "fifo"
        self._profit_target_net = max(0.02, _env_float("AUTONOMOUS_PROFIT_TARGET_NET", 0.02))
        self._entry_fee_bps = max(
            0.0,
            _env_float("AUTONOMOUS_ENTRY_FEE_BPS", max(30.0, float(self.settings.execution.fee_bps))),
        )
        self._exit_fee_bps = max(
            0.0,
            _env_float("AUTONOMOUS_EXIT_FEE_BPS", max(30.0, float(self.settings.execution.fee_bps))),
        )
        self._slippage_bps_profit_gate = max(
            0.1,
            _env_float("AUTONOMOUS_PROFIT_GATE_SLIPPAGE_BPS", max(15.0, float(self.settings.execution.slippage_bps))),
        )
        self._funding_bps_multiplier = max(0.0, _env_float("AUTONOMOUS_FUTURES_FUNDING_BPS_MULTIPLIER", 1.0))
        self._exits_only_mode_until_s = 0.0
        self._exits_only_reason = ""
        self.profit_gate = ProfitGate(
            ProfitGateConfig(
                min_net_profit_ratio=self._profit_target_net,
                default_entry_fee_bps=self._entry_fee_bps,
                default_exit_fee_bps=self._exit_fee_bps,
                default_slippage_bps=self._slippage_bps_profit_gate,
                accounting_method=self._position_accounting_method,
            )
        )
        self._ledgers: dict[str, FuturesPositionLedger] = {}

    def _norm_symbol(self, symbol: str) -> str:
        return str(symbol or "").strip().upper()

    def _intent_key(self, intent: Any) -> str:
        payload = f"{self.run_id}|{getattr(intent, 'symbol', '')}|{getattr(intent, 'side', '')}|{round(float(getattr(intent, 'target_notional', 0.0)), 6)}|{int(time.time() // 5)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _evict_recent(self, now: float) -> None:
        for key, ts in list(self._recent_ids.items()):
            if now - ts > self._recent_ttl_s:
                del self._recent_ids[key]

    def _parse_rows(self, payload: Any, candidates: list[str]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if not isinstance(payload, dict):
            return []
        for key in candidates:
            raw = payload.get(key)
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
            if isinstance(raw, dict):
                return [raw]
        if payload:
            return [payload]
        return []

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    def _refresh_instruments(self, *, force: bool = False) -> None:
        now = time.time()
        if self._instruments and not force and (now - self._instruments_ts) <= self._instrument_ttl_s:
            return
        payload = self.connector.instruments()
        rows = self._parse_rows(payload, ["instruments", "products", "result"]) if payload is not None else []
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            symbol = self._norm_symbol(row.get("symbol", row.get("product_id", "")))
            if not symbol:
                continue
            tick_size = self._safe_float(row.get("tickSize", row.get("tick_size", row.get("priceIncrement", 0.0))), 0.0)
            lot_step = self._safe_float(row.get("contractSize", row.get("contract_size", row.get("lotSize", row.get("qtyStep", 1.0)))), 1.0)
            quote = str(row.get("quote", row.get("settlementCurrency", "USD")) or "USD").upper()
            out[symbol] = {
                "symbol": symbol,
                "tick_size": tick_size,
                "lot_step": lot_step if lot_step > 0.0 else 1.0,
                "quote": quote,
                "raw": row,
            }
        self._instruments = out
        self._instruments_ts = now

    def _instrument_meta(self, symbol: str) -> dict[str, Any]:
        self._refresh_instruments()
        key = self._norm_symbol(symbol)
        meta = self._instruments.get(key)
        if isinstance(meta, dict):
            return meta
        return {
            "symbol": key,
            "tick_size": 0.0,
            "lot_step": 1.0,
            "quote": "USD",
            "raw": {},
        }

    def _round_qty_down(self, qty: float, lot_step: float) -> float:
        q = max(0.0, float(qty))
        step = max(1e-9, float(lot_step))
        return math.floor(q / step) * step

    def _round_price(self, price: float, tick_size: float, *, side: str) -> float:
        px = max(0.0, float(price))
        tick = max(0.0, float(tick_size))
        if tick <= 0.0:
            return px
        if side == "buy":
            return math.floor(px / tick) * tick
        return math.ceil(px / tick) * tick

    def _rate_limit_cooldown_result(self, payload: dict[str, Any] | None = None) -> LiveExecutionResult:
        remaining = max(0.0, self.rate_limit_cooldown_until_s - time.time())
        return LiveExecutionResult(
            status="blocked",
            reason="rate_limit_cooldown",
            order={"cooldown_remaining_s": remaining, **(payload or {})},
        )

    def _activate_rate_limit_cooldown(self) -> None:
        self.rate_limit_cooldown_until_s = max(
            self.rate_limit_cooldown_until_s,
            time.time() + self._rate_limit_cooldown_s,
        )

    def _reject_guard(self, exc: Exception, payload: dict[str, Any] | None = None) -> LiveExecutionResult:
        reason = str(exc)
        if isinstance(exc, KrakenFuturesRateLimitError) or "rate limit" in reason.lower() or "429" in reason:
            self._activate_rate_limit_cooldown()
            return self._rate_limit_cooldown_result({"error": reason, **(payload or {})})
        if isinstance(exc, KrakenFuturesAuthError):
            return LiveExecutionResult(status="rejected", reason="auth_error", order={"error": reason, **(payload or {})})
        if isinstance(exc, KrakenFuturesOrderError):
            return LiveExecutionResult(status="rejected", reason=reason, order=payload)
        return LiveExecutionResult(status="rejected", reason=reason, order=payload)

    def _market_snapshot_uncached(self, symbol: str) -> dict[str, Any]:
        snap = self.connector.market_snapshot(symbol)
        if not isinstance(snap, dict):
            raise KrakenFuturesConnectorError(f"invalid_market_snapshot:{symbol}")
        bid = self._safe_float(snap.get("bid"), 0.0)
        ask = self._safe_float(snap.get("ask"), 0.0)
        mark = self._safe_float(snap.get("mark_price", snap.get("markPrice", 0.0)), 0.0)
        index = self._safe_float(snap.get("index_price", snap.get("indexPrice", 0.0)), 0.0)
        funding = self._safe_float(snap.get("funding_rate", snap.get("fundingRate", 0.0)), 0.0)
        oi = self._safe_float(snap.get("open_interest", snap.get("openInterest", 0.0)), 0.0)
        vol24 = self._safe_float(snap.get("volume_24h", snap.get("volume24h", 0.0)), 0.0)
        try:
            book = self.connector.orderbook(symbol, depth=10)
        except Exception:
            book = {}
        rows_bid = self._parse_rows(book, ["bids", "buy", "bid", "book"])
        rows_ask = self._parse_rows(book, ["asks", "sell", "ask", "book"])
        bid_qty = 0.0
        ask_qty = 0.0
        depth = 0.0
        if rows_bid:
            first = rows_bid[0]
            if isinstance(first, dict):
                bid_qty = self._safe_float(first.get("size", first.get("qty", first.get("volume", 0.0))), 0.0)
                bid_lvl_px = self._safe_float(first.get("price", bid), bid)
                depth += max(0.0, bid_lvl_px) * max(0.0, bid_qty)
        if rows_ask:
            first = rows_ask[0]
            if isinstance(first, dict):
                ask_qty = self._safe_float(first.get("size", first.get("qty", first.get("volume", 0.0))), 0.0)
                ask_lvl_px = self._safe_float(first.get("price", ask), ask)
                depth += max(0.0, ask_lvl_px) * max(0.0, ask_qty)
        mid = self._safe_float(snap.get("mid"), 0.0)
        if mid <= 0.0:
            if bid > 0.0 and ask > 0.0:
                mid = (bid + ask) / 2.0
            else:
                mid = max(mark, index)
        spread_bps = 0.0
        if bid > 0.0 and ask > 0.0 and mid > 0.0:
            spread_bps = ((ask - bid) / max(mid, 1e-9)) * 10000.0
        return {
            "pair": self._norm_symbol(symbol),
            "bid": bid,
            "ask": ask,
            "bid_qty": bid_qty,
            "ask_qty": ask_qty,
            "mid": mid,
            "spread_bps": spread_bps,
            "mark_price": mark,
            "index_price": index,
            "funding_rate": funding,
            "open_interest": oi,
            "volume_24h": vol24,
            "depth_notional": depth,
            "ts": time.time(),
            "stale": False,
            "level": "L2",
            "source": "rest_fallback",
        }

    def market_snapshot(self, symbol: str, *, max_age_s: float | None = None, force_refresh: bool = False) -> dict[str, Any]:
        key = self._norm_symbol(symbol)
        ttl = self._ticker_ttl_s if max_age_s is None else max(0.05, float(max_age_s))
        now = time.time()
        if not force_refresh:
            cached = self._ticker_cache.get(key, {})
            ts = self._ticker_cache_ts.get(key, 0.0)
            if cached and (now - ts) <= ttl:
                return dict(cached)
        snap = self._market_snapshot_uncached(key)
        self._ticker_cache[key] = dict(snap)
        self._ticker_cache_ts[key] = now
        return snap

    def _open_positions_rows(self) -> list[dict[str, Any]]:
        payload = self.connector.open_positions()
        return self._parse_rows(payload, ["openPositions", "positions", "open_positions", "result"])

    def _position_row_for_symbol(self, symbol: str) -> dict[str, Any] | None:
        key = self._norm_symbol(symbol)
        for row in self._open_positions_rows():
            row_symbol = self._norm_symbol(row.get("symbol", row.get("instrument", row.get("product_id", ""))))
            if row_symbol == key:
                return row
        return None

    def _parse_signed_qty(self, row: dict[str, Any]) -> float:
        size = self._safe_float(
            row.get("size", row.get("qty", row.get("positionSize", row.get("contracts", row.get("balance", 0.0))))),
            0.0,
        )
        side = str(row.get("side", row.get("direction", "")) or "").strip().lower()
        if side in {"short", "sell"} and size > 0.0:
            return -size
        if side in {"long", "buy"} and size < 0.0:
            return abs(size)
        return size

    def _ledger_for(self, symbol: str) -> FuturesPositionLedger:
        key = self._norm_symbol(symbol)
        return self._ledgers.setdefault(key, FuturesPositionLedger())

    def _estimate_unrealized(self, qty_signed: float, mark: float, entry_price: float) -> float:
        if qty_signed > 0.0:
            return (mark - entry_price) * abs(qty_signed)
        if qty_signed < 0.0:
            return (entry_price - mark) * abs(qty_signed)
        return 0.0

    def sync_fill_ledger(self, symbol: str, mark_price: float) -> dict[str, Any]:
        key = self._norm_symbol(symbol)
        ledger = self._ledger_for(key)
        row = self._position_row_for_symbol(key)
        now = time.time()
        if row is None:
            ledger.position_qty = 0.0
            ledger.avg_entry_price = 0.0
            ledger.position_open_ts = None
            ledger.realized_quote = 0.0
            ledger.unrealized_quote = 0.0
            ledger.fees_quote = 0.0
            ledger.funding_quote = 0.0
            ledger.interest_quote = 0.0
            ledger.filled_notional_quote = 0.0
            ledger.lots = []
        else:
            qty_signed = self._parse_signed_qty(row)
            entry_px = self._safe_float(row.get("entryPrice", row.get("avgEntryPrice", row.get("price", row.get("avgPrice", 0.0)))), 0.0)
            if entry_px <= 0.0 and mark_price > 0.0 and abs(qty_signed) > 0.0:
                entry_px = mark_price
            realized = self._safe_float(row.get("realizedPnl", row.get("realized", row.get("pnlRealized", 0.0))), 0.0)
            unrealized = self._safe_float(
                row.get("unrealizedPnl", row.get("pnl", row.get("pnlUnrealized", 0.0))),
                self._estimate_unrealized(qty_signed, mark_price, entry_px),
            )
            fees = self._safe_float(row.get("fee", row.get("fees", row.get("tradingFee", 0.0))), 0.0)
            funding = self._safe_float(row.get("funding", row.get("fundingPayment", row.get("realizedFunding", 0.0))), 0.0)
            interest = self._safe_float(row.get("interest", row.get("borrowInterest", 0.0)), 0.0)
            ledger.position_qty = qty_signed
            ledger.avg_entry_price = entry_px
            ledger.realized_quote = realized
            ledger.unrealized_quote = unrealized
            ledger.fees_quote = fees
            ledger.funding_quote = funding
            ledger.interest_quote = interest
            ledger.filled_notional_quote = abs(qty_signed) * max(entry_px, 0.0)
            if abs(qty_signed) > 0.0:
                if ledger.position_open_ts is None:
                    ledger.position_open_ts = now
                ledger.lots = [
                    PositionLot(
                        qty=abs(qty_signed),
                        entry_price=max(0.0, entry_px),
                        entry_fee_quote=max(0.0, fees),
                        funding_quote=float(funding),
                        interest_quote=float(interest),
                        opened_ts=ledger.position_open_ts,
                    )
                ]
            else:
                ledger.position_open_ts = None
                ledger.lots = []

        mark = max(0.0, float(mark_price))
        exposure = abs(ledger.position_qty) * mark
        signed_notional = ledger.position_qty * mark
        min_trade_notional = max(0.25, self._instrument_meta(key).get("lot_step", 1.0) * max(mark, 0.0))
        pos_age = 0.0
        if ledger.position_open_ts is not None:
            pos_age = max(0.0, now - float(ledger.position_open_ts))

        net_quote = ledger.realized_quote + ledger.unrealized_quote - ledger.fees_quote - ledger.funding_quote - ledger.interest_quote
        return {
            "symbol": key,
            "position_qty": ledger.position_qty,
            "avg_entry_price": ledger.avg_entry_price,
            "position_notional_signed": signed_notional,
            "exposure_notional": exposure,
            "realized_gross_quote": ledger.realized_quote,
            "unrealized_pnl_quote": ledger.unrealized_quote,
            "fees_quote": ledger.fees_quote,
            "funding_quote": ledger.funding_quote,
            "interest_quote": ledger.interest_quote,
            "filled_notional_quote": ledger.filled_notional_quote,
            "net_pnl_after_fees_quote": net_quote,
            "min_trade_notional_quote": float(min_trade_notional),
            "position_age_s": pos_age,
            "execution_qa": {
                "implementation_shortfall_bps": 0.0,
                "latency_p50_ms": 0.0,
                "latency_p95_ms": 0.0,
                "latency_p99_ms": 0.0,
                "latency_bucket_fast": 0.0,
                "latency_bucket_medium": 0.0,
                "latency_bucket_slow": 0.0,
                "orders_filled": 0.0,
                "fill_probability": 0.0,
            },
        }

    def _available_quote_balance(self, symbol: str) -> tuple[str, float]:
        key = self._norm_symbol(symbol)
        quote = str(self._instrument_meta(key).get("quote", "USD") or "USD").upper()
        payload = self.connector.account_overview()
        rows = self._parse_rows(payload, ["accounts", "account", "result"])
        if rows:
            for row in rows:
                ccy = str(row.get("currency", row.get("ccy", quote)) or quote).upper()
                value = self._safe_float(
                    row.get("availableMargin", row.get("availableFunds", row.get("cash", row.get("balance", row.get("equity", 0.0))))),
                    0.0,
                )
                if ccy == quote:
                    return ccy, max(0.0, value)
        if isinstance(payload, dict):
            value = self._safe_float(
                payload.get("availableMargin", payload.get("availableFunds", payload.get("cash", payload.get("balance", payload.get("equity", 0.0))))),
                0.0,
            )
            if value > 0.0:
                return quote, value
        return quote, 0.0

    def _close_profit_gate(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        bid: float,
        ask: float,
        tick_size: float,
        funding_bps: float = 0.0,
        interest_bps: float = 0.0,
    ) -> tuple[bool, str, float, dict[str, Any]]:
        snap = self.sync_fill_ledger(symbol, mark_price=(bid + ask) / 2.0 if bid > 0.0 and ask > 0.0 else max(bid, ask, 0.0))
        lots = list(self._ledger_for(symbol).lots)
        if not lots:
            return False, "missing_cost_basis", 0.0, {"symbol": symbol, "side": side}
        signed_qty = self._safe_float(snap.get("position_qty"), 0.0)
        close_qty = min(max(0.0, qty), abs(signed_qty))
        if close_qty <= 0.0:
            return False, "no_position_to_close", 0.0, {"symbol": symbol, "side": side}
        if side == "sell" and signed_qty > 0.0:
            decision = self.profit_gate.can_close_long(
                lots=lots,
                exit_price=max(0.0, bid),
                exit_qty=close_qty,
                tick_size=tick_size,
                min_profit_ratio=self._profit_target_net,
                entry_fee_bps=self._entry_fee_bps,
                exit_fee_bps=self._exit_fee_bps,
                slippage_bps=self._slippage_bps_profit_gate,
                funding_bps=max(0.0, float(funding_bps)),
                interest_bps=max(0.0, float(interest_bps)),
                accounting_method=self._position_accounting_method,
            )
            payload = {
                "required_exit_price": decision.required_exit_price,
                "eligible_qty": decision.eligible_qty,
                "matched_qty": decision.matched_qty,
                "min_profit_ratio": decision.min_profit_ratio,
                "symbol": symbol,
                "side": side,
            }
            if not decision.allowed:
                return False, "profit_gate_block", 0.0, payload
            return True, "ok", min(close_qty, decision.eligible_qty or close_qty), payload
        if side == "buy" and signed_qty < 0.0:
            decision = self.profit_gate.can_close_short(
                lots=lots,
                exit_price=max(0.0, ask),
                close_qty=close_qty,
                tick_size=tick_size,
                min_profit_ratio=self._profit_target_net,
                entry_fee_bps=self._entry_fee_bps,
                exit_fee_bps=self._exit_fee_bps,
                slippage_bps=self._slippage_bps_profit_gate,
                funding_bps=max(0.0, float(funding_bps)),
                interest_bps=max(0.0, float(interest_bps)),
                accounting_method=self._position_accounting_method,
            )
            payload = {
                "required_exit_price": decision.required_exit_price,
                "eligible_qty": decision.eligible_qty,
                "matched_qty": decision.matched_qty,
                "min_profit_ratio": decision.min_profit_ratio,
                "symbol": symbol,
                "side": side,
            }
            if not decision.allowed:
                return False, "profit_gate_block", 0.0, payload
            return True, "ok", min(close_qty, decision.eligible_qty or close_qty), payload
        return True, "not_reduce_close", close_qty, {}

    def _is_reduce_only_intent(self, intent: Any, signed_qty: float) -> bool:
        why = getattr(intent, "why", {}) if isinstance(getattr(intent, "why", {}), dict) else {}
        route = why.get("execution_route", {}) if isinstance(why, dict) else {}
        risk = why.get("risk", {}) if isinstance(why, dict) else {}
        governance = why.get("governance", {}) if isinstance(why, dict) else {}
        if bool((risk or {}).get("reduce_only", False)):
            return True
        if bool((governance or {}).get("reduce_only", False)):
            return True
        if str((route or {}).get("reduce_only", "")).lower() in {"1", "true", "yes", "on"}:
            return True
        side = str(getattr(intent, "side", "")).lower()
        if side == "sell" and signed_qty > 0.0:
            return True
        if side == "buy" and signed_qty < 0.0:
            return True
        return False

    def preflight(self) -> tuple[bool, str]:
        if self.settings.execution_mode_enum() == ExecutionMode.LIVE_READONLY:
            return True, "readonly"
        if not self.connector.has_credentials:
            return False, "missing_futures_credentials"
        # Keep backward compatibility with current provider whitelist semantics.
        if "kraken_spot" not in self.settings.provider_whitelist and "kraken_futures" not in self.settings.provider_whitelist:
            return False, "provider_not_whitelisted"
        try:
            self._refresh_instruments(force=True)
        except Exception as exc:
            return False, f"futures_instruments_error:{exc}"
        return True, "ok"

    def execute_readonly(self, intent: Any) -> LiveExecutionResult:
        symbol = self._norm_symbol(getattr(intent, "symbol", ""))
        try:
            snap = self.market_snapshot(symbol, force_refresh=True)
        except Exception as exc:
            return LiveExecutionResult(status="readonly_preview", reason=f"snapshot_error:{exc}", order={"symbol": symbol})
        return LiveExecutionResult(
            status="readonly_preview",
            order={
                "symbol": symbol,
                "target_notional": float(getattr(intent, "target_notional", 0.0) or 0.0),
                "snapshot": snap,
            },
        )

    def execute_intent(self, intent: Any) -> LiveExecutionResult:
        now = time.time()
        if self.killed:
            return LiveExecutionResult(status="killed", reason=self.kill_reason or "kill_switch_active")
        if self.safe_mode:
            return LiveExecutionResult(status="blocked", reason="safe_mode")
        if now < self.rate_limit_cooldown_until_s:
            return self._rate_limit_cooldown_result({"symbol": getattr(intent, "symbol", "")})
        if now < self.cooldown_until_s:
            return LiveExecutionResult(status="blocked", reason="cooldown")

        symbol = self._norm_symbol(getattr(intent, "symbol", ""))
        side = str(getattr(intent, "side", "")).strip().lower()
        if not symbol:
            return LiveExecutionResult(status="blocked", reason="missing_symbol")
        if side not in {"buy", "sell"}:
            return LiveExecutionResult(status="blocked", reason="invalid_side")
        if now < self._exits_only_mode_until_s and side == "buy":
            return LiveExecutionResult(
                status="blocked",
                reason="exits_only_mode",
                order={
                    "symbol": symbol,
                    "side": side,
                    "exits_only_reason": self._exits_only_reason,
                    "exits_only_until_s": float(self._exits_only_mode_until_s),
                },
            )

        dedupe = self._intent_key(intent)
        self._evict_recent(now)
        if dedupe in self._recent_ids:
            return LiveExecutionResult(status="deduped", reason="intent_dedupe", order={"intent_id": dedupe})

        try:
            snap = self.market_snapshot(symbol, max_age_s=max(0.5, self._ticker_ttl_s))
            bid = self._safe_float(snap.get("bid"), 0.0)
            ask = self._safe_float(snap.get("ask"), 0.0)
            mid = self._safe_float(snap.get("mid"), 0.0)
            funding_rate = self._safe_float(snap.get("funding_rate"), 0.0)
            funding_bps_est = max(0.0, abs(funding_rate) * 10000.0 * self._funding_bps_multiplier)
            if mid <= 0.0:
                return LiveExecutionResult(status="blocked", reason="invalid_book", order={"symbol": symbol})
        except Exception as exc:
            return self._reject_guard(exc, {"symbol": symbol})

        meta = self._instrument_meta(symbol)
        tick_size = self._safe_float(meta.get("tick_size"), 0.0)
        lot_step = max(1e-9, self._safe_float(meta.get("lot_step"), 1.0))
        target_notional = max(0.0, float(getattr(intent, "target_notional", 0.0) or 0.0))
        raw_qty = target_notional / max(mid, 1e-9)
        qty = self._round_qty_down(raw_qty, lot_step)
        if qty <= 0.0:
            qty = self._round_qty_down(lot_step, lot_step)
        if qty <= 0.0:
            return LiveExecutionResult(status="blocked", reason="min_order_block", order={"symbol": symbol, "lot_step": lot_step})

        live_state = self.sync_fill_ledger(symbol, mark_price=mid)
        signed_qty = self._safe_float(live_state.get("position_qty"), 0.0)
        reduce_only = self._is_reduce_only_intent(intent, signed_qty)
        if reduce_only and abs(signed_qty) <= 1e-12:
            return LiveExecutionResult(status="blocked", reason="reduce_only_no_position", order={"symbol": symbol})

        gate_required_exit_price = 0.0
        if reduce_only:
            ok_gate, gate_reason, gate_qty, gate_payload = self._close_profit_gate(
                symbol=symbol,
                side=side,
                qty=qty,
                bid=bid,
                ask=ask,
                tick_size=tick_size,
                funding_bps=funding_bps_est,
            )
            if not ok_gate:
                return LiveExecutionResult(status="blocked", reason=gate_reason, order=gate_payload)
            qty = self._round_qty_down(gate_qty, lot_step)
            if qty <= 0.0:
                return LiveExecutionResult(status="blocked", reason="profit_gate_qty_zero", order=gate_payload)
            gate_required_exit_price = self._safe_float(gate_payload.get("required_exit_price"), 0.0)

        why = getattr(intent, "why", {}) if isinstance(getattr(intent, "why", {}), dict) else {}
        route = why.get("execution_route", {}) if isinstance(why, dict) else {}
        forced_type = str(route.get("order_type", "") if isinstance(route, dict) else "").lower()
        maker = bool(self.settings.execution.maker_preference)
        if forced_type == "taker":
            maker = False
        elif forced_type == "maker":
            maker = True

        limit_price = 0.0
        if reduce_only:
            maker = True
            if gate_required_exit_price <= 0.0:
                return LiveExecutionResult(status="blocked", reason="profit_gate_floor_invalid", order={"symbol": symbol})
            if side == "sell":
                limit_price = self._round_price(max(gate_required_exit_price, bid), tick_size, side="sell")
                if limit_price <= 0.0 or limit_price < gate_required_exit_price:
                    return LiveExecutionResult(status="blocked", reason="profit_gate_floor_invalid", order={"symbol": symbol})
            else:
                # For short close, never allow buy limit above the profit-gate max exit.
                limit_price = self._round_price(min(gate_required_exit_price, max(ask - max(tick_size, 1e-9), 0.0)), tick_size, side="buy")
                if limit_price <= 0.0:
                    return LiveExecutionResult(status="blocked", reason="profit_gate_floor_invalid", order={"symbol": symbol})
                if ask > gate_required_exit_price:
                    return LiveExecutionResult(
                        status="blocked",
                        reason="profit_gate_block",
                        order={"symbol": symbol, "required_exit_price": gate_required_exit_price, "ask": ask},
                    )
        elif maker:
            px_ref = bid if side == "buy" else ask
            limit_price = self._round_price(px_ref, tick_size, side=side)
            if limit_price <= 0.0:
                return LiveExecutionResult(status="blocked", reason="invalid_limit_price", order={"symbol": symbol})

        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "size": f"{qty:.8f}",
            "cliOrdId": f"{self.run_id[:8]}-{dedupe}",
            "reduceOnly": "true" if reduce_only else "false",
        }
        if maker:
            params.update(
                {
                    "orderType": "lmt",
                    "limitPrice": f"{limit_price:.12f}",
                    "postOnly": "true",
                }
            )
        else:
            params.update({"orderType": "mkt"})

        try:
            out = self.connector.send_order(params)
        except Exception as exc:
            return self._reject_guard(exc, {"symbol": symbol, "side": side, "qty": qty, "params": params})

        self._recent_ids[dedupe] = now
        status = "submitted"
        reason = "futures_order_submitted"
        if maker:
            reason = "futures_order_submitted_post_only"
        if reduce_only:
            reason = "futures_reduce_only_submitted"

        return LiveExecutionResult(
            status=status,
            reason=reason,
            order={
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "notional": qty * mid,
                "reduce_only": reduce_only,
                "execution_mode": "maker" if maker else "taker",
                "required_exit_price": gate_required_exit_price if reduce_only else 0.0,
                "request_sent": True,
                "raw": out if isinstance(out, dict) else {"result": out},
            },
        )

    def reconcile_live_state(self, internal_exposure: float) -> tuple[bool, str]:
        try:
            rows = self._open_positions_rows()
        except Exception as exc:
            return False, f"reconcile_open_positions_error:{exc}"
        live_exposure = 0.0
        for row in rows:
            qty_signed = self._parse_signed_qty(row)
            symbol = self._norm_symbol(row.get("symbol", row.get("instrument", row.get("product_id", ""))))
            if not symbol:
                continue
            mark = self._safe_float(row.get("markPrice", row.get("mark_price", 0.0)), 0.0)
            if mark <= 0.0:
                try:
                    snap = self.market_snapshot(symbol)
                    mark = self._safe_float(snap.get("mid"), 0.0)
                except Exception:
                    mark = 0.0
            live_exposure += abs(qty_signed) * max(mark, 0.0)
        diff = abs(live_exposure - abs(float(internal_exposure)))
        tol = max(1.0, live_exposure * 0.5, abs(float(internal_exposure)) * 0.5)
        ok = diff <= tol
        return ok, "ok" if ok else f"futures_ledger_mismatch:{diff:.6f}"

    def request_kill(self, reason: str = "operator_kill") -> None:
        self.killed = True
        self.safe_mode = True
        self.kill_reason = reason
        self.cooldown_until_s = max(self.cooldown_until_s, time.time() + 300)

    def flatten_all_positions(self) -> tuple[bool, str]:
        # Never force-close below +2% net. Only cancel stale orders and opportunistically
        # close if the ProfitGate allows it at current quotes.
        try:
            self.connector.cancel_all_orders()
        except Exception:
            pass

        rows = self._open_positions_rows()
        if not rows:
            return True, "flat"

        blocked = 0
        closed = 0
        for row in rows:
            symbol = self._norm_symbol(row.get("symbol", row.get("instrument", row.get("product_id", ""))))
            if not symbol:
                continue
            qty_signed = self._parse_signed_qty(row)
            if abs(qty_signed) <= 1e-12:
                continue
            try:
                snap = self.market_snapshot(symbol, force_refresh=True)
            except Exception:
                blocked += 1
                continue
            side = "sell" if qty_signed > 0.0 else "buy"
            ok_gate, _reason, gate_qty, gate_payload = self._close_profit_gate(
                symbol=symbol,
                side=side,
                qty=abs(qty_signed),
                bid=self._safe_float(snap.get("bid"), 0.0),
                ask=self._safe_float(snap.get("ask"), 0.0),
                tick_size=self._safe_float(self._instrument_meta(symbol).get("tick_size"), 0.0),
            )
            if not ok_gate or gate_qty <= 0.0:
                blocked += 1
                continue
            meta = self._instrument_meta(symbol)
            lot_step = self._safe_float(meta.get("lot_step"), 1.0)
            tick_size = self._safe_float(meta.get("tick_size"), 0.0)
            qty = self._round_qty_down(gate_qty, lot_step)
            if qty <= 0.0:
                blocked += 1
                continue
            required_exit = self._safe_float(gate_payload.get("required_exit_price"), 0.0)
            if required_exit <= 0.0:
                blocked += 1
                continue
            if side == "sell":
                limit_price = self._round_price(max(required_exit, self._safe_float(snap.get("bid"), 0.0)), tick_size, side="sell")
                if limit_price < required_exit or limit_price <= 0.0:
                    blocked += 1
                    continue
            else:
                if self._safe_float(snap.get("ask"), 0.0) > required_exit:
                    blocked += 1
                    continue
                limit_price = self._round_price(required_exit, tick_size, side="buy")
                if limit_price <= 0.0:
                    blocked += 1
                    continue
            params = {
                "symbol": symbol,
                "side": side,
                "size": f"{qty:.8f}",
                "orderType": "lmt",
                "limitPrice": f"{limit_price:.12f}",
                "postOnly": "true",
                "reduceOnly": "true",
                "cliOrdId": f"{self.run_id[:8]}-flatten-{int(time.time())}",
            }
            try:
                self.connector.send_order(params)
                closed += 1
            except Exception:
                blocked += 1

        if blocked > 0:
            return False, "profit_gate_block_open_positions"
        return True, "flatten_best_effort"

    def set_fee_profile(self, profile: Any) -> None:
        if profile is None:
            return
        taker = max(
            0.0,
            self._safe_float(getattr(profile, "perps_taker_fee_bps", self._exit_fee_bps), self._exit_fee_bps),
        )
        maker = max(
            0.0,
            self._safe_float(getattr(profile, "perps_maker_fee_bps", self._entry_fee_bps), self._entry_fee_bps),
        )
        worst_case = max(taker, maker, self._entry_fee_bps, self._exit_fee_bps)
        self._entry_fee_bps = worst_case
        self._exit_fee_bps = worst_case
        self.profit_gate.config.default_entry_fee_bps = float(worst_case)
        self.profit_gate.config.default_exit_fee_bps = float(worst_case)

    def set_profit_gate_slippage_bps(self, bps: float) -> None:
        val = max(0.1, float(bps))
        self._slippage_bps_profit_gate = val
        self.profit_gate.config.default_slippage_bps = val

    def set_exits_only_mode(self, *, reason: str, duration_s: float = 180.0) -> None:
        self._exits_only_mode_until_s = max(
            self._exits_only_mode_until_s,
            time.time() + max(1.0, float(duration_s)),
        )
        self._exits_only_reason = str(reason or "exits_only_mode")

    def clear_exits_only_mode(self) -> None:
        self._exits_only_mode_until_s = 0.0
        self._exits_only_reason = ""

    def set_health_ok(self, ok: bool) -> None:
        if bool(ok):
            self.clear_exits_only_mode()
