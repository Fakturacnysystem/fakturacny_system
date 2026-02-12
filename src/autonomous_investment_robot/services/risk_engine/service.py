from __future__ import annotations

from dataclasses import dataclass

from autonomous_investment_robot.config.settings import RiskLimits, UNSPECIFIED
from autonomous_investment_robot.services.policy.service import OrderIntent


@dataclass
class RiskState:
    kill_switch: bool = False
    safe_mode: bool = False
    orders_in_current_min: int = 0


@dataclass
class RiskDecision:
    allowed: bool
    reason: str


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
        ]
        return all(v != UNSPECIFIED for v in required)

    def evaluate(
        self,
        intent: OrderIntent,
        current_exposure: float,
        drawdown_pct: float,
        daily_loss_pct: float,
        data_stale: bool,
        reconciliation_ok: bool,
    ) -> RiskDecision:
        if self.state.safe_mode:
            return RiskDecision(False, "safe_mode_default")
        if not self._limits_complete():
            return RiskDecision(False, "risk_limits_unspecified")
        if data_stale or not reconciliation_ok:
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
        if intent.target_notional > float(self.limits.max_position_notional):
            return RiskDecision(False, "position_notional_exceeded")
        if current_exposure + intent.target_notional > float(self.limits.max_exposure_notional):
            return RiskDecision(False, "exposure_notional_exceeded")
        if int(self.limits.leverage) != 0:
            return RiskDecision(False, "leverage_must_be_zero_in_mvp")
        self.state.orders_in_current_min += 1
        return RiskDecision(True, "passed")
