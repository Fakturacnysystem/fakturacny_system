#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any, Mapping


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if isinstance(row, dict):
                yield row


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _extract_context(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    tradable = payload.get("tradable_context", {})
    if isinstance(tradable, Mapping) and tradable:
        return tradable
    policy_debug = payload.get("policy_debug", {})
    if isinstance(policy_debug, Mapping) and policy_debug:
        return policy_debug
    decision = payload.get("decision", {})
    if isinstance(decision, Mapping):
        detail = decision.get("reason_details", {})
        if isinstance(detail, Mapping):
            return detail
    return {}


def analyze_affordability(*, run_dir: Path, runtime_audit_path: Path | None = None) -> dict[str, Any]:
    audit_log = run_dir / "audit.log"
    harmony_report = run_dir / "harmony_report.json"
    dashboard_snapshot = run_dir / "dashboard_snapshot.json"

    runtime_audit = _read_json(runtime_audit_path) if runtime_audit_path else {}
    harmony = _read_json(harmony_report)
    dashboard = _read_json(dashboard_snapshot)

    total_rows = 0
    reason_counts: dict[str, int] = {}
    affordability_samples: list[dict[str, float]] = []
    decision_tick_ts: list[float] = []

    for row in _iter_jsonl(audit_log):
        total_rows += 1
        event_type = str(row.get("event_type", "") or "")
        payload = row.get("payload", {})
        if not isinstance(payload, Mapping):
            payload = {}

        reason = ""
        if event_type == "decision_tick":
            decision = payload.get("decision", {})
            if isinstance(decision, Mapping):
                reason = str(decision.get("reason", "") or "")
            decision_tick_ts.append(_as_float(payload.get("ts", 0.0)))
        elif event_type == "scheduler_probe_suppressed":
            reason = str(payload.get("reason", "") or "")
        elif event_type == "heartbeat":
            reason = str(payload.get("reason", "") or "")
        elif event_type == "live_exec":
            reason = str(payload.get("reason", "") or "")

        if reason:
            reason_counts[reason] = int(reason_counts.get(reason, 0)) + 1

        if reason == "entry_insufficient_quote":
            ctx = _extract_context(payload)
            required = _as_float(ctx.get("required_quote", 0.0))
            usable = _as_float(ctx.get("usable_quote", 0.0))
            affordability = _as_float(ctx.get("affordability", usable / required if required > 0 else 0.0))
            affordability_samples.append(
                {
                    "required_quote": required,
                    "usable_quote": usable,
                    "affordability": affordability,
                }
            )

    cadence_s = _as_float(harmony.get("order_cadence_s", 0.0))
    req_values = [sample["required_quote"] for sample in affordability_samples]
    usable_values = [sample["usable_quote"] for sample in affordability_samples]
    aff_values = [sample["affordability"] for sample in affordability_samples]

    avg_decision_spacing = 0.0
    if len(decision_tick_ts) >= 2:
        diffs = [max(0.0, decision_tick_ts[idx] - decision_tick_ts[idx - 1]) for idx in range(1, len(decision_tick_ts))]
        if diffs:
            avg_decision_spacing = mean(diffs)

    recommendation: list[str] = []
    if affordability_samples and mean(aff_values) < 0.25:
        recommendation.append("capital_or_min_quote_mismatch")
    if reason_counts.get("entry_insufficient_quote", 0) > reason_counts.get("rebalance_deadzone", 0):
        recommendation.append("prioritize_affordability_tuning")

    groups = dashboard.get("groups", {}) if isinstance(dashboard.get("groups"), dict) else {}
    execution = groups.get("execution", {}) if isinstance(groups.get("execution"), dict) else {}

    return {
        "run_dir": str(run_dir),
        "artifacts": {
            "audit_log": str(audit_log),
            "harmony_report": str(harmony_report),
            "dashboard_snapshot": str(dashboard_snapshot),
            "runtime_audit": str(runtime_audit_path) if runtime_audit_path else "",
        },
        "counts": {
            "rows_total": int(total_rows),
            "entry_insufficient_quote": int(reason_counts.get("entry_insufficient_quote", 0)),
            "rebalance_deadzone": int(reason_counts.get("rebalance_deadzone", 0)),
            "no_intent": int(reason_counts.get("no_intent", 0)),
            "reason_top": dict(sorted(reason_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]),
        },
        "affordability": {
            "samples": int(len(affordability_samples)),
            "required_quote_avg": float(mean(req_values) if req_values else 0.0),
            "required_quote_min": float(min(req_values) if req_values else 0.0),
            "required_quote_max": float(max(req_values) if req_values else 0.0),
            "usable_quote_avg": float(mean(usable_values) if usable_values else 0.0),
            "usable_quote_min": float(min(usable_values) if usable_values else 0.0),
            "usable_quote_max": float(max(usable_values) if usable_values else 0.0),
            "affordability_avg": float(mean(aff_values) if aff_values else 0.0),
            "affordability_min": float(min(aff_values) if aff_values else 0.0),
            "affordability_max": float(max(aff_values) if aff_values else 0.0),
        },
        "cadence": {
            "order_cadence_s": cadence_s,
            "decision_tick_count": int(len(decision_tick_ts)),
            "decision_tick_spacing_avg_s": float(avg_decision_spacing),
        },
        "execution_summary": {
            "orders_submitted_total": execution.get("orders_submitted_total"),
            "orders_rejected_total": execution.get("orders_rejected_total"),
            "fill_rate": execution.get("fill_rate"),
            "reject_rate": execution.get("reject_rate"),
        },
        "harmony": {
            "guards_mode": harmony.get("guards_mode"),
            "effective_min_order_quote": harmony.get("effective_min_order_quote"),
            "sell_min_profit_bps": harmony.get("sell_min_profit_bps"),
            "hard_sell_floor_bps": harmony.get("hard_sell_floor_bps"),
            "sell_min_profit_ok": float(harmony.get("sell_min_profit_bps", 0.0) or 0.0)
            >= float(harmony.get("hard_sell_floor_bps", 30.0) or 30.0),
        },
        "runtime_audit": {
            "system_state": runtime_audit.get("system_state"),
            "hard_invariants": runtime_audit.get("hard_invariants", {}),
            "order_stats": runtime_audit.get("order_stats", {}),
            "order_stats_source": runtime_audit.get("order_stats_source", ""),
        },
        "recommendations": recommendation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze affordability pressure from bounded runtime artifacts.")
    parser.add_argument("--run-dir", required=True, help="Runtime directory containing audit.log and reports.")
    parser.add_argument("--runtime-audit", default="", help="Optional runtime audit JSON path.")
    parser.add_argument("--output", default="", help="Optional output JSON path.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    runtime_audit = Path(args.runtime_audit).resolve() if str(args.runtime_audit).strip() else None
    report = analyze_affordability(run_dir=run_dir, runtime_audit_path=runtime_audit)

    if str(args.output).strip():
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
