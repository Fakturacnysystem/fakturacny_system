class ReconciliationService:
    def reconcile(self, orders: list[dict], fills: list[dict], balances: dict) -> tuple[bool, str]:
        if len(fills) > len(orders):
            return False, "fill_count_exceeds_orders"
        return True, "ok"
