from __future__ import annotations

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
