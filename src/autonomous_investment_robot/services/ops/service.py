from __future__ import annotations

import json
import math
import os
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from autonomous_investment_robot.services.distributed import RedisAuditPublisher


class OpsService:
    def __init__(self, run_dir: str) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.metrics: dict[str, Any] = {}
        self._memory_trace_path = self.run_dir / "universe_memory_trace.jsonl"
        self._memory_trace_max_rows = max(1, int(float(os.getenv("AUTONOMOUS_UNIVERSE_MEMORY_TRACE_MAX_ROWS", "4000") or "4000")))
        self._audit_stream_publisher = RedisAuditPublisher.from_env(run_id=str(self.run_dir))
        health = self._audit_stream_publisher.health().to_dict()
        self.metrics["distributed_audit_stream_enabled"] = 1.0 if bool(health.get("enabled")) else 0.0
        self.metrics["distributed_audit_stream_ok"] = 1.0 if bool(health.get("ok")) else 0.0
        self.metrics["universe_memory_trace_rows"] = 0.0
        self.metrics["universe_memory_trace_last_has_packet"] = 0.0

    def set_metric(self, name: str, value: Any) -> None:
        self.metrics[name] = value

    def inc_metric(self, name: str, value: float = 1.0) -> None:
        current = self.metrics.get(name, 0.0)
        if not isinstance(current, (int, float)):
            current = 0.0
        self.metrics[name] = float(current) + value

    def emit_alert(self, name: str, reason: str) -> None:
        self.audit_event("alert", {"name": name, "reason": reason})

    def audit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        p = self.run_dir / "audit.log"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event_type": event_type, "payload": payload}, sort_keys=True) + "\n")
        symbol = str(payload.get("symbol", "") or "")
        market_class = str(payload.get("market_class", "") or "")
        if not symbol and isinstance(payload.get("decision"), dict):
            decision = payload.get("decision", {})
            if isinstance(decision, dict):
                symbol = str(decision.get("symbol", "") or symbol)
                market_class = str(decision.get("market_class", "") or market_class)
        _ = self._audit_stream_publisher.publish(
            event_type=event_type,
            payload=payload,
            symbol=symbol,
            market_class=market_class,
        )
        if str(os.getenv("AUTONOMOUS_DISTRIBUTED_ENABLED", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}:
            h = self._audit_stream_publisher.health()
            self.metrics["distributed_audit_stream_ok"] = 1.0 if h.ok else 0.0

    def track_config(self, config_data: dict[str, Any]) -> str:
        serialized = json.dumps(config_data, sort_keys=True)
        cfg_hash = sha256(serialized.encode("utf-8")).hexdigest()
        p = self.run_dir / "config_history.jsonl"
        prev = None
        if p.exists():
            lines = [x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
            if lines:
                prev = json.loads(lines[-1])
        diff = {"changed": True if prev is None else prev.get("hash") != cfg_hash}
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"hash": cfg_hash, "config": config_data, "diff": diff}, sort_keys=True) + "\n")
        return cfg_hash

    def export_prometheus(self) -> str:
        p = self.run_dir / "metrics.prom"
        lines: list[str] = []
        for k, v in sorted(self.metrics.items()):
            if not isinstance(v, (int, float)):
                continue
            val = float(v)
            if math.isnan(val) or math.isinf(val):
                continue
            lines.append(f"{k} {val}")
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(p)

    def record_universe_memory_trace(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        row = dict(payload or {})
        ts = row.get("ts", 0.0)
        try:
            ts = float(ts)
        except Exception:
            ts = 0.0
        trace = {
            "ts": ts,
            "symbol": str(row.get("symbol", "") or "").upper(),
            "action": str(row.get("action", "none") or "none"),
            "reason": str(row.get("reason", "") or ""),
            "packet_id": str(row.get("packet_id", "") or ""),
            "mission": str(row.get("mission", "") or ""),
            "shield_mode": str(row.get("shield_mode", "") or ""),
            "execution_abort": bool(row.get("execution_abort", False)),
            "gated_by": list(row.get("gated_by", [])) if isinstance(row.get("gated_by", []), list) else [],
            "bounded_retention_status": str(row.get("bounded_retention_status", "") or ""),
            "bounded_retention_within_limit": bool(row.get("bounded_retention_within_limit", False)),
            "errors_count": max(0, int(float(row.get("errors_count", 0) or 0))),
            "world_state_source": str(row.get("world_state_source", "") or ""),
            "world_state_available": bool(row.get("world_state_available", False)),
            "world_state_graph_available": bool(row.get("world_state_graph_available", False)),
            "world_state_safe_to_trade": bool(row.get("world_state_safe_to_trade", False)),
            "world_state_stale_domains": (
                [str(item) for item in row.get("world_state_stale_domains", []) if str(item)]
                if isinstance(row.get("world_state_stale_domains", []), list)
                else []
            ),
            "world_state_stale_critical_domains": (
                [str(item) for item in row.get("world_state_stale_critical_domains", []) if str(item)]
                if isinstance(row.get("world_state_stale_critical_domains", []), list)
                else []
            ),
        }
        with self._memory_trace_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(trace, sort_keys=True) + "\n")
        lines = [line for line in self._memory_trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(lines) > self._memory_trace_max_rows:
            lines = lines[-self._memory_trace_max_rows :]
            self._memory_trace_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.metrics["universe_memory_trace_rows"] = float(len(lines))
        self.metrics["universe_memory_trace_last_has_packet"] = 1.0 if bool(trace["packet_id"]) else 0.0
        return trace

    def export_dashboard_snapshot(self) -> str:
        groups = {
            "risk": ["drawdown", "exposure_notional", "kill_switch_state", "reconciliation_mismatch_total", "risk_reject_total"],
            "costs": ["cost_total_bps", "slippage_bps", "funding_paid", "funding_budget_utilization"],
            "policy": ["crowding_score", "crowding_level"],
            "performance": ["pnl", "net_pnl_after_fees", "max_drawdown", "sharpe", "sortino"],
            "execution": [
                "orders_submitted_total",
                "orders_rejected_total",
                "fill_rate",
                "reject_rate",
                "maker_fill_rate",
                "rate_limit_events",
                "slippage_vs_model_bps",
                "intents_total",
                "executions_attempted_total",
                "executions_submitted_total",
                "fills_confirmed_total",
                "expected_total_cost_bps",
                "expected_net_edge_bps",
                "expected_fill_prob",
                "route_order_type",
                "venue_selected",
            ],
            "portfolio": ["portfolio_symbol_score", "adaptive_size_scale", "portfolio_scan_symbols", "portfolio_universe_size"],
            "execution_qa": [
                "implementation_shortfall_bps",
                "execution_shortfall_bps",
                "latency_p50_ms",
                "latency_p95_ms",
                "latency_p99_ms",
                "latency_bucket_fast",
                "latency_bucket_medium",
                "latency_bucket_slow",
                "fill_probability",
            ],
            "attribution": [
                "signal_edge_gross_quote",
                "execution_cost_quote",
                "alpha_net_quote",
                "signal_edge_gross_bps",
                "execution_cost_bps",
                "alpha_net_bps",
            ],
            "model_ops": ["champion_score", "challenger_score", "active_model_challenger"],
            "market_data": ["feed_quality_primary", "feed_quality_selected", "feed_fallback_active", "clock_drift_ms"],
            "treasury": ["treasury_throttle", "treasury_reserve_ratio", "treasury_margin_buffer"],
            "governance": ["governance_allowed", "governance_block_total"],
            "reliability": ["bus_delivery_ok", "bus_delivery_failed"],
            "efficiency": [
                "tco_total_bps_rt",
                "cost_to_alpha_ratio",
                "cost_to_alpha_ratio_modeled",
                "execution_cost_bps",
                "execution_shortfall_bps",
                "realized_slippage_bps",
                "live_vs_backtest_divergence_bps",
                "net_pnl_after_fees",
            ],
            "self_tuner": [
                "self_tuner_size_scale",
                "self_tuner_min_order_notional_quote",
                "self_tuner_submitted_rate",
                "self_tuner_insufficient_rate",
                "self_tuner_min_order_block_rate",
                "self_tuner_rate_limit_rate",
                "self_tuner_window_events",
            ],
            "microstructure": [
                "toxicity_score",
                "toxicity_throttle",
                "toxicity_freeze_events",
            ],
            "decision": [
                "decision_tick_total",
                "decision_tick_skip_total",
                "decision_tick_last_reason",
                "active_universe_count",
            ],
            "universe_memory": [
                "universe_memory_trace_rows",
                "universe_memory_trace_last_has_packet",
            ],
            "harmony": [
                "harmony_order_cadence_s",
                "harmony_effective_min_order_quote",
                "harmony_sell_min_profit_bps",
                "harmony_guards_mode",
            ],
            "tp": [
                "tp_hard_min_net_bps",
                "tp_effective_target_net_bps",
                "tp_effective_target_gross_bps",
                "tp_blocks_total",
                "modeled_cost_bps",
                "min_sell_price_hard",
                "target_sell_price",
                "tp_ladder_hold_s_last",
            ],
            "diagnosis": [
                "diagnosis_reason_count",
                "diagnosis_last_reason",
            ],
            "market_watch": [
                "market_watch_trend_30s_bps",
                "market_watch_trend_2m_bps",
                "market_watch_trend_10m_bps",
                "market_watch_realized_vol_2m",
                "market_watch_realized_vol_10m",
                "market_watch_confidence",
                "spread_spike_active",
            ],
            "world_state": [
                "world_state_available",
                "world_state_graph_available",
                "world_state_safe_to_trade",
                "world_state_stale_domains_count",
                "world_state_stale_critical_domains_count",
                "world_state_freshness_max_s",
                "world_state_market_stale_s",
            ],
        }
        payload = {
            "groups": {g: {k: self.metrics.get(k, 0.0) for k in keys} for g, keys in groups.items()},
            "metrics_count": len(self.metrics),
        }
        p = self.run_dir / "dashboard_snapshot.json"
        p.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        return str(p)
