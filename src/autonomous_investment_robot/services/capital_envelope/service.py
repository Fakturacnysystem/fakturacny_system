from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.config.settings import UNSPECIFIED
from autonomous_investment_robot.core.contracts import CapitalEnvelopeReport


class CapitalEnvelopeService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def summarize(
        self,
        *,
        reserve_state: Any | None = None,
        inventory_state: Any | None = None,
        portfolio_allocation: Any | None = None,
        execution_plan: Any | None = None,
        execution_result: Any | None = None,
    ) -> dict[str, dict[str, Any]]:
        reserve_fraction = max(0.0, min(0.95, float(self.settings.capital_envelope.reserve_fraction)))
        policy_budget = max(0.0, float(self.settings.policy.base_risk_budget))
        max_exposure = self.settings.risk.max_exposure_notional
        max_exposure_value = policy_budget if max_exposure == UNSPECIFIED else max(0.0, float(max_exposure))
        pair_cap = min(max_exposure_value, float(self.settings.capital_envelope.max_pair_exposure_notional))

        total_equity = max(0.0, float(getattr(reserve_state, "total_capital", 0.0) or 0.0))
        free_quote_balance = max(
            0.0,
            float(
                getattr(reserve_state, "quote_free_balance", None)
                if reserve_state is not None and getattr(reserve_state, "quote_free_balance", None) is not None
                else getattr(reserve_state, "free_quote", 0.0)
            ),
        )
        forced_reserve = max(
            float(getattr(reserve_state, "reserve_floor_quote", 0.0) or 0.0),
            total_equity * reserve_fraction,
        )
        gross_open = max(0.0, float(getattr(inventory_state, "gross_open_notional", 0.0) or 0.0))
        plan_target = max(0.0, float(getattr(execution_plan, "target_notional", 0.0) or 0.0))
        deployable_capital = max(0.0, min(free_quote_balance if free_quote_balance > 0.0 else total_equity, total_equity - forced_reserve))
        live_deployment_cap = max(0.0, min(deployable_capital, max_exposure_value))
        playbook_level_cap = max(0.0, live_deployment_cap * float(self.settings.capital_envelope.max_playbook_heat))
        regime_level_cap = max(0.0, live_deployment_cap * float(self.settings.capital_envelope.max_regime_heat))
        reserved_capital = max(0.0, total_equity - deployable_capital)
        observed_heat_notional = gross_open + plan_target
        portfolio_heat = 0.0 if total_equity <= 0.0 else min(1.5, observed_heat_notional / max(total_equity, 1.0))
        idle_capital = max(0.0, deployable_capital - plan_target)
        weighted_age_minutes = max(0.0, float(getattr(inventory_state, "weighted_age_seconds", 0.0) or 0.0) / 60.0)
        stale_pressure = max(0.0, float(getattr(inventory_state, "stale_inventory_score", 0.0) or 0.0))
        capital_efficiency_score = max(
            0.0,
            min(
                1.0,
                (
                    (0.0 if total_equity <= 0.0 else min(1.0, observed_heat_notional / max(total_equity, 1.0))) * 0.45
                    + (1.0 - min(1.0, weighted_age_minutes / max(float(self.settings.capital_envelope.max_capital_lock_time_min), 1.0))) * 0.20
                    + (1.0 - stale_pressure) * 0.20
                    + (0.15 if execution_result is not None else 0.0)
                ),
            ),
        )
        dead_capital_pressure = max(
            0.0,
            min(
                1.0,
                idle_capital / max(total_equity, 1.0) * 0.55
                + stale_pressure * 0.30
                + max(0.0, weighted_age_minutes / max(float(self.settings.capital_envelope.max_capital_lock_time_min), 1.0) - 0.5) * 0.15,
            ),
        )
        report = CapitalEnvelopeReport(
            ts=datetime.now(timezone.utc),
            total_equity=total_equity,
            free_quote_balance=free_quote_balance,
            reserved_capital=reserved_capital,
            deployable_capital=deployable_capital,
            live_deployment_cap=live_deployment_cap,
            pair_level_cap=pair_cap,
            playbook_level_cap=playbook_level_cap,
            regime_level_cap=regime_level_cap,
            portfolio_heat=portfolio_heat,
            idle_capital=idle_capital,
            forced_reserve=forced_reserve,
            capital_efficiency_score=capital_efficiency_score,
            capital_lock_time_minutes=weighted_age_minutes,
            dead_capital_pressure=dead_capital_pressure,
            reasons=[
                *(list(getattr(reserve_state, "reasons", []) or []) if reserve_state is not None else []),
                "reserve_floor_binding" if forced_reserve >= deployable_capital and total_equity > 0.0 else "",
                "idle_capital_high" if dead_capital_pressure >= 0.5 else "",
            ],
            metadata={
                "gross_open_notional": gross_open,
                "planned_notional": plan_target,
                "recommended_notional": float(getattr(portfolio_allocation, "recommended_notional", 0.0) or 0.0),
                "stale_inventory_score": stale_pressure,
            },
        )
        payload = asdict(report)
        payload["reasons"] = [reason for reason in payload["reasons"] if reason]
        utilization_pct = 0.0 if total_equity <= 0.0 else observed_heat_notional / max(total_equity, 1.0) * 100.0
        return {
            "capital_envelope_summary": payload,
            "capital_utilization_diagnostics": {
                "ts": payload["ts"],
                "capital_utilization_pct": utilization_pct,
                "target_capital_utilization_min": float(self.settings.capital_envelope.target_capital_utilization_min) * 100.0,
                "idle_capital_pct": 0.0 if total_equity <= 0.0 else idle_capital / max(total_equity, 1.0) * 100.0,
                "planned_notional": plan_target,
                "gross_open_notional": gross_open,
            },
            "portfolio_heat_summary": {
                "ts": payload["ts"],
                "portfolio_heat": portfolio_heat,
                "max_portfolio_heat": float(self.settings.capital_envelope.max_portfolio_heat),
                "max_regime_heat": float(self.settings.capital_envelope.max_regime_heat),
                "max_playbook_heat": float(self.settings.capital_envelope.max_playbook_heat),
            },
            "capital_efficiency_report": {
                "ts": payload["ts"],
                "capital_efficiency_score": capital_efficiency_score,
                "capital_efficiency_min_score": float(self.settings.capital_envelope.capital_efficiency_min_score),
                "capital_lock_time_minutes": weighted_age_minutes,
                "max_capital_lock_time_min": float(self.settings.capital_envelope.max_capital_lock_time_min),
            },
            "capital_utilization_report": {
                "ts": payload["ts"],
                "idle_capital": idle_capital,
                "idle_capital_alert_threshold": float(self.settings.capital_envelope.idle_capital_alert_threshold),
                "deployable_capital": deployable_capital,
                "forced_reserve": forced_reserve,
            },
            "deployment_efficiency_report": {
                "ts": payload["ts"],
                "live_deployment_cap": live_deployment_cap,
                "pair_level_cap": pair_cap,
                "playbook_level_cap": playbook_level_cap,
                "regime_level_cap": regime_level_cap,
            },
            "dead_capital_pressure_report": {
                "ts": payload["ts"],
                "dead_capital_pressure": dead_capital_pressure,
                "idle_capital": idle_capital,
                "weighted_age_minutes": weighted_age_minutes,
                "stale_inventory_score": stale_pressure,
            },
        }

