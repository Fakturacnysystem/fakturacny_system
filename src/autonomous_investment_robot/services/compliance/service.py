from dataclasses import dataclass

from autonomous_investment_robot.config.settings import ComplianceSettings


@dataclass
class ComplianceDecision:
    allowed: bool
    reason: str


class ComplianceService:
    def __init__(self, settings: ComplianceSettings) -> None:
        self.settings = settings

    def check_provider_authorization(self) -> ComplianceDecision:
        if self.settings.require_authorized_provider and not self.settings.allowed_providers:
            return ComplianceDecision(False, "no_authorized_provider_configured")
        return ComplianceDecision(True, "authorized")
