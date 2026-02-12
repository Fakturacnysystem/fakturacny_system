from __future__ import annotations

from dataclasses import dataclass

from autonomous_investment_robot.config.settings import RiskLimits, UNSPECIFIED
from autonomous_investment_robot.core.contracts import OrderIntent, RiskDecision


@dataclass
class KillSwitchState:
    state: str = "SAFE_MODE"


class RiskEngineService:
    def __init__(self, limits: RiskLimits, safe_mode: bool = True) -> None:
        self.limits = limits
        self.state = KillSwitchState("SAFE_MODE" if safe_mode else "ACTIVE")

    def evaluate(self, intent: OrderIntent, snapshot: dict) -> RiskDecision:
        if self.state.state == "SAFE_MODE":
            return RiskDecision(allowed=False, reason="safe_mode_default", kill_action="NO_TRADE")
        if self.limits.max_daily_loss_pct == UNSPECIFIED:
            return RiskDecision(allowed=False, reason="risk_limits_unspecified", kill_action="NO_TRADE")
        if snapshot.get("market_integrity_issue"):
            return RiskDecision(allowed=False, reason="market_integrity_kill", kill_action="FLATTEN")
        return RiskDecision(allowed=True, reason="passed")
