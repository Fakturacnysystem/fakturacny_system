from dataclasses import dataclass


@dataclass
class ComplianceDecision:
    allowed: bool
    reason: str


class ComplianceService:
    def __init__(self, provider_whitelist: list[str]) -> None:
        self.provider_whitelist = provider_whitelist

    def check_provider_authorization(self, provider: str) -> ComplianceDecision:
        if provider not in self.provider_whitelist:
            return ComplianceDecision(False, "provider_not_authorized")
        return ComplianceDecision(True, "authorized")
