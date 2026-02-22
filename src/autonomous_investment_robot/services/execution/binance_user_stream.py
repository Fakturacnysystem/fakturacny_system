from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autonomous_investment_robot.connectors.cex.binance_um_perps import BinanceUMPerpsConnector
from autonomous_investment_robot.services.event_store.service import EventStore


@dataclass
class UserStreamEvent:
    event_type: str
    event_time_ms: int
    order_id: str
    payload: dict[str, Any]


@dataclass
class UserStreamState:
    listen_key: str = ""
    last_keepalive_s: float = 0.0
    seen: set[tuple[int, str]] = field(default_factory=set)


class BinanceUserStream:
    KEEPALIVE_INTERVAL_S = 30 * 60

    def __init__(self, connector: BinanceUMPerpsConnector, event_store: EventStore, run_dir: str) -> None:
        self.connector = connector
        self.event_store = event_store
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state = UserStreamState()

    def open(self) -> str:
        payload = self.connector.create_listen_key()
        self.state.listen_key = payload.get("listenKey", "")
        self.state.last_keepalive_s = time.time()
        return self.state.listen_key

    def maybe_keepalive(self) -> None:
        if not self.state.listen_key:
            return
        now = time.time()
        if (now - self.state.last_keepalive_s) < self.KEEPALIVE_INTERVAL_S:
            return
        self.connector.keepalive_listen_key(self.state.listen_key)
        self.state.last_keepalive_s = now

    def close(self) -> None:
        if self.state.listen_key:
            self.connector.close_listen_key(self.state.listen_key)
            self.state.listen_key = ""

    def parse(self, raw: dict[str, Any]) -> UserStreamEvent | None:
        event_type = raw.get("e", "")
        event_time_ms = int(raw.get("E", 0))

        if event_type == "ORDER_TRADE_UPDATE":
            order = raw.get("o", {})
            order_id = str(order.get("i", order.get("c", "")))
        elif event_type == "TRADE_LITE":
            order_id = str(raw.get("i", ""))
        elif event_type == "ACCOUNT_UPDATE":
            order_id = "account"
        else:
            return None

        dedupe_key = (event_time_ms, order_id)
        if dedupe_key in self.state.seen:
            return None
        self.state.seen.add(dedupe_key)

        return UserStreamEvent(event_type=event_type, event_time_ms=event_time_ms, order_id=order_id, payload=raw)

    def persist(self, event: UserStreamEvent) -> None:
        self.event_store.append(
            "user_stream",
            {
                "event_type": event.event_type,
                "event_time_ms": event.event_time_ms,
                "order_id": event.order_id,
                "payload": event.payload,
            },
        )
        p = self.run_dir / "user_stream_audit.jsonl"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.payload, sort_keys=True, default=str) + "\n")

    def sort_by_event_time(self, events: list[UserStreamEvent]) -> list[UserStreamEvent]:
        return sorted(events, key=lambda e: (e.event_time_ms, e.order_id))
