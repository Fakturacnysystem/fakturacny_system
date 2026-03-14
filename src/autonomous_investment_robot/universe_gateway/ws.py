from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from autonomous_investment_robot.universe_gateway.contracts import WS_REDIS_CHANNELS
from autonomous_investment_robot.universe_gateway.event_bus import UniverseEventBus

LOGGER = logging.getLogger(__name__)


@dataclass
class ConnectionState:
    websocket: Any
    channel: str
    role: str
    last_telemetry_ts: float = 0.0


class UniverseWebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[str, dict[int, ConnectionState]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def connect(self, *, channel: str, websocket: Any, role: str) -> ConnectionState:
        state = ConnectionState(websocket=websocket, channel=channel, role=role)
        async with self._lock:
            self._connections[channel][id(state)] = state
        return state

    async def disconnect(self, state: ConnectionState) -> None:
        async with self._lock:
            if state.channel in self._connections:
                self._connections[state.channel].pop(id(state), None)

    async def publish(self, *, channel: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            states = list(self._connections.get(channel, {}).values())
        if not states:
            return
        now = time.time()
        text = json.dumps(payload, sort_keys=True, default=str)
        stale: list[ConnectionState] = []
        for state in states:
            try:
                if channel == "telemetry" and (now - state.last_telemetry_ts) < 0.2:
                    continue
                await state.websocket.send_text(text)
                if channel == "telemetry":
                    state.last_telemetry_ts = now
            except Exception:
                stale.append(state)
        for state in stale:
            await self.disconnect(state)

    async def active_counts(self) -> dict[str, int]:
        async with self._lock:
            return {channel: len(states) for channel, states in self._connections.items()}


async def redis_pubsub_bridge(*, bus: UniverseEventBus, hub: UniverseWebSocketHub, stop_event: asyncio.Event) -> None:
    channels = list(WS_REDIS_CHANNELS.values())
    pubsub = bus.create_pubsub(channels=channels)
    if pubsub is None:
        LOGGER.warning("universe_ws_pubsub_unavailable")
        while not stop_event.is_set():
            await asyncio.sleep(1.0)
        return

    reverse = {redis_name: channel for channel, redis_name in WS_REDIS_CHANNELS.items()}

    try:
        while not stop_event.is_set():
            try:
                message = pubsub.get_message(timeout=1.0)
            except Exception:
                message = None
            if not message:
                await asyncio.sleep(0.02)
                continue
            channel_raw = message.get("channel") if isinstance(message, dict) else None
            data_raw = message.get("data") if isinstance(message, dict) else None
            if isinstance(channel_raw, bytes):
                channel_name = channel_raw.decode("utf-8", errors="ignore")
            else:
                channel_name = str(channel_raw or "")
            mapped = reverse.get(channel_name)
            if not mapped:
                continue
            if isinstance(data_raw, bytes):
                payload_text = data_raw.decode("utf-8", errors="ignore")
            else:
                payload_text = str(data_raw or "{}")
            try:
                payload = json.loads(payload_text)
            except Exception:
                payload = {"raw": payload_text}
            if not isinstance(payload, dict):
                payload = {"payload": payload}
            await hub.publish(channel=mapped, payload=payload)
    finally:
        try:
            pubsub.close()
        except Exception:
            pass
