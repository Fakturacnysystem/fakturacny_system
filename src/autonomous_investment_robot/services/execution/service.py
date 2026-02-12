from dataclasses import dataclass

from autonomous_investment_robot.core.contracts import OrderIntent, RiskDecision


@dataclass
class ExecutionResult:
    status: str
    venue: str
    symbol: str
    qty: float
    slippage_bps: float


class ExecutionService:
    def __init__(self, paper_mode: bool = True) -> None:
        self.paper_mode = paper_mode

    def pre_trade_checks(self, intent: OrderIntent) -> tuple[bool, list[str]]:
        issues = []
        if intent.max_slippage_bps <= 0:
            issues.append("invalid_slippage_cap")
        return (len(issues) == 0, issues)

    def execute(self, intent: OrderIntent, risk: RiskDecision) -> ExecutionResult:
        ok, issues = self.pre_trade_checks(intent)
        if not ok or not risk.allowed:
            return ExecutionResult(status=f"blocked:{','.join(issues) or risk.reason}", venue="paper", symbol=intent.symbol, qty=0.0, slippage_bps=0.0)
        mode = "paper" if self.paper_mode else "live"
        return ExecutionResult(status=f"executed_{mode}", venue=mode, symbol=intent.symbol, qty=intent.qty * risk.throttle, slippage_bps=2.0)
