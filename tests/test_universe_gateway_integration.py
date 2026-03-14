from __future__ import annotations

import os
from uuid import uuid4

import pytest

from autonomous_investment_robot.universe_gateway.contracts import EVENT_STREAMS, EventEnvelope
from autonomous_investment_robot.universe_gateway.event_bus import UniverseEventBus


@pytest.mark.integration
def test_redis_stream_publish_consume_and_pending_recovery() -> None:
    redis_url = os.getenv("AUTONOMOUS_REDIS_URL", "redis://localhost:6379/0")
    bus = UniverseEventBus(redis_url=redis_url)
    health = bus.health()
    if not health.get("ok"):
        pytest.skip(f"redis_unavailable:{health.get('error')}")

    stream = EVENT_STREAMS["decision"]
    group = f"test-universe-{uuid4().hex[:10]}"
    consumer = "worker-a"

    bus.ensure_consumer_group(stream=stream, group=group)

    envelope = EventEnvelope.build(
        event_type="decision_tick",
        run_id=f"run-{uuid4().hex[:8]}",
        symbol="BTCUSD",
        mode="Canary",
        confidence=0.73,
        source_module="integration-test",
        payload={"action": "enter"},
        event_id=f"evt-{uuid4().hex}",
    )
    assert bus.publish_event(domain="decision", envelope=envelope) is True

    delivered = bus.consume(
        stream_names=[stream],
        group=group,
        consumer=consumer,
        count=10,
        block_ms=2000,
    )
    assert delivered, "expected freshly published event"

    msg_stream, msg_id, msg_env = delivered[0]
    assert msg_stream == stream
    assert msg_env.event_id == envelope.event_id

    # Simulate restart recovery: read unacked pending for the same consumer.
    recovered = bus.consume_pending(
        stream_names=[stream],
        group=group,
        consumer=consumer,
        count=10,
    )
    assert recovered, "expected pending event recovery"
    assert recovered[0][2].event_id == envelope.event_id

    bus.ack(stream=stream, group=group, message_id=msg_id)

    empty_after_ack = bus.consume_pending(
        stream_names=[stream],
        group=group,
        consumer=consumer,
        count=10,
    )
    assert not empty_after_ack
