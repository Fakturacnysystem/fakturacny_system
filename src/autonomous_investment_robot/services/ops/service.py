from __future__ import annotations

import json
import math
from hashlib import sha256
from pathlib import Path
from typing import Any


class OpsService:
    def __init__(self, run_dir: str) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.metrics: dict[str, Any] = {}

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
        }
        payload = {
            "groups": {g: {k: self.metrics.get(k, 0.0) for k in keys} for g, keys in groups.items()},
            "metrics_count": len(self.metrics),
        }
        p = self.run_dir / "dashboard_snapshot.json"
        p.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        return str(p)
