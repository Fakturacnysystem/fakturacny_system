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
                "sell_min_profit_bps": 120.0,
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

    report = mod.run_audit(run_dir=run_dir, event_limit=3000)
    assert report["order_stats"]["submitted_orders"] == 1
    assert report["hard_invariants"]["ok"] is True
    assert report["harmony"]["sell_min_profit_ok"] is True
    assert report["event_bus_topics"]["execution"] > 0
