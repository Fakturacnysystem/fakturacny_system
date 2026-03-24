from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from typing import Any


class ReplayCoordinator:
    def __init__(self, *, raw: Any, portfolio: Any, legacy_fill_payload: Any) -> None:
        self.raw = raw
        self.portfolio = portfolio
        self.legacy_fill_payload = legacy_fill_payload

    def persist_outputs(
        self,
        *,
        equity: float,
        drawdown: float,
        drawdown_signed: float,
        funding_paid_pct: float,
        fills_all: list[Any],
        plans: list[dict[str, Any]],
        trade_log: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.raw.write_table("order_plans", plans)
        self.raw.write_table("fills", [asdict(f) for f in fills_all])
        self.raw.write_table("portfolio_ledger", self.portfolio.ledger_rows())
        self.raw.write_table("report", [{"equity": equity, "drawdown_pct": drawdown, "drawdown_signed_pct": drawdown_signed, "funding_paid_pct": funding_paid_pct}])
        self.raw.write_table("trade_log", trade_log)

        checksums = {
            "orders_checksum": sha256(json.dumps(plans, sort_keys=True, default=str).encode()).hexdigest(),
            "fills_checksum": sha256(json.dumps([self.legacy_fill_payload(f) for f in fills_all], sort_keys=True, default=str).encode()).hexdigest(),
            "equity_checksum": sha256(json.dumps({"equity": equity, "drawdown": drawdown_signed}, sort_keys=True).encode()).hexdigest(),
        }
        self.raw.write_table("checksums", [checksums])
        return checksums
