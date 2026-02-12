from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IncidentAction:
    action: str
    reason: str


class IncidentPolicy:
    def evaluate(self, metrics: dict[str, float]) -> IncidentAction | None:
        if metrics.get("data_lag_seconds", 0) > 60:
            return IncidentAction("safe_mode", "DataStale")
        if metrics.get("orders_rejected_total", 0) > 20:
            return IncidentAction("cooldown", "RejectStorm")
        if metrics.get("reconciliation_mismatch_total", 0) > 0:
            return IncidentAction("flatten", "ReconciliationMismatch")
        if metrics.get("slippage_bps", 0) > 20:
            return IncidentAction("reduce_size", "HighSlippage")
        return None


class Notifier:
    def notify(self, title: str, body: str) -> None:
        # stub for telegram/signal integration
        print(f"NOTIFY {title}: {body}")
