from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import math
import time
from typing import Any, Callable


@dataclass
class ExitOrderManagerConfig:
    reprice_interval_s: float = 30.0
    max_order_age_s: float = 1800.0
    cancel_replace_min_move_ticks: int = 2
    min_time_between_reprice_s: float = 10.0
    post_only_default: bool = True
    max_cancel_replace_per_min: int = 120
    cancel_replace_budget_per_symbol_per_min: int = 5


@dataclass
class ExitOrderManagerStats:
    scanned: int = 0
    repriced: int = 0
    skipped_churn: int = 0
    skipped_invalid: int = 0


class ExitOrderManager:
    """Keeps open SELL exits aligned with ProfitGate floor while limiting cancel/replace churn."""

    def __init__(
        self,
        *,
        connector: Any,
        min_guard: Any,
        config: ExitOrderManagerConfig,
        call_with_retry: Callable[[Callable[[], Any], str], Any],
        round_price_up_to_tick: Callable[[str, float], float],
    ) -> None:
        self.connector = connector
        self.min_guard = min_guard
        self.config = config
        self._call_with_retry = call_with_retry
        self._round_price_up_to_tick = round_price_up_to_tick
        self._last_run_ts: dict[str, float] = {}
        self._cancel_replace_ts: deque[float] = deque(maxlen=4096)
        self._cancel_replace_ts_by_pair: dict[str, deque[float]] = {}
        self._last_reprice_submit_ts: dict[str, float] = {}

    def _tick_size(self, pair: str) -> float:
        meta = self.min_guard.pair_meta(pair)
        pair_decimals = int(meta.get("pair_decimals", 8) or 8)
        return 10 ** (-max(0, pair_decimals))

    def _tick_distance(self, pair: str, p1: float, p2: float) -> int:
        tick = max(self._tick_size(pair), 1e-12)
        return int(abs(float(p1) - float(p2)) / tick)

    def _allow_cancel_replace(self, pair: str, now_ts: float) -> bool:
        now = float(now_ts)
        while self._cancel_replace_ts and (now - self._cancel_replace_ts[0]) > 60.0:
            self._cancel_replace_ts.popleft()
        if len(self._cancel_replace_ts) >= max(1, int(self.config.max_cancel_replace_per_min)):
            return False
        pair_q = self._cancel_replace_ts_by_pair.setdefault(str(pair), deque(maxlen=1024))
        while pair_q and (now - pair_q[0]) > 60.0:
            pair_q.popleft()
        if len(pair_q) >= max(1, int(self.config.cancel_replace_budget_per_symbol_per_min)):
            return False
        self._cancel_replace_ts.append(now)
        pair_q.append(now)
        return True

    def maybe_reprice(
        self,
        *,
        pair: str,
        bid: float,
        ask: float,
        now_ts: float,
        should_manage_order: Callable[[dict[str, Any], str], bool],
        required_floor_price: Callable[[float], tuple[bool, float]],
    ) -> ExitOrderManagerStats:
        out = ExitOrderManagerStats()
        last = float(self._last_run_ts.get(pair, 0.0) or 0.0)
        if (float(now_ts) - last) < self.config.reprice_interval_s:
            return out
        self._last_run_ts[pair] = float(now_ts)
        if not hasattr(self.connector, "open_orders"):
            return out
        try:
            raw = self.connector.open_orders()
        except Exception:
            return out
        rows = raw.get("open", raw) if isinstance(raw, dict) else {}
        if not isinstance(rows, dict):
            return out
        for txid, row in rows.items():
            if not isinstance(row, dict):
                continue
            out.scanned += 1
            descr = row.get("descr", {}) if isinstance(row.get("descr"), dict) else {}
            if not should_manage_order(descr, pair):
                continue
            oprice = float(descr.get("price", row.get("price", 0.0)) or 0.0)
            ovol = float(row.get("vol", row.get("volume", 0.0)) or 0.0)
            oexec = float(row.get("vol_exec", 0.0) or 0.0)
            rem_qty = max(0.0, ovol - oexec)
            if rem_qty <= 0.0:
                out.skipped_invalid += 1
                continue
            allowed, floor_px = required_floor_price(rem_qty)
            if not allowed or floor_px <= 0.0:
                out.skipped_invalid += 1
                continue
            floor_px = self._round_price_up_to_tick(pair, floor_px)
            opened_ts = float(row.get("opentm", row.get("open_ts", now_ts)) or now_ts)
            age_s = max(0.0, float(now_ts) - opened_ts)
            moved_ticks = self._tick_distance(pair, oprice, floor_px)
            needs_reprice = (oprice + 1e-12) < floor_px or age_s > self.config.max_order_age_s
            if not needs_reprice:
                continue
            if moved_ticks < max(1, int(self.config.cancel_replace_min_move_ticks)) and age_s <= self.config.max_order_age_s:
                out.skipped_churn += 1
                continue
            last_submit_ts = float(self._last_reprice_submit_ts.get(pair, 0.0) or 0.0)
            if (float(now_ts) - last_submit_ts) < max(0.0, float(self.config.min_time_between_reprice_s)):
                out.skipped_churn += 1
                continue
            if not self._allow_cancel_replace(pair, now_ts):
                out.skipped_churn += 1
                continue
            try:
                self._call_with_retry(lambda: self.connector.cancel_order(str(txid)), "exit_reprice_cancel")
            except Exception:
                out.skipped_invalid += 1
                continue
            try:
                params = {
                    "pair": pair,
                    "type": "sell",
                    "ordertype": "limit",
                    "price": f"{floor_px:.8f}",
                    "volume": f"{rem_qty:.8f}",
                }
                if self.config.post_only_default:
                    # Force posted price to avoid taker close slippage.
                    tick = self._tick_size(pair)
                    if floor_px <= bid:
                        floor_px = self._round_price_up_to_tick(pair, bid + tick)
                        params["price"] = f"{floor_px:.8f}"
                    params["oflags"] = "post"
                self._call_with_retry(lambda: self.connector.add_order(params), "exit_reprice_submit")
                self._last_reprice_submit_ts[pair] = float(now_ts)
                out.repriced += 1
            except Exception:
                out.skipped_invalid += 1
                continue
        return out

    def submit_sell_limit_floor(
        self,
        *,
        pair: str,
        qty: float,
        floor_price: float,
        bid: float,
        extra_params: dict[str, Any] | None = None,
        stage: str = "exit_submit",
    ) -> dict[str, Any]:
        """Submit a profit-locked SELL exit as post-only limit floor."""
        price = self._round_price_up_to_tick(pair, float(floor_price))
        if price <= 0.0:
            raise ValueError("invalid_floor_price")
        tick = self._tick_size(pair)
        params: dict[str, Any] = {
            "pair": str(pair),
            "type": "sell",
            "ordertype": "limit",
            "price": f"{price:.8f}",
            "volume": f"{max(0.0, float(qty)):.8f}",
        }
        if self.config.post_only_default:
            if price <= float(bid):
                price = self._round_price_up_to_tick(pair, float(bid) + tick)
                params["price"] = f"{price:.8f}"
            params["oflags"] = "post"
        if isinstance(extra_params, dict):
            params.update({k: v for k, v in extra_params.items() if k not in {"price", "volume", "ordertype", "type", "pair"}})
        return self._call_with_retry(lambda: self.connector.add_order(params), stage)
