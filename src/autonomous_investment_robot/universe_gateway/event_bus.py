from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Iterable

from autonomous_investment_robot.universe_gateway.contracts import EVENT_STREAMS, EventEnvelope, WS_REDIS_CHANNELS

LOGGER = logging.getLogger(__name__)


class UniverseEventBus:
    """Redis Streams + PubSub gateway bus wrapper."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = str(redis_url or "").strip()
        self._client: Any = None
        self._client_error = ""

    @classmethod
    def from_env(cls) -> "UniverseEventBus":
        redis_url = str(
            os.getenv("AUTONOMOUS_REDIS_URL", "")
            or os.getenv("REDIS_URL", "")
            or ""
        ).strip()
        return cls(redis_url=redis_url)

    def _connect(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.redis_url:
            self._client_error = "missing_redis_url"
            return None
        try:
            import redis  # type: ignore
        except Exception as exc:  # pragma: no cover
            self._client_error = f"dependency_missing:{exc}"
            return None
        try:
            self._client = redis.Redis.from_url(self.redis_url, decode_responses=False)
            self._client.ping()
            self._client_error = ""
            return self._client
        except Exception as exc:
            self._client = None
            self._client_error = str(exc)
            return None

    def health(self) -> dict[str, Any]:
        return {
            "backend": "redis_streams",
            "ok": self._connect() is not None,
            "error": self._client_error,
            "redis_url_set": bool(self.redis_url),
            "streams": dict(EVENT_STREAMS),
        }

    def publish_event(self, *, domain: str, envelope: EventEnvelope) -> bool:
        stream = EVENT_STREAMS.get(str(domain))
        if not stream:
            return False
        client = self._connect()
        if client is None:
            return False
        data = json.dumps(envelope.to_dict(), sort_keys=True, separators=(",", ":"), default=str)
        try:
            client.xadd(stream, {"data": data}, maxlen=100_000, approximate=True)
            return True
        except Exception as exc:
            self._client_error = str(exc)
            LOGGER.warning("universe_event_publish_failed stream=%s err=%s", stream, exc)
            return False

    def publish_ws(self, *, channel: str, payload: dict[str, Any]) -> bool:
        channel_name = WS_REDIS_CHANNELS.get(str(channel))
        if not channel_name:
            return False
        client = self._connect()
        if client is None:
            return False
        try:
            client.publish(channel_name, json.dumps(payload, sort_keys=True, default=str))
            return True
        except Exception as exc:
            self._client_error = str(exc)
            LOGGER.warning("universe_ws_publish_failed channel=%s err=%s", channel_name, exc)
            return False

    def ensure_consumer_group(self, *, stream: str, group: str) -> None:
        client = self._connect()
        if client is None:
            return
        try:
            client.xgroup_create(stream, group, id="$", mkstream=True)
        except Exception as exc:
            text = str(exc)
            if "BUSYGROUP" not in text:
                self._client_error = text

    def ensure_groups(self, *, streams: Iterable[str], group: str) -> None:
        for stream in streams:
            self.ensure_consumer_group(stream=stream, group=group)

    def consume(
        self,
        *,
        stream_names: list[str],
        group: str,
        consumer: str,
        count: int = 100,
        block_ms: int = 1000,
    ) -> list[tuple[str, str, EventEnvelope]]:
        client = self._connect()
        if client is None:
            time.sleep(max(0.1, block_ms / 1000.0))
            return []
        if not stream_names:
            return []
        self.ensure_groups(streams=stream_names, group=group)
        return self._consume_with_ids(
            stream_ids={stream: ">" for stream in stream_names},
            group=group,
            consumer=consumer,
            count=count,
            block_ms=block_ms,
        )

    def consume_pending(
        self,
        *,
        stream_names: list[str],
        group: str,
        consumer: str,
        count: int = 100,
    ) -> list[tuple[str, str, EventEnvelope]]:
        if not stream_names:
            return []
        return self._consume_with_ids(
            stream_ids={stream: "0" for stream in stream_names},
            group=group,
            consumer=consumer,
            count=count,
            block_ms=1,
        )

    def ack(self, *, stream: str, group: str, message_id: str) -> None:
        client = self._connect()
        if client is None:
            return
        try:
            client.xack(stream, group, message_id)
        except Exception:
            return

    def _consume_with_ids(
        self,
        *,
        stream_ids: dict[str, str],
        group: str,
        consumer: str,
        count: int,
        block_ms: int,
    ) -> list[tuple[str, str, EventEnvelope]]:
        client = self._connect()
        if client is None:
            time.sleep(max(0.1, block_ms / 1000.0))
            return []
        if not stream_ids:
            return []
        self.ensure_groups(streams=stream_ids.keys(), group=group)
        try:
            result = client.xreadgroup(
                group,
                consumer,
                stream_ids,
                count=max(1, count),
                block=max(1, block_ms),
            )
        except Exception as exc:
            self._client_error = str(exc)
            return []
        out: list[tuple[str, str, EventEnvelope]] = []
        for stream_raw, rows in result or []:
            stream = stream_raw.decode("utf-8") if isinstance(stream_raw, bytes) else str(stream_raw)
            for msg_id_raw, fields in rows:
                msg_id = msg_id_raw.decode("utf-8") if isinstance(msg_id_raw, bytes) else str(msg_id_raw)
                blob = fields.get(b"data") if isinstance(fields, dict) else None
                if blob is None and isinstance(fields, dict):
                    blob = fields.get("data")
                if isinstance(blob, bytes):
                    text = blob.decode("utf-8", errors="ignore")
                else:
                    text = str(blob or "{}")
                try:
                    payload = json.loads(text)
                except Exception:
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                out.append((stream, msg_id, EventEnvelope.from_mapping(payload)))
        return out

    def create_pubsub(self, *, channels: list[str]) -> Any:
        client = self._connect()
        if client is None:
            return None
        try:
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            if channels:
                pubsub.subscribe(*channels)
            return pubsub
        except Exception:
            return None
