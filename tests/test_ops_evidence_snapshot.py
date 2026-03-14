from __future__ import annotations

from autonomous_investment_robot.services.ops.evidence import DecisionTickEmitter, build_evidence_snapshot
from autonomous_investment_robot.services.ops.service import OpsService


def test_build_evidence_snapshot_schema_stable() -> None:
    snap = build_evidence_snapshot(
        ts=123.4,
        symbol="xbteur",
        mode="live",
        guards_mode="strict",
        market={"bid": 1.0, "ask": 1.1, "mid": 1.05, "spread_bps": 9.5, "depth_notional": 500.0, "stale_s": 0.2, "latency_ms": 45.0, "toxicity_score": 0.4},
        model={"regime": "RANGE", "liquidity_regime": "GOOD", "mu": 0.1, "confidence": 0.7, "model_version": "m1"},
        route={"venue_selected": "kraken_spot", "route_order_type": "maker", "expected_fill_prob": 0.5, "expected_total_cost_bps": 3.0, "expected_net_edge_bps": 2.5},
        constraints={"exchange_min_notional_quote": 5.0, "user_min_notional_quote": 1.0, "effective_min_notional_quote": 5.0, "price_precision": 2, "qty_precision": 6},
        balances={"quote_free": 10.0, "base_free": 0.01, "sellable_quote": 8.0},
        kpis={"fill_rate": 0.1, "reject_rate": 0.2, "rate_limit_events": 3, "cost_to_alpha_ratio_modeled": 0.8, "tco_total_bps_rt": 2.2},
        decision={"action": "buy", "reason": "intent_generated", "notional_quote": 7.5, "cooldown_remaining_s": 0.0, "gated_by": ["none"]},
    )
    assert snap["symbol"] == "XBTEUR"
    assert set(snap.keys()) == {"ts", "symbol", "mode", "guards_mode", "universe", "market", "model", "route", "constraints", "balances", "kpis", "decision"}
    assert set(snap["decision"].keys()) == {"action", "reason", "notional_quote", "cooldown_remaining_s", "gated_by"}


def test_decision_tick_emitter_dedupes_per_bucket() -> None:
    emitter = DecisionTickEmitter(interval_s=60.0, per_symbol=True)
    assert emitter.should_emit(symbol="XBTUSD", now_ts=100.0) is True
    assert emitter.should_emit(symbol="XBTUSD", now_ts=119.9) is False
    assert emitter.should_emit(symbol="ETHUSD", now_ts=119.9) is True
    assert emitter.should_emit(symbol="XBTUSD", now_ts=160.1) is True


def test_decision_tick_emitter_global_mode() -> None:
    emitter = DecisionTickEmitter(interval_s=30.0, per_symbol=False)
    assert emitter.should_emit(symbol="XBTUSD", now_ts=90.0) is True
    assert emitter.should_emit(symbol="ETHUSD", now_ts=90.1) is False
    assert emitter.should_emit(symbol="ETHUSD", now_ts=121.0) is True


def test_ops_service_records_universe_memory_trace_with_bounded_retention(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AUTONOMOUS_UNIVERSE_MEMORY_TRACE_MAX_ROWS", "3")
    ops = OpsService(str(tmp_path))
    for idx in range(5):
        row = ops.record_universe_memory_trace(
            {
                "ts": 100.0 + idx,
                "symbol": "xbteur",
                "action": "buy",
                "reason": f"r{idx}",
                "packet_id": f"pkt-{idx}",
                "mission": "momentum_extraction",
                "shield_mode": "normal",
                "execution_abort": False,
                "gated_by": [],
                "bounded_retention_status": "healthy",
                "bounded_retention_within_limit": True,
                "errors_count": 0,
                "world_state_source": "runtime_observation",
                "world_state_available": True,
                "world_state_graph_available": True,
                "world_state_safe_to_trade": True,
                "world_state_stale_domains": [],
                "world_state_stale_critical_domains": [],
            }
        )
        assert row["symbol"] == "XBTEUR"
        assert row["world_state_source"] == "runtime_observation"
    trace_path = tmp_path / "universe_memory_trace.jsonl"
    lines = [line for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 3
    assert ops.metrics["universe_memory_trace_rows"] == 3.0
    assert ops.metrics["universe_memory_trace_last_has_packet"] == 1.0


def test_ops_service_memory_trace_world_state_defaults(tmp_path) -> None:
    ops = OpsService(str(tmp_path))
    row = ops.record_universe_memory_trace(
        {
            "ts": 200.0,
            "symbol": "ethusd",
            "action": "hold",
            "reason": "default_world_state_diag",
        }
    )
    assert row["symbol"] == "ETHUSD"
    assert row["world_state_source"] == ""
    assert row["world_state_available"] is False
    assert row["world_state_graph_available"] is False
    assert row["world_state_safe_to_trade"] is False
    assert row["world_state_stale_domains"] == []
    assert row["world_state_stale_critical_domains"] == []
