from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChaosScenarioResult:
    name: str
    kill: bool
    safe_mode: bool
    flatten: bool
    cooldown: bool
    reason: str


def apply_flash_crash(rows: list[dict], drop_pct: float = 0.2) -> list[dict]:
    shocked = [r.copy() for r in rows]
    if len(shocked) > 2:
        idx = len(shocked) // 2
        shocked[idx]["price"] *= (1 - drop_pct)
    return shocked


def run_paper_chaos_suite(risk_engine, execution_service, intent) -> list[ChaosScenarioResult]:
    # Deterministic scenarios expected to force fail-closed behavior.
    scenarios = [
        ("flash_crash_gap", dict(data_lag_seconds=0.0, spread_bps=80.0, depth_notional=10_000.0, reconciliation_ok=True, funding_paid_pct=0.0, oi_spike_pct=0.0, liquidation_spike=0.0, divergence_bps=0.0, margin_buffer=3.0)),
        ("feed_outage", dict(data_lag_seconds=999.0, spread_bps=1.0, depth_notional=10_000.0, reconciliation_ok=True, funding_paid_pct=0.0, oi_spike_pct=0.0, liquidation_spike=0.0, divergence_bps=0.0, margin_buffer=3.0)),
        ("divergence_spike", dict(data_lag_seconds=0.0, spread_bps=1.0, depth_notional=10_000.0, reconciliation_ok=True, funding_paid_pct=0.0, oi_spike_pct=0.0, liquidation_spike=0.0, divergence_bps=999.0, margin_buffer=3.0)),
        ("funding_shock", dict(data_lag_seconds=0.0, spread_bps=15.0, depth_notional=10_000.0, reconciliation_ok=True, funding_paid_pct=0.2, oi_spike_pct=6.0, liquidation_spike=150_000.0, divergence_bps=40.0, margin_buffer=3.0, funding_rate_abs=0.01)),
        ("recon_mismatch", dict(data_lag_seconds=0.0, spread_bps=1.0, depth_notional=10_000.0, reconciliation_ok=False, funding_paid_pct=0.0, oi_spike_pct=0.0, liquidation_spike=0.0, divergence_bps=0.0, margin_buffer=3.0)),
    ]
    results: list[ChaosScenarioResult] = []
    for name, kwargs in scenarios:
        if hasattr(risk_engine, "state"):
            risk_engine.state.safe_mode = False
            risk_engine.state.kill_switch = False
            if hasattr(risk_engine.state, "cooldown_steps_remaining"):
                risk_engine.state.cooldown_steps_remaining = 0
            if hasattr(risk_engine, "reset_periodic_limits"):
                risk_engine.reset_periodic_limits(reset_orders=True)
        d = risk_engine.evaluate(
            intent,
            current_exposure=100.0,
            drawdown_pct=0.0,
            daily_loss_pct=0.0,
            **kwargs,
        )
        flatten = bool(getattr(d, "flatten", False))
        if flatten:
            execution_service.flatten_worst_case(intent.symbol, 100.0)
        results.append(
            ChaosScenarioResult(
                name=name,
                kill=bool(getattr(risk_engine.state, "kill_switch", False)),
                safe_mode=bool(getattr(risk_engine.state, "safe_mode", False)),
                flatten=flatten,
                cooldown=bool(getattr(risk_engine.state, "cooldown_steps_remaining", 0) > 0),
                reason=getattr(d, "reason", ""),
            )
        )
    return results


def summarize_chaos_suite(results: list[ChaosScenarioResult]) -> dict[str, object]:
    passed = all(r.safe_mode and r.flatten and (r.kill or r.cooldown) for r in results)
    return {
        "passed": passed,
        "scenarios": [r.__dict__ for r in results],
        "count": len(results),
    }
