from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import OrderLifecycleRecord, OrderLifecycleState, OrderLifecycleTransition


_ALLOWED_TRANSITIONS: dict[str | None, set[str]] = {
    None: {
        OrderLifecycleState.SUBMITTED.value,
        OrderLifecycleState.ACCEPTED.value,
        OrderLifecycleState.WORKING.value,
        OrderLifecycleState.PARTIALLY_FILLED.value,
        OrderLifecycleState.FILLED.value,
        OrderLifecycleState.CANCELLED.value,
        OrderLifecycleState.REJECTED.value,
        OrderLifecycleState.EXPIRED.value,
    },
    OrderLifecycleState.SUBMITTED.value: {
        OrderLifecycleState.ACCEPTED.value,
        OrderLifecycleState.WORKING.value,
        OrderLifecycleState.PARTIALLY_FILLED.value,
        OrderLifecycleState.FILLED.value,
        OrderLifecycleState.CANCELLED.value,
        OrderLifecycleState.REJECTED.value,
        OrderLifecycleState.EXPIRED.value,
        OrderLifecycleState.TIMED_OUT.value,
        OrderLifecycleState.ORPHANED.value,
    },
    OrderLifecycleState.ACCEPTED.value: {
        OrderLifecycleState.WORKING.value,
        OrderLifecycleState.PARTIALLY_FILLED.value,
        OrderLifecycleState.FILLED.value,
        OrderLifecycleState.CANCEL_PENDING.value,
        OrderLifecycleState.REPLACE_PENDING.value,
        OrderLifecycleState.REPLACED.value,
        OrderLifecycleState.CANCELLED.value,
        OrderLifecycleState.REJECTED.value,
        OrderLifecycleState.EXPIRED.value,
        OrderLifecycleState.TIMED_OUT.value,
    },
    OrderLifecycleState.WORKING.value: {
        OrderLifecycleState.PARTIALLY_FILLED.value,
        OrderLifecycleState.FILLED.value,
        OrderLifecycleState.CANCEL_PENDING.value,
        OrderLifecycleState.REPLACE_PENDING.value,
        OrderLifecycleState.REPLACED.value,
        OrderLifecycleState.CANCELLED.value,
        OrderLifecycleState.EXPIRED.value,
        OrderLifecycleState.TIMED_OUT.value,
        OrderLifecycleState.STUCK.value,
    },
    OrderLifecycleState.PARTIALLY_FILLED.value: {
        OrderLifecycleState.PARTIALLY_FILLED.value,
        OrderLifecycleState.FILLED.value,
        OrderLifecycleState.CANCEL_PENDING.value,
        OrderLifecycleState.REPLACE_PENDING.value,
        OrderLifecycleState.REPLACED.value,
        OrderLifecycleState.CANCELLED.value,
        OrderLifecycleState.EXPIRED.value,
        OrderLifecycleState.TIMED_OUT.value,
        OrderLifecycleState.RECOVERED.value,
    },
    OrderLifecycleState.REPLACE_PENDING.value: {
        OrderLifecycleState.REPLACED.value,
        OrderLifecycleState.REPLACE_REJECTED.value,
        OrderLifecycleState.CANCELLED.value,
        OrderLifecycleState.FILLED.value,
        OrderLifecycleState.PARTIALLY_FILLED.value,
        OrderLifecycleState.EXPIRED.value,
    },
    OrderLifecycleState.REPLACE_REJECTED.value: {
        OrderLifecycleState.WORKING.value,
        OrderLifecycleState.PARTIALLY_FILLED.value,
        OrderLifecycleState.FILLED.value,
        OrderLifecycleState.CANCEL_PENDING.value,
        OrderLifecycleState.EXPIRED.value,
    },
    OrderLifecycleState.CANCEL_PENDING.value: {
        OrderLifecycleState.CANCELLED.value,
        OrderLifecycleState.CANCEL_REJECTED.value,
        OrderLifecycleState.FILLED.value,
        OrderLifecycleState.PARTIALLY_FILLED.value,
    },
    OrderLifecycleState.CANCEL_REJECTED.value: {
        OrderLifecycleState.WORKING.value,
        OrderLifecycleState.PARTIALLY_FILLED.value,
        OrderLifecycleState.FILLED.value,
        OrderLifecycleState.CANCEL_PENDING.value,
    },
    OrderLifecycleState.TIMED_OUT.value: {
        OrderLifecycleState.CANCEL_PENDING.value,
        OrderLifecycleState.CANCELLED.value,
        OrderLifecycleState.FILLED.value,
        OrderLifecycleState.RECOVERED.value,
        OrderLifecycleState.STUCK.value,
    },
    OrderLifecycleState.ORPHANED.value: {
        OrderLifecycleState.CANCEL_PENDING.value,
        OrderLifecycleState.CANCELLED.value,
        OrderLifecycleState.RECOVERED.value,
        OrderLifecycleState.STUCK.value,
    },
}

_TERMINAL_STATES = {
    OrderLifecycleState.FILLED.value,
    OrderLifecycleState.CANCELLED.value,
    OrderLifecycleState.REJECTED.value,
    OrderLifecycleState.EXPIRED.value,
}


class OrderLifecycleMirror:
    def __init__(self, *, venue: str) -> None:
        self.venue = venue
        self._records: dict[str, OrderLifecycleRecord] = {}
        self._aliases: dict[str, str] = {}
        self._pending: list[OrderLifecycleTransition] = []

    def reset(self) -> None:
        self._records = {}
        self._aliases = {}
        self._pending = []

    def _resolve_key(self, order_key: str) -> str:
        return self._aliases.get(order_key, order_key)

    def _remember_aliases(self, record: OrderLifecycleRecord) -> None:
        if record.order_id:
            self._aliases[record.order_id] = record.order_key
        if record.client_order_id:
            self._aliases[record.client_order_id] = record.order_key

    def _transition(
        self,
        *,
        symbol: str,
        order_key: str,
        to_state: str,
        source: str,
        reason: str,
        confidence: str,
        metadata: dict[str, Any] | None = None,
        order_id: str = "",
        client_order_id: str = "",
    ) -> tuple[bool, str, OrderLifecycleTransition]:
        ts = datetime.now(timezone.utc)
        canonical_key = self._resolve_key(order_key)
        record = self._records.get(canonical_key)
        prior_state = None if record is None else record.state
        if prior_state == to_state:
            transition = OrderLifecycleTransition(
                symbol=symbol,
                venue=self.venue,
                ts=ts,
                order_key=canonical_key,
                from_state=prior_state,
                to_state=to_state,
                source=source,
                reason="duplicate_lifecycle_event",
                accepted=False,
                duplicate=True,
                metadata={} if metadata is None else dict(metadata),
            )
            self._pending.append(transition)
            return False, "duplicate_lifecycle_event", transition

        allowed = _ALLOWED_TRANSITIONS.get(prior_state, set()) | ({to_state} if prior_state in _TERMINAL_STATES and prior_state == to_state else set())
        if prior_state is not None and to_state not in allowed and to_state != OrderLifecycleState.RECOVERED.value:
            transition = OrderLifecycleTransition(
                symbol=symbol,
                venue=self.venue,
                ts=ts,
                order_key=canonical_key,
                from_state=prior_state,
                to_state=to_state,
                source=source,
                reason="out_of_order_lifecycle_event",
                accepted=False,
                out_of_order=True,
                metadata={} if metadata is None else dict(metadata),
            )
            self._pending.append(transition)
            return False, "out_of_order_lifecycle_event", transition

        if record is None:
            record = OrderLifecycleRecord(
                symbol=symbol,
                venue=self.venue,
                order_key=canonical_key,
                state=to_state,
                confidence=confidence,
                order_id=order_id,
                client_order_id=client_order_id,
                last_event_ts=ts,
                metadata={} if metadata is None else dict(metadata),
            )
        else:
            record.state = to_state
            record.confidence = confidence
            record.last_event_ts = ts
            if order_id:
                record.order_id = order_id
            if client_order_id:
                record.client_order_id = client_order_id
            record.metadata.update({} if metadata is None else dict(metadata))
        self._records[canonical_key] = record
        self._remember_aliases(record)
        transition = OrderLifecycleTransition(
            symbol=symbol,
            venue=self.venue,
            ts=ts,
            order_key=canonical_key,
            from_state=prior_state,
            to_state=to_state,
            source=source,
            reason=reason,
            metadata={} if metadata is None else dict(metadata),
        )
        self._pending.append(transition)
        return True, "ok", transition

    def submit(self, *, symbol: str, order_key: str, metadata: dict[str, Any] | None = None) -> tuple[bool, str]:
        ok, reason, _ = self._transition(
            symbol=symbol,
            order_key=order_key,
            to_state=OrderLifecycleState.SUBMITTED.value,
            source="local_submit",
            reason="intent_submitted",
            confidence="local",
            metadata=metadata,
            client_order_id=order_key,
        )
        return ok, reason

    def apply_exchange_update(self, order: dict[str, Any]) -> tuple[bool, str]:
        symbol = str(order.get("symbol", ""))
        order_id = str(order.get("orderId", order.get("order_id", "")))
        client_order_id = str(order.get("clientOrderId", order.get("origClientOrderId", order.get("cliOrdId", order.get("clOrdId", "")))))
        order_key = client_order_id or order_id
        status = str(order.get("status", "NEW")).upper()
        replace_supported = bool(
            order.get("supportsReplace", order.get("replaceSupported", order.get("replace_supported", False)))
        )
        replace_statuses = {"PENDING_REPLACE", "REPLACE_PENDING", "AMEND_PENDING", "REPLACED", "AMENDED", "REPLACE_REJECTED", "AMEND_REJECTED"}
        if status in replace_statuses and not replace_supported:
            ts = datetime.now(timezone.utc)
            transition = OrderLifecycleTransition(
                symbol=symbol or "",
                venue=self.venue,
                ts=ts,
                order_key=order_key,
                from_state=self._records.get(self._resolve_key(order_key)).state if self._records.get(self._resolve_key(order_key)) is not None else None,
                to_state=OrderLifecycleState.UNKNOWN.value,
                source="exchange_order_update",
                reason="unsupported_replace",
                accepted=False,
                metadata={"status": status, "raw": order.get("raw", order)},
            )
            self._pending.append(transition)
            return False, "unsupported_replace"
        state = {
            "NEW": OrderLifecycleState.ACCEPTED.value,
            "ACK": OrderLifecycleState.ACCEPTED.value,
            "ACKNOWLEDGED": OrderLifecycleState.ACCEPTED.value,
            "PARTIALLY_FILLED": OrderLifecycleState.PARTIALLY_FILLED.value,
            "FILLED": OrderLifecycleState.FILLED.value,
            "EXECUTED": OrderLifecycleState.FILLED.value,
            "CANCELED": OrderLifecycleState.CANCELLED.value,
            "CANCELLED": OrderLifecycleState.CANCELLED.value,
            "REJECTED": OrderLifecycleState.REJECTED.value,
            "EXPIRED": OrderLifecycleState.EXPIRED.value,
            "PENDING_REPLACE": OrderLifecycleState.REPLACE_PENDING.value,
            "REPLACE_PENDING": OrderLifecycleState.REPLACE_PENDING.value,
            "AMEND_PENDING": OrderLifecycleState.REPLACE_PENDING.value,
            "REPLACED": OrderLifecycleState.REPLACED.value,
            "AMENDED": OrderLifecycleState.REPLACED.value,
            "REPLACE_REJECTED": OrderLifecycleState.REPLACE_REJECTED.value,
            "AMEND_REJECTED": OrderLifecycleState.REPLACE_REJECTED.value,
        }.get(status, OrderLifecycleState.WORKING.value)
        ok, reason, _ = self._transition(
            symbol=symbol or "",
            order_key=order_key,
            to_state=state,
            source="exchange_order_update",
            reason=status.lower(),
            confidence="exchange",
            metadata={"status": status, "raw": order.get("raw", order)},
            order_id=order_id,
            client_order_id=client_order_id,
        )
        return ok, reason

    def cancel_requested(self, *, symbol: str, order_key: str) -> tuple[bool, str]:
        ok, reason, _ = self._transition(
            symbol=symbol,
            order_key=order_key,
            to_state=OrderLifecycleState.CANCEL_PENDING.value,
            source="local_cancel",
            reason="cancel_requested",
            confidence="local",
        )
        return ok, reason

    def cancel_rejected(self, *, symbol: str, order_key: str, error: str) -> tuple[bool, str]:
        ok, reason, _ = self._transition(
            symbol=symbol,
            order_key=order_key,
            to_state=OrderLifecycleState.CANCEL_REJECTED.value,
            source="local_cancel",
            reason="cancel_rejected",
            confidence="local",
            metadata={"error": error},
        )
        return ok, reason

    def timed_out(self, *, symbol: str, order_key: str) -> tuple[bool, str]:
        ok, reason, _ = self._transition(
            symbol=symbol,
            order_key=order_key,
            to_state=OrderLifecycleState.TIMED_OUT.value,
            source="local_timeout",
            reason="maker_timeout",
            confidence="local",
        )
        return ok, reason

    def orphaned(self, *, symbol: str, order_key: str, exchange_status: str) -> tuple[bool, str]:
        ok, reason, _ = self._transition(
            symbol=symbol,
            order_key=order_key,
            to_state=OrderLifecycleState.ORPHANED.value,
            source="recovery",
            reason="orphan_open_order",
            confidence="recovery",
            metadata={"exchange_status": exchange_status},
        )
        return ok, reason

    def recovered(self, *, symbol: str, order_key: str, metadata: dict[str, Any] | None = None) -> tuple[bool, str]:
        ok, reason, _ = self._transition(
            symbol=symbol,
            order_key=order_key,
            to_state=OrderLifecycleState.RECOVERED.value,
            source="recovery",
            reason="recovered_from_history",
            confidence="recovery",
            metadata=metadata,
        )
        return ok, reason

    def rejected(self, *, symbol: str, order_key: str, error: str) -> tuple[bool, str]:
        ok, reason, _ = self._transition(
            symbol=symbol,
            order_key=order_key,
            to_state=OrderLifecycleState.REJECTED.value,
            source="local_reject",
            reason="order_rejected",
            confidence="local",
            metadata={"error": error},
        )
        return ok, reason

    def note_fill(self, *, order_key: str) -> None:
        canonical_key = self._resolve_key(order_key)
        record = self._records.get(canonical_key)
        if record is not None:
            record.fill_count += 1

    def drain_transitions(self) -> list[dict[str, Any]]:
        pending = [asdict(item) for item in self._pending]
        self._pending = []
        return pending

    def snapshot(self) -> list[dict[str, Any]]:
        return [asdict(record) for record in self._records.values()]
