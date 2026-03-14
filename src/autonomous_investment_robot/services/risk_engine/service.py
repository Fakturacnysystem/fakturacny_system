from __future__ import annotations

from dataclasses import dataclass, field
import os
import time

from autonomous_investment_robot.config.settings import RiskLimits, UNSPECIFIED
from autonomous_investment_robot.services.policy.service import OrderIntent


@dataclass
class RiskState:
    kill_switch: bool = False
    safe_mode: bool = False
    safe_mode_steps: int = 0
    weekly_stop: bool = False
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
    shield_mode: str = ""
    shield_reason_codes: list[str] = field(default_factory=list)
    shield_source: str = ""
    shield_updated_ts: float = 0.0


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
        self.state = RiskState(safe_mode=safe_mode)

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

    def _rolling_vol_pct(self) -> float:
        vals = self.state.rolling_returns[-120:]
        if len(vals) < 5:
            return 0.0
        m = sum(vals) / len(vals)
        return (sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5

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
        if reset_weekly:
            self.state.weekly_stop = False

    def _enter_cooldown(self, steps: int) -> None:
        self.state.cooldown_steps_remaining = max(self.state.cooldown_steps_remaining, max(0, int(steps)))

    def _activate_safe_mode(self, cooldown_steps: int = 0) -> None:
        self.state.safe_mode = True
        self.state.safe_mode_steps = 0
        if cooldown_steps > 0:
            self._enter_cooldown(cooldown_steps)

    def _safe_mode_release_steps(self) -> int:
        return max(1, int(os.getenv("AUTONOMOUS_SAFE_MODE_RELEASE_STEPS", "8") or "8"))

    def _tick_cooldown(self) -> None:
        if self.state.cooldown_steps_remaining > 0:
            self.state.cooldown_steps_remaining -= 1

    def apply_shield_telemetry(
        self,
        *,
        mode: str,
        reason_codes: list[str] | tuple[str, ...] | None = None,
        source: str = "universe_shadow",
        hard_stop_forced: bool = False,
        no_trade_forced: bool = False,
        now_ts: float | None = None,
    ) -> None:
        mode_norm = str(mode or "").strip().lower()
        codes_raw = list(reason_codes or [])
        codes = [str(code) for code in codes_raw if str(code)]
        self.state.shield_mode = mode_norm
        self.state.shield_reason_codes = codes[:16]
        self.state.shield_source = str(source or "universe_shadow")
        self.state.shield_updated_ts = float(time.time() if now_ts is None else now_ts)
        if mode_norm == "hard_stop" or bool(hard_stop_forced):
            self.state.kill_switch = True
            self.state.safe_mode = True
            self._enter_cooldown(10)
        elif mode_norm == "observe_only" or bool(no_trade_forced):
            self.state.safe_mode = True

    def shield_telemetry_snapshot(self) -> dict[str, object]:
        return {
            "shield_mode": str(self.state.shield_mode),
            "shield_reason_codes": list(self.state.shield_reason_codes),
            "shield_source": str(self.state.shield_source),
            "shield_updated_ts": float(self.state.shield_updated_ts),
            "risk_safe_mode": bool(self.state.safe_mode),
            "risk_kill_switch": bool(self.state.kill_switch),
        }

    def _maybe_recover_from_dd_safe_mode(self) -> None:
        if self.state.kill_switch:
            return
        if not self.state.safe_mode:
            return
        if self.state.cooldown_steps_remaining > 0:
            return
        steps_needed = self._safe_mode_release_steps()
        stable_needed = max(1, int(getattr(self.limits, "drawdown_recovery_stable_steps", 5)))
        if self.state.safe_mode_steps >= steps_needed or self.state.stable_steps >= stable_needed:
            self.state.safe_mode = False
            self.state.safe_mode_steps = 0
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
        side: str = "buy",
    ) -> RiskDecision:
        if str(self.state.shield_mode).lower() == "hard_stop":
            self.state.kill_switch = True
            self.state.safe_mode = True
            if is_reduce_only:
                return RiskDecision(
                    True,
                    "shield_hard_stop_reduce_only",
                    adjusted_notional=max(0.0, float(intent.target_notional)),
                    details=self.shield_telemetry_snapshot(),
                )
            return RiskDecision(
                False,
                "shield_hard_stop",
                flatten=True,
                details=self.shield_telemetry_snapshot(),
            )
        if str(self.state.shield_mode).lower() == "observe_only" and not is_reduce_only:
            return RiskDecision(
                False,
                "shield_observe_only",
                flatten=False,
                details=self.shield_telemetry_snapshot(),
            )
        if self.state.weekly_stop and not is_reduce_only:
            return RiskDecision(False, "weekly_stop_safe_mode")
        if self.state.safe_mode:
            if is_reduce_only:
                # Safe-mode must not trap existing inventory; allow only exposure-reducing actions.
                self.state.safe_mode_steps += 1
                self._maybe_recover_from_dd_safe_mode()
            elif self.state.cooldown_steps_remaining > 0:
                self._tick_cooldown()
                return RiskDecision(False, "cooldown_active")
            else:
                self.state.safe_mode_steps += 1
                self._maybe_recover_from_dd_safe_mode()
            if self.state.safe_mode and not is_reduce_only:
                return RiskDecision(False, "safe_mode_default")
        if not self._limits_complete():
            return RiskDecision(False, "risk_limits_unspecified")

        self._update_dd_throttle(drawdown_pct)
        if self.state.dd_throttle == 0.0:
            self._activate_safe_mode(getattr(self.limits, "drawdown_cooldown_steps", 10))
            return RiskDecision(False, "drawdown_safe_mode", flatten=True)

        self.state.last_crowding_score, self.state.last_crowding_components = self._crowding_score(
            funding_rate_abs, oi_spike_pct, liquidation_spike, spread_bps, divergence_bps
        )
        self.state.last_crowding_level = self._crowding_level(self.state.last_crowding_score)
        if self.state.last_crowding_level == "extreme":
            self.state.kill_switch = True
            self._activate_safe_mode(10)
            return RiskDecision(
                False,
                "crowding_radar_kill",
                flatten=True,
                details={"crowding_score": self.state.last_crowding_score, "crowding_level": self.state.last_crowding_level, "crowding_components": dict(self.state.last_crowding_components)},
            )

        if data_lag_seconds > float(self.limits.stale_data_seconds):
            self.state.kill_switch = True
            self._activate_safe_mode(10)
            return RiskDecision(False, "stale_data_kill", flatten=True)
        if divergence_bps > float(self.limits.divergence_threshold_bps):
            self.state.kill_switch = True
            self._activate_safe_mode(10)
            return RiskDecision(False, "cross_feed_divergence_kill", flatten=True)
        if spread_bps > float(self.limits.max_spread_bps):
            self.state.kill_switch = True
            self._activate_safe_mode(10)
            return RiskDecision(False, "spread_explosion_kill", flatten=True)
        if depth_notional < float(self.limits.min_depth_notional):
            self.state.kill_switch = True
            self._activate_safe_mode(10)
            return RiskDecision(False, "liquidity_hole_kill", flatten=True)
        if not reconciliation_ok:
            self.state.kill_switch = True
            self._activate_safe_mode(10)
            return RiskDecision(False, "reconciliation_kill", flatten=True)
        if self.limits.max_funding_cost_per_day != UNSPECIFIED:
            max_funding = max(float(self.limits.max_funding_cost_per_day), 1e-9)
            self.state.funding_budget_utilization = max(0.0, funding_paid_pct / max_funding)
            if funding_paid_pct > max_funding:
                return RiskDecision(False, "funding_cost_limit", details={"funding_budget_utilization": self.state.funding_budget_utilization})
        else:
            self.state.funding_budget_utilization = 0.0
        if oi_spike_pct > float(self.limits.max_oi_spike_pct) and liquidation_spike > float(self.limits.max_liquidation_spike):
            self.state.kill_switch = True
            self._activate_safe_mode(10)
            return RiskDecision(False, "squeeze_risk_kill", flatten=True)
        if margin_buffer < float(self.limits.min_margin_buffer):
            self.state.kill_switch = True
            self._activate_safe_mode(10)
            return RiskDecision(False, "margin_buffer_kill", flatten=True)

        if self.state.orders_in_current_min >= int(self.limits.max_orders_per_min):
            return RiskDecision(False, "orders_per_min_exceeded")
        if daily_loss_pct <= -float(self.limits.max_daily_loss_pct):
            self.state.kill_switch = True
            self._activate_safe_mode(20)
            return RiskDecision(False, "daily_loss_kill", flatten=True)
        if self.limits.max_weekly_loss_pct != UNSPECIFIED and weekly_loss_pct <= -float(self.limits.max_weekly_loss_pct):
            self.state.kill_switch = True
            self._activate_safe_mode(100)
            self.state.weekly_stop = True
            return RiskDecision(False, "weekly_loss_stop", flatten=True)

        cvar_scale = 1.0
        cvar_min_samples = max(5, int(os.getenv("AUTONOMOUS_CVAR_MIN_SAMPLES", "20") or "20"))
        cvar = self._approx_cvar() if len(self.state.rolling_returns) >= cvar_min_samples else 0.0
        if self.limits.cvar_limit_pct != UNSPECIFIED:
            cvar_limit = max(float(self.limits.cvar_limit_pct), 1e-9)
            if cvar > cvar_limit * 1.5:
                return RiskDecision(False, "cvar_guard")
            if cvar > 0:
                cvar_scale = max(0.25, min(1.0, cvar_limit / cvar))

        stress_limit = self.limits.stress_loss_limit_pct
        if stress_limit != UNSPECIFIED:
            stress_loss = self._approx_stress_loss_pct(
                current_exposure=current_exposure,
                max_exposure_notional=float(self.limits.max_exposure_notional),
                spread_bps=spread_bps,
                oi_spike_pct=oi_spike_pct,
            )
            if stress_loss > float(stress_limit):
                return RiskDecision(False, "stress_guard")

        if (market_regime in {"PANIC", "SQUEEZE_RISK"} or liquidity_regime == "THIN") and not is_reduce_only:
            return RiskDecision(False, "regime_open_block_reduce_only")
        if self.state.last_crowding_level == "high" and not is_reduce_only:
            return RiskDecision(
                False,
                "crowding_high_block_open_reduce_only",
                details={"crowding_score": self.state.last_crowding_score, "crowding_level": self.state.last_crowding_level, "crowding_components": dict(self.state.last_crowding_components)},
            )

        adjusted = intent.target_notional * self.state.de_risk_multiplier * self.state.dd_throttle
        vol_scale = 1.0
        if self.limits.target_portfolio_vol != UNSPECIFIED:
            target_vol = max(float(self.limits.target_portfolio_vol), 1e-9)
            current_vol = self._rolling_vol_pct()
            if current_vol > 0:
                vol_scale = max(0.25, min(2.0, target_vol / current_vol))
            else:
                vol_scale = 1.5
            adjusted *= vol_scale
        adjusted *= cvar_scale
        if self.state.last_crowding_level == "medium":
            adjusted *= 0.5
        if self.state.funding_budget_utilization >= 0.8 and not is_reduce_only:
            return RiskDecision(False, "funding_budget_throttle_block_open", details={"funding_budget_utilization": self.state.funding_budget_utilization})
        if self.state.funding_budget_utilization >= 0.6:
            adjusted *= 0.5
        reduce_side = str(side).lower() == "sell" or is_reduce_only
        if not reduce_side:
            max_pos = float(self.limits.max_position_notional)
            if max_pos > 0.0:
                adjusted = min(adjusted, max_pos)
            max_exp = float(self.limits.max_exposure_notional)
            if max_exp > 0.0:
                adjusted = min(adjusted, max(0.0, max_exp - current_exposure))
            if self.limits.max_symbol_exposure_notional != UNSPECIFIED:
                sx = current_exposure if symbol_exposure is None else symbol_exposure
                adjusted = min(adjusted, max(0.0, float(self.limits.max_symbol_exposure_notional) - sx))
            if self.limits.max_cluster_exposure_notional != UNSPECIFIED:
                cx = current_exposure if cluster_exposure is None else cluster_exposure
                adjusted = min(adjusted, max(0.0, float(self.limits.max_cluster_exposure_notional) - cx))
            if adjusted <= 0.0:
                return RiskDecision(False, "exposure_notional_exceeded")
        else:
            projected_exposure = max(0.0, current_exposure - adjusted)
            if projected_exposure > float(self.limits.max_exposure_notional):
                return RiskDecision(False, "exposure_notional_exceeded")
        if int(self.limits.leverage) != 0:
            return RiskDecision(False, "leverage_must_be_zero_in_mvp")

        self.state.orders_in_current_min += 1
        return RiskDecision(
            True,
            "passed",
            adjusted_notional=adjusted,
            details={
                "crowding_score": self.state.last_crowding_score,
                "crowding_level": self.state.last_crowding_level,
                "crowding_components": dict(self.state.last_crowding_components),
                "funding_budget_utilization": self.state.funding_budget_utilization,
                "portfolio_scale_vol": vol_scale,
                "portfolio_scale_cvar": cvar_scale,
            },
        )
