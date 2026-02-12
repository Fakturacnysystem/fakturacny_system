from __future__ import annotations

from dataclasses import dataclass, field

from autonomous_investment_robot.config.settings import RiskLimits, UNSPECIFIED
from autonomous_investment_robot.services.policy.service import OrderIntent


@dataclass
class RiskState:
    kill_switch: bool = False
    safe_mode: bool = False
    orders_in_current_min: int = 0
    rolling_returns: list[float] = field(default_factory=list)
    loss_streak: int = 0
    de_risk_multiplier: float = 1.0
    dd_throttle: float = 1.0
    last_crowding_score: float = 0.0


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    adjusted_notional: float = 0.0
    flatten: bool = False


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
        if self.state.loss_streak >= 3:
            self.state.de_risk_multiplier = 0.5

    def _crowding_score(self, funding_rate_abs: float, oi_spike_pct: float, liquidation_spike: float, spread_bps: float, divergence_bps: float) -> float:
        return funding_rate_abs * 10000 + max(0.0, oi_spike_pct) + (liquidation_spike / 50000) + spread_bps / 10 + divergence_bps / 10

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
    ) -> RiskDecision:
        if self.state.safe_mode:
            return RiskDecision(False, "safe_mode_default")
        if not self._limits_complete():
            return RiskDecision(False, "risk_limits_unspecified")

        self._update_dd_throttle(drawdown_pct)
        if self.state.dd_throttle == 0.0:
            self.state.kill_switch = True
            return RiskDecision(False, "drawdown_safe_mode", flatten=True)

        self.state.last_crowding_score = self._crowding_score(funding_rate_abs, oi_spike_pct, liquidation_spike, spread_bps, divergence_bps)
        if self.state.last_crowding_score > float(self.limits.crowding_score_kill):
            self.state.kill_switch = True
            return RiskDecision(False, "crowding_radar_kill", flatten=True)

        if data_lag_seconds > float(self.limits.stale_data_seconds):
            self.state.kill_switch = True
            return RiskDecision(False, "stale_data_kill", flatten=True)
        if divergence_bps > float(self.limits.divergence_threshold_bps):
            self.state.kill_switch = True
            return RiskDecision(False, "cross_feed_divergence_kill", flatten=True)
        if spread_bps > float(self.limits.max_spread_bps):
            self.state.kill_switch = True
            return RiskDecision(False, "spread_explosion_kill", flatten=True)
        if depth_notional < float(self.limits.min_depth_notional):
            self.state.kill_switch = True
            return RiskDecision(False, "liquidity_hole_kill", flatten=True)
        if not reconciliation_ok:
            self.state.kill_switch = True
            return RiskDecision(False, "reconciliation_kill", flatten=True)
        if funding_paid_pct > float(self.limits.max_funding_cost_per_day):
            return RiskDecision(False, "funding_cost_limit")
        if oi_spike_pct > float(self.limits.max_oi_spike_pct) and liquidation_spike > float(self.limits.max_liquidation_spike):
            self.state.kill_switch = True
            return RiskDecision(False, "squeeze_risk_kill", flatten=True)
        if margin_buffer < float(self.limits.min_margin_buffer):
            self.state.kill_switch = True
            return RiskDecision(False, "margin_buffer_kill", flatten=True)

        if self.state.orders_in_current_min >= int(self.limits.max_orders_per_min):
            return RiskDecision(False, "orders_per_min_exceeded")
        if daily_loss_pct <= -float(self.limits.max_daily_loss_pct):
            self.state.kill_switch = True
            return RiskDecision(False, "daily_loss_kill", flatten=True)

        cvar = self._approx_cvar()
        if self.limits.cvar_limit_pct != UNSPECIFIED and cvar > float(self.limits.cvar_limit_pct):
            return RiskDecision(False, "cvar_guard")

        adjusted = intent.target_notional * self.state.de_risk_multiplier * self.state.dd_throttle
        if adjusted > float(self.limits.max_position_notional):
            return RiskDecision(False, "position_notional_exceeded")
        if current_exposure + adjusted > float(self.limits.max_exposure_notional):
            return RiskDecision(False, "exposure_notional_exceeded")
        if int(self.limits.leverage) != 0:
            return RiskDecision(False, "leverage_must_be_zero_in_mvp")

        self.state.orders_in_current_min += 1
        return RiskDecision(True, "passed", adjusted_notional=adjusted)
