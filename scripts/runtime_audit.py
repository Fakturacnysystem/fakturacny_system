#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict, deque
import argparse
import json
from pathlib import Path
from typing import Any


BLOCKER_PATTERNS: dict[str, tuple[str, ...]] = {
    "no_intent": ("no_intent",),
    "cooldown_active": ("cooldown", "cadence_cooldown"),
    "min_order_block": ("min_order", "inventory_below_min_order", "dust_accumulate"),
    "insufficient_balance": ("insufficient_balance", "insufficient funds"),
    "insufficient_base_balance": ("insufficient_base_balance",),
    "rate_limit": ("rate_limit", "rate_budget_exhausted"),
    "volatility_guard": ("vol_stop", "high_vol"),
    "uncertainty_guard": ("uncertainty_guard",),
    "confidence_guard": ("confidence_guard",),
    "regime_filter": ("regime_filter",),
    "liquidity_filter": ("liquidity_filter", "liquidity_map"),
    "spread_spike": ("spread_spike",),
    "latency_guard": ("latency_guard",),
    "execution_risk": ("execution_risk",),
    "drift_guard": ("drift_guard",),
    "risk_budget_exhausted": ("risk_budget", "treasury_reject"),
    "portfolio_exposure_limit": ("portfolio_exposure_limit", "pretrade_exposure_notional"),
    "drawdown_guard": ("drawdown_guard", "max_drawdown"),
}


def _tail_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: deque[dict[str, Any]] = deque(maxlen=max(1, limit))
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                items.append(payload)
    return list(items)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_event_bus_topics(path: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                topic = str(row.get("topic", "") or "").strip()
                if topic:
                    counts[topic] += 1
    return dict(counts)


def _extract_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    return {
        "event_type": str(row.get("event_type", "") or ""),
        "reason": str(payload.get("reason", "") or ""),
        "status": str(payload.get("status", "") or ""),
        "side": str(payload.get("side", "") or ""),
        "symbol": str(payload.get("symbol", "") or ""),
        "price": float(payload.get("price", payload.get("bid", payload.get("ask", 0.0))) or 0.0),
        "quantity": float(payload.get("quantity", payload.get("qty", payload.get("notional", 0.0))) or 0.0),
        "ts": float(row.get("ts", payload.get("ts", 0.0)) or 0.0),
    }


def _categorize_blocker(reason: str) -> str | None:
    reason_l = reason.lower()
    for category, pats in BLOCKER_PATTERNS.items():
        if any(pat in reason_l for pat in pats):
            return category
    return None


def _latest_run_dir(runs_root: Path) -> Path:
    dirs = [p for p in runs_root.iterdir() if p.is_dir()] if runs_root.exists() else []
    if not dirs:
        return runs_root / "latest"
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[0]


def run_audit(*, run_dir: Path, event_limit: int = 3000) -> dict[str, Any]:
    audit_path = run_dir / "audit.log"
    dashboard_path = run_dir / "dashboard_snapshot.json"
    event_bus_path = run_dir / "event_bus.jsonl"
    harmony_path = run_dir / "harmony_report.json"
    mastermind_path = run_dir / "mastermind_status.json"
    governance_path = run_dir / "governance_audit.jsonl"
    llm_diag_path = run_dir / "llm_self_improvement_diagnostics.json"
    discovery_path = run_dir / "market_discovery.json"
    universe_diag_path = run_dir / "universe_diagnostics.json"

    events_raw = _tail_jsonl(audit_path, event_limit)
    events = [_extract_row(row) for row in events_raw]
    event_type_counts: Counter[str] = Counter(ev["event_type"] for ev in events if ev["event_type"])
    reason_counts: Counter[str] = Counter(ev["reason"] for ev in events if ev["reason"])

    submitted_orders = 0
    blocked_orders = 0
    rejected_orders = 0
    killed_orders = 0
    sell_submitted = 0
    buy_submitted = 0
    for ev in events:
        if ev["event_type"] != "live_exec":
            continue
        status = ev["status"].lower()
        side = ev["side"].lower()
        if status in {"submitted", "filled_maker", "filled_taker_fallback", "submitted_limit_floor", "submitted_ladder"}:
            submitted_orders += 1
            if side == "sell":
                sell_submitted += 1
            elif side == "buy":
                buy_submitted += 1
        elif status in {"blocked", "skipped"}:
            blocked_orders += 1
        elif status in {"rejected", "error"}:
            rejected_orders += 1
        elif status in {"killed", "fatal"}:
            killed_orders += 1

    blocker_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "last_occurrence_ts": 0.0, "symbol": ""})
    for ev in events:
        category = _categorize_blocker(ev["reason"])
        if category is None:
            continue
        row = blocker_stats[category]
        row["count"] += 1
        if ev["ts"] >= float(row["last_occurrence_ts"]):
            row["last_occurrence_ts"] = ev["ts"]
            row["symbol"] = ev["symbol"]

    profit_lock_sell_below_entry = int(reason_counts.get("profit_lock_sell_below_entry", 0))
    profit_lock_sell_below_min_profit = int(reason_counts.get("profit_lock_sell_below_min_profit", 0))

    harmony = _read_json(harmony_path)
    dashboard = _read_json(dashboard_path)
    groups = dashboard.get("groups", {}) if isinstance(dashboard.get("groups"), dict) else {}
    execution_group = groups.get("execution", {}) if isinstance(groups.get("execution"), dict) else {}
    efficiency_group = groups.get("efficiency", {}) if isinstance(groups.get("efficiency"), dict) else {}
    topic_counts = _load_event_bus_topics(event_bus_path)
    mastermind = _read_json(mastermind_path)
    llm_diag = _read_json(llm_diag_path)
    discovery = _read_json(discovery_path)
    universe_diag = _read_json(universe_diag_path)

    live_exec_presence = {
        "submitted": submitted_orders,
        "blocked": blocked_orders,
        "rejected": rejected_orders,
        "killed": killed_orders,
    }
    execution_topic_present = topic_counts.get("execution", 0) > 0
    sell_min_profit_bps = float(harmony.get("sell_min_profit_bps", 0.0) or 0.0)

    system_state = "OK"
    if profit_lock_sell_below_entry > 0 or profit_lock_sell_below_min_profit > 0:
        system_state = "FATAL"
    elif not execution_topic_present or (submitted_orders == 0 and (blocked_orders + rejected_orders) > 0):
        system_state = "BLOCKED"
    elif blocked_orders > submitted_orders or len(blocker_stats) > 0:
        system_state = "WARN"

    recommendation = {
        "parameter": "",
        "why": "",
        "safe_range": "",
    }
    if system_state in {"WARN", "BLOCKED"}:
        if blocker_stats.get("cooldown_active", {}).get("count", 0) > 0:
            recommendation = {
                "parameter": "AUTONOMOUS_ORDER_CADENCE_S",
                "why": "cooldown gate dominates intent throughput",
                "safe_range": "3-10",
            }
        elif blocker_stats.get("uncertainty_guard", {}).get("count", 0) > 0:
            recommendation = {
                "parameter": "AUTONOMOUS_UNCERTAINTY_THRESHOLD_BPS",
                "why": "uncertainty guard is blocking decisions",
                "safe_range": "85-110",
            }
        elif blocker_stats.get("confidence_guard", {}).get("count", 0) > 0:
            recommendation = {
                "parameter": "AUTONOMOUS_CONFIDENCE_THRESHOLD",
                "why": "confidence guard too strict for current market state",
                "safe_range": "0.45-0.60",
            }

    return {
        "run_dir": str(run_dir),
        "artifact_paths": {
            "audit_log": str(audit_path),
            "dashboard_snapshot": str(dashboard_path),
            "event_bus": str(event_bus_path),
            "harmony_report": str(harmony_path),
            "mastermind_status": str(mastermind_path),
            "governance_audit": str(governance_path),
            "llm_diagnostics": str(llm_diag_path),
            "market_discovery": str(discovery_path),
            "universe_diagnostics": str(universe_diag_path),
        },
        "event_window": {
            "requested": int(event_limit),
            "loaded": len(events),
            "top_event_types": dict(event_type_counts.most_common(20)),
            "top_reasons": dict(reason_counts.most_common(20)),
        },
        "order_stats": {
            "submitted_orders": submitted_orders,
            "blocked_orders": blocked_orders,
            "rejected_orders": rejected_orders,
            "killed_orders": killed_orders,
            "sell_submitted": sell_submitted,
            "buy_submitted": buy_submitted,
        },
        "blockers": dict(sorted(blocker_stats.items(), key=lambda x: x[1]["count"], reverse=True)),
        "hard_invariants": {
            "profit_lock_sell_below_entry": profit_lock_sell_below_entry,
            "profit_lock_sell_below_min_profit": profit_lock_sell_below_min_profit,
            "ok": profit_lock_sell_below_entry == 0 and profit_lock_sell_below_min_profit == 0,
        },
        "harmony": {
            "guards_mode": harmony.get("guards_mode"),
            "order_cadence_s": harmony.get("order_cadence_s"),
            "effective_min_order_quote": harmony.get("effective_min_order_quote"),
            "sell_min_profit_bps": sell_min_profit_bps,
            "sell_target_profit_bps": harmony.get("sell_target_profit_bps"),
            "sell_min_profit_ok": sell_min_profit_bps >= 120.0,
        },
        "dashboard_metrics": {
            "execution.intents_total": execution_group.get("intents_total"),
            "execution.orders_submitted_total": execution_group.get("orders_submitted_total"),
            "execution.orders_rejected_total": execution_group.get("orders_rejected_total"),
            "execution.fill_rate": execution_group.get("fill_rate"),
            "execution.reject_rate": execution_group.get("reject_rate"),
            "efficiency.tco_total_bps_rt": efficiency_group.get("tco_total_bps_rt"),
            "efficiency.cost_to_alpha_ratio": efficiency_group.get("cost_to_alpha_ratio"),
        },
        "event_bus_topics": {
            "market_data": int(topic_counts.get("market_data", 0)),
            "signal": int(topic_counts.get("signal", 0)),
            "decision": int(topic_counts.get("decision", 0)),
            "execution": int(topic_counts.get("execution", 0)),
            "risk": int(topic_counts.get("risk", 0)),
            "portfolio": int(topic_counts.get("portfolio", 0)),
            "all_topics": topic_counts,
        },
        "mastermind": {
            "exists": mastermind_path.exists(),
            "health": mastermind.get("health"),
            "guardrails": mastermind.get("guardrails"),
            "conflicts": mastermind.get("conflicts"),
            "overrides": mastermind.get("overrides"),
        },
        "provider_diagnostics": {
            "exists": llm_diag_path.exists(),
            "provider": llm_diag.get("provider"),
            "model": llm_diag.get("model"),
            "model_fallback": llm_diag.get("model_fallback"),
            "model_effective": llm_diag.get("model_effective"),
            "llm_enabled": llm_diag.get("llm_enabled"),
            "llm_augment_enabled": llm_diag.get("llm_augment_enabled"),
            "provider_health": llm_diag.get("provider_health"),
        },
        "xstocks": {
            "discovery_exists": discovery_path.exists(),
            "universe_diag_exists": universe_diag_path.exists(),
            "detected_symbols": discovery.get("xstocks_symbols", []),
            "detected_etf_symbols": discovery.get("xstocks_etf_symbols", []),
            "discovery_market_class_counts": discovery.get("market_class_counts", {}),
            "eligible_market_class_counts": universe_diag.get("eligible_market_class_counts", {}),
            "detected_market_class_counts": universe_diag.get("detected_market_class_counts", {}),
            "filter_reasons": universe_diag.get("filter_reasons", {}),
            "mixed_universe_mode": universe_diag.get("mixed_universe_mode"),
        },
        "execution_presence": {
            "live_exec_counts": live_exec_presence,
            "execution_topic_present": execution_topic_present,
        },
        "system_state": system_state,
        "optimization_recommendation": recommendation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run post-start runtime audit on latest run artifacts.")
    parser.add_argument("--runs-root", default="runs", help="Runs directory root.")
    parser.add_argument("--run-dir", default="", help="Explicit run directory.")
    parser.add_argument("--event-limit", type=int, default=3000, help="Number of audit events to analyze.")
    parser.add_argument("--output", default="", help="Optional output JSON file path.")
    args = parser.parse_args()

    runs_root = Path(args.runs_root).resolve()
    run_dir = Path(args.run_dir).resolve() if str(args.run_dir).strip() else _latest_run_dir(runs_root)
    report = run_audit(run_dir=run_dir, event_limit=max(100, int(args.event_limit)))

    if str(args.output).strip():
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["system_state"] == "FATAL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
