from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

from autonomous_investment_robot.services.distributed import (
    ComputeWorkerConfig,
    DistributedConsumerGroups,
    DistributedEnvelope,
    DistributedStreamNames,
    LocalComputeBridge,
    PostgresMirrorSink,
    RedisAuditPublisher,
    build_compute_bridge_from_env,
    build_idempotency_key,
    decode_stream_entry,
    encode_stream_entry,
)
from autonomous_investment_robot.services.universe_core import CrossAssetAllocator, UniverseAllocationInput


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


def test_consumer_group_defaults() -> None:
    groups = DistributedConsumerGroups.from_env()
    assert groups.live_node == "live_node"
    assert groups.compute_node == "compute_node"


def test_compute_worker_config_reads_consumer_group(monkeypatch: object) -> None:
    monkeypatch.setenv("AUTONOMOUS_CONSUMER_GROUP_COMPUTE_NODE", "compute-a")
    monkeypatch.setenv("AUTONOMOUS_CONSUMER_GROUP_LIVE_NODE", "live-a")
    cfg = ComputeWorkerConfig.from_env()
    assert cfg.consumer_group == "compute-a"
    assert cfg.live_result_group == "live-a"
    assert cfg.consumer_name


def test_audit_publisher_disabled_path() -> None:
    publisher = RedisAuditPublisher(
        run_id="run-x",
        redis_url="redis://127.0.0.1:6379/0",
        enabled=False,
    )
    health = publisher.health()
    assert not health.ok
    assert health.enabled is False
    assert publisher.publish(event_type="x", payload={"ok": True}) is False


def test_phase20_cross_asset_allocator_normalizes_classes_and_caps_deterministically() -> None:
    allocator = CrossAssetAllocator(
        market_class_weight_caps={
            "crypto_spot": 0.55,
            "xstock": 0.30,
            "futures": 0.40,
        }
    )
    inputs = [
        UniverseAllocationInput("crypto_spot_a", "spot", 0.9, 0.9, 0.9, 0.9),
        UniverseAllocationInput("crypto_spot_b", "crypto_spot", 0.8, 0.8, 0.9, 0.9),
        UniverseAllocationInput("xstock_a", "equity", 0.7, 0.8, 0.8, 0.9),
        UniverseAllocationInput("futures_a", "future", 0.75, 0.85, 0.82, 0.9),
    ]
    first = allocator.allocate(inputs)
    second = allocator.allocate(inputs)
    assert [row.to_dict() for row in first] == [row.to_dict() for row in second]
    assert abs(sum(row.weight for row in first) - 1.0) < 1e-9
    class_totals: dict[str, float] = {}
    for row in first:
        class_totals[row.market_class] = class_totals.get(row.market_class, 0.0) + float(row.weight)
    assert class_totals.get("crypto_spot", 0.0) <= 0.55 + 1e-9
    assert class_totals.get("xstock", 0.0) <= 0.30 + 1e-9
    assert class_totals.get("futures", 0.0) <= 0.40 + 1e-9


def test_phase20_local_compute_bridge_normalizes_market_class_aliases() -> None:
    bridge = LocalComputeBridge()
    response = bridge.request_rankings(
        run_id="run-2",
        symbols=["PI_XBTUSD", "AAPLxUSD"],
        market_class_by_symbol={"PI_XBTUSD": "perpetual", "AAPLxUSD": "equity"},
        top_n=2,
        timeout_s=0.5,
    )
    assert response.ok
    assert response.rankings["PI_XBTUSD"].market_class == "crypto_perp"
    assert response.rankings["AAPLxUSD"].market_class == "xstock"


def test_phase21_manifest_validator_classifies_missing_runtime_evidence_as_blocked() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "validate_deployment_manifests.py"
    run = subprocess.run(
        [sys.executable, str(script)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0
    payload = json.loads(run.stdout)
    assert payload["ok"] is True
    assert payload["rollout_claim_ready"] is False
    checks = {str(row.get("check_id", "")): row for row in payload.get("runtime_checks", [])}
    assert checks["runtime_evidence_bundle"]["status"] == "blocked"
    assert checks["runtime_evidence_bundle"]["required"] is True
    assert checks["docker_host_runtime"]["status"] in {"pass", "blocked"}


def test_phase21_manifest_validator_can_enforce_runtime_evidence_gate(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-evidence"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "distributed_runtime_diagnostics.json").write_text(
        json.dumps(
            {
                "compute_bridge": {"backend": "redis_streams"},
                "postgres_mirror": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "audit.log").write_text("distributed_compute_rankings\\n", encoding="utf-8")
    (run_dir / "event_bus.jsonl").write_text('{"topic":"execution"}\\n{"topic":"decision"}\\n', encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "validate_deployment_manifests.py"
    run = subprocess.run(
        [
            sys.executable,
            str(script),
            "--runtime-evidence-run-dir",
            str(run_dir),
            "--require-runtime-evidence",
            "--skip-docker-check",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0
    payload = json.loads(run.stdout)
    assert payload["ok"] is True
    assert payload["rollout_claim_ready"] is True
