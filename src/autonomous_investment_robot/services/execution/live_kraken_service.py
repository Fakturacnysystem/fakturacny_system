from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.kraken_derivatives import KrakenDerivativesConnector
from autonomous_investment_robot.services.policy.service import OrderIntent


@dataclass
class LiveExecutionResult:
    status: str
    reason: str = ""
    order: dict[str, Any] | None = None


class LiveKrakenService:
    def __init__(self, settings: RobotSettings, run_id: str, connector: KrakenDerivativesConnector | None = None) -> None:
        self.settings = settings
        self.run_id = run_id
        self.connector = connector or KrakenDerivativesConnector(settings.execution.kraken)
        self.safe_mode = False
        self.killed = False

    def preflight(self) -> tuple[bool, str]:
        mode = self.settings.execution_mode_enum()
        if "kraken_derivatives" not in self.settings.provider_whitelist:
            return False, "provider_not_whitelisted"
        if mode == ExecutionMode.LIVE_READONLY:
            # readonly path can operate without credentials
            return True, "readonly"
        if not self.connector.has_credentials:
            return False, "missing_credentials"
        ok_perm, reason_perm = self.connector.verify_live_permissions()
        if not ok_perm:
            return False, reason_perm
        # Full trading path intentionally blocked until order API is implemented.
        return False, "kraken_live_trading_not_implemented"

    def execute_readonly(self, intent: OrderIntent) -> LiveExecutionResult:
        preview = {
            "symbol": intent.symbol,
            "side": intent.side,
            "target_notional": intent.target_notional,
            "book": self.connector.book_ticker(intent.symbol),
        }
        return LiveExecutionResult(status="readonly_preview", order=preview)

    def execute_intent(self, intent: OrderIntent) -> LiveExecutionResult:  # noqa: ARG002
        return LiveExecutionResult(status="blocked", reason="kraken_live_trading_not_implemented")

    def flatten_all_positions(self, max_attempts: int = 3) -> tuple[bool, str]:  # noqa: ARG002
        return False, "kraken_live_trading_not_implemented"
