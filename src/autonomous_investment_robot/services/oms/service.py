from __future__ import annotations

from dataclasses import dataclass, field


VALID_TRANSITIONS = {
    "INTENT": {"SUBMITTED", "REJECTED"},
    "SUBMITTED": {"ACK", "CANCELLED", "REJECTED"},
    "ACK": {"PARTIAL", "FILLED", "CANCELLED"},
    "PARTIAL": {"PARTIAL", "FILLED", "CANCELLED"},
    "FILLED": set(),
    "REJECTED": set(),
    "CANCELLED": set(),
}


@dataclass
class ManagedOrder:
    order_id: str
    symbol: str
    side: str
    notional: float
    state: str = "INTENT"
    fills_notional: float = 0.0
    idempotency_key: str = ""


@dataclass
class OMSService:
    orders: dict[str, ManagedOrder] = field(default_factory=dict)
    idempotency_seen: set[str] = field(default_factory=set)

    def submit_intent(self, order: ManagedOrder) -> tuple[bool, str]:
        if order.idempotency_key in self.idempotency_seen:
            return False, "duplicate_submit"
        self.idempotency_seen.add(order.idempotency_key)
        self.orders[order.order_id] = order
        return self.transition(order.order_id, "SUBMITTED")

    def transition(self, order_id: str, next_state: str) -> tuple[bool, str]:
        order = self.orders[order_id]
        if next_state not in VALID_TRANSITIONS[order.state]:
            return False, f"invalid_transition:{order.state}->{next_state}"
        order.state = next_state
        return True, "ok"

    def apply_fill(self, order_id: str, fill_notional: float) -> tuple[bool, str]:
        order = self.orders[order_id]
        if order.state not in {"ACK", "PARTIAL"}:
            return False, "fill_out_of_order"
        order.fills_notional += fill_notional
        if order.fills_notional >= order.notional:
            return self.transition(order_id, "FILLED")
        return self.transition(order_id, "PARTIAL")
