#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict, deque
import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping


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

CANONICAL_TOPICS: tuple[str, ...] = ("market_data", "signal", "decision", "execution", "risk", "portfolio")
TOPIC_ALIASES: dict[str, str] = {
    "market_data": "market_data",
    "market": "market_data",
    "md": "market_data",
    "signal": "signal",
    "signals": "signal",
    "decision": "decision",
    "intent": "decision",
    "execution": "execution",
    "exec": "execution",
    "fill": "execution",
    "fills": "execution",
    "order": "execution",
    "orders": "execution",
    "risk": "risk",
    "portfolio": "portfolio",
    "position": "portfolio",
    "positions": "portfolio",
    "account": "portfolio",
}
LEGACY_STREAM_TOPIC_MAP: dict[str, str] = {
    "orders": "execution",
    "fills": "execution",
    "risk": "risk",
    "compliance": "risk",
    "positions": "portfolio",
    "portfolio": "portfolio",
    "market": "market_data",
    "market_data": "market_data",
    "signal": "signal",
    "signals": "signal",
    "decision": "decision",
    "intent": "decision",
}
LEGACY_EVENT_TYPE_TOPIC_MAP: dict[str, str] = {
    "ORDER_INTENT": "decision",
    "STRATEGYPROPOSALEVENT": "decision",
    "ORDER_ACK": "execution",
    "ORDER_EVENT": "execution",
    "ORDEREVENT": "execution",
    "FILL": "execution",
    "FILLEVENT": "execution",
    "EXECUTIONPLANEVENT": "execution",
    "RISK_EVENT": "risk",
    "RISKEVENT": "risk",
    "POSITION_SNAPSHOT": "portfolio",
    "ACCOUNTSNAPSHOTEVENT": "portfolio",
}
EVENT_DOMAIN_TOPIC_MAP: dict[str, str] = {
    "market": "market_data",
    "execution": "execution",
    "risk": "risk",
    "account": "portfolio",
    "portfolio": "portfolio",
    "strategy": "signal",
    "mission": "decision",
    "regime": "signal",
}
PROFIT_LOCK_REASONS: tuple[str, ...] = (
    "profit_lock_sell_below_entry",
    "profit_lock_sell_below_min_profit",
)
PROFIT_LOCK_VIOLATION_EVENT_TYPES: set[str] = {
    "policy_violation_fatal",
    "invariant_violation",
    "hard_invariant_violation",
}
PROFIT_LOCK_VIOLATION_STATUSES: set[str] = {
    "submitted",
    "filled",
    "filled_maker",
    "filled_taker_fallback",
    "submitted_limit_floor",
    "submitted_ladder",
    "executed",
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


def _event_bus_paths(run_dir: Path) -> list[Path]:
    root = run_dir / "event_bus.jsonl"
    fallback = run_dir / "universe_events" / "event_bus.jsonl"
    out: list[Path] = []
    for path in (root, fallback):
        if path.exists():
            out.append(path)
    return out


def _canonical_topic(topic: str) -> str:
    return TOPIC_ALIASES.get(str(topic or "").strip().lower(), "")


def _mapped_topics_from_payload(payload: Mapping[str, Any]) -> set[str]:
    topics: set[str] = set()
    metadata = payload.get("metadata", {})
    if isinstance(metadata, Mapping):
        legacy_stream = str(metadata.get("legacy_stream", "") or "").strip().lower()
        if legacy_stream:
            mapped = LEGACY_STREAM_TOPIC_MAP.get(legacy_stream, "")
            if mapped:
                topics.add(mapped)
        legacy_event_type = str(metadata.get("legacy_event_type", "") or "").strip().upper()
        if legacy_event_type:
            mapped = LEGACY_EVENT_TYPE_TOPIC_MAP.get(legacy_event_type, "")
            if mapped:
                topics.add(mapped)
    event_type = str(payload.get("event_type", "") or "").strip().upper()
    if event_type:
        mapped = LEGACY_EVENT_TYPE_TOPIC_MAP.get(event_type, "")
        if mapped:
            topics.add(mapped)
    event_domain = str(payload.get("event_domain", "") or "").strip().lower()
    if event_domain:
        mapped = EVENT_DOMAIN_TOPIC_MAP.get(event_domain, "")
        if mapped:
            topics.add(mapped)
    return topics


def _resolved_audit_topics(row: Mapping[str, Any]) -> set[str]:
    resolved: set[str] = set()
    direct_topic = _canonical_topic(str(row.get("topic", "") or ""))
    if direct_topic:
        resolved.add(direct_topic)

    payload = row.get("payload", {})
    if isinstance(payload, Mapping):
        resolved.update(_mapped_topics_from_payload(payload))
    return resolved


def _load_event_bus_topics(paths: list[Path], *, line_limit: int) -> tuple[dict[str, int], dict[str, Any]]:
    canonical: Counter[str] = Counter()
    diagnostics: dict[str, Any] = {"sources": {}, "paths_used": [str(path) for path in paths]}
    max_rows = max(1, int(line_limit))
    for path in paths:
        if not path.exists():
            continue
        raw_topics: Counter[str] = Counter()
        normalized_topics: Counter[str] = Counter()
        lines_seen = 0
        rows: deque[str] = deque(maxlen=max_rows)
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                lines_seen += 1
                rows.append(line)
        parsed_rows = 0
        for line in rows:
            row_text = line.strip()
            if not row_text:
                continue
            try:
                row = json.loads(row_text)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            parsed_rows += 1
            raw_topic = str(row.get("topic", "") or "").strip()
            if raw_topic:
                raw_topics[raw_topic] += 1
            for topic in _resolved_audit_topics(row):
                normalized_topics[topic] += 1
                canonical[topic] += 1
        diagnostics["sources"][str(path)] = {
            "lines_seen": int(lines_seen),
            "lines_considered": int(min(lines_seen, max_rows)),
            "parsed_rows": int(parsed_rows),
            "truncated_to_line_limit": bool(lines_seen > max_rows),
            "raw_topics": dict(raw_topics),
            "normalized_topics": dict(normalized_topics),
        }
    return dict(canonical), diagnostics


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


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def _extract_event_file_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    submitted = 0
    blocked = 0
    rejected = 0
    killed = 0
    buy_submitted = 0
    sell_submitted = 0
    for row in rows:
        payload = row.get("payload", {})
        if not isinstance(payload, Mapping):
            payload = {}
        event_type = str(row.get("event_type", payload.get("event_type", "")) or "").strip().upper()
        status = str(payload.get("status", "") or "").strip().lower()
        side = str(payload.get("side", "") or "").strip().lower()
        if event_type == "ORDER_INTENT" or status in {"submitted", "filled_maker", "filled_taker_fallback", "submitted_limit_floor", "submitted_ladder"}:
            submitted += 1
            if side == "buy":
                buy_submitted += 1
            elif side == "sell":
                sell_submitted += 1
            continue
        if status in {"blocked", "skipped"}:
            blocked += 1
            continue
        if event_type in {"ORDER_REJECT", "ORDER_ERROR"} or status in {"rejected", "error"}:
            rejected += 1
            continue
        if event_type in {"ORDER_KILLED", "ORDER_FATAL", "KILL"} or status in {"killed", "fatal"}:
            killed += 1
            continue
    return {
        "submitted_orders": submitted,
        "blocked_orders": blocked,
        "rejected_orders": rejected,
        "killed_orders": killed,
        "buy_submitted": buy_submitted,
        "sell_submitted": sell_submitted,
    }


def _merge_order_evidence(*, audit_counts: Mapping[str, int], event_counts: Mapping[str, int]) -> tuple[dict[str, int], str]:
    audit_activity = sum(int(audit_counts.get(k, 0)) for k in ("submitted_orders", "blocked_orders", "rejected_orders", "killed_orders")) > 0
    event_activity = sum(int(event_counts.get(k, 0)) for k in ("submitted_orders", "blocked_orders", "rejected_orders", "killed_orders")) > 0
    if audit_activity and event_activity:
        source = "merged"
    elif audit_activity:
        source = "audit_log"
    elif event_activity:
        source = "events_files"
    else:
        source = "none"

    if source == "audit_log":
        merged = {k: int(audit_counts.get(k, 0)) for k in ("submitted_orders", "blocked_orders", "rejected_orders", "killed_orders", "buy_submitted", "sell_submitted")}
    elif source == "events_files":
        merged = {k: int(event_counts.get(k, 0)) for k in ("submitted_orders", "blocked_orders", "rejected_orders", "killed_orders", "buy_submitted", "sell_submitted")}
    elif source == "merged":
        merged = {
            "submitted_orders": max(int(audit_counts.get("submitted_orders", 0)), int(event_counts.get("submitted_orders", 0))),
            "blocked_orders": max(int(audit_counts.get("blocked_orders", 0)), int(event_counts.get("blocked_orders", 0))),
            "rejected_orders": max(int(audit_counts.get("rejected_orders", 0)), int(event_counts.get("rejected_orders", 0))),
            "killed_orders": max(int(audit_counts.get("killed_orders", 0)), int(event_counts.get("killed_orders", 0))),
            "buy_submitted": max(int(audit_counts.get("buy_submitted", 0)), int(event_counts.get("buy_submitted", 0))),
            "sell_submitted": max(int(audit_counts.get("sell_submitted", 0)), int(event_counts.get("sell_submitted", 0))),
        }
    else:
        merged = {
            "submitted_orders": 0,
            "blocked_orders": 0,
            "rejected_orders": 0,
            "killed_orders": 0,
            "buy_submitted": 0,
            "sell_submitted": 0,
        }
    return merged, source


def _extract_bridge_flag(payload: Mapping[str, Any], *keys: str) -> tuple[bool, bool]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value, True
        if isinstance(value, Mapping):
            for nested in ("enabled", "active", "ready", "ok"):
                nested_value = value.get(nested)
                if isinstance(nested_value, bool):
                    return nested_value, True
    return False, False


def run_audit(*, run_dir: Path, event_limit: int = 3000) -> dict[str, Any]:
    audit_path = run_dir / "audit.log"
    dashboard_path = run_dir / "dashboard_snapshot.json"
    event_bus_path = run_dir / "event_bus.jsonl"
    event_bus_fallback_path = run_dir / "universe_events" / "event_bus.jsonl"
    event_bus_paths = _event_bus_paths(run_dir)
    harmony_path = run_dir / "harmony_report.json"
    mastermind_path = run_dir / "mastermind_status.json"
    governance_path = run_dir / "governance_audit.jsonl"
    llm_diag_path = run_dir / "llm_self_improvement_diagnostics.json"
    discovery_path = run_dir / "market_discovery.json"
    universe_diag_path = run_dir / "universe_diagnostics.json"
    distributed_diag_path = run_dir / "distributed_runtime_diagnostics.json"
    orders_path = run_dir / "events_orders.jsonl"
    fills_path = run_dir / "events_fills.jsonl"

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
    audit_order_stats = {
        "submitted_orders": submitted_orders,
        "blocked_orders": blocked_orders,
        "rejected_orders": rejected_orders,
        "killed_orders": killed_orders,
        "buy_submitted": buy_submitted,
        "sell_submitted": sell_submitted,
    }

    order_rows = _tail_jsonl(orders_path, event_limit)
    fill_rows = _tail_jsonl(fills_path, event_limit)
    event_file_stats = _extract_event_file_counts(order_rows)
    merged_order_stats, order_stats_source = _merge_order_evidence(audit_counts=audit_order_stats, event_counts=event_file_stats)
    order_stats_sources = {
        "audit_log": dict(audit_order_stats),
        "events_files": {
            **event_file_stats,
            "fills_observed": int(len(fill_rows)),
            "orders_rows_observed": int(len(order_rows)),
        },
    }

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

    profit_lock_guard_hits: Counter[str] = Counter()
    profit_lock_violation_hits: Counter[str] = Counter()
    for ev in events:
        reason = str(ev["reason"] or "").strip()
        if reason not in PROFIT_LOCK_REASONS:
            continue
        event_type = str(ev["event_type"] or "").strip().lower()
        status = str(ev["status"] or "").strip().lower()
        if event_type in PROFIT_LOCK_VIOLATION_EVENT_TYPES or status in PROFIT_LOCK_VIOLATION_STATUSES:
            profit_lock_violation_hits[reason] += 1
        else:
            # Expected behavior: safety doctrine prevented unsafe sell execution.
            profit_lock_guard_hits[reason] += 1
    profit_lock_sell_below_entry = int(profit_lock_violation_hits.get("profit_lock_sell_below_entry", 0))
    profit_lock_sell_below_min_profit = int(profit_lock_violation_hits.get("profit_lock_sell_below_min_profit", 0))

    harmony = _read_json(harmony_path)
    dashboard = _read_json(dashboard_path)
    groups = dashboard.get("groups", {}) if isinstance(dashboard.get("groups"), dict) else {}
    execution_group = groups.get("execution", {}) if isinstance(groups.get("execution"), dict) else {}
    efficiency_group = groups.get("efficiency", {}) if isinstance(groups.get("efficiency"), dict) else {}
    topic_counts, event_bus_diag = _load_event_bus_topics(event_bus_paths, line_limit=max(100, int(event_limit)))
    mastermind = _read_json(mastermind_path)
    llm_diag = _read_json(llm_diag_path)
    discovery = _read_json(discovery_path)
    universe_diag = _read_json(universe_diag_path)
    distributed_diag = _read_json(distributed_diag_path)

    shared_infra = distributed_diag.get("shared_infra", {})
    if not isinstance(shared_infra, Mapping):
        shared_infra = {}
    shared_redis = shared_infra.get("redis", {})
    if not isinstance(shared_redis, Mapping):
        shared_redis = {}
    shared_postgres = shared_infra.get("postgres", {})
    if not isinstance(shared_postgres, Mapping):
        shared_postgres = {}
    redis_backend = str(
        shared_redis.get("backend", distributed_diag.get("redis_backend", "")) or ""
    ).strip().lower()
    postgres_enabled, postgres_declared = _extract_bridge_flag(shared_postgres, "enabled")
    if not postgres_declared:
        postgres_enabled, postgres_declared = _extract_bridge_flag(distributed_diag, "postgres_enabled")
    compute_bridge_enabled, compute_bridge_declared = _extract_bridge_flag(distributed_diag, "compute_bridge_enabled")
    remote_advisory_ready, advisory_declared = _extract_bridge_flag(distributed_diag, "advisory_remote_ready")
    execution_bridge_enabled, execution_bridge_declared = _extract_bridge_flag(universe_diag, "execution_plan_bridge")
    distributed_bridge_enabled, distributed_bridge_declared = _extract_bridge_flag(universe_diag, "distributed_bridge")
    storm_enabled, storm_declared = _extract_bridge_flag(universe_diag, "storm")

    runtime_bridges = {
        "redis_streams": {
            "declared": bool(redis_backend),
            "active": bool(redis_backend not in {"", "local", "none"}),
            "backend": redis_backend or "unspecified",
            "reason": "configured" if redis_backend else "missing_backend_declaration",
        },
        "postgres_mirror": {
            "declared": bool(postgres_declared),
            "active": bool(postgres_enabled),
            "reason": "configured" if postgres_declared else "missing_enablement_flag",
        },
        "compute_bridge": {
            "declared": bool(compute_bridge_declared),
            "active": bool(compute_bridge_enabled),
            "reason": "configured" if compute_bridge_declared else "missing_enablement_flag",
        },
        "remote_advisory": {
            "declared": bool(advisory_declared),
            "active": bool(remote_advisory_ready),
            "reason": "configured" if advisory_declared else "missing_enablement_flag",
        },
        "execution_plan_bridge": {
            "declared": bool(execution_bridge_declared),
            "active": bool(execution_bridge_enabled),
            "reason": "configured" if execution_bridge_declared else "missing_enablement_flag",
        },
        "distributed_bridge": {
            "declared": bool(distributed_bridge_declared),
            "active": bool(distributed_bridge_enabled),
            "reason": "configured" if distributed_bridge_declared else "missing_enablement_flag",
        },
        "storm_model_bridge": {
            "declared": bool(storm_declared),
            "active": bool(storm_enabled),
            "reason": "configured" if storm_declared else "missing_enablement_flag",
        },
    }

    live_exec_presence = {
        "submitted": int(merged_order_stats.get("submitted_orders", 0)),
        "blocked": int(merged_order_stats.get("blocked_orders", 0)),
        "rejected": int(merged_order_stats.get("rejected_orders", 0)),
        "killed": int(merged_order_stats.get("killed_orders", 0)),
    }
    execution_topic_present = topic_counts.get("execution", 0) > 0
    sell_min_profit_bps = float(harmony.get("sell_min_profit_bps", 0.0) or 0.0)
    hard_sell_floor_bps = float(harmony.get("hard_sell_floor_bps", 30.0) or 30.0)

    system_state = "OK"
    if profit_lock_sell_below_entry > 0 or profit_lock_sell_below_min_profit > 0:
        system_state = "FATAL"
    elif not execution_topic_present or (
        int(merged_order_stats.get("submitted_orders", 0)) == 0
        and (int(merged_order_stats.get("blocked_orders", 0)) + int(merged_order_stats.get("rejected_orders", 0))) > 0
    ):
        system_state = "BLOCKED"
    elif int(merged_order_stats.get("blocked_orders", 0)) > int(merged_order_stats.get("submitted_orders", 0)) or len(blocker_stats) > 0:
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
    rollback_reason_codes: list[str] = []
    if system_state == "FATAL":
        rollback_reason_codes.append("system_state_fatal")
    if not execution_topic_present:
        rollback_reason_codes.append("execution_topic_missing")
    if not (profit_lock_sell_below_entry == 0 and profit_lock_sell_below_min_profit == 0):
        rollback_reason_codes.append("hard_invariants_failed")
    rollback_validated = bool(
        system_state != "FATAL"
        and execution_topic_present
        and profit_lock_sell_below_entry == 0
        and profit_lock_sell_below_min_profit == 0
    )
    rollback_artifact_id = _stable_hash(
        {
            "type": "runtime_audit_rollback_dry_run",
            "run_dir": str(run_dir),
            "system_state": system_state,
            "order_stats": live_exec_presence,
            "hard_invariants": {
                "profit_lock_sell_below_entry": profit_lock_sell_below_entry,
                "profit_lock_sell_below_min_profit": profit_lock_sell_below_min_profit,
            },
            "execution_topic_present": execution_topic_present,
        }
    )

    return {
        "run_dir": str(run_dir),
        "artifact_paths": {
            "audit_log": str(audit_path),
            "dashboard_snapshot": str(dashboard_path),
            "event_bus": str(event_bus_path),
            "event_bus_fallback": str(event_bus_fallback_path),
            "harmony_report": str(harmony_path),
            "mastermind_status": str(mastermind_path),
            "governance_audit": str(governance_path),
            "llm_diagnostics": str(llm_diag_path),
            "market_discovery": str(discovery_path),
            "universe_diagnostics": str(universe_diag_path),
            "distributed_runtime_diagnostics": str(distributed_diag_path),
            "orders_events": str(orders_path),
            "fills_events": str(fills_path),
        },
        "event_window": {
            "requested": int(event_limit),
            "loaded": len(events),
            "top_event_types": dict(event_type_counts.most_common(20)),
            "top_reasons": dict(reason_counts.most_common(20)),
        },
        "order_stats": {
            "submitted_orders": int(merged_order_stats.get("submitted_orders", 0)),
            "blocked_orders": int(merged_order_stats.get("blocked_orders", 0)),
            "rejected_orders": int(merged_order_stats.get("rejected_orders", 0)),
            "killed_orders": int(merged_order_stats.get("killed_orders", 0)),
            "sell_submitted": int(merged_order_stats.get("sell_submitted", 0)),
            "buy_submitted": int(merged_order_stats.get("buy_submitted", 0)),
        },
        "order_stats_source": order_stats_source,
        "order_stats_sources": order_stats_sources,
        "order_evidence_consistency": {
            "submitted_delta_abs": abs(
                int(audit_order_stats.get("submitted_orders", 0)) - int(event_file_stats.get("submitted_orders", 0))
            ),
            "rejected_delta_abs": abs(
                int(audit_order_stats.get("rejected_orders", 0)) - int(event_file_stats.get("rejected_orders", 0))
            ),
            "killed_delta_abs": abs(
                int(audit_order_stats.get("killed_orders", 0)) - int(event_file_stats.get("killed_orders", 0))
            ),
            "blocked_delta_abs": abs(
                int(audit_order_stats.get("blocked_orders", 0)) - int(event_file_stats.get("blocked_orders", 0))
            ),
        },
        "blockers": dict(sorted(blocker_stats.items(), key=lambda x: x[1]["count"], reverse=True)),
        "hard_invariants": {
            "profit_lock_sell_below_entry": profit_lock_sell_below_entry,
            "profit_lock_sell_below_min_profit": profit_lock_sell_below_min_profit,
            "profit_lock_guard_hits": {
                "profit_lock_sell_below_entry": int(profit_lock_guard_hits.get("profit_lock_sell_below_entry", 0)),
                "profit_lock_sell_below_min_profit": int(profit_lock_guard_hits.get("profit_lock_sell_below_min_profit", 0)),
            },
            "ok": profit_lock_sell_below_entry == 0 and profit_lock_sell_below_min_profit == 0,
        },
        "harmony": {
            "guards_mode": harmony.get("guards_mode"),
            "order_cadence_s": harmony.get("order_cadence_s"),
            "effective_min_order_quote": harmony.get("effective_min_order_quote"),
            "sell_min_profit_bps": sell_min_profit_bps,
            "sell_target_profit_bps": harmony.get("sell_target_profit_bps"),
            "hard_sell_floor_bps": hard_sell_floor_bps,
            "sell_min_profit_ok": sell_min_profit_bps >= hard_sell_floor_bps,
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
            "source_diagnostics": event_bus_diag,
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
        "runtime_bridges": runtime_bridges,
        "system_state": system_state,
        "optimization_recommendation": recommendation,
        "rollback_dry_run": {
            "validated": rollback_validated,
            "artifact_id": rollback_artifact_id,
            "reason_codes": rollback_reason_codes,
        },
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
