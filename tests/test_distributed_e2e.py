from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock, Thread
import sys
import time
from typing import Any

from autonomous_investment_robot.services.distributed.compute_bridge import RedisComputeBridge
from autonomous_investment_robot.services.distributed.compute_worker import ComputeWorkerConfig, RedisComputeWorker
from autonomous_investment_robot.services.distributed.contracts import DistributedConsumerGroups, DistributedStreamNames


@dataclass
class _FakeRedisStore:
    streams: dict[str, list[tuple[bytes, dict[bytes, bytes]]]] = field(default_factory=dict)
    group_offsets: dict[tuple[str, str], int] = field(default_factory=dict)
    counter: int = 0
    lock: RLock = field(default_factory=RLock)

    @staticmethod
    def _stream_name(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        return str(value)

    @staticmethod
    def _to_bytes(value: Any) -> bytes:
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        return str(value).encode("utf-8")

    def xgroup_create(self, stream: Any, group: Any, *, id: str = "$", mkstream: bool = False) -> None:
        stream_name = self._stream_name(stream)
        group_name = self._stream_name(group)
        with self.lock:
            if mkstream:
                self.streams.setdefault(stream_name, [])
            key = (group_name, stream_name)
            if key in self.group_offsets:
                raise RuntimeError("BUSYGROUP Consumer Group name already exists")
            start = len(self.streams.get(stream_name, [])) if str(id) == "$" else 0
            self.group_offsets[key] = int(start)

    def xadd(self, stream: Any, fields: dict[Any, Any], *, maxlen: int = 5000, approximate: bool = True) -> bytes:
        _ = approximate
        stream_name = self._stream_name(stream)
        with self.lock:
            rows = self.streams.setdefault(stream_name, [])
            self.counter += 1
            msg_id = f"{self.counter}-0".encode("utf-8")
            payload = {self._to_bytes(k): self._to_bytes(v) for k, v in dict(fields).items()}
            rows.append((msg_id, payload))
            if maxlen > 0 and len(rows) > int(maxlen):
                trim = len(rows) - int(maxlen)
                del rows[:trim]
            return msg_id

    def xreadgroup(
        self,
        group: Any,
        consumer: Any,
        streams: dict[Any, Any],
        *,
        count: int = 1,
        block: int = 0,
    ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
        _ = consumer
        _ = block
        group_name = self._stream_name(group)
        out: list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]] = []
        with self.lock:
            for stream_raw in streams.keys():
                stream_name = self._stream_name(stream_raw)
                key = (group_name, stream_name)
                if key not in self.group_offsets:
                    raise RuntimeError("NOGROUP No such key")
                offset = int(self.group_offsets[key])
                rows = self.streams.get(stream_name, [])
                if offset >= len(rows):
                    continue
                take = rows[offset : offset + max(1, int(count))]
                self.group_offsets[key] = offset + len(take)
                out.append((stream_name.encode("utf-8"), [(msg_id, dict(fields)) for msg_id, fields in take]))
        return out

    def xack(self, stream: Any, group: Any, msg_id: Any) -> int:
        _ = stream
        _ = group
        _ = msg_id
        return 1

    def ping(self) -> bool:
        return True


class _FakeRedisClient:
    def __init__(self, store: _FakeRedisStore) -> None:
        self._store = store

    def ping(self) -> bool:
        return self._store.ping()

    def xgroup_create(self, stream: Any, group: Any, id: str = "$", mkstream: bool = False) -> None:
        return self._store.xgroup_create(stream, group, id=id, mkstream=mkstream)

    def xadd(self, stream: Any, fields: dict[Any, Any], maxlen: int = 5000, approximate: bool = True) -> bytes:
        return self._store.xadd(stream, fields, maxlen=maxlen, approximate=approximate)

    def xreadgroup(
        self,
        group: Any,
        consumer: Any,
        streams: dict[Any, Any],
        count: int = 1,
        block: int = 0,
    ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
        return self._store.xreadgroup(group, consumer, streams, count=count, block=block)

    def xack(self, stream: Any, group: Any, msg_id: Any) -> int:
        return self._store.xack(stream, group, msg_id)


def _install_fake_redis(monkeypatch: object, store: _FakeRedisStore) -> None:
    class _RedisFactory:
        @staticmethod
        def from_url(url: str, decode_responses: bool = False) -> _FakeRedisClient:
            _ = url
            _ = decode_responses
            return _FakeRedisClient(store)

    class _FakeRedisModule:
        Redis = _RedisFactory

    monkeypatch.setitem(sys.modules, "redis", _FakeRedisModule)


def test_distributed_roundtrip_live_to_compute_to_live(monkeypatch: object) -> None:
    store = _FakeRedisStore()
    _install_fake_redis(monkeypatch, store)
    groups = DistributedConsumerGroups(live_node="live_node", compute_node="compute_node")
    streams = DistributedStreamNames.from_prefix("autobot")

    bridge = RedisComputeBridge(
        redis_url="redis://fake/0",
        stream_names=streams,
        consumer_groups=groups,
    )
    cfg = ComputeWorkerConfig(
        redis_url="redis://fake/0",
        stream_prefix="autobot",
        consumer_group="compute_node",
        live_result_group="live_node",
        consumer_name="compute-test",
        block_ms=5,
        idle_sleep_s=0.0,
    )
    worker = RedisComputeWorker(cfg)
    assert bool(worker.connect().get("ok"))

    result_holder: dict[str, Any] = {}

    def _request_rankings() -> None:
        result_holder["response"] = bridge.request_rankings(
            run_id="run-e2e",
            symbols=["XXBTZUSD", "TSLAxUSD"],
            market_class_by_symbol={"XXBTZUSD": "crypto_spot", "TSLAxUSD": "xstock"},
            top_n=2,
            timeout_s=1.5,
        )

    thread = Thread(target=_request_rankings, daemon=True)
    thread.start()

    processed = 0
    for _ in range(200):
        tick = worker.poll_once()
        processed += int(tick.get("processed", 0) or 0)
        if "response" in result_holder:
            break
        time.sleep(0.005)
    thread.join(timeout=2.0)

    assert processed >= 1
    response = result_holder.get("response")
    assert response is not None
    assert response.ok is True
    assert str(response.source) == "redis_streams"
    assert set(response.rankings.keys()) == {"XXBTZUSD", "TSLAxUSD"}
    assert str(response.rankings["TSLAxUSD"].market_class) == "xstock"
