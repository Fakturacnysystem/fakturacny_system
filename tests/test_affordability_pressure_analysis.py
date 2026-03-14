from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "analyze_affordability_pressure.py"
    spec = importlib.util.spec_from_file_location("analyze_affordability_pressure", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_affordability_analysis_extracts_expected_metrics(tmp_path: Path) -> None:
    mod = _load_module()
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    audit_rows = [
        {
            "event_type": "decision_tick",
            "payload": {
                "ts": 10.0,
                "decision": {"reason": "entry_insufficient_quote"},
                "tradable_context": {"required_quote": 2.0, "usable_quote": 0.5, "affordability": 0.25},
            },
        },
        {
            "event_type": "decision_tick",
            "payload": {
                "ts": 20.0,
                "decision": {"reason": "entry_insufficient_quote"},
                "tradable_context": {"required_quote": 2.0, "usable_quote": 0.8, "affordability": 0.4},
            },
        },
        {"event_type": "heartbeat", "payload": {"reason": "rebalance_deadzone"}},
    ]
    (run_dir / "audit.log").write_text("\n".join(json.dumps(row) for row in audit_rows), encoding="utf-8")
    (run_dir / "harmony_report.json").write_text(
        json.dumps(
            {
                "guards_mode": "strict",
                "effective_min_order_quote": 2.0,
                "sell_min_profit_bps": 40.0,
                "hard_sell_floor_bps": 30.0,
                "order_cadence_s": 9.0,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "dashboard_snapshot.json").write_text(
        json.dumps({"groups": {"execution": {"orders_submitted_total": 2, "fill_rate": 0.5}}}),
        encoding="utf-8",
    )
    runtime_audit_path = run_dir / "runtime_audit.json"
    runtime_audit_path.write_text(
        json.dumps({"system_state": "OK", "order_stats": {"submitted_orders": 2}, "order_stats_source": "merged"}),
        encoding="utf-8",
    )

    report = mod.analyze_affordability(run_dir=run_dir, runtime_audit_path=runtime_audit_path)
    assert report["counts"]["entry_insufficient_quote"] == 2
    assert report["affordability"]["samples"] == 2
    assert report["affordability"]["required_quote_avg"] == 2.0
    assert report["affordability"]["usable_quote_avg"] == 0.65
    assert report["cadence"]["decision_tick_count"] == 2
    assert report["cadence"]["decision_tick_spacing_avg_s"] == 10.0
    assert report["harmony"]["sell_min_profit_ok"] is True
    assert report["runtime_audit"]["order_stats_source"] == "merged"
