from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from autonomous_investment_robot.services.live_runtime.order_lifecycle import OrderLifecycleMirror


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
    reduce_only: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    state: str = "INTENT"
    fills_notional: float = 0.0
    idempotency_key: str = ""
    fill_ids_seen: set[str] = field(default_factory=set)
    lifecycle_key: str = ""
    lifecycle_confidence: str = "local"


class OmsLifecycleAdapter:
    def __init__(self) -> None:
        self._mirror = OrderLifecycleMirror(venue="oms")

    def submit(self, order: ManagedOrder) -> tuple[bool, str]:
        key = order.lifecycle_key or order.order_id
        order.lifecycle_key = key
        return self._mirror.submit(symbol=order.symbol, order_key=key, metadata={"oms_state": order.state})

    def apply_state(self, order: ManagedOrder, next_state: str, *, error: str = "") -> tuple[bool, str]:
        key = order.lifecycle_key or order.order_id
        order.lifecycle_key = key
        state = next_state.upper()
        if state == "ACK":
            return self._mirror.apply_exchange_update({"clientOrderId": key, "orderId": order.order_id, "symbol": order.symbol, "status": "ACK"})
        if state == "PARTIAL":
            return self._mirror.apply_exchange_update({"clientOrderId": key, "orderId": order.order_id, "symbol": order.symbol, "status": "PARTIALLY_FILLED"})
        if state == "FILLED":
            return self._mirror.apply_exchange_update({"clientOrderId": key, "orderId": order.order_id, "symbol": order.symbol, "status": "FILLED"})
        if state == "CANCELLED":
            return self._mirror.apply_exchange_update({"clientOrderId": key, "orderId": order.order_id, "symbol": order.symbol, "status": "CANCELED"})
        if state == "REJECTED":
            return self._mirror.rejected(symbol=order.symbol, order_key=key, error=error or "oms_rejected")
        if state == "SUBMITTED":
            return self._mirror.submit(symbol=order.symbol, order_key=key, metadata={"resubmitted": True})
        return False, "unsupported_lifecycle_state"

    def note_fill(self, order: ManagedOrder) -> None:
        key = order.lifecycle_key or order.order_id
        self._mirror.note_fill(order_key=key)

    def request_cancel(self, order: ManagedOrder) -> tuple[bool, str]:
        key = order.lifecycle_key or order.order_id
        return self._mirror.cancel_requested(symbol=order.symbol, order_key=key)

    def reject_cancel(self, order: ManagedOrder, error: str) -> tuple[bool, str]:
        key = order.lifecycle_key or order.order_id
        return self._mirror.cancel_rejected(symbol=order.symbol, order_key=key, error=error)

    def mark_timed_out(self, order: ManagedOrder) -> tuple[bool, str]:
        key = order.lifecycle_key or order.order_id
        return self._mirror.timed_out(symbol=order.symbol, order_key=key)

    def mark_orphaned(self, order: ManagedOrder, exchange_status: str) -> tuple[bool, str]:
        key = order.lifecycle_key or order.order_id
        return self._mirror.orphaned(symbol=order.symbol, order_key=key, exchange_status=exchange_status)

    def mark_recovered(self, order: ManagedOrder, metadata: dict[str, Any] | None = None) -> tuple[bool, str]:
        key = order.lifecycle_key or order.order_id
        return self._mirror.recovered(symbol=order.symbol, order_key=key, metadata=metadata)

    def reconcile_exchange_order(self, payload: dict[str, Any]) -> tuple[bool, str]:
        return self._mirror.apply_exchange_update(payload)

    def drain_transitions(self) -> list[dict[str, Any]]:
        return self._mirror.drain_transitions()

    def snapshot(self) -> list[dict[str, Any]]:
        return self._mirror.snapshot()


@dataclass
class OMSService:
    orders: dict[str, ManagedOrder] = field(default_factory=dict)
    idempotency_seen: set[str] = field(default_factory=set)
    lifecycle: OmsLifecycleAdapter = field(default_factory=OmsLifecycleAdapter)

    def _doctrine_submit_block(self, order: ManagedOrder) -> str | None:
        target = order.metadata.get("doctrine_target", {}) if isinstance(order.metadata, dict) else {}
        if not isinstance(target, dict):
            target = {}
        if str(order.side).lower() == "sell" and not bool(order.reduce_only) and bool(target.get("long_only", False)):
            return "long_only_non_reduce_sell_block"
        return None

    def submit_intent(self, order: ManagedOrder) -> tuple[bool, str]:
        doctrine_block = self._doctrine_submit_block(order)
        if doctrine_block is not None:
            return False, doctrine_block
        if order.idempotency_key in self.idempotency_seen:
            return False, "duplicate_submit"
        self.idempotency_seen.add(order.idempotency_key)
        self.orders[order.order_id] = order
        self.lifecycle.submit(order)
        return self.transition(order.order_id, "SUBMITTED")

    def transition(self, order_id: str, next_state: str) -> tuple[bool, str]:
        order = self.orders[order_id]
        if next_state not in VALID_TRANSITIONS[order.state]:
            return False, f"invalid_transition:{order.state}->{next_state}"
        order.state = next_state
        if next_state not in {"SUBMITTED"}:
            self.lifecycle.apply_state(order, next_state)
        return True, "ok"

    def apply_fill(self, order_id: str, fill_notional: float, fill_id: str | None = None) -> tuple[bool, str]:
        order = self.orders[order_id]
        if order.state not in {"ACK", "PARTIAL"}:
            return False, "fill_out_of_order"
        if fill_notional <= 0:
            return False, "non_positive_fill_notional"
        if fill_id:
            if fill_id in order.fill_ids_seen:
                return False, "duplicate_fill_id"
            order.fill_ids_seen.add(fill_id)
        if order.fills_notional + fill_notional > order.notional * 1.001:
            return False, "overfill_notional"
        order.fills_notional += fill_notional
        self.lifecycle.note_fill(order)
        if order.fills_notional >= order.notional:
            return self.transition(order_id, "FILLED")
        return self.transition(order_id, "PARTIAL")

    def request_cancel(self, order_id: str) -> tuple[bool, str]:
        order = self.orders[order_id]
        ok, reason = self.lifecycle.request_cancel(order)
        if not ok:
            return False, reason
        return True, "ok"

    def reject_cancel(self, order_id: str, error: str) -> tuple[bool, str]:
        order = self.orders[order_id]
        return self.lifecycle.reject_cancel(order, error)

    def mark_timed_out(self, order_id: str) -> tuple[bool, str]:
        order = self.orders[order_id]
        return self.lifecycle.mark_timed_out(order)

    def mark_orphaned(self, order_id: str, exchange_status: str) -> tuple[bool, str]:
        order = self.orders[order_id]
        return self.lifecycle.mark_orphaned(order, exchange_status)

    def mark_recovered(self, order_id: str, metadata: dict[str, Any] | None = None) -> tuple[bool, str]:
        order = self.orders[order_id]
        return self.lifecycle.mark_recovered(order, metadata)

    def reconcile_exchange_order(self, order_id: str, payload: dict[str, Any]) -> tuple[bool, str]:
        order = self.orders[order_id]
        if not order.lifecycle_key:
            order.lifecycle_key = order.order_id
        return self.lifecycle.reconcile_exchange_order(
            {
                "clientOrderId": order.lifecycle_key,
                "orderId": payload.get("orderId", order.order_id),
                "symbol": payload.get("symbol", order.symbol),
                "status": payload.get("status", "NEW"),
                "raw": payload,
            }
        )

    def lifecycle_snapshot(self) -> list[dict[str, Any]]:
        return self.lifecycle.snapshot()

    def drain_lifecycle_transitions(self) -> list[dict[str, Any]]:
        return self.lifecycle.drain_transitions()
