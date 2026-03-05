from __future__ import annotations

import re
from typing import Iterable


class SecurityService:
    def validate_key_policy(self, withdrawals_disabled: bool, ip_allowlist: list[str]) -> tuple[bool, list[str]]:
        issues = []
        if not withdrawals_disabled:
            issues.append("withdrawals_must_be_disabled")
        if not ip_allowlist:
            issues.append("ip_allowlist_required")
        return (len(issues) == 0, issues)

    def key_rotation_due(self, age_days: int, max_age_days: int = 30) -> tuple[bool, str]:
        if age_days >= max_age_days:
            return True, "rotation_required"
        return False, "rotation_not_required"

    def least_privilege_check(self, granted_scopes: Iterable[str], allowed_scopes: Iterable[str]) -> tuple[bool, list[str]]:
        granted = {str(x) for x in granted_scopes}
        allowed = {str(x) for x in allowed_scopes}
        forbidden = sorted(granted - allowed)
        return (len(forbidden) == 0, forbidden)

    def secret_scan(self, text: str) -> list[str]:
        findings: list[str] = []
        patterns = [
            (r"(?i)api[_-]?key\\s*[:=]\\s*['\\\"][A-Za-z0-9+/=]{16,}['\\\"]", "api_key_literal"),
            (r"(?i)api[_-]?secret\\s*[:=]\\s*['\\\"][A-Za-z0-9+/=]{16,}['\\\"]", "api_secret_literal"),
            (r"(?i)private[_-]?key\\s*[:=]\\s*['\\\"][A-Za-z0-9+/=]{16,}['\\\"]", "private_key_literal"),
        ]
        for pattern, label in patterns:
            if re.search(pattern, text):
                findings.append(label)
        return findings
