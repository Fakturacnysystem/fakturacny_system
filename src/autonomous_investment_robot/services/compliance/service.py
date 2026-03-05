from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass
class ComplianceDecision:
    allowed: bool
    reason: str


class ComplianceService:
    def __init__(self, provider_whitelist: list[str]) -> None:
        self.provider_whitelist = provider_whitelist

    def check_provider_authorization(self, provider: str) -> ComplianceDecision:
        # Paper simulation must stay available even when config whitelist contains only
        # live providers, so runtime can safely downgrade without manual edits.
        if provider == "paper_sim_provider":
            return ComplianceDecision(True, "authorized")
        if provider not in self.provider_whitelist:
            return ComplianceDecision(False, "provider_not_authorized")
        return ComplianceDecision(True, "authorized")

    def check_provider_permissions(self, required: dict[str, bool], granted: dict[str, bool]) -> ComplianceDecision:
        missing = [k for k, needed in required.items() if needed and not bool(granted.get(k, False))]
        if missing:
            return ComplianceDecision(False, f"missing_permissions:{','.join(sorted(missing))}")
        return ComplianceDecision(True, "permissions_ok")

    def policy_constraints(
        self,
        *,
        jurisdiction: str,
        symbol: str,
        notional: float,
        max_notional: float,
    ) -> ComplianceDecision:
        if notional > max_notional:
            return ComplianceDecision(False, "policy_max_notional_exceeded")
        # Basic jurisdiction placeholder for explicit policy branching.
        if jurisdiction.upper() in {"US", "SK", "CZ", "EU"}:
            return ComplianceDecision(True, "jurisdiction_policy_ok")
        return ComplianceDecision(True, "jurisdiction_policy_unscoped")

    def write_report(
        self,
        *,
        run_dir: str,
        jurisdiction: str,
        provider: str,
        decision: ComplianceDecision,
        extra: dict[str, Any] | None = None,
    ) -> str:
        p = Path(run_dir) / "compliance_engine_report.json"
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "jurisdiction": jurisdiction,
            "provider": provider,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "extra": extra or {},
        }
        p.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str), encoding="utf-8")
        return str(p)
