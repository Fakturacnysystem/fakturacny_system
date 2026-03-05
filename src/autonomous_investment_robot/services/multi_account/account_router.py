from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass
class AccountRoutingDecision:
    account_id: str
    reason: str


class AccountRouter:
    def __init__(self, strategy: str | None = None) -> None:
        self.strategy = str(strategy or os.getenv("AUTONOMOUS_ACCOUNT_ROUTING_STRATEGY", "round_robin")).strip().lower()
        self._accounts = self._discover_accounts()
        self._rr_idx = 0

    def _discover_accounts(self) -> list[str]:
        accounts: list[str] = []
        if str(os.getenv("KRKN_API_KEY_MAIN", "") or "").strip():
            accounts.append("main")
        for i in range(1, 10):
            if str(os.getenv(f"KRKN_API_KEY_SUB{i}", "") or "").strip():
                accounts.append(f"sub{i}")
        if not accounts:
            accounts.append("main")
        return accounts

    @property
    def accounts(self) -> list[str]:
        return list(self._accounts)

    def choose_account(
        self,
        *,
        symbol: str,
        available_margin_by_account: dict[str, float] | None = None,
        rate_limit_pressure_by_account: dict[str, float] | None = None,
    ) -> AccountRoutingDecision:
        margins = available_margin_by_account or {}
        rl = rate_limit_pressure_by_account or {}
        if self.strategy == "liquidity_based":
            best = max(
                self._accounts,
                key=lambda acc: float(margins.get(acc, 0.0)) - float(rl.get(acc, 0.0)),
            )
            return AccountRoutingDecision(account_id=best, reason=f"liquidity_based:{symbol}")

        idx = self._rr_idx % max(1, len(self._accounts))
        self._rr_idx += 1
        return AccountRoutingDecision(account_id=self._accounts[idx], reason=f"round_robin:{symbol}")
