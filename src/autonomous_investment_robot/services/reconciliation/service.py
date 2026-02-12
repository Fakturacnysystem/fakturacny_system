from __future__ import annotations

from autonomous_investment_robot.services.execution.service import Fill


class ReconciliationService:
    def reconcile(self, fills: list[Fill], expected_notional: float) -> tuple[bool, str]:
        got = sum(f.notional for f in fills)
        if abs(got - expected_notional) > max(1.0, expected_notional * 0.5):
            return False, "notional_mismatch"
        return True, "ok"
