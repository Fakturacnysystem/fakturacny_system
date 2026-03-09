from __future__ import annotations

from pathlib import Path
import time

from autonomous_investment_robot.services.distributed import (
    DistributedEnvelope,
    DistributedStreamNames,
    LocalComputeBridge,
    PostgresMirrorSink,
    build_compute_bridge_from_env,
    build_idempotency_key,
    decode_stream_entry,
    encode_stream_entry,
)


def test_distributed_envelope_roundtrip() -> None:
    env = DistributedEnvelope(
        task_id="task-1",
        run_id="run-a",
        symbol="XXBTZUSD",
        market_class="crypto_spot",
        ts=time.time(),
        ttl_s=5.0,
        payload_version="v1",
        idempotency_key="idem-1",
        payload={"kind": "scan_rank", "symbols": ["XXBTZUSD"]},
    )
    row = encode_stream_entry(env)
    parsed = decode_stream_entry(row)
    assert parsed.task_id == "task-1"
    assert parsed.idempotency_key == "idem-1"
    assert parsed.payload.get("kind") == "scan_rank"


def test_idempotency_key_stable() -> None:
    payload = {"kind": "scan_rank", "symbols": ["A", "B"]}
    one = build_idempotency_key(
        stream="autobot.tasks.scan",
        run_id="run-a",
        symbol="*",
        payload=payload,
    )
    two = build_idempotency_key(
        stream="autobot.tasks.scan",
        run_id="run-a",
        symbol="*",
        payload=payload,
    )
    assert one == two


def test_local_compute_bridge_rankings() -> None:
    bridge = LocalComputeBridge()
    response = bridge.request_rankings(
        run_id="run-1",
        symbols=["XXBTZUSD", "AAPLxUSD"],
        market_class_by_symbol={"XXBTZUSD": "crypto_spot", "AAPLxUSD": "xstock"},
        top_n=2,
        timeout_s=0.5,
    )
    assert response.ok
    assert response.source == "local"
    assert set(response.rankings.keys()) == {"XXBTZUSD", "AAPLxUSD"}
    assert all(0.0 <= row.confidence <= 1.0 for row in response.rankings.values())


def test_build_compute_bridge_defaults_to_local(monkeypatch: object) -> None:
    monkeypatch.delenv("AUTONOMOUS_COMPUTE_BRIDGE", raising=False)
    monkeypatch.delenv("AUTONOMOUS_REDIS_URL", raising=False)
    bridge = build_compute_bridge_from_env()
    health = bridge.health()
    assert health.get("backend") == "local"
    assert bool(health.get("ok"))


def test_postgres_mirror_sqlite_fallback(tmp_path: Path) -> None:
    dsn = f"sqlite:///{tmp_path / 'mirror.db'}"
    sink = PostgresMirrorSink(
        dsn=dsn,
        run_id="run-test",
        enabled=True,
    )
    h = sink.health()
    assert h.enabled
    assert h.ok
    assert sink.record_decision({"symbol": "XXBTZUSD", "decision": "hold"})
    assert sink.record_execution({"symbol": "XXBTZUSD", "status": "submitted"})


def test_stream_name_prefix() -> None:
    names = DistributedStreamNames.from_prefix("robot")
    assert names.task_scan == "robot.tasks.scan"
    assert names.result_rankings == "robot.results.rankings"
