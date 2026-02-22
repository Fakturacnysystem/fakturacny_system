class SecurityService:
    def validate_key_policy(self, withdrawals_disabled: bool, ip_allowlist: list[str]) -> tuple[bool, list[str]]:
        issues = []
        if not withdrawals_disabled:
            issues.append("withdrawals_must_be_disabled")
        if not ip_allowlist:
            issues.append("ip_allowlist_required")
        return (len(issues) == 0, issues)
