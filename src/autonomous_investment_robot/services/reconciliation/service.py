from __future__ import annotations

import json
from pathlib import Path

from autonomous_investment_robot.services.execution.service import Fill


class ReconciliationService:
    def expected_exposure(self, fills: list[Fill]) -> float:
        return sum(f.notional if f.side == "buy" else -f.notional for f in fills)

    def reconcile(
        self,
        fills: list[Fill],
        internal_exposure: float,
        open_orders_state_ok: bool,
        cash_ok: bool,
    ) -> tuple[bool, str]:
        expected = self.expected_exposure(fills)
        if abs(expected - internal_exposure) > max(1.0, abs(expected) * 0.3):
            return False, "position_mismatch"
        if not open_orders_state_ok:
            return False, "open_order_state_mismatch"
        if not cash_ok:
            return False, "cash_mismatch"
        return True, "ok"

    def reconcile_live(
        self,
        exchange_exposure: float,
        internal_exposure: float,
        open_orders_state_ok: bool,
        cash_ok: bool,
    ) -> tuple[bool, str]:
        if abs(exchange_exposure - internal_exposure) > max(2.0, abs(exchange_exposure) * 0.1):
            return False, "live_position_mismatch"
        if not open_orders_state_ok:
            return False, "live_open_order_state_mismatch"
        if not cash_ok:
            return False, "live_cash_mismatch"
        return True, "ok"

    def persist_report(self, run_dir: str, report: dict) -> str:
        out = Path(run_dir) / "reconciliation_report.jsonl"
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(report, sort_keys=True, default=str) + "\n")
        return str(out)
