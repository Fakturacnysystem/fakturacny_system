from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_runtime_audit_module():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "runtime_audit.py"
    spec = importlib.util.spec_from_file_location("runtime_audit", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_runtime_audit_summarizes_blockers_and_invariants(tmp_path: Path) -> None:
    mod = _load_runtime_audit_module()
    run_dir = tmp_path / "run_1"
    run_dir.mkdir(parents=True, exist_ok=True)

    audit_events = [
        {"event_type": "live_exec", "ts": 1.0, "payload": {"status": "blocked", "reason": "no_intent", "side": "buy", "symbol": "XBTUSD"}},
        {"event_type": "live_exec", "ts": 2.0, "payload": {"status": "submitted", "reason": "spot_order_submitted", "side": "buy", "symbol": "XBTUSD"}},
        {"event_type": "live_exec", "ts": 3.0, "payload": {"status": "blocked", "reason": "cooldown_active", "side": "buy", "symbol": "XBTUSD"}},
    ]
    (run_dir / "audit.log").write_text("\n".join(json.dumps(row) for row in audit_events), encoding="utf-8")
    (run_dir / "event_bus.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"topic": "market_data"}),
                json.dumps({"topic": "decision"}),
                json.dumps({"topic": "execution"}),
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "harmony_report.json").write_text(
        json.dumps(
            {
                "guards_mode": "fatal_only",
                "order_cadence_s": 5.0,
                "effective_min_order_quote": 2.0,
                "sell_min_profit_bps": 30.0,
                "sell_target_profit_bps": 180.0,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "dashboard_snapshot.json").write_text(
        json.dumps(
            {
                "groups": {
                    "execution": {
                        "intents_total": 3,
                        "orders_submitted_total": 1,
                        "orders_rejected_total": 2,
                        "fill_rate": 0.2,
                        "reject_rate": 0.66,
                    },
                    "efficiency": {"tco_total_bps_rt": 14.0, "cost_to_alpha_ratio": 0.8},
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "mastermind_status.json").write_text(
        json.dumps({"health": {"status": "OK"}, "guardrails": {}, "conflicts": [], "overrides": {}}),
        encoding="utf-8",
    )
    (run_dir / "llm_self_improvement_diagnostics.json").write_text(
        json.dumps(
            {
                "provider": "groq",
                "model": "openai/gpt-oss-120b",
                "model_fallback": "openai/gpt-oss-20b",
                "model_effective": "openai/gpt-oss-20b",
                "llm_enabled": True,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "market_discovery.json").write_text(
        json.dumps(
            {
                "xstocks_symbols": ["TSLAXUSD"],
                "xstocks_etf_symbols": ["SPYXUSD"],
                "market_class_counts": {"xstock": 1, "xstock_etf": 1},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "universe_diagnostics.json").write_text(
        json.dumps(
            {
                "eligible_market_class_counts": {"xstock": 1},
                "detected_market_class_counts": {"xstock": 2},
                "filter_reasons": {"xstocks_allowlist_block": 1},
                "mixed_universe_mode": True,
            }
        ),
        encoding="utf-8",
    )

    report = mod.run_audit(run_dir=run_dir, event_limit=3000)
    assert report["order_stats"]["submitted_orders"] == 1
    assert report["order_stats_source"] in {"audit_log", "merged"}
    assert "audit_log" in report["order_stats_sources"]
    assert "events_files" in report["order_stats_sources"]
    assert report["hard_invariants"]["ok"] is True
    assert report["harmony"]["sell_min_profit_ok"] is True
    assert report["event_bus_topics"]["execution"] > 0
    assert report["provider_diagnostics"]["provider"] == "groq"
    assert report["xstocks"]["detected_symbols"] == ["TSLAXUSD"]
    assert "runtime_bridges" in report
    assert report["runtime_bridges"]["redis_streams"]["active"] is False
    assert report["runtime_bridges"]["compute_bridge"]["declared"] is False
    assert report["rollback_dry_run"]["validated"] is True
    assert report["rollback_dry_run"]["artifact_id"]


def test_runtime_audit_distinguishes_no_intent_from_affordability_blocks(tmp_path: Path) -> None:
    mod = _load_runtime_audit_module()
    run_dir = tmp_path / "run_2"
    run_dir.mkdir(parents=True, exist_ok=True)

    audit_events = [
        {"event_type": "live_exec", "ts": 1.0, "payload": {"status": "blocked", "reason": "no_intent", "side": "buy", "symbol": "XBTUSD"}},
        {"event_type": "live_exec", "ts": 2.0, "payload": {"status": "skipped", "reason": "entry_insufficient_quote", "side": "buy", "symbol": "XBTUSD"}},
        {"event_type": "live_exec", "ts": 3.0, "payload": {"status": "skipped", "reason": "insufficient_balance_precheck", "side": "buy", "symbol": "XBTUSD"}},
    ]
    (run_dir / "audit.log").write_text("\n".join(json.dumps(row) for row in audit_events), encoding="utf-8")
    (run_dir / "event_bus.jsonl").write_text("", encoding="utf-8")
    (run_dir / "harmony_report.json").write_text(
        json.dumps({"guards_mode": "fatal_only", "sell_min_profit_bps": 30.0, "sell_target_profit_bps": 60.0}),
        encoding="utf-8",
    )
    (run_dir / "dashboard_snapshot.json").write_text(json.dumps({}), encoding="utf-8")

    report = mod.run_audit(run_dir=run_dir, event_limit=3000)
    assert int(report["blockers"]["no_intent"]["count"]) == 1
    assert int(report["blockers"]["insufficient_balance"]["count"]) >= 1
    assert report["rollback_dry_run"]["validated"] is False
    assert "execution_topic_missing" in report["rollback_dry_run"]["reason_codes"]


def test_runtime_audit_reads_universe_event_bus_fallback_for_execution_topic(tmp_path: Path) -> None:
    mod = _load_runtime_audit_module()
    run_dir = tmp_path / "run_fallback"
    fallback_dir = run_dir / "universe_events"
    fallback_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "audit.log").write_text("", encoding="utf-8")
    (run_dir / "harmony_report.json").write_text(
        json.dumps({"guards_mode": "strict", "sell_min_profit_bps": 30.0, "sell_target_profit_bps": 60.0}),
        encoding="utf-8",
    )
    (run_dir / "dashboard_snapshot.json").write_text(json.dumps({}), encoding="utf-8")

    fallback_rows = [
        {
            "topic": "universe",
            "payload": {
                "event_type": "HealthEvent",
                "event_domain": "telemetry",
                "metadata": {"legacy_stream": "orders", "legacy_event_type": "ORDER_INTENT"},
            },
        },
        {
            "topic": "universe",
            "payload": {
                "event_type": "HealthEvent",
                "event_domain": "telemetry",
                "metadata": {"legacy_stream": "fills", "legacy_event_type": "FILL"},
            },
        },
    ]
    (fallback_dir / "event_bus.jsonl").write_text("\n".join(json.dumps(row) for row in fallback_rows), encoding="utf-8")

    report = mod.run_audit(run_dir=run_dir, event_limit=3000)
    assert report["event_bus_topics"]["execution"] >= 1
    assert report["event_bus_topics"]["decision"] >= 1
    assert report["execution_presence"]["execution_topic_present"] is True
    assert "execution_topic_missing" not in report["rollback_dry_run"]["reason_codes"]
    assert report["rollback_dry_run"]["validated"] is True


def test_runtime_audit_merges_root_and_fallback_topics(tmp_path: Path) -> None:
    mod = _load_runtime_audit_module()
    run_dir = tmp_path / "run_merge"
    fallback_dir = run_dir / "universe_events"
    fallback_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "audit.log").write_text("", encoding="utf-8")
    (run_dir / "harmony_report.json").write_text(
        json.dumps({"guards_mode": "strict", "sell_min_profit_bps": 30.0, "sell_target_profit_bps": 60.0}),
        encoding="utf-8",
    )
    (run_dir / "dashboard_snapshot.json").write_text(json.dumps({}), encoding="utf-8")
    (run_dir / "event_bus.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"topic": "market_data"}),
                json.dumps({"topic": "intent"}),
            ]
        ),
        encoding="utf-8",
    )
    (fallback_dir / "event_bus.jsonl").write_text(
        json.dumps(
            {
                "topic": "universe",
                "payload": {
                    "event_type": "HealthEvent",
                    "event_domain": "telemetry",
                    "metadata": {"legacy_stream": "fills", "legacy_event_type": "FILL"},
                },
            }
        ),
        encoding="utf-8",
    )

    report = mod.run_audit(run_dir=run_dir, event_limit=3000)
    assert report["event_bus_topics"]["market_data"] == 1
    assert report["event_bus_topics"]["decision"] == 1
    assert report["event_bus_topics"]["execution"] == 1
    assert report["execution_presence"]["execution_topic_present"] is True


def test_runtime_audit_uses_events_files_when_live_exec_rows_missing(tmp_path: Path) -> None:
    mod = _load_runtime_audit_module()
    run_dir = tmp_path / "run_events_fallback"
    fallback_dir = run_dir / "universe_events"
    fallback_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "audit.log").write_text("", encoding="utf-8")
    (run_dir / "harmony_report.json").write_text(
        json.dumps({"guards_mode": "strict", "sell_min_profit_bps": 30.0, "sell_target_profit_bps": 60.0}),
        encoding="utf-8",
    )
    (run_dir / "dashboard_snapshot.json").write_text(json.dumps({}), encoding="utf-8")
    (fallback_dir / "event_bus.jsonl").write_text(
        json.dumps(
            {
                "topic": "universe",
                "payload": {
                    "event_type": "HealthEvent",
                    "event_domain": "telemetry",
                    "metadata": {"legacy_stream": "orders", "legacy_event_type": "ORDER_INTENT"},
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "events_orders.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"event_type": "ORDER_INTENT", "payload": {"side": "buy"}}),
                json.dumps({"event_type": "ORDER_INTENT", "payload": {"side": "sell"}}),
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "events_fills.jsonl").write_text(
        json.dumps({"event_type": "FILL", "payload": {"side": "buy"}}),
        encoding="utf-8",
    )

    report = mod.run_audit(run_dir=run_dir, event_limit=3000)
    assert report["order_stats_source"] in {"events_files", "merged"}
    assert report["order_stats"]["submitted_orders"] >= 2
    assert report["order_stats_sources"]["events_files"]["fills_observed"] == 1
    assert report["execution_presence"]["execution_topic_present"] is True
    assert report["system_state"] == "OK"


def test_runtime_audit_treats_profit_lock_skips_as_guard_hits_not_invariant_failures(tmp_path: Path) -> None:
    mod = _load_runtime_audit_module()
    run_dir = tmp_path / "run_profit_lock_guard"
    run_dir.mkdir(parents=True, exist_ok=True)

    audit_events = [
        {
            "event_type": "policy_violation_warn",
            "ts": 1.0,
            "payload": {"reason": "profit_lock_sell_below_entry", "side": "sell", "symbol": "XBTUSD"},
        },
        {
            "event_type": "live_exec",
            "ts": 2.0,
            "payload": {"status": "skipped", "reason": "profit_lock_sell_below_entry", "side": "sell", "symbol": "XBTUSD"},
        },
    ]
    (run_dir / "audit.log").write_text("\n".join(json.dumps(row) for row in audit_events), encoding="utf-8")
    (run_dir / "event_bus.jsonl").write_text(json.dumps({"topic": "execution"}), encoding="utf-8")
    (run_dir / "harmony_report.json").write_text(
        json.dumps({"guards_mode": "strict", "sell_min_profit_bps": 33.0, "sell_target_profit_bps": 53.0}),
        encoding="utf-8",
    )
    (run_dir / "dashboard_snapshot.json").write_text(json.dumps({}), encoding="utf-8")

    report = mod.run_audit(run_dir=run_dir, event_limit=3000)
    assert report["hard_invariants"]["ok"] is True
    assert report["hard_invariants"]["profit_lock_sell_below_entry"] == 0
    assert report["hard_invariants"]["profit_lock_guard_hits"]["profit_lock_sell_below_entry"] == 2
    assert report["system_state"] != "FATAL"


def test_runtime_audit_flags_profit_lock_violation_when_unsafe_sell_submitted(tmp_path: Path) -> None:
    mod = _load_runtime_audit_module()
    run_dir = tmp_path / "run_profit_lock_violation"
    run_dir.mkdir(parents=True, exist_ok=True)

    audit_events = [
        {
            "event_type": "live_exec",
            "ts": 1.0,
            "payload": {"status": "submitted", "reason": "profit_lock_sell_below_min_profit", "side": "sell", "symbol": "XBTUSD"},
        },
    ]
    (run_dir / "audit.log").write_text("\n".join(json.dumps(row) for row in audit_events), encoding="utf-8")
    (run_dir / "event_bus.jsonl").write_text(json.dumps({"topic": "execution"}), encoding="utf-8")
    (run_dir / "harmony_report.json").write_text(
        json.dumps({"guards_mode": "strict", "sell_min_profit_bps": 33.0, "sell_target_profit_bps": 53.0}),
        encoding="utf-8",
    )
    (run_dir / "dashboard_snapshot.json").write_text(json.dumps({}), encoding="utf-8")

    report = mod.run_audit(run_dir=run_dir, event_limit=3000)
    assert report["hard_invariants"]["ok"] is False
    assert report["hard_invariants"]["profit_lock_sell_below_min_profit"] == 1
    assert report["system_state"] == "FATAL"
    assert "hard_invariants_failed" in report["rollback_dry_run"]["reason_codes"]
