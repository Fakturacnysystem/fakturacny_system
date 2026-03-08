from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    if out != out:  # NaN guard
        return float(default)
    return out


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return str(default)
    return str(value)


def build_evidence_snapshot(
    *,
    ts: float,
    symbol: str,
    mode: str,
    guards_mode: str,
    universe: dict[str, Any] | None = None,
    market: dict[str, Any] | None = None,
    model: dict[str, Any] | None = None,
    route: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
    balances: dict[str, Any] | None = None,
    kpis: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    m = dict(market or {})
    u = dict(universe or {})
    mdl = dict(model or {})
    rt = dict(route or {})
    c = dict(constraints or {})
    b = dict(balances or {})
    k = dict(kpis or {})
    d = dict(decision or {})
    return {
        "ts": _safe_float(ts),
        "symbol": _safe_str(symbol).upper(),
        "mode": _safe_str(mode),
        "guards_mode": _safe_str(guards_mode),
        "universe": {
            "active_count": _safe_int(u.get("active_count"), 0),
            "active_symbols_sample": u.get("active_symbols_sample", []) if isinstance(u.get("active_symbols_sample"), list) else [],
        },
        "market": {
            "bid": _safe_float(m.get("bid")),
            "ask": _safe_float(m.get("ask")),
            "mid": _safe_float(m.get("mid")),
            "spread_bps": _safe_float(m.get("spread_bps")),
            "depth_notional": _safe_float(m.get("depth_notional")),
            "stale_s": _safe_float(m.get("stale_s")),
            "latency_ms": _safe_float(m.get("latency_ms")),
            "toxicity_score": _safe_float(m.get("toxicity_score")),
        },
        "model": {
            "regime": _safe_str(mdl.get("regime")),
            "liquidity_regime": _safe_str(mdl.get("liquidity_regime")),
            "mu": _safe_float(mdl.get("mu")),
            "confidence": _safe_float(mdl.get("confidence")),
            "model_version": _safe_str(mdl.get("model_version")),
        },
        "route": {
            "venue_selected": _safe_str(rt.get("venue_selected")),
            "route_order_type": _safe_str(rt.get("route_order_type")),
            "expected_fill_prob": _safe_float(rt.get("expected_fill_prob")),
            "expected_total_cost_bps": _safe_float(rt.get("expected_total_cost_bps")),
            "expected_net_edge_bps": _safe_float(rt.get("expected_net_edge_bps")),
            "ranked": rt.get("ranked", []) if isinstance(rt.get("ranked"), list) else [],
        },
        "constraints": {
            "exchange_min_notional_quote": _safe_float(c.get("exchange_min_notional_quote")),
            "user_min_notional_quote": _safe_float(c.get("user_min_notional_quote")),
            "effective_min_notional_quote": _safe_float(c.get("effective_min_notional_quote")),
            "price_precision": _safe_int(c.get("price_precision"), 8),
            "qty_precision": _safe_int(c.get("qty_precision"), 8),
        },
        "balances": {
            "quote_free": _safe_float(b.get("quote_free")),
            "base_free": _safe_float(b.get("base_free")),
            "sellable_quote": _safe_float(b.get("sellable_quote")),
        },
        "kpis": {
            "fill_rate": _safe_float(k.get("fill_rate")),
            "reject_rate": _safe_float(k.get("reject_rate")),
            "rate_limit_events": _safe_float(k.get("rate_limit_events")),
            "cost_to_alpha_ratio_modeled": _safe_float(k.get("cost_to_alpha_ratio_modeled")),
            "tco_total_bps_rt": _safe_float(k.get("tco_total_bps_rt")),
        },
        "decision": {
            "action": _safe_str(d.get("action", "none")),
            "reason": _safe_str(d.get("reason")),
            "notional_quote": _safe_float(d.get("notional_quote")),
            "cooldown_remaining_s": _safe_float(d.get("cooldown_remaining_s")),
            "gated_by": d.get("gated_by", []) if isinstance(d.get("gated_by"), list) else [],
        },
    }


@dataclass
class DecisionTickEmitter:
    interval_s: float = 60.0
    per_symbol: bool = True
    _last_bucket_by_key: dict[str, int] = field(default_factory=dict)

    def should_emit(self, *, symbol: str, now_ts: float) -> bool:
        interval = max(1.0, float(self.interval_s))
        bucket = int(float(now_ts) // interval)
        key = str(symbol).upper() if self.per_symbol else "__global__"
        if self._last_bucket_by_key.get(key) == bucket:
            return False
        self._last_bucket_by_key[key] = bucket
        return True
