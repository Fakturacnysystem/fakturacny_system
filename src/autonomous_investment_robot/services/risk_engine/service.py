from __future__ import annotations

import time
from dataclasses import dataclass, field

from autonomous_investment_robot.config.settings import RiskLimits, UNSPECIFIED
from autonomous_investment_robot.services.policy.service import OrderIntent


@dataclass
class RiskState:
    kill_switch: bool = False
    safe_mode: bool = False
    weekly_stop: bool = False
    risk_mode: str = "normal"
    orders_in_current_min: int = 0
    rolling_returns: list[float] = field(default_factory=list)
    loss_streak: int = 0
    de_risk_multiplier: float = 1.0
    dd_throttle: float = 1.0
    last_crowding_score: float = 0.0
    last_crowding_level: str = "none"
    last_crowding_components: dict[str, float] = field(default_factory=dict)
    funding_budget_utilization: float = 0.0
    cooldown_steps_remaining: int = 0
    stable_steps: int = 0
    orders_window_started_monotonic: float = field(default_factory=time.monotonic)


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    adjusted_notional: float = 0.0
    flatten: bool = False
    details: dict = field(default_factory=dict)


class RiskEngineService:
    def __init__(self, limits: RiskLimits, safe_mode: bool = True) -> None:
        self.limits = limits
        self.state = RiskState(safe_mode=safe_mode, risk_mode="defensive" if safe_mode else "normal")

    def _set_risk_mode(self, mode: str) -> None:
        self.state.risk_mode = mode

    def _decision(self, allowed: bool, reason: str, adjusted_notional: float = 0.0, flatten: bool = False, details: dict | None = None) -> RiskDecision:
        payload = dict(details or {})
        payload.setdefault("risk_mode", self.state.risk_mode)
        return RiskDecision(allowed, reason, adjusted_notional=adjusted_notional, flatten=flatten, details=payload)

    def _refresh_order_window(self) -> None:
        now = time.monotonic()
        if now - self.state.orders_window_started_monotonic >= 60.0:
            self.state.orders_in_current_min = 0
            self.state.orders_window_started_monotonic = now

    def record_order_attempt(self) -> None:
        self._refresh_order_window()
        self.state.orders_in_current_min += 1

    def _limits_complete(self) -> bool:
        required = [
            self.limits.max_daily_loss_pct,
            self.limits.max_drawdown_pct,
            self.limits.max_position_notional,
            self.limits.max_exposure_notional,
            self.limits.max_orders_per_min,
            self.limits.leverage,
            self.limits.max_spread_bps,
            self.limits.min_depth_notional,
            self.limits.stale_data_seconds,
            self.limits.min_margin_buffer,
            self.limits.max_funding_cost_per_day,
            self.limits.max_oi_spike_pct,
            self.limits.max_liquidation_spike,
            self.limits.divergence_threshold_bps,
        ]
        return all(v != UNSPECIFIED for v in required)

    def _approx_cvar(self) -> float:
        if len(self.state.rolling_returns) < 5:
            return 0.0
        tails = sorted(self.state.rolling_returns)[: max(1, len(self.state.rolling_returns) // 20)]
        return abs(sum(tails) / len(tails)) * 100

    def _approx_stress_loss_pct(self, current_exposure: float, max_exposure_notional: float, spread_bps: float, oi_spike_pct: float) -> float:
        if max_exposure_notional <= 0:
            return 0.0
        exposure_util = max(0.0, min(2.0, current_exposure / max_exposure_notional))
        spread_shock = max(0.0, spread_bps) * 0.03
        oi_shock = max(0.0, oi_spike_pct) * 0.2
        base_gap = 1.0
        return exposure_util * (base_gap + spread_shock + oi_shock)

    def _update_dd_throttle(self, drawdown_pct: float) -> None:
        dd = abs(min(0.0, drawdown_pct))
        if dd < 2:
            self.state.dd_throttle = 1.0
        elif dd < 5:
            self.state.dd_throttle = 0.5
        elif dd < float(self.limits.max_drawdown_pct):
            self.state.dd_throttle = 0.25
        else:
            self.state.dd_throttle = 0.0

    def record_return(self, ret_pct: float) -> None:
        self.state.rolling_returns.append(ret_pct)
        self.state.rolling_returns = self.state.rolling_returns[-500:]
        self.state.loss_streak = self.state.loss_streak + 1 if ret_pct < 0 else 0
        if ret_pct >= 0:
            self.state.stable_steps += 1
        else:
            self.state.stable_steps = 0
        if self.state.loss_streak >= 3:
            self.state.de_risk_multiplier = 0.5

    def reset_periodic_limits(self, *, reset_orders: bool = True, reset_weekly: bool = False) -> None:
        if reset_orders:
            self.state.orders_in_current_min = 0
            self.state.orders_window_started_monotonic = time.monotonic()
        if reset_weekly:
            self.state.weekly_stop = False

    def _enter_cooldown(self, steps: int) -> None:
        self.state.cooldown_steps_remaining = max(self.state.cooldown_steps_remaining, max(0, int(steps)))

    def _tick_cooldown(self) -> None:
        if self.state.cooldown_steps_remaining > 0:
            self.state.cooldown_steps_remaining -= 1

    def _maybe_recover_from_dd_safe_mode(self) -> None:
        if self.state.kill_switch:
            return
        if not self.state.safe_mode:
            return
        if self.state.cooldown_steps_remaining > 0:
            return
        needed = max(1, int(getattr(self.limits, "drawdown_recovery_stable_steps", 5)))
        if self.state.stable_steps >= needed:
            self.state.safe_mode = False
            self._set_risk_mode("cautious")
            self.state.de_risk_multiplier = min(self.state.de_risk_multiplier, 0.5)

    def _crowding_thresholds(self) -> tuple[float, float, float]:
        extreme = (
            float(self.limits.crowding_score_extreme)
            if self.limits.crowding_score_extreme != UNSPECIFIED
            else float(self.limits.crowding_score_kill)
        )
        high = (
            float(self.limits.crowding_score_high)
            if self.limits.crowding_score_high != UNSPECIFIED
            else extreme * 0.75
        )
        medium = (
            float(self.limits.crowding_score_medium)
            if self.limits.crowding_score_medium != UNSPECIFIED
            else extreme * 0.5
        )
        return medium, high, extreme

    def _crowding_score(
        self,
        funding_rate_abs: float,
        oi_spike_pct: float,
        liquidation_spike: float,
        spread_bps: float,
        divergence_bps: float,
    ) -> tuple[float, dict[str, float]]:
        # z-like normalized components against configured risk limits / breakers
        c = {
            "funding": 0.0,
            "oi_impulse": 0.0,
            "liquidation_velocity": 0.0,
            "basis_widen": 0.0,
            "spread_widen": 0.0,
        }
        if self.limits.max_funding_cost_per_day != UNSPECIFIED:
            daily_budget = max(float(self.limits.max_funding_cost_per_day), 1e-9)
            c["funding"] = min(5.0, (funding_rate_abs * 100.0) / daily_budget * 4.0)
        if self.limits.max_oi_spike_pct != UNSPECIFIED:
            c["oi_impulse"] = min(5.0, max(0.0, oi_spike_pct) / max(float(self.limits.max_oi_spike_pct), 1e-9) * 3.0)
        if self.limits.max_liquidation_spike != UNSPECIFIED:
            c["liquidation_velocity"] = min(5.0, max(0.0, liquidation_spike) / max(float(self.limits.max_liquidation_spike), 1e-9) * 3.0)
        if self.limits.divergence_threshold_bps != UNSPECIFIED:
            c["basis_widen"] = min(5.0, max(0.0, divergence_bps) / max(float(self.limits.divergence_threshold_bps), 1e-9) * 3.0)
        if self.limits.max_spread_bps != UNSPECIFIED:
            c["spread_widen"] = min(5.0, max(0.0, spread_bps) / max(float(self.limits.max_spread_bps), 1e-9) * 3.0)
        score = c["funding"] + c["oi_impulse"] + c["liquidation_velocity"] + c["basis_widen"] + c["spread_widen"]
        return score, c

    def _crowding_level(self, score: float) -> str:
        medium, high, extreme = self._crowding_thresholds()
        if score >= extreme:
            return "extreme"
        if score >= high:
            return "high"
        if score >= medium:
            return "medium"
        return "low"

    def evaluate(
        self,
        intent: OrderIntent,
        current_exposure: float,
        drawdown_pct: float,
        daily_loss_pct: float,
        data_lag_seconds: float,
        spread_bps: float,
        depth_notional: float,
        reconciliation_ok: bool,
        funding_paid_pct: float,
        oi_spike_pct: float,
        liquidation_spike: float,
        divergence_bps: float,
        margin_buffer: float,
        funding_rate_abs: float = 0.0,
        weekly_loss_pct: float = 0.0,
        symbol_exposure: float | None = None,
        cluster_exposure: float | None = None,
        market_regime: str = "RANGE",
        liquidity_regime: str = "GOOD",
        is_reduce_only: bool = False,
        balance_state_ok: bool = True,
        api_error_burst: int = 0,
        order_reject_burst: int = 0,
        abnormal_latency_ms: float = 0.0,
        slippage_drift_bps: float = 0.0,
        unexplained_pnl_deviation_pct: float = 0.0,
        free_quote_reserve_pct: float | None = None,
        inventory_staleness_score: float | None = None,
        capital_release_pressure: float | None = None,
        round_trip_edge_bps: float | None = None,
        doctrine_action: str | None = None,
        doctrine_size_multiplier: float | None = None,
        doctrine_truth_strength: float | None = None,
        doctrine_survival_score: float | None = None,
        doctrine_robustness_score: float | None = None,
        doctrine_execution_survivability_score: float | None = None,
        doctrine_partial_truth_penalty: float | None = None,
    ) -> RiskDecision:
        self._refresh_order_window()
        if self.state.weekly_stop:
            self._set_risk_mode("flatten-only")
            return self._decision(False, "weekly_stop_safe_mode")
        if self.state.safe_mode:
            self._set_risk_mode("defensive")
            if self.state.cooldown_steps_remaining > 0:
                self._tick_cooldown()
                return self._decision(False, "cooldown_active")
            self._maybe_recover_from_dd_safe_mode()
            if self.state.safe_mode:
                return self._decision(False, "safe_mode_default")
        if not self._limits_complete():
            self._set_risk_mode("kill-switch")
            return self._decision(False, "risk_limits_unspecified")

        self._update_dd_throttle(drawdown_pct)
        if self.state.dd_throttle == 0.0:
            self.state.safe_mode = True
            self._set_risk_mode("defensive")
            self._enter_cooldown(getattr(self.limits, "drawdown_cooldown_steps", 10))
            return self._decision(False, "drawdown_safe_mode", flatten=True)

        self.state.last_crowding_score, self.state.last_crowding_components = self._crowding_score(
            funding_rate_abs, oi_spike_pct, liquidation_spike, spread_bps, divergence_bps
        )
        self.state.last_crowding_level = self._crowding_level(self.state.last_crowding_score)
        if self.state.last_crowding_level == "extreme":
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "crowding_radar_kill", flatten=True, details={"crowding_score": self.state.last_crowding_score, "crowding_level": self.state.last_crowding_level, "crowding_components": dict(self.state.last_crowding_components)})

        if not balance_state_ok:
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "balance_state_kill", flatten=True)
        doctrine_target = intent.why.get("doctrine_target", {}) if isinstance(intent.why, dict) and isinstance(intent.why.get("doctrine_target", {}), dict) else {}
        if (
            not is_reduce_only
            and str(intent.side).lower() == "sell"
            and bool(doctrine_target.get("long_only", False))
        ):
            self._set_risk_mode("flatten-only")
            return self._decision(
                False,
                "long_only_sell_block",
                details={"doctrine_target": doctrine_target},
            )
        if round_trip_edge_bps is not None and round_trip_edge_bps <= 0.0 and not is_reduce_only:
            self._set_risk_mode("degraded")
            return self._decision(
                False,
                "round_trip_profitability_guard",
                details={"round_trip_edge_bps": round_trip_edge_bps},
            )
        if doctrine_truth_strength is not None and doctrine_truth_strength < 0.35 and not is_reduce_only:
            self._set_risk_mode("flatten-only")
            return self._decision(
                False,
                "decision_doctrine_truth_weak",
                flatten=current_exposure > 0.0,
                details={"doctrine_truth_strength": doctrine_truth_strength},
            )
        if doctrine_partial_truth_penalty is not None and doctrine_partial_truth_penalty > 0.70 and not is_reduce_only:
            self._set_risk_mode("flatten-only")
            return self._decision(
                False,
                "decision_doctrine_partial_truth",
                flatten=current_exposure > 0.0,
                details={"doctrine_partial_truth_penalty": doctrine_partial_truth_penalty},
            )
        if doctrine_action in {"no_trade", "wait"} and not is_reduce_only:
            self._set_risk_mode("degraded" if doctrine_action == "wait" else "flatten-only")
            return self._decision(
                False,
                "decision_doctrine_no_trade" if doctrine_action == "no_trade" else "decision_doctrine_wait",
                flatten=current_exposure > 0.0 and doctrine_action == "no_trade" and (capital_release_pressure or 0.0) >= 0.5,
                details={
                    "doctrine_action": doctrine_action,
                    "doctrine_survival_score": doctrine_survival_score,
                    "doctrine_robustness_score": doctrine_robustness_score,
                },
            )
        if doctrine_execution_survivability_score is not None and doctrine_execution_survivability_score < 0.35 and not is_reduce_only:
            self._set_risk_mode("degraded")
            return self._decision(
                False,
                "decision_doctrine_execution_toxic",
                details={"doctrine_execution_survivability_score": doctrine_execution_survivability_score},
            )
        if doctrine_robustness_score is not None and doctrine_robustness_score < 0.35 and not is_reduce_only:
            self._set_risk_mode("degraded")
            return self._decision(
                False,
                "decision_doctrine_robustness_fail",
                details={"doctrine_robustness_score": doctrine_robustness_score},
            )
        if free_quote_reserve_pct is not None and free_quote_reserve_pct < 0.05 and not is_reduce_only:
            self._set_risk_mode("flatten-only")
            return self._decision(
                False,
                "free_quote_reserve_critical",
                flatten=current_exposure > 0.0 and (capital_release_pressure or 0.0) >= 0.5,
                details={
                    "free_quote_reserve_pct": free_quote_reserve_pct,
                    "capital_release_pressure": capital_release_pressure,
                },
            )
        if free_quote_reserve_pct is not None and free_quote_reserve_pct < 0.2 and not is_reduce_only:
            self._set_risk_mode("defensive")
        if (inventory_staleness_score or 0.0) >= 0.75 and (capital_release_pressure or 0.0) >= 0.5 and not is_reduce_only:
            self._set_risk_mode("flatten-only")
            return self._decision(
                False,
                "inventory_release_priority",
                flatten=current_exposure > 0.0,
                details={
                    "inventory_staleness_score": inventory_staleness_score,
                    "capital_release_pressure": capital_release_pressure,
                },
            )
        if (inventory_staleness_score or 0.0) >= 0.45 and not is_reduce_only:
            self._set_risk_mode("cautious")
        if api_error_burst >= 5:
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "api_error_burst_kill", flatten=True, details={"api_error_burst": api_error_burst})
        if order_reject_burst >= 5:
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "order_reject_burst_kill", flatten=True, details={"order_reject_burst": order_reject_burst})
        if unexplained_pnl_deviation_pct > 1.0:
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "pnl_deviation_kill", flatten=True, details={"unexplained_pnl_deviation_pct": unexplained_pnl_deviation_pct})
        if data_lag_seconds > float(self.limits.stale_data_seconds):
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "stale_data_kill", flatten=True)
        if divergence_bps > float(self.limits.divergence_threshold_bps):
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "cross_feed_divergence_kill", flatten=True)
        if spread_bps > float(self.limits.max_spread_bps):
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "spread_explosion_kill", flatten=True)
        if depth_notional < float(self.limits.min_depth_notional):
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "liquidity_hole_kill", flatten=True)
        if not reconciliation_ok:
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "reconciliation_kill", flatten=True)
        if self.limits.max_funding_cost_per_day != UNSPECIFIED:
            max_funding = max(float(self.limits.max_funding_cost_per_day), 1e-9)
            self.state.funding_budget_utilization = max(0.0, funding_paid_pct / max_funding)
            if funding_paid_pct > max_funding:
                self._set_risk_mode("defensive")
                return self._decision(False, "funding_cost_limit", details={"funding_budget_utilization": self.state.funding_budget_utilization})
        else:
            self.state.funding_budget_utilization = 0.0
        if oi_spike_pct > float(self.limits.max_oi_spike_pct) and liquidation_spike > float(self.limits.max_liquidation_spike):
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "squeeze_risk_kill", flatten=True)
        if margin_buffer < float(self.limits.min_margin_buffer):
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "margin_buffer_kill", flatten=True)
        if abnormal_latency_ms > 5000:
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(10)
            return self._decision(False, "abnormal_latency_kill", flatten=True, details={"abnormal_latency_ms": abnormal_latency_ms})

        if self.state.orders_in_current_min >= int(self.limits.max_orders_per_min):
            self._set_risk_mode("cautious")
            return self._decision(False, "orders_per_min_exceeded")
        if daily_loss_pct <= -float(self.limits.max_daily_loss_pct):
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._set_risk_mode("kill-switch")
            self._enter_cooldown(20)
            return self._decision(False, "daily_loss_kill", flatten=True)
        if self.limits.max_weekly_loss_pct != UNSPECIFIED and weekly_loss_pct <= -float(self.limits.max_weekly_loss_pct):
            self.state.kill_switch = True
            self.state.safe_mode = True
            self.state.weekly_stop = True
            self._set_risk_mode("flatten-only")
            self._enter_cooldown(100)
            return self._decision(False, "weekly_loss_stop", flatten=True)

        cvar = self._approx_cvar()
        if self.limits.cvar_limit_pct != UNSPECIFIED and cvar > float(self.limits.cvar_limit_pct):
            self._set_risk_mode("cautious")
            return self._decision(False, "cvar_guard")

        stress_limit = self.limits.stress_loss_limit_pct
        if stress_limit != UNSPECIFIED:
            stress_loss = self._approx_stress_loss_pct(
                current_exposure=current_exposure,
                max_exposure_notional=float(self.limits.max_exposure_notional),
                spread_bps=spread_bps,
                oi_spike_pct=oi_spike_pct,
            )
            if stress_loss > float(stress_limit):
                self._set_risk_mode("defensive")
                return self._decision(False, "stress_guard")

        if (market_regime in {"PANIC", "SQUEEZE_RISK"} or liquidity_regime == "THIN") and not is_reduce_only:
            self._set_risk_mode("flatten-only")
            return self._decision(False, "regime_open_block_reduce_only")
        if self.state.last_crowding_level == "high" and not is_reduce_only:
            self._set_risk_mode("flatten-only")
            return self._decision(False, "crowding_high_block_open_reduce_only", details={"crowding_score": self.state.last_crowding_score, "crowding_level": self.state.last_crowding_level, "crowding_components": dict(self.state.last_crowding_components)})

        adjusted = intent.target_notional * self.state.de_risk_multiplier * self.state.dd_throttle
        if doctrine_size_multiplier is not None:
            adjusted *= max(0.0, min(1.0, doctrine_size_multiplier))
        if self.state.last_crowding_level == "medium":
            self._set_risk_mode("cautious")
            adjusted *= 0.5
        if self.state.funding_budget_utilization >= 0.8 and not is_reduce_only:
            self._set_risk_mode("flatten-only")
            return self._decision(False, "funding_budget_throttle_block_open", details={"funding_budget_utilization": self.state.funding_budget_utilization})
        if self.state.funding_budget_utilization >= 0.6:
            self._set_risk_mode("cautious")
            adjusted *= 0.5
        if abnormal_latency_ms > 2000:
            self._set_risk_mode("degraded")
            adjusted *= 0.5
        if slippage_drift_bps > max(10.0, float(self.limits.max_spread_bps) * 0.5):
            self._set_risk_mode("degraded")
            adjusted *= 0.5
        if adjusted > float(self.limits.max_position_notional):
            return self._decision(False, "position_notional_exceeded")
        if current_exposure + adjusted > float(self.limits.max_exposure_notional):
            return self._decision(False, "exposure_notional_exceeded")
        if self.limits.max_symbol_exposure_notional != UNSPECIFIED:
            sx = current_exposure if symbol_exposure is None else symbol_exposure
            if sx + adjusted > float(self.limits.max_symbol_exposure_notional):
                return self._decision(False, "symbol_exposure_notional_exceeded")
        if self.limits.max_cluster_exposure_notional != UNSPECIFIED:
            cx = current_exposure if cluster_exposure is None else cluster_exposure
            if cx + adjusted > float(self.limits.max_cluster_exposure_notional):
                return self._decision(False, "cluster_exposure_notional_exceeded")
        if int(self.limits.leverage) != 0:
            self._set_risk_mode("kill-switch")
            return self._decision(False, "leverage_must_be_zero_in_mvp")

        if self.state.risk_mode == "normal":
            if abnormal_latency_ms > 2000 or slippage_drift_bps > 10:
                self._set_risk_mode("degraded")
            elif self.state.last_crowding_level == "medium" or self.state.funding_budget_utilization >= 0.6:
                self._set_risk_mode("cautious")
            else:
                self._set_risk_mode("normal")
        return self._decision(True, "passed", adjusted_notional=adjusted, details={"crowding_score": self.state.last_crowding_score, "crowding_level": self.state.last_crowding_level, "crowding_components": dict(self.state.last_crowding_components), "funding_budget_utilization": self.state.funding_budget_utilization, "api_error_burst": api_error_burst, "order_reject_burst": order_reject_burst, "abnormal_latency_ms": abnormal_latency_ms, "slippage_drift_bps": slippage_drift_bps, "balance_state_ok": balance_state_ok, "doctrine_action": doctrine_action, "doctrine_size_multiplier": doctrine_size_multiplier, "doctrine_truth_strength": doctrine_truth_strength, "doctrine_survival_score": doctrine_survival_score, "doctrine_robustness_score": doctrine_robustness_score, "doctrine_execution_survivability_score": doctrine_execution_survivability_score, "doctrine_partial_truth_penalty": doctrine_partial_truth_penalty})
