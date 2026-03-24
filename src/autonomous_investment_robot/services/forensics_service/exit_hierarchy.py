from __future__ import annotations

from autonomous_investment_robot.core.contracts import TradeForensicsContext


def classify_exit_hierarchy(context: TradeForensicsContext) -> tuple[int, str]:
    exit_reason = str(context.metadata.get("exit_reason", "")).lower()
    risk_reason = str(context.metadata.get("risk_reason", "")).lower()
    lifecycle = context.lifecycle or {}
    reconciliation = context.reconciliation or {}
    quantum = context.quantum_context or {}
    capital_release = context.capital_release_context or {}

    if any(token in exit_reason for token in {"risk", "kill", "flatten"}) or any(token in risk_reason for token in {"kill", "drawdown", "risk"}):
        return 1, "forced_risk_exit"
    if reconciliation and (not bool(reconciliation.get("ok", True)) or str(reconciliation.get("action", "")) in {"flatten_only", "halt", "halt_and_flatten"}):
        return 2, "reconciliation_or_truth_degradation_exit"
    if str(lifecycle.get("state", "")).lower() in {"orphaned", "stuck", "cancel_rejected", "timed_out"}:
        return 3, "lifecycle_anomaly_exit"
    if bool(capital_release.get("allowed", False)) and str(capital_release.get("action", "")) == "partial_exit":
        return 4, "stale_inventory_release_exit"
    if "profit_lock" in exit_reason or bool(context.metadata.get("profit_locking", False)):
        return 5, "profit_locking_partial_exit"
    if any(token in exit_reason for token in {"scenario", "branch_invalidation"}) or float(quantum.get("no_trade_probability", 0.0)) >= 0.6:
        return 6, "scenario_collapse_exit"
    return 7, "tactical_discretionary_exit"
