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


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    adjusted_notional: float = 0.0


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
        ]
        return all(v != UNSPECIFIED for v in required)

    def _approx_cvar(self) -> float:
        if len(self.state.rolling_returns) < 5:
            return 0.0
        tails = sorted(self.state.rolling_returns)[: max(1, len(self.state.rolling_returns) // 20)]
        return abs(sum(tails) / len(tails)) * 100

    def record_return(self, ret_pct: float) -> None:
        self.state.rolling_returns.append(ret_pct)
        self.state.rolling_returns = self.state.rolling_returns[-500:]
        if ret_pct < 0:
            self.state.loss_streak += 1
        else:
            self.state.loss_streak = 0
        if self.state.loss_streak >= 3:
            self.state.de_risk_multiplier = 0.5

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
    ) -> RiskDecision:
        if self.state.safe_mode:
            return RiskDecision(False, "safe_mode_default")
        if not self._limits_complete():
            return RiskDecision(False, "risk_limits_unspecified")
        if data_lag_seconds > float(self.limits.stale_data_seconds):
            self.state.kill_switch = True
            return RiskDecision(False, "stale_data_kill")
        if spread_bps > float(self.limits.max_spread_bps):
            self.state.kill_switch = True
            return RiskDecision(False, "spread_explosion_kill")
        if depth_notional < float(self.limits.min_depth_notional):
            self.state.kill_switch = True
            return RiskDecision(False, "liquidity_hole_kill")
        if not reconciliation_ok:
            self.state.kill_switch = True
            return RiskDecision(False, "integrity_kill_switch")
        if self.state.orders_in_current_min >= int(self.limits.max_orders_per_min):
            return RiskDecision(False, "orders_per_min_exceeded")
        if drawdown_pct <= -float(self.limits.max_drawdown_pct):
            self.state.kill_switch = True
            return RiskDecision(False, "drawdown_kill")
        if daily_loss_pct <= -float(self.limits.max_daily_loss_pct):
            self.state.kill_switch = True
            return RiskDecision(False, "daily_loss_kill")
        cvar = self._approx_cvar()
        if self.limits.cvar_limit_pct != UNSPECIFIED and cvar > float(self.limits.cvar_limit_pct):
            return RiskDecision(False, "cvar_guard")
        adjusted = intent.target_notional * self.state.de_risk_multiplier
        if adjusted > float(self.limits.max_position_notional):
            return RiskDecision(False, "position_notional_exceeded")
        if current_exposure + adjusted > float(self.limits.max_exposure_notional):
            return RiskDecision(False, "exposure_notional_exceeded")
        if int(self.limits.leverage) != 0:
            return RiskDecision(False, "leverage_must_be_zero_in_mvp")
        self.state.orders_in_current_min += 1
        return RiskDecision(True, "passed", adjusted_notional=adjusted)
