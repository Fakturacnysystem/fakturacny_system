from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass
class IncidentAction:
    action: str
    reason: str


@dataclass
class IncidentExecutionResult:
    action: str
    reason: str
    kill: bool
    safe_mode: bool
    flatten_requested: bool
    cooldown_applied: bool


class IncidentPolicy:
    def evaluate(self, metrics: dict[str, float]) -> IncidentAction | None:
        if metrics.get("data_lag_seconds", 0) > 60:
            return IncidentAction("kill_safe_mode_no_open", "DataStale")
        if metrics.get("cross_feed_divergence_bps", 0) > metrics.get("cross_feed_divergence_limit_bps", 30):
            return IncidentAction("kill_flatten_cooldown", "CrossFeedDivergence")
        if metrics.get("reconciliation_mismatch_total", 0) > 0:
            return IncidentAction("kill_flatten_stop", "ReconciliationMismatch")
        if metrics.get("auth_errors_total", 0) > 0:
            return IncidentAction("kill_flatten_cooldown", "AuthError")
        if metrics.get("orders_rejected_total", 0) > 20:
            return IncidentAction("kill_flatten_cooldown", "RejectStorm")
        if metrics.get("order_latency_ms_p99", 0) > metrics.get("order_latency_limit_ms", 3000):
            return IncidentAction("kill_flatten_cooldown", "AbnormalLatency")
        if metrics.get("ws_disconnects_5m", 0) > 10:
            return IncidentAction("no_open_until_stable", "WsDisconnectStorm")
        if metrics.get("liquidation_spike", 0) > metrics.get("max_liquidation_spike", 0):
            return IncidentAction("risk_throttle_or_exit", "LiquidationSpike")
        if metrics.get("oi_spike_pct", 0) > metrics.get("max_oi_spike_pct", 0):
            return IncidentAction("risk_throttle_or_exit", "OpenInterestSpike")
        if metrics.get("crowding_level", 0) >= 4 or metrics.get("crowding_score", 0) >= metrics.get("crowding_score_extreme", 1e9):
            return IncidentAction("kill_flatten_cooldown", "CrowdingExtreme")
        if metrics.get("crowding_level", 0) >= 3:
            return IncidentAction("no_open_until_stable", "CrowdingHigh")
        if metrics.get("funding_budget_utilization", 0) >= 1.0:
            return IncidentAction("exit_or_block_open", "FundingBudgetExceeded")
        if metrics.get("funding_budget_utilization", 0) >= 0.8:
            return IncidentAction("risk_throttle_or_exit", "FundingBudgetHigh")
        if metrics.get("slippage_bps", 0) > 20:
            return IncidentAction("reduce_size", "HighSlippage")
        return None


class IncidentResponder:
    def execute(self, incident: IncidentAction, *, risk_engine=None, live_service=None) -> IncidentExecutionResult:
        action = incident.action
        kill = False
        safe_mode = False
        flatten_requested = False
        cooldown_applied = False

        if risk_engine is not None and hasattr(risk_engine, "state"):
            if any(x in action for x in ["kill", "no_open", "stop"]):
                risk_engine.state.safe_mode = True
                safe_mode = True
            if "kill" in action:
                setattr(risk_engine.state, "kill_switch", True)
                kill = True
            if "cooldown" in action and hasattr(risk_engine, "_enter_cooldown"):
                risk_engine._enter_cooldown(10)  # noqa: SLF001 - explicit ops automation hook
                cooldown_applied = True
            if "flatten" in action:
                flatten_requested = True

        if live_service is not None:
            if any(x in action for x in ["kill", "stop"]):
                if hasattr(live_service, "request_kill"):
                    live_service.request_kill(f"incident:{incident.reason}")
                else:
                    live_service.killed = True
                    live_service.safe_mode = True
                kill = True
                safe_mode = True
                cooldown_applied = True
            if "flatten" in action and hasattr(live_service, "flatten_all_positions"):
                flatten_requested = True

        return IncidentExecutionResult(
            action=incident.action,
            reason=incident.reason,
            kill=kill,
            safe_mode=safe_mode,
            flatten_requested=flatten_requested,
            cooldown_applied=cooldown_applied,
        )


class Notifier:
    def notify(self, title: str, body: str) -> None:
        # Optional Telegram notifier. Defaults to noop if env is missing.
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        signal_recipient = os.getenv("SIGNAL_RECIPIENT", "")
        if not token or not chat_id:
            if signal_recipient:
                print(f"SIGNAL {signal_recipient} {title}: {body}")
            return
        print(f"TELEGRAM {chat_id} {title}: {body}")
