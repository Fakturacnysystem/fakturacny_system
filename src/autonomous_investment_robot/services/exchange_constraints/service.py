from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import time
from pathlib import Path
from typing import Any


@dataclass
class Constraints:
    symbol: str
    min_base_qty: float
    min_quote_notional: float
    price_precision: int
    qty_precision: int
    tick_size: float
    lot_step: float
    order_types_allowed: list[str]
    refreshed_ts: float


@dataclass
class ValidatedOrder:
    symbol: str
    side: str
    order_type: str
    rounded_price: float
    rounded_qty: float
    rounded_notional_quote: float
    min_quote_notional: float
    max_quote_notional: float


class ExchangeConstraintsOracle:
    def __init__(self, connector: Any, run_dir: str, ttl_s: float = 1800.0) -> None:
        self.connector = connector
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_s = max(30.0, float(ttl_s))
        self.cache_path = self.run_dir / "exchange_constraints.json"
        self._pairs_cache: dict[str, dict[str, Any]] = {}
        self._constraints_cache: dict[str, Constraints] = {}
        self._loaded_disk = False
        self._last_refresh_ts = 0.0

    def _load_disk(self) -> None:
        if self._loaded_disk:
            return
        self._loaded_disk = True
        if not self.cache_path.exists():
            return
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        self._last_refresh_ts = float(payload.get("saved_ts", 0.0) or 0.0)
        entries = payload.get("constraints", {})
        if not isinstance(entries, dict):
            return
        for symbol, row in entries.items():
            if not isinstance(row, dict):
                continue
            try:
                self._constraints_cache[str(symbol).upper()] = Constraints(
                    symbol=str(row.get("symbol", symbol)).upper(),
                    min_base_qty=float(row.get("min_base_qty", 0.0) or 0.0),
                    min_quote_notional=float(row.get("min_quote_notional", 0.0) or 0.0),
                    price_precision=int(row.get("price_precision", 8) or 8),
                    qty_precision=int(row.get("qty_precision", 8) or 8),
                    tick_size=float(row.get("tick_size", 0.0) or 0.0),
                    lot_step=float(row.get("lot_step", 0.0) or 0.0),
                    order_types_allowed=[str(x).lower() for x in (row.get("order_types_allowed", []) or [])],
                    refreshed_ts=float(row.get("refreshed_ts", self._last_refresh_ts) or self._last_refresh_ts),
                )
            except Exception:
                continue

    def _save_disk(self) -> None:
        out = {
            "saved_ts": time.time(),
            "constraints": {symbol: asdict(value) for symbol, value in sorted(self._constraints_cache.items())},
        }
        self.cache_path.write_text(json.dumps(out, sort_keys=True, indent=2), encoding="utf-8")

    def _pairs_stale(self) -> bool:
        return not self._pairs_cache or (time.time() - self._last_refresh_ts) > self.ttl_s

    def _refresh_pairs(self) -> None:
        if not self._pairs_stale():
            return
        raw = self.connector.asset_pairs()
        if not isinstance(raw, dict):
            return
        out: dict[str, dict[str, Any]] = {}
        for key, meta in raw.items():
            if not isinstance(meta, dict):
                continue
            out[str(key).upper()] = meta
            alt = str(meta.get("altname", "") or "").upper()
            ws = str(meta.get("wsname", "") or "").upper()
            if alt:
                out[alt] = meta
                out[alt.replace("/", "")] = meta
            if ws:
                out[ws] = meta
                out[ws.replace("/", "")] = meta
        self._pairs_cache = out
        self._last_refresh_ts = time.time()

    def _safe_ticker_mid(self, symbol: str) -> float:
        try:
            row = self.connector.ticker(symbol)
        except Exception:
            return 0.0
        if not isinstance(row, dict):
            return 0.0
        pick = row.get(symbol)
        if not isinstance(pick, dict) and row:
            first = next(iter(row.values()))
            pick = first if isinstance(first, dict) else {}
        if not isinstance(pick, dict):
            return 0.0
        bid_raw = pick.get("b", 0.0)
        ask_raw = pick.get("a", 0.0)
        try:
            bid = float(bid_raw[0] if isinstance(bid_raw, list) and bid_raw else bid_raw or 0.0)
            ask = float(ask_raw[0] if isinstance(ask_raw, list) and ask_raw else ask_raw or 0.0)
        except Exception:
            return 0.0
        if bid <= 0.0 or ask <= 0.0:
            return 0.0
        return (bid + ask) / 2.0

    def _pair_meta(self, symbol: str) -> dict[str, Any]:
        self._load_disk()
        self._refresh_pairs()
        key = str(symbol).upper()
        if key in self._pairs_cache:
            return self._pairs_cache[key]
        key = key.replace("/", "")
        return self._pairs_cache.get(key, {})

    def _build_constraints(self, symbol: str) -> Constraints:
        meta = self._pair_meta(symbol)
        ordermin = float(meta.get("ordermin", 0.0) or 0.0)
        costmin = float(meta.get("costmin", 0.0) or 0.0)
        price_precision = int(meta.get("pair_decimals", 8) or 8)
        qty_precision = int(meta.get("lot_decimals", 8) or 8)
        tick_size = 10 ** (-max(0, price_precision))
        lot_step = 10 ** (-max(0, qty_precision))
        ordertypes = meta.get("ordertype", [])
        if not isinstance(ordertypes, list):
            ordertypes = []
        mid = self._safe_ticker_mid(str(symbol))
        min_quote_notional = max(costmin, ordermin * max(mid, 0.0))
        if min_quote_notional <= 0.0:
            # Fallback for startup if ticker unavailable.
            min_quote_notional = max(costmin, ordermin)
        return Constraints(
            symbol=str(symbol).upper().replace("/", ""),
            min_base_qty=max(0.0, ordermin),
            min_quote_notional=max(0.0, min_quote_notional),
            price_precision=max(0, price_precision),
            qty_precision=max(0, qty_precision),
            tick_size=tick_size,
            lot_step=lot_step,
            order_types_allowed=[str(x).lower() for x in ordertypes],
            refreshed_ts=time.time(),
        )

    def get_constraints(self, symbol: str) -> Constraints:
        self._load_disk()
        sym = str(symbol).upper().replace("/", "")
        cached = self._constraints_cache.get(sym)
        if cached is not None and (time.time() - cached.refreshed_ts) <= self.ttl_s:
            return cached
        fresh = self._build_constraints(sym)
        self._constraints_cache[sym] = fresh
        self._save_disk()
        return fresh

    def validate_and_round_order(
        self,
        symbol: str,
        side: str,
        notional_quote: float,
        bid: float,
        ask: float,
        *,
        order_type: str = "market",
        max_quote_notional: float | None = None,
    ) -> tuple[bool, ValidatedOrder | str]:
        sym = str(symbol).upper().replace("/", "")
        side_n = str(side).lower().strip()
        if side_n not in {"buy", "sell"}:
            return False, "invalid_side"
        if not math.isfinite(float(bid)) or not math.isfinite(float(ask)) or float(bid) <= 0.0 or float(ask) <= 0.0:
            return False, "invalid_book"
        c = self.get_constraints(sym)
        order_type_n = str(order_type).lower().strip()
        if c.order_types_allowed and order_type_n not in c.order_types_allowed:
            return False, "order_type_not_allowed"
        px = float(ask) if side_n == "buy" else float(bid)
        target_notional = max(0.0, float(notional_quote))
        max_notional = max(0.0, float(max_quote_notional if max_quote_notional is not None else target_notional))
        if max_notional > 0.0:
            target_notional = min(target_notional, max_notional)
        if target_notional < c.min_quote_notional:
            target_notional = c.min_quote_notional

        qty_raw = target_notional / max(px, 1e-12)
        qty_scale = 10 ** max(0, c.qty_precision)
        px_scale = 10 ** max(0, c.price_precision)
        rounded_qty = math.floor(max(0.0, qty_raw) * qty_scale) / qty_scale
        rounded_price = math.floor(max(0.0, px) * px_scale) / px_scale
        rounded_notional = rounded_qty * rounded_price
        qty_step = c.lot_step if c.lot_step > 0.0 else (1.0 / max(1.0, float(qty_scale)))

        if rounded_qty <= 0.0 or rounded_price <= 0.0:
            return False, "exchange_constraint_invalid"
        if rounded_qty < c.min_base_qty:
            return False, "min_base_qty"
        # Floor rounding can drift just below exchange min notional. Try one-way adjust.
        if rounded_notional < c.min_quote_notional:
            needed_qty = math.ceil((c.min_quote_notional / max(rounded_price, 1e-12)) * qty_scale) / qty_scale
            needed_qty = max(needed_qty, rounded_qty + qty_step)
            needed_notional = needed_qty * rounded_price
            if max_notional > 0.0 and needed_notional > max_notional:
                return False, "min_notional"
            rounded_qty = needed_qty
            rounded_notional = needed_notional
        if rounded_notional < c.min_quote_notional:
            return False, "min_notional"
        return True, ValidatedOrder(
            symbol=sym,
            side=side_n,
            order_type=order_type_n,
            rounded_price=rounded_price,
            rounded_qty=rounded_qty,
            rounded_notional_quote=rounded_notional,
            min_quote_notional=c.min_quote_notional,
            max_quote_notional=max_notional,
        )
