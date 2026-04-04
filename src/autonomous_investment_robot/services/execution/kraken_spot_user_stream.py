from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    import websockets
except ImportError:  # pragma: no cover - exercised through launch-path safety tests
    websockets = None

from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector
from autonomous_investment_robot.services.event_store.service import EventStore


OrderUpdateHandler = Callable[[dict[str, Any]], None]
FillUpdateHandler = Callable[[dict[str, Any]], None]
StateHandler = Callable[[dict[str, Any]], None]


@dataclass
class KrakenSpotUserStreamState:
    token: str = ""
    connected: bool = False
    last_connect_s: float = 0.0
    last_event_s: float = 0.0
    last_error: str = ""
    subscribed_channels: set[str] = field(default_factory=set)
    open_orders_seeded: bool = False
    own_trades_seeded: bool = False
    seen_trade_ids: set[str] = field(default_factory=set)
    seen_order_updates: set[tuple[int, str, str]] = field(default_factory=set)


class KrakenSpotUserStream:
    CHANNELS = ("openOrders", "ownTrades")

    def __init__(
        self,
        *,
        connector: KrakenSpotConnector,
        event_store: EventStore,
        run_dir: str,
        ws_private_url: str,
        on_order_update: OrderUpdateHandler | None = None,
        on_fill_update: FillUpdateHandler | None = None,
        on_state_change: StateHandler | None = None,
    ) -> None:
        self.connector = connector
        self.event_store = event_store
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.ws_private_url = str(ws_private_url or "wss://ws-auth.kraken.com/")
        self.on_order_update = on_order_update
        self.on_fill_update = on_fill_update
        self.on_state_change = on_state_change
        self.state = KrakenSpotUserStreamState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._state_lock = threading.Lock()

    @property
    def connected(self) -> bool:
        with self._state_lock:
            return bool(self.state.connected)

    @property
    def open_orders_seeded(self) -> bool:
        with self._state_lock:
            return bool(self.state.open_orders_seeded)

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                "connected": bool(self.state.connected),
                "subscribed_channels": sorted(self.state.subscribed_channels),
                "last_connect_s": float(self.state.last_connect_s or 0.0),
                "last_event_s": float(self.state.last_event_s or 0.0),
                "last_error": str(self.state.last_error or ""),
                "open_orders_seeded": bool(self.state.open_orders_seeded),
                "own_trades_seeded": bool(self.state.own_trades_seeded),
            }

    def subscription_messages(self, token: str) -> list[dict[str, Any]]:
        return [
            {"event": "subscribe", "subscription": {"name": "openOrders", "token": token}},
            {"event": "subscribe", "subscription": {"name": "ownTrades", "token": token}},
        ]

    def open(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="kraken-spot-user-stream", daemon=True)
        self._thread.start()

    def wait_until_connected(self, timeout_s: float) -> bool:
        deadline = time.time() + max(0.0, float(timeout_s))
        while time.time() < deadline:
            if self.connected:
                return True
            if self._stop.is_set():
                break
            time.sleep(0.05)
        return self.connected

    def close(self) -> None:
        self._stop.set()
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(lambda: None)
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._listen_forever())
        finally:
            self._set_connected(False, error="user_stream_loop_closed")
            self._loop.close()

    async def _listen_forever(self) -> None:
        if websockets is None:
            raise RuntimeError("websockets_dependency_missing")
        while not self._stop.is_set():
            try:
                token = self.connector.get_websockets_token()
                with self._state_lock:
                    self.state.token = token
                    self.state.last_error = ""
                    self.state.subscribed_channels = set()
                self._persist({"type": "token_acquired"})
                async with websockets.connect(self.ws_private_url, ping_interval=20, ping_timeout=20) as ws:
                    self._persist({"type": "socket_open", "url": self.ws_private_url})
                    for message in self.subscription_messages(token):
                        await ws.send(json.dumps(message, sort_keys=True))
                        self._persist({"type": "subscribe", "payload": message})
                    while not self._stop.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        payload = json.loads(raw)
                        self.handle_message(payload)
            except Exception as exc:
                self._set_connected(False, error=str(exc))
                self._persist({"type": "socket_error", "error": str(exc)})
                if self._stop.is_set():
                    break
                await asyncio.sleep(1.0)

    def handle_message(self, raw: Any) -> None:
        now_s = time.time()
        with self._state_lock:
            self.state.last_event_s = now_s
        self._persist({"type": "message", "payload": raw})
        if isinstance(raw, dict):
            self._handle_control_message(raw, now_s=now_s)
            return
        channel, payload, meta = self.parse_channel_message(raw)
        if not channel:
            return
        if channel == "openOrders":
            self._handle_open_orders(payload, meta=meta, now_s=now_s)
            return
        if channel == "ownTrades":
            self._handle_own_trades(payload, meta=meta, now_s=now_s)

    def _handle_control_message(self, raw: dict[str, Any], *, now_s: float) -> None:
        event = str(raw.get("event", "") or "")
        if event != "subscriptionStatus":
            return
        status = str(raw.get("status", "") or "").lower()
        subscription = raw.get("subscription", {}) if isinstance(raw.get("subscription"), dict) else {}
        channel = str(subscription.get("name", raw.get("channelName", "")) or "")
        if not channel:
            return
        with self._state_lock:
            if status == "subscribed":
                self.state.subscribed_channels.add(channel)
                self.state.last_error = ""
            elif status in {"error", "unsubscribed"}:
                self.state.subscribed_channels.discard(channel)
                self.state.last_error = str(raw.get("errorMessage", raw.get("message", status)) or status)
            all_channels = all(name in self.state.subscribed_channels for name in self.CHANNELS)
            self.state.connected = all_channels
            if all_channels:
                self.state.last_connect_s = now_s
        if self.on_state_change is not None:
            self.on_state_change(self.status())

    def parse_channel_message(self, raw: Any) -> tuple[str, Any, dict[str, Any]]:
        if not isinstance(raw, list):
            return "", None, {}
        channel = next((item for item in raw if isinstance(item, str) and item in self.CHANNELS), "")
        if not channel:
            return "", None, {}
        meta = next(
            (
                item
                for item in reversed(raw)
                if isinstance(item, dict) and ("sequence" in item or "channelName" in item)
            ),
            {},
        )
        payload: Any = None
        for item in raw:
            if item == channel or item is meta:
                continue
            if isinstance(item, (list, dict)):
                payload = item
                break
        return channel, payload, meta if isinstance(meta, dict) else {}

    def _handle_open_orders(self, payload: Any, *, meta: dict[str, Any], now_s: float) -> None:
        updates = self.normalize_open_orders(payload, meta=meta)
        with self._state_lock:
            self.state.open_orders_seeded = True
            self.state.connected = all(name in self.state.subscribed_channels for name in self.CHANNELS)
            if self.state.connected and not self.state.last_connect_s:
                self.state.last_connect_s = now_s
        if self.on_state_change is not None:
            self.on_state_change(self.status())
        if self.on_order_update is None:
            return
        for update in updates:
            self.on_order_update(update)

    def _handle_own_trades(self, payload: Any, *, meta: dict[str, Any], now_s: float) -> None:
        updates = self.normalize_own_trades(payload, meta=meta)
        with self._state_lock:
            self.state.own_trades_seeded = True
            self.state.connected = all(name in self.state.subscribed_channels for name in self.CHANNELS)
            if self.state.connected and not self.state.last_connect_s:
                self.state.last_connect_s = now_s
        if self.on_state_change is not None:
            self.on_state_change(self.status())
        if self.on_fill_update is None:
            return
        for update in updates:
            self.on_fill_update(update)

    def normalize_open_orders(self, payload: Any, *, meta: dict[str, Any]) -> list[dict[str, Any]]:
        sequence = int(meta.get("sequence", 0) or 0)
        rows: list[dict[str, Any]] = []
        for item in payload if isinstance(payload, list) else [payload]:
            if not isinstance(item, dict):
                continue
            for order_id, body in item.items():
                if not isinstance(body, dict):
                    continue
                descr = body.get("descr", {}) if isinstance(body.get("descr"), dict) else {}
                cl_ord_id = str(body.get("cl_ord_id", body.get("clOrdID", "")) or "")
                userref = str(body.get("userref", "") or "")
                status_raw = str(body.get("status", "") or "").lower()
                dedupe = (sequence, str(order_id), status_raw)
                with self._state_lock:
                    if sequence > 0 and dedupe in self.state.seen_order_updates:
                        continue
                    if sequence > 0:
                        self.state.seen_order_updates.add(dedupe)
                vol = float(body.get("vol", 0.0) or 0.0)
                vol_exec = float(body.get("vol_exec", 0.0) or 0.0)
                price = float(body.get("avg_price", body.get("price", 0.0)) or 0.0)
                symbol = self.connector.symbol_from_market_id(str(descr.get("pair", "") or ""))
                if not symbol:
                    symbol = str(descr.get("pair", "") or "")
                rows.append(
                    {
                        "clientOrderId": cl_ord_id,
                        "orderId": str(order_id),
                        "status": self._normalize_kraken_status(status_raw=status_raw, vol=vol, vol_exec=vol_exec),
                        "symbol": symbol,
                        "side": str(descr.get("type", "")).upper(),
                        "executedQty": str(vol_exec),
                        "avgPrice": str(price),
                        "filledNotional": str(vol_exec * price),
                        "raw": {
                            "source": "kraken_private_ws_openOrders",
                            "sequence": sequence,
                            "userref": userref,
                            **body,
                        },
                    }
                )
        return rows

    def normalize_own_trades(self, payload: Any, *, meta: dict[str, Any]) -> list[dict[str, Any]]:
        sequence = int(meta.get("sequence", 0) or 0)
        rows: list[dict[str, Any]] = []
        for item in payload if isinstance(payload, list) else [payload]:
            if not isinstance(item, dict):
                continue
            for trade_id, body in item.items():
                if not isinstance(body, dict):
                    continue
                with self._state_lock:
                    if str(trade_id) in self.state.seen_trade_ids:
                        continue
                    self.state.seen_trade_ids.add(str(trade_id))
                price = float(body.get("price", 0.0) or 0.0)
                volume = float(body.get("vol", 0.0) or 0.0)
                rows.append(
                    {
                        "fill_id": str(trade_id),
                        "order_id": str(body.get("ordertxid", "") or ""),
                        "notional": float(body.get("cost", price * volume) or 0.0),
                        "timestamp_ms": int(float(body.get("time", 0.0) or 0.0) * 1000),
                        "raw": {
                            "source": "kraken_private_ws_ownTrades",
                            "sequence": sequence,
                            **body,
                        },
                    }
                )
        return rows

    def _normalize_kraken_status(self, *, status_raw: str, vol: float, vol_exec: float) -> str:
        normalized = str(status_raw or "").lower()
        if normalized in {"pending", "open"}:
            if vol_exec > 0.0 and vol_exec + 1e-12 < max(vol, 0.0):
                return "PARTIALLY_FILLED"
            if vol > 0.0 and vol_exec >= vol:
                return "FILLED"
            return "NEW"
        if normalized in {"closed", "filled"}:
            if vol > 0.0 and vol_exec + 1e-12 < vol:
                return "CANCELED"
            return "FILLED"
        if normalized in {"canceled", "cancelled"}:
            return "CANCELED"
        if normalized == "expired":
            return "EXPIRED"
        if normalized == "rejected":
            return "REJECTED"
        return "WORKING"

    def _set_connected(self, connected: bool, *, error: str = "") -> None:
        with self._state_lock:
            self.state.connected = bool(connected)
            if error:
                self.state.last_error = error
            if connected:
                self.state.last_error = ""
                self.state.last_connect_s = time.time()
        if self.on_state_change is not None:
            self.on_state_change(self.status())

    def _persist(self, payload: dict[str, Any]) -> None:
        self.event_store.append("user_stream", payload)
        path = self.run_dir / "user_stream_audit.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
