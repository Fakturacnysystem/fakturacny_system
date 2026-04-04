from __future__ import annotations

import hashlib
import math
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector, KrakenSpotTradeRow
from autonomous_investment_robot.core.contracts import UnrealizedPnlTruth
from autonomous_investment_robot.services.event_store.service import EventStore
from autonomous_investment_robot.services.execution.kraken_spot_user_stream import KrakenSpotUserStream
from autonomous_investment_robot.services.live_runtime.ledger import (
    NormalizedLiveFillRecord,
    _build_normalized_fill,
)
from autonomous_investment_robot.services.live_runtime.order_lifecycle import OrderLifecycleMirror
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.reconciliation.service import ReconciliationService


@dataclass
class LiveExecutionResult:
    status: str
    reason: str = ""
    order: dict[str, Any] | None = None
    ledger_records: list[NormalizedLiveFillRecord] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RejectTracker:
    timestamps: list[float] = field(default_factory=list)

    def add_reject(self, ts: float) -> None:
        self.timestamps.append(ts)
        self.timestamps = [x for x in self.timestamps if (ts - x) <= 60.0]

    def reject_storm(self, max_rejects: int) -> bool:
        return len(self.timestamps) > max_rejects


@dataclass
class RateLimitTracker:
    timestamps: list[float] = field(default_factory=list)

    def add_hit(self, ts: float) -> None:
        self.timestamps.append(ts)
        self.timestamps = [x for x in self.timestamps if (ts - x) <= 60.0]

    def storm(self, max_hits: int) -> bool:
        return len(self.timestamps) > max_hits


class LiveKrakenSpotService:
    def __init__(
        self,
        settings: RobotSettings,
        run_id: str,
        connector: KrakenSpotConnector | None = None,
        user_stream: KrakenSpotUserStream | None = None,
    ) -> None:
        self.settings = settings
        self.run_id = run_id
        self.connector = connector or KrakenSpotConnector(settings.execution.kraken_spot)
        self.recon = ReconciliationService()
        self.rejects = RejectTracker()
        self.rate_limits = RateLimitTracker()
        self.safe_mode = False
        self.flatten_only = False
        self.killed = False
        self.kill_reason = ""
        self.cooldown_until_s = 0.0
        self._recent_cids: dict[str, float] = {}
        self._recent_intents: dict[str, float] = {}
        self._dedupe_ttl_s = 600.0
        self._order_status_by_id: dict[str, str] = {}
        self._fill_ids_seen: set[str] = set()
        self._lifecycle = OrderLifecycleMirror(venue="kraken_spot")
        self._market_integrity_state: dict[str, Any] = {
            "ts": None,
            "sequence_ok": True,
            "checksum_ok": True,
            "gap_count": 0,
            "checksum_mismatch_count": 0,
        }
        self._last_book_signature = ""
        self._last_book_change_ts: float | None = None
        self._book_repeat_count = 0
        self._auth_validated = False
        self._private_api_healthy = True
        self._flatten_history: list[dict[str, Any]] = []
        self._runtime_event_store = EventStore(settings.storage.run_dir)
        self._user_stream_events: deque[dict[str, Any]] = deque()
        self._user_stream_open_orders_seeded = False
        self._user_stream_own_trades_seeded = False
        self._user_stream_status: dict[str, Any] = {}
        self._lifecycle_proof_summary: dict[str, Any] = {
            "enabled": bool(self.settings.execution.kraken_spot.lifecycle_proof_enabled),
            "requested": False,
            "mode_active": False,
            "submitted": False,
            "exchange_acknowledged": False,
            "rest_query_confirmed": False,
            "terminal_observed": False,
            "reconciliation_complete": False,
            "upgrade_eligible": False,
            "submit_source": "",
            "reject_source": "",
            "last_terminal_state": "",
            "last_reason": "",
            "last_client_order_id": "",
            "last_order_id": "",
        }
        self.user_stream_connected = False
        self.supports_replace = False
        self.supports_expire = True
        self._userref_to_client_order_id: dict[str, str] = {}
        self._user_stream = user_stream
        if self._user_stream is None and hasattr(self.connector, "get_websockets_token"):
            self._user_stream = KrakenSpotUserStream(
                connector=self.connector,
                event_store=self._runtime_event_store,
                run_dir=self.settings.storage.run_dir,
                ws_private_url=self.settings.execution.kraken_spot.ws_private_url,
                on_order_update=self._queue_user_stream_order_update,
                on_fill_update=self._queue_user_stream_fill_update,
                on_state_change=self._handle_user_stream_state_change,
            )

    def _doctrine(self) -> dict[str, Any]:
        doctrine = getattr(self.settings, "doctrine", None)
        return {
            "target_provider": str(getattr(doctrine, "target_provider", "") or self.settings.execution.provider_id),
            "product_target": str(getattr(doctrine, "product_target", "") or "spot"),
            "long_only": bool(getattr(doctrine, "long_only", False)),
            "never_open_new_short_exposure": bool(getattr(doctrine, "never_open_new_short_exposure", False)),
            "minimum_sell_net_profit_bps": float(getattr(doctrine, "minimum_sell_net_profit_bps", 120.0) or 120.0),
            "enforce_cost_basis_sell_block": bool(getattr(doctrine, "enforce_cost_basis_sell_block", False)),
            "enforce_net_profit_sell_block": bool(getattr(doctrine, "enforce_net_profit_sell_block", False)),
            "block_non_reduce_only_sells": bool(getattr(doctrine, "block_non_reduce_only_sells", False)),
        }

    def _handle_user_stream_state_change(self, payload: dict[str, Any]) -> None:
        self._user_stream_status = dict(payload or {})
        self.user_stream_connected = bool(self._user_stream_status.get("connected", False))
        self._user_stream_open_orders_seeded = bool(self._user_stream_status.get("open_orders_seeded", False))
        self._user_stream_own_trades_seeded = bool(self._user_stream_status.get("own_trades_seeded", False))

    def _queue_user_stream_order_update(self, payload: dict[str, Any]) -> None:
        self._user_stream_events.append({"kind": "order", "payload": dict(payload or {})})

    def _queue_user_stream_fill_update(self, payload: dict[str, Any]) -> None:
        self._user_stream_events.append({"kind": "fill", "payload": dict(payload or {})})

    def _decorate_user_stream_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        decorated = dict(payload or {})
        raw = decorated.get("raw", {}) if isinstance(decorated.get("raw"), dict) else {}
        userref = str(raw.get("userref", "") or "")
        if userref and not decorated.get("clientOrderId"):
            decorated["clientOrderId"] = self._userref_to_client_order_id.get(userref, "")
        return decorated

    def _consume_user_stream_events(self) -> None:
        while self._user_stream_events:
            event = self._user_stream_events.popleft()
            kind = str(event.get("kind", "") or "")
            payload = dict(event.get("payload", {}) or {})
            if kind == "order":
                self.apply_order_update(self._decorate_user_stream_order(payload))
            elif kind == "fill":
                self.apply_fill_update(payload)

    def _refresh_user_stream_state(self) -> None:
        if self._user_stream is None:
            return
        self.user_stream_connected = bool(self._user_stream.connected)
        self._user_stream_open_orders_seeded = bool(self._user_stream.open_orders_seeded)
        self._user_stream_status = dict(self._user_stream.status())
        self._consume_user_stream_events()

    def _ensure_user_stream_connected(self, *, wait_s: float | None = None) -> bool:
        if self._user_stream is None or not bool(self.connector.has_credentials):
            return False
        self._user_stream.open()
        timeout = self.settings.execution.kraken_spot.user_stream_connect_timeout_s if wait_s is None else wait_s
        connected = self._user_stream.wait_until_connected(timeout)
        self._refresh_user_stream_state()
        return bool(connected)

    def _doctrine_ready(self) -> tuple[bool, str]:
        doctrine = self._doctrine()
        if doctrine["target_provider"] != "kraken_spot":
            return False, "doctrine_target_provider_not_kraken_spot"
        if doctrine["product_target"] != "spot":
            return False, "doctrine_product_target_not_spot"
        if not doctrine["long_only"]:
            return False, "doctrine_long_only_disabled"
        if not doctrine["never_open_new_short_exposure"]:
            return False, "doctrine_short_exposure_lock_disabled"
        if not doctrine["enforce_cost_basis_sell_block"]:
            return False, "doctrine_cost_basis_sell_block_disabled"
        if not doctrine["enforce_net_profit_sell_block"]:
            return False, "doctrine_net_profit_sell_block_disabled"
        if not doctrine["block_non_reduce_only_sells"]:
            return False, "doctrine_non_reduce_sell_block_disabled"
        if float(doctrine["minimum_sell_net_profit_bps"]) < 120.0:
            return False, "doctrine_minimum_sell_profit_floor_below_120bps"
        if not bool(getattr(self.settings.harmony, "enabled", False)):
            return False, "harmony_disabled"
        if not bool(getattr(self.settings.market_watch, "enabled", False)):
            return False, "market_watch_disabled"
        return True, "ok"

    def preflight(self) -> tuple[bool, str]:
        if "kraken_spot" not in self.settings.provider_whitelist:
            return False, "provider_not_whitelisted"
        doctrine_ok, doctrine_reason = self._doctrine_ready()
        if not doctrine_ok:
            return False, doctrine_reason
        mode = self.settings.execution_mode_enum()
        if mode == ExecutionMode.LIVE_READONLY:
            return True, "readonly"
        if not self.connector.has_credentials:
            return False, "missing_credentials"
        ok_perm, reason_perm = self.connector.verify_live_permissions()
        if not ok_perm:
            return False, reason_perm
        self._auth_validated = True
        if self.settings.risk.leverage != 0:
            return False, "risk_leverage_must_be_zero"
        self._ensure_user_stream_connected()
        info = self.connector.exchange_info()
        symbol_rows = {
            str(s.get("symbol", "")): s
            for s in info.get("symbols", [])
            if isinstance(s, dict)
        }
        for symbol in self.settings.universe:
            row = symbol_rows.get(symbol)
            if row is None:
                return False, f"symbol_missing:{symbol}"
            if not bool(row.get("active", False)) or not bool(row.get("spot", False)):
                return False, f"symbol_not_active_spot:{symbol}"
            constraints = self.connector.market_constraints(symbol)
            if not bool(constraints.get("active", False)) or not bool(constraints.get("spot", False)):
                return False, f"symbol_constraints_invalid:{symbol}"
            bal = self.connector.base_balance(symbol)
            if float(bal.get("total", 0.0) or 0.0) > max(1e-9, float(constraints.get("min_order_size", 0.0) or 0.0)):
                inventory = self._authoritative_inventory_state(symbol)
                if not inventory["ok"]:
                    return False, f"inventory_truth_invalid:{symbol}:{inventory['reason']}"
        return True, "ok"

    def _client_order_id(self, symbol: str, side: str, ts: float, slice_idx: int = 0) -> str:
        base = f"{self.run_id}|kraken_spot|{symbol}|{side}|{int(ts)}|{slice_idx}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]

    def _client_order_userref(self, client_order_id: str) -> int:
        if hasattr(self.connector, "client_order_userref"):
            return int(self.connector.client_order_userref(client_order_id))
        digest = hashlib.sha256(client_order_id.encode("utf-8")).hexdigest()[:8]
        return max(1, int(digest, 16))

    def _evict_dedupes(self, now: float) -> None:
        for store in (self._recent_cids, self._recent_intents):
            for k, t in list(store.items()):
                if now - t > self._dedupe_ttl_s:
                    del store[k]

    def _is_rate_limit_error(self, reason: str) -> bool:
        msg = reason.lower()
        return "429" in msg or "too many" in msg or "rate limit" in msg

    def _rate_limit_guard(self, reason: str, cid: str | None = None) -> LiveExecutionResult:
        now = time.time()
        self.rate_limits.add_hit(now)
        self._private_api_healthy = False
        if self.rate_limits.storm(max_hits=3):
            self.request_kill("rate_limit_storm")
            return LiveExecutionResult(status="killed", reason="rate_limit_storm", order={"clientOrderId": cid} if cid else None)
        return LiveExecutionResult(status="rejected", reason=reason, order={"clientOrderId": cid} if cid else None)

    def _reject_guard(self, reason: str, cid: str | None = None) -> LiveExecutionResult:
        if self._is_rate_limit_error(reason):
            return self._rate_limit_guard(reason, cid=cid)
        now = time.time()
        self.rejects.add_reject(now)
        if self.rejects.reject_storm(max_rejects=5):
            self.request_kill("reject_storm")
            return LiveExecutionResult(status="killed", reason="reject_storm", order={"clientOrderId": cid} if cid else None)
        return LiveExecutionResult(status="rejected", reason=reason, order={"clientOrderId": cid} if cid else None)

    def request_kill(self, reason: str = "operator_kill") -> None:
        self.killed = True
        self.safe_mode = True
        self.kill_reason = reason
        self.cooldown_until_s = max(self.cooldown_until_s, time.time() + 300)

    def enter_flatten_only(self, reason: str = "flatten_only") -> None:
        self.flatten_only = True
        self.safe_mode = True
        self.kill_reason = reason

    def freeze_new_openings(self, reason: str = "operator_freeze_only") -> tuple[bool, str]:
        ordering_ok, ordering_reason = self._ordering_authorized()
        if not ordering_ok:
            return False, ordering_reason
        self.enter_flatten_only(reason)
        self._flatten_history.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "action": "freeze_only",
                "reason": reason,
                "scope": "all",
            }
        )
        return True, reason

    def _status_rank(self, status: str) -> int:
        ranks = {
            "NEW": 1,
            "PARTIALLY_FILLED": 2,
            "FILLED": 3,
            "CANCELED": 3,
            "REJECTED": 3,
            "EXECUTED": 3,
            "CLOSED": 3,
        }
        return ranks.get(str(status).upper(), 0)

    def _normalize_order_update(self, order: dict[str, Any]) -> dict[str, Any]:
        return {
            "clientOrderId": str(order.get("clientOrderId", order.get("cliOrdId", order.get("clOrdId", "")))),
            "orderId": str(order.get("orderId", order.get("order_id", ""))),
            "status": str(order.get("status", "NEW")).upper(),
            "symbol": str(order.get("symbol", "")),
            "raw": order,
        }

    def capture_market_integrity_evidence(self, book: dict[str, Any], now_dt: Any) -> None:
        prior = dict(self._market_integrity_state)
        raw_ts = book.get("ts") or book.get("timestamp") or book.get("event_time") or now_dt
        ts = raw_ts.isoformat() if hasattr(raw_ts, "isoformat") else raw_ts
        bid = str(book.get("bidPrice", ""))
        ask = str(book.get("askPrice", ""))
        bid_qty = str(book.get("bidQty", ""))
        ask_qty = str(book.get("askQty", ""))
        signature = f"{bid}|{ask}|{bid_qty}|{ask_qty}"
        capture_ts = float(now_dt.timestamp()) if hasattr(now_dt, "timestamp") else float(now_dt if isinstance(now_dt, (int, float)) else time.time())
        if signature == self._last_book_signature:
            self._book_repeat_count += 1
        else:
            self._book_repeat_count = 0
            self._last_book_signature = signature
            self._last_book_change_ts = capture_ts
        sequence_ok = bool(book.get("sequence_ok", book.get("sequenceOk", True)))
        checksum_ok = bool(book.get("checksum_ok", book.get("checksumOk", True)))
        gap_count = int(book.get("gap_count", 0) or 0)
        checksum_mismatch_count = int(book.get("checksum_mismatch_count", 0) or 0)
        if not sequence_ok:
            gap_count = max(gap_count, int(prior.get("gap_count", 0) or 0) + 1)
        if not checksum_ok:
            checksum_mismatch_count = max(checksum_mismatch_count, int(prior.get("checksum_mismatch_count", 0) or 0) + 1)
        self._market_integrity_state = {
            "ts": ts,
            "sequence_ok": sequence_ok,
            "checksum_ok": checksum_ok,
            "gap_count": gap_count,
            "checksum_mismatch_count": checksum_mismatch_count,
        }

    def market_integrity_evidence(self, now_dt: Any | None = None) -> dict[str, Any]:
        if hasattr(now_dt, "timestamp"):
            now_ts = float(now_dt.timestamp())
        else:
            now_ts = float(now_dt if isinstance(now_dt, (int, float)) else time.time())
        self._refresh_user_stream_state()
        return {
            **dict(self._market_integrity_state),
            "user_stream_connected": self.user_stream_connected,
            "supports_replace": self.supports_replace,
            "supports_expire": self.supports_expire,
            "public_market_data_connected": bool(self._market_integrity_state.get("ts") is not None),
            "private_api_healthy": self._private_api_healthy,
            "auth_validated": self._auth_validated,
            "book_repeat_count": self._book_repeat_count,
            "seconds_since_distinct_book_change": 0.0
            if self._last_book_change_ts is None
            else max(0.0, now_ts - self._last_book_change_ts),
        }

    def capability_evidence(self, now_dt: Any | None = None) -> dict[str, Any]:
        self._refresh_user_stream_state()
        evidence = self.market_integrity_evidence(now_dt=now_dt)
        lifecycle_snapshot = self.lifecycle_snapshot()
        proof = self.lifecycle_proof_summary()
        quote_balance = self.connector.quote_balance(self.settings.universe[0]) if hasattr(self.connector, "quote_balance") and self.settings.universe else {}
        lifecycle_snapshot_count = len(lifecycle_snapshot)
        lifecycle_seeded = self._user_stream_open_orders_seeded or lifecycle_snapshot_count > 0
        reasons: list[str] = []
        partial = False
        if not self.user_stream_connected and not bool(proof.get("upgrade_eligible", False)):
            reasons.append("user_stream_not_connected")
            partial = True
        if not lifecycle_seeded:
            reasons.append("lifecycle_snapshot_absent")
            partial = True
        elif not bool(proof.get("upgrade_eligible", False)):
            reasons.append("lifecycle_proof_incomplete")
        if not bool(evidence.get("public_market_data_connected", False)):
            reasons.append("public_market_data_not_connected")
            partial = True
        if not bool(self._private_api_healthy):
            reasons.append("private_api_health_degraded")
            partial = True
        if bool(self.connector.has_credentials) and not bool(self._auth_validated):
            reasons.append("auth_validation_unproven")
            partial = True
        classifications = {
            "execution_blocker": [reason for reason in reasons if reason in {"private_api_health_degraded", "auth_validation_unproven"}],
            "promotion_blocker": [reason for reason in reasons if reason in {"user_stream_not_connected", "lifecycle_snapshot_absent", "lifecycle_proof_incomplete"}],
            "confidence_haircut": [reason for reason in reasons if reason in {"public_market_data_not_connected"}],
            "informational_only": [],
        }
        return {
            "ts": evidence.get("ts"),
            "user_stream_connected": self.user_stream_connected,
            "lifecycle_snapshot_count": lifecycle_snapshot_count,
            "lifecycle_snapshot_seeded": lifecycle_seeded,
            "sequence_ok": bool(evidence.get("sequence_ok", True)),
            "checksum_ok": bool(evidence.get("checksum_ok", True)),
            "replace_support_evidence": "dynamic",
            "expire_support_evidence": "dynamic",
            "auth_validated": self._auth_validated,
            "private_api_healthy": self._private_api_healthy,
            "public_market_data_connected": bool(evidence.get("public_market_data_connected", False)),
            "book_repeat_count": int(evidence.get("book_repeat_count", 0) or 0),
            "seconds_since_distinct_book_change": float(evidence.get("seconds_since_distinct_book_change", 0.0) or 0.0),
            "has_credentials": bool(self.connector.has_credentials),
            "supports_live_trading": bool(getattr(self.connector, "supports_live_trading", False)),
            "single_process_scope": True,
            "rest_lifecycle_proven": bool(proof.get("upgrade_eligible", False)),
            "lifecycle_reconciliation_complete": bool(proof.get("reconciliation_complete", False)),
            "lifecycle_proof_complete": bool(proof.get("upgrade_eligible", False)),
            "ws_lifecycle_observability": bool(self.user_stream_connected and lifecycle_seeded),
            "reasons": reasons,
            "partial": partial,
            "classifications": classifications,
            "lifecycle_proof_mode": "local_submit_plus_rest_query"
            if bool(proof.get("requested", False))
            else ("rest_truth_without_local_lifecycle" if not lifecycle_snapshot else "local_observed_without_full_proof"),
            "lifecycle_proof_summary": proof,
            "quote_asset": str(quote_balance.get("asset", "") or ""),
            "quote_total_balance": float(quote_balance.get("total", 0.0) or 0.0),
            "quote_free_balance": float(quote_balance.get("free", 0.0) or 0.0),
            "quote_used_balance": float(quote_balance.get("used", 0.0) or 0.0),
            "user_stream_status": dict(self._user_stream_status),
        }

    def _lifecycle_proof_requested(self, intent: OrderIntent) -> bool:
        if not bool(self.settings.execution.kraken_spot.lifecycle_proof_enabled):
            return False
        if not isinstance(intent.why, dict):
            return False
        payload = intent.why.get("lifecycle_proof", {})
        return isinstance(payload, dict) and bool(payload.get("enabled", False))

    def _proof_payload(self, intent: OrderIntent) -> dict[str, Any]:
        if not isinstance(intent.why, dict):
            return {}
        payload = intent.why.get("lifecycle_proof", {})
        return payload if isinstance(payload, dict) else {}

    def _lifecycle_proof_timeout_s(self) -> int:
        return max(0, int(self.settings.execution.kraken_spot.lifecycle_proof_timeout_s))

    def _lifecycle_proof_max_notional(self) -> float:
        return max(0.0, float(self.settings.execution.kraken_spot.lifecycle_proof_max_notional))

    def _effective_min_free_quote_reserve_pct(self, intent: OrderIntent) -> tuple[float, str, float]:
        configured_pct = max(0.0, float(self.settings.policy.min_free_quote_reserve_pct))
        override = self.settings.execution.kraken_spot.lifecycle_proof_min_free_quote_reserve_pct
        if (
            self._lifecycle_proof_requested(intent)
            and str(self.settings.execution.provider_id) == "kraken_spot"
            and str(self.settings.rollout_stage().value) == "tiny_live"
            and str(intent.side).lower() == "buy"
            and override is not None
        ):
            applied_pct = min(configured_pct, max(0.0, float(override)))
            return applied_pct, "tiny_live_lifecycle_proof_override", configured_pct
        return configured_pct, "policy_default", configured_pct

    def _update_lifecycle_proof(self, **fields: Any) -> None:
        self._lifecycle_proof_summary.update({k: v for k, v in fields.items()})
        self._lifecycle_proof_summary["enabled"] = bool(self.settings.execution.kraken_spot.lifecycle_proof_enabled)
        self._lifecycle_proof_summary["lifecycle_snapshot_count"] = len(self.lifecycle_snapshot())
        self._lifecycle_proof_summary["upgrade_eligible"] = bool(
            self._lifecycle_proof_summary.get("submitted", False)
            and self._lifecycle_proof_summary.get("exchange_acknowledged", False)
            and self._lifecycle_proof_summary.get("terminal_observed", False)
            and self._lifecycle_proof_summary.get("reconciliation_complete", False)
            and self._lifecycle_proof_summary.get("lifecycle_snapshot_count", 0) > 0
        )

    def lifecycle_proof_summary(self) -> dict[str, Any]:
        summary = dict(self._lifecycle_proof_summary)
        summary["lifecycle_snapshot_count"] = len(self.lifecycle_snapshot())
        summary["upgrade_eligible"] = bool(
            summary.get("submitted", False)
            and summary.get("exchange_acknowledged", False)
            and summary.get("terminal_observed", False)
            and summary.get("reconciliation_complete", False)
            and summary.get("lifecycle_snapshot_count", 0) > 0
        )
        return summary

    def _result_metadata(self, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = {
            "lifecycle_proof": self.lifecycle_proof_summary(),
            "capability_evidence": self.capability_evidence(),
        }
        if extra:
            metadata.update({k: v for k, v in extra.items()})
        return metadata

    def record_lifecycle_reconciliation(
        self,
        *,
        result_status: str,
        fill_truth_ok: bool,
        gap_reasons: list[str],
    ) -> dict[str, Any]:
        terminal = bool(self._lifecycle_proof_summary.get("terminal_observed", False))
        reconciliation_ok = terminal and (
            (result_status in {"filled_maker", "filled_taker_fallback", "filled_marketable_limit"} and fill_truth_ok and not gap_reasons)
            or result_status not in {"filled_maker", "filled_taker_fallback", "filled_marketable_limit"}
        )
        self._update_lifecycle_proof(
            reconciliation_complete=reconciliation_ok,
            last_reason="reconciliation_complete" if reconciliation_ok else (";".join(gap_reasons) if gap_reasons else result_status),
        )
        return self.lifecycle_proof_summary()

    def apply_order_update(self, order: dict[str, Any]) -> tuple[bool, str]:
        normalized = self._normalize_order_update(order)
        key = normalized["clientOrderId"] or normalized["orderId"]
        if not key:
            return False, "missing_order_id"
        raw = normalized.get("raw", {}) if isinstance(normalized.get("raw"), dict) else {}
        userref = str(raw.get("userref", "") or "")
        if userref and normalized["clientOrderId"]:
            self._userref_to_client_order_id[userref] = str(normalized["clientOrderId"])
        prior = self._order_status_by_id.get(key)
        if prior is not None and self._status_rank(normalized["status"]) < self._status_rank(prior):
            return False, "out_of_order_order_update"
        self._order_status_by_id[key] = normalized["status"]
        lifecycle_ok, lifecycle_reason = self._lifecycle.apply_exchange_update(normalized)
        status = str(normalized["status"]).upper()
        self._update_lifecycle_proof(
            exchange_acknowledged=status not in {"", "REJECTED"},
            last_client_order_id=str(normalized["clientOrderId"]),
            last_order_id=str(normalized["orderId"]),
            terminal_observed=status in {"FILLED", "CANCELED", "CANCELLED", "REJECTED", "EXPIRED", "EXECUTED", "CLOSED"},
            last_terminal_state=status if status in {"FILLED", "CANCELED", "CANCELLED", "REJECTED", "EXPIRED", "EXECUTED", "CLOSED"} else self._lifecycle_proof_summary.get("last_terminal_state", ""),
            last_reason=status.lower(),
        )
        return (True, "ok") if lifecycle_ok else (False, "out_of_order_order_update" if lifecycle_reason == "out_of_order_lifecycle_event" else lifecycle_reason)

    def apply_fill_update(self, fill: dict[str, Any]) -> tuple[bool, str]:
        fill_id = str(fill.get("fill_id", fill.get("fillId", fill.get("id", ""))))
        if not fill_id:
            return False, "missing_fill_id"
        if fill_id in self._fill_ids_seen:
            return False, "duplicate_fill_update"
        notional = float(fill.get("notional", fill.get("filledNotional", fill.get("quoteQty", 0.0))))
        if notional <= 0.0:
            return False, "non_positive_fill_notional"
        self._fill_ids_seen.add(fill_id)
        order_key = str(fill.get("order_id", fill.get("orderId", "")))
        if order_key:
            self._lifecycle.note_fill(order_key=order_key)
        return True, "ok"

    def rehydrate_state(self, order_events: list[dict[str, Any]], fill_events: list[dict[str, Any]]) -> dict[str, int]:
        self._order_status_by_id = {}
        self._fill_ids_seen = set()
        self._lifecycle.reset()
        order_count = 0
        fill_count = 0
        for event in order_events:
            payload = event.get("payload", event) if isinstance(event, dict) else {}
            if isinstance(payload, dict):
                ok, _ = self.apply_order_update(payload)
                if ok:
                    order_count += 1
        for event in fill_events:
            payload = event.get("payload", event) if isinstance(event, dict) else {}
            if isinstance(payload, dict):
                ok, _ = self.apply_fill_update(payload)
                if ok:
                    fill_count += 1
        return {"orders": order_count, "fills": fill_count}

    def drain_lifecycle_transitions(self) -> list[dict[str, Any]]:
        self._consume_user_stream_events()
        return self._lifecycle.drain_transitions()

    def lifecycle_snapshot(self) -> list[dict[str, Any]]:
        self._consume_user_stream_events()
        return self._lifecycle.snapshot()

    def _all_trade_history(self, symbol: str, *, limit: int = 50, max_pages: int = 20) -> list[KrakenSpotTradeRow]:
        rows: list[KrakenSpotTradeRow] = []
        seen: set[str] = set()
        offset = 0
        for _ in range(max_pages):
            page = self.connector.trade_history(symbol, offset=offset, limit=limit)
            if not page:
                break
            new_rows = [row for row in page if row.trade_id not in seen]
            if not new_rows:
                break
            rows.extend(new_rows)
            for row in new_rows:
                seen.add(row.trade_id)
            if len(page) < limit:
                break
            offset += len(page)
        rows.sort(key=lambda item: (item.timestamp_ms, item.trade_id))
        return rows

    def _filtered_trade_history(
        self,
        symbol: str,
        *,
        side: str | None = None,
        order_id: str | None = None,
        since_ms: int | None = None,
    ) -> list[KrakenSpotTradeRow]:
        rows = self._all_trade_history(symbol)
        filtered: list[KrakenSpotTradeRow] = []
        for row in rows:
            if since_ms is not None and int(row.timestamp_ms) < int(since_ms):
                continue
            if order_id is not None and str(row.order_id) != str(order_id):
                continue
            if side is not None and str(row.side).lower() != str(side).lower():
                continue
            filtered.append(row)
        return filtered

    def _inventory_balance_state(self, symbol: str) -> dict[str, Any]:
        balance = self.connector.base_balance(symbol)
        constraints = self.connector.market_constraints(symbol)
        total_qty = float(balance.get("total", 0.0) or 0.0)
        free_qty = float(balance.get("free", 0.0) or 0.0)
        min_qty = float(constraints.get("min_order_size", 0.0) or 0.0)
        tolerance = max(1e-8, min_qty, total_qty * 0.02)
        return {
            "total_qty": total_qty,
            "free_qty": free_qty,
            "tolerance_qty": tolerance,
            "flat": abs(total_qty) <= tolerance,
        }

    def _reconstruct_inventory_state(self, symbol: str) -> dict[str, Any]:
        rows = self._all_trade_history(symbol)
        lots: list[dict[str, float]] = []
        realized_total = 0.0
        for row in rows:
            qty = float(row.base_qty or 0.0)
            if qty <= 0.0:
                continue
            if row.side == "buy":
                unit_cost = (float(row.quote_cost) + float(row.fee_quote)) / max(qty, 1e-12)
                lots.append({"qty": qty, "unit_cost": unit_cost})
                continue
            if row.side != "sell":
                continue
            remaining = qty
            basis_quote = 0.0
            while remaining > 1e-12 and lots:
                head = lots[0]
                consume = min(remaining, head["qty"])
                basis_quote += consume * head["unit_cost"]
                head["qty"] -= consume
                remaining -= consume
                if head["qty"] <= 1e-12:
                    lots.pop(0)
            if remaining > 1e-9:
                return {
                    "ok": False,
                    "reason": "trade_history_sell_exceeds_buys",
                    "lots": [],
                    "remaining_qty": 0.0,
                    "remaining_basis_quote": 0.0,
                    "avg_cost_quote": None,
                }
            realized_total += float(row.quote_cost) - float(row.fee_quote) - basis_quote
        remaining_qty = sum(float(lot["qty"]) for lot in lots)
        remaining_basis_quote = sum(float(lot["qty"]) * float(lot["unit_cost"]) for lot in lots)
        avg_cost = None if remaining_qty <= 1e-12 else remaining_basis_quote / remaining_qty
        return {
            "ok": True,
            "reason": "ok",
            "lots": lots,
            "remaining_qty": remaining_qty,
            "remaining_basis_quote": remaining_basis_quote,
            "avg_cost_quote": avg_cost,
            "realized_total_quote": realized_total,
            "trade_count": len(rows),
            "history_rows": rows,
        }

    def _authoritative_inventory_state(self, symbol: str) -> dict[str, Any]:
        state = self._reconstruct_inventory_state(symbol)
        if not state["ok"]:
            return state
        try:
            inventory_balance = self._inventory_balance_state(symbol)
        except Exception as exc:
            return {**state, "ok": False, "reason": f"balance_or_constraints_error:{exc}"}
        total_qty = float(inventory_balance["total_qty"])
        tolerance = float(inventory_balance["tolerance_qty"])
        if abs(total_qty - float(state["remaining_qty"])) > tolerance:
            return {
                **state,
                "ok": False,
                "reason": "inventory_balance_history_mismatch",
                "balance_total_qty": total_qty,
                "balance_free_qty": float(inventory_balance["free_qty"]),
                "tolerance_qty": tolerance,
            }
        return {
            **state,
            "balance_total_qty": total_qty,
            "balance_free_qty": float(inventory_balance["free_qty"]),
        }

    def _basis_quote_for_qty(self, symbol: str, qty: float) -> tuple[float | None, list[str]]:
        state = self._authoritative_inventory_state(symbol)
        if not state["ok"]:
            return None, [str(state["reason"])]
        remaining = qty
        total_basis = 0.0
        for lot in state["lots"]:
            if remaining <= 1e-12:
                break
            consume = min(remaining, float(lot["qty"]))
            total_basis += consume * float(lot["unit_cost"])
            remaining -= consume
        if remaining > 1e-9:
            return None, ["requested_sell_qty_exceeds_authoritative_inventory"]
        return total_basis, []

    def authoritative_fill_history(
        self,
        symbol: str,
        *,
        side: str,
        order_id: str | None = None,
        client_order_id: str | None = None,  # noqa: ARG002
        since_ms: int | None = None,
    ) -> tuple[list[NormalizedLiveFillRecord], list[str]]:
        direct_rows = self._filtered_trade_history(
            symbol,
            side=side,
            order_id=order_id,
            since_ms=since_ms,
        )
        if not direct_rows:
            return ([], ["execution_history_empty"]) if order_id is not None else ([], [])
        if str(side).lower() != "sell":
            records = [
                _build_normalized_fill(
                    venue="kraken_spot",
                    symbol=symbol,
                    side=row.side,
                    order_id=str(row.order_id),
                    fill_id=str(row.trade_id),
                    notional=float(row.quote_cost),
                    fee=float(row.fee_quote),
                    latency_ms=0,
                    status="FILLED",
                    realized_pnl=0.0,
                    fee_authoritative=True,
                    realized_pnl_authoritative=False,
                    metadata={
                        "timestamp_ms": int(row.timestamp_ms),
                        "price": float(row.price),
                        "base_qty": float(row.base_qty),
                    },
                    truth_evidence={"source": "kraken_spot_trade_history"},
                )
                for row in direct_rows
            ]
            return records, []
        state = self._reconstruct_inventory_state(symbol)
        if not state["ok"]:
            return [], [str(state["reason"])]
        records: list[NormalizedLiveFillRecord] = []
        gaps: list[str] = []
        lots: list[dict[str, float]] = []
        for row in state["history_rows"]:
            qty = float(row.base_qty or 0.0)
            if qty <= 0.0:
                continue
            if row.side == "buy":
                unit_cost = (float(row.quote_cost) + float(row.fee_quote)) / max(qty, 1e-12)
                lots.append({"qty": qty, "unit_cost": unit_cost})
            elif row.side == "sell":
                remaining = qty
                basis_quote = 0.0
                while remaining > 1e-12 and lots:
                    head = lots[0]
                    consume = min(remaining, head["qty"])
                    basis_quote += consume * head["unit_cost"]
                    head["qty"] -= consume
                    remaining -= consume
                    if head["qty"] <= 1e-12:
                        lots.pop(0)
                if remaining > 1e-9:
                    gaps.append("trade_history_sell_exceeds_buys")
                    break
            else:
                continue
            if since_ms is not None and int(row.timestamp_ms) < int(since_ms):
                continue
            if order_id is not None and str(row.order_id) != str(order_id):
                continue
            if str(row.side).lower() != str(side).lower():
                continue
            realized_pnl = 0.0
            realized_authoritative = False
            if row.side == "sell":
                realized_pnl = float(row.quote_cost) - float(row.fee_quote) - basis_quote
                realized_authoritative = True
            records.append(
                _build_normalized_fill(
                    venue="kraken_spot",
                    symbol=symbol,
                    side=row.side,
                    order_id=str(row.order_id),
                    fill_id=str(row.trade_id),
                    notional=float(row.quote_cost),
                    fee=float(row.fee_quote),
                    latency_ms=0,
                    status="FILLED",
                    realized_pnl=realized_pnl,
                    fee_authoritative=True,
                    realized_pnl_authoritative=realized_authoritative,
                    metadata={
                        "timestamp_ms": int(row.timestamp_ms),
                        "price": float(row.price),
                        "base_qty": float(row.base_qty),
                    },
                    truth_evidence={"source": "kraken_spot_trade_history"},
                )
            )
        if not records:
            return ([], ["execution_history_empty"]) if order_id is not None else ([], list(sorted(set(gaps))))
        return records, sorted(set(gaps))

    def authoritative_realized_pnl(self, symbol: str, *, since_ms: int | None = None) -> tuple[float | None, list[str]]:
        records, gaps = self.authoritative_fill_history(symbol, side="sell", since_ms=since_ms)
        if not records:
            return (None, gaps) if gaps else (0.0, [])
        return sum(float(record.realized_pnl) for record in records), gaps

    def authoritative_unrealized_pnl(self, symbol: str):
        try:
            inventory_balance = self._inventory_balance_state(symbol)
        except Exception as exc:
            return None, [f"balance_or_constraints_error:{exc}"]
        if bool(inventory_balance["flat"]):
            return UnrealizedPnlTruth(
                symbol=symbol,
                ts=datetime.now(timezone.utc),
                source="spot_balance_flat",
                confidence="authoritative",
                venue_value=0.0,
                reason="no_open_spot_inventory",
                evidence={
                    "remaining_qty": float(inventory_balance["total_qty"]),
                    "tolerance_qty": float(inventory_balance["tolerance_qty"]),
                },
            ), []
        state = self._authoritative_inventory_state(symbol)
        if not state["ok"]:
            return None, [str(state["reason"])]
        qty = float(state.get("balance_total_qty", 0.0) or 0.0)
        book = self.connector.book_ticker(symbol)
        bid = float(book.get("bidPrice", 0.0) or 0.0)
        if not math.isfinite(bid) or bid <= 0.0:
            return None, ["book_invalid_for_unrealized_pnl"]
        venue_value = qty * bid - float(state.get("remaining_basis_quote", 0.0) or 0.0)
        return UnrealizedPnlTruth(
            symbol=symbol,
            ts=datetime.now(timezone.utc),
            source="spot_trade_history_and_balance",
            confidence="authoritative",
            venue_value=venue_value,
            reason="fifo_cost_basis_and_live_bid",
            evidence={
                "remaining_qty": qty,
                "remaining_basis_quote": float(state.get("remaining_basis_quote", 0.0) or 0.0),
                "bid": bid,
            },
        ), []

    def _ledger_records_from_order(self, order: dict[str, Any], intent: OrderIntent) -> tuple[list[NormalizedLiveFillRecord], list[str]]:
        if not self._is_filled(order):
            return [], []
        order_id = str(order.get("orderId", order.get("order_id", order.get("raw", {}).get("order_id", ""))))
        records, gaps = self.authoritative_fill_history(
            intent.symbol,
            side=intent.side,
            order_id=order_id or None,
        )
        accepted_records: list[NormalizedLiveFillRecord] = []
        accepted_gaps = list(gaps)
        for record in records:
            accepted, accepted_reason = self.apply_fill_update({"fill_id": record.fill.fill_id, "notional": record.fill.notional, "order_id": record.fill.order_id})
            if not accepted:
                accepted_gaps.append(accepted_reason)
                continue
            accepted_records.append(record)
        return accepted_records, sorted(set(accepted_gaps))

    def _taker_fallback_edge_ok(self, intent: OrderIntent) -> bool:
        profitability = intent.why.get("profitability", {}) if isinstance(intent.why, dict) and isinstance(intent.why.get("profitability", {}), dict) else {}
        return float(profitability.get("net_edge_bps", 0.0) or 0.0) > 0.0

    def _intent_fingerprint(self, intent: OrderIntent) -> str:
        bucket = int(time.time() // 5)
        payload = f"{intent.symbol}|{intent.side}|{round(intent.target_notional, 6)}|{bucket}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def _book_prices(self, symbol: str) -> tuple[float, float]:
        book = self.connector.book_ticker(symbol)
        bid = float(book.get("bidPrice", 0.0) or 0.0)
        ask = float(book.get("askPrice", 0.0) or 0.0)
        if not math.isfinite(bid) or not math.isfinite(ask) or bid <= 0.0 or ask <= 0.0:
            raise ValueError(f"book_invalid:{bid}:{ask}")
        return bid, ask

    def _reduce_only(self, intent: OrderIntent) -> bool:
        if not isinstance(intent.why, dict):
            return False
        return bool(intent.why.get("reduce_only", False))

    def _market_watch_action(self, intent: OrderIntent) -> str:
        if not isinstance(intent.why, dict):
            return "continue"
        market_watch = intent.why.get("market_watch", {})
        if not isinstance(market_watch, dict):
            return "continue"
        return str(market_watch.get("action", "continue") or "continue")

    def _market_integrity_action(self, intent: OrderIntent) -> str:
        if not isinstance(intent.why, dict):
            return "continue"
        integrity = intent.why.get("market_integrity", {})
        if not isinstance(integrity, dict):
            return "continue"
        return str(integrity.get("action", "continue") or "continue")

    def _execution_plan_payload(self, intent: OrderIntent) -> dict[str, Any]:
        if not isinstance(intent.why, dict):
            return {}
        payload = intent.why.get("execution_plan", {})
        return payload if isinstance(payload, dict) else {}

    def _requested_order_style(self, intent: OrderIntent) -> str:
        style = str(self._execution_plan_payload(intent).get("order_style", "passive_limit") or "passive_limit")
        if style not in {"limit", "passive_limit", "marketable_limit"}:
            return "passive_limit"
        return style

    def _doctrine_target_ok(self, intent: OrderIntent) -> tuple[bool, str]:
        payload = intent.why if isinstance(intent.why, dict) else {}
        target = payload.get("doctrine_target", {})
        if not isinstance(target, dict):
            target = {}
        provider = str(target.get("provider", self.settings.execution.provider_id) or self.settings.execution.provider_id)
        product = str(target.get("product", "spot") or "spot")
        if provider != "kraken_spot":
            return False, f"doctrine_target_provider_invalid:{provider}"
        if product != "spot":
            return False, f"doctrine_target_product_invalid:{product}"
        return True, "ok"

    def _ordering_authorized(self) -> tuple[bool, str]:
        if self.settings.execution_mode_enum() != ExecutionMode.LIVE:
            return False, f"ordering_not_allowed_in_mode:{self.settings.execution_mode_enum().value}"
        doctrine_ok, doctrine_reason = self._doctrine_ready()
        if not doctrine_ok:
            return False, doctrine_reason
        if not self._auth_validated:
            return False, "preflight_not_completed"
        return True, "ok"

    def _sell_profit_guard(self, intent: OrderIntent, qty: float, bid: float, ask: float) -> str | None:
        doctrine = self._doctrine()
        if not doctrine["block_non_reduce_only_sells"] or not doctrine["enforce_cost_basis_sell_block"] or not doctrine["enforce_net_profit_sell_block"]:
            return "sell_doctrine_guards_disabled"
        inventory = self._authoritative_inventory_state(intent.symbol)
        if not inventory["ok"]:
            return f"inventory_truth_missing:{inventory['reason']}"
        free_qty = float(inventory.get("balance_free_qty", 0.0) or 0.0)
        tolerance = max(1e-8, qty * 0.02)
        if qty > free_qty + tolerance:
            return f"insufficient_spot_inventory:{qty:.8f}>{free_qty:.8f}"
        basis_quote, gaps = self._basis_quote_for_qty(intent.symbol, qty)
        if basis_quote is None:
            return f"cost_basis_truth_missing:{','.join(gaps) if gaps else 'unknown'}"
        sell_quote = qty * bid
        if sell_quote <= basis_quote:
            return f"sell_below_cost_basis:{sell_quote:.8f}<={basis_quote:.8f}"
        spread_bps = ((ask - bid) / max((ask + bid) / 2.0, 1e-9)) * 10000.0
        modeled_cost_bps = float(self.settings.execution.fee_bps) + float(self.settings.execution.slippage_bps) + max(0.0, spread_bps)
        modeled_exit_cost_quote = sell_quote * modeled_cost_bps / 10000.0
        net_profit_quote = sell_quote - modeled_exit_cost_quote - basis_quote
        if net_profit_quote <= 0.0:
            return f"sell_net_profit_non_positive:{net_profit_quote:.8f}"
        net_profit_bps = (net_profit_quote / max(basis_quote, 1e-9)) * 10000.0
        if net_profit_bps < max(120.0, float(doctrine["minimum_sell_net_profit_bps"])):
            return f"sell_net_profit_floor_breach:{net_profit_bps:.4f}"
        return None

    def _pre_submit_validate_intent(self, intent: OrderIntent) -> tuple[str | None, dict[str, Any]]:
        ok_target, target_reason = self._doctrine_target_ok(intent)
        if not ok_target:
            return target_reason, {}
        side = str(intent.side).lower()
        if side not in {"buy", "sell"}:
            return f"invalid_order_side:{intent.side}", {}
        try:
            target_notional = float(intent.target_notional)
        except Exception:
            return "invalid_target_notional:non_numeric", {}
        if not math.isfinite(target_notional) or target_notional <= 0.0:
            return f"invalid_target_notional:{target_notional}", {}
        if self._market_watch_action(intent) == "block_entries" and not self._reduce_only(intent):
            return "market_watch_blocks_entries", {}
        if self._market_integrity_action(intent) in {"flatten_only", "halt"} and not self._reduce_only(intent):
            return "market_integrity_blocks_entries", {}
        try:
            constraints = self.connector.market_constraints(intent.symbol)
            bid, ask = self._book_prices(intent.symbol)
        except Exception as exc:
            return str(exc), {}
        if not bool(constraints.get("active", False)) or not bool(constraints.get("spot", False)):
            return f"invalid_spot_symbol_constraints:{intent.symbol}", {}
        maker_price = bid if side == "buy" else ask
        conservative_price = ask if side == "buy" else bid
        try:
            raw_qty = target_notional / max(conservative_price, 1e-12)
            qty = self.connector.normalize_amount(intent.symbol, raw_qty)
            price = self.connector.normalize_price(intent.symbol, maker_price)
        except Exception as exc:
            return str(exc), {}
        if not math.isfinite(qty) or qty <= 0.0:
            return f"invalid_quantity:{qty}", {}
        if not math.isfinite(price) or price <= 0.0:
            return f"invalid_price:{price}", {}
        min_qty = float(constraints.get("min_order_size", 0.0) or 0.0)
        min_notional = float(constraints.get("min_notional", 0.0) or 0.0)
        executable_notional = qty * conservative_price
        if qty < min_qty:
            return f"below_min_order_size:{qty:.8f}", {}
        if executable_notional < min_notional:
            return f"below_min_notional:{executable_notional:.8f}", {}
        affordability: dict[str, Any] = {}
        if side == "buy" and hasattr(self.connector, "quote_balance"):
            quote_balance = dict(self.connector.quote_balance(intent.symbol))
            quote_asset = str(quote_balance.get("asset", "") or "")
            quote_total = max(0.0, float(quote_balance.get("total", 0.0) or 0.0))
            quote_free = max(0.0, float(quote_balance.get("free", 0.0) or 0.0))
            quote_used = max(0.0, float(quote_balance.get("used", 0.0) or 0.0))
            required_quote = qty * max(price, conservative_price, 0.0)
            fee_buffer_quote = required_quote * (float(self.settings.execution.fee_bps) / 10000.0)
            precision_epsilon_quote = max(required_quote * 1e-6, float(constraints.get("price_tick", 0.0) or 0.0) * qty)
            applied_reserve_pct, reserve_policy_source, configured_reserve_pct = self._effective_min_free_quote_reserve_pct(intent)
            reserve_floor_quote = quote_total * applied_reserve_pct
            entry_buying_power_quote = max(0.0, quote_free - reserve_floor_quote)
            required_with_buffer = required_quote + fee_buffer_quote + precision_epsilon_quote
            affordability = {
                "quote_asset": quote_asset,
                "quote_total_balance": quote_total,
                "quote_free_balance": quote_free,
                "quote_used_balance": quote_used,
                "required_quote": required_quote,
                "fee_buffer_quote": fee_buffer_quote,
                "precision_epsilon_quote": precision_epsilon_quote,
                "reserve_floor_quote": reserve_floor_quote,
                "entry_buying_power_quote": entry_buying_power_quote,
                "required_quote_with_fee_buffer": required_with_buffer,
                "configured_minimum_reserve_pct": configured_reserve_pct,
                "applied_minimum_reserve_pct": applied_reserve_pct,
                "reserve_policy_source": reserve_policy_source,
            }
            if quote_free + 1e-9 < required_quote:
                return "insufficient_free_quote", {"affordability": affordability}
            if quote_free + 1e-9 < (required_quote + fee_buffer_quote):
                return "insufficient_free_quote_after_fee_buffer", {"affordability": affordability}
            if entry_buying_power_quote + 1e-9 < required_with_buffer:
                return "insufficient_free_quote_after_reserve", {"affordability": affordability}
        if side == "sell":
            if not self._reduce_only(intent):
                return "long_only_non_reduce_sell_block", {}
            sell_guard = self._sell_profit_guard(intent, qty, bid, ask)
            if sell_guard is not None:
                return sell_guard, {}
        return None, {
            "qty": qty,
            "maker_price": price,
            "conservative_price": conservative_price,
            "constraints": constraints,
            "affordability": affordability,
        }

    def _submit_limit_order(
        self,
        *,
        intent: OrderIntent,
        cid: str,
        now: float,
        fp: str,
        qty: float,
        price: float,
        post_only: bool,
        success_status: str,
        timeout_reason: str,
        timeout_s: int | None = None,
    ) -> LiveExecutionResult:
        preview_ok, preview_reason = self.connector.validate_order_preview(
            symbol=intent.symbol,
            side=str(intent.side),
            amount=qty,
            price=price,
            post_only=post_only,
        )
        if not preview_ok:
            self._lifecycle.rejected(symbol=intent.symbol, order_key=cid, error=preview_reason)
            self.request_kill(f"order_preview_failed:{preview_reason}")
            return LiveExecutionResult(status="killed", reason=f"order_preview_failed:{preview_reason}", metadata={"lifecycle_proof": self.lifecycle_proof_summary()})

        payload = {
            "symbol": intent.symbol,
            "side": str(intent.side).upper(),
            "quantity": f"{qty:.8f}",
            "newClientOrderId": cid,
            "type": "LIMIT",
            "price": f"{price:.8f}",
        }
        if post_only:
            payload["postOnly"] = True
        self._userref_to_client_order_id[str(self._client_order_userref(cid))] = cid
        try:
            placed = self.connector.place_order(payload)
            self.apply_order_update(placed)
            self._recent_cids[cid] = now
            self._recent_intents[fp] = now
            self._update_lifecycle_proof(
                submitted=True,
                mode_active=self._lifecycle_proof_requested(intent),
                requested=self._lifecycle_proof_requested(intent),
                submit_source="exchange_submit",
                reject_source="",
            )
        except Exception as exc:
            current = None
            try:
                current = self._query_existing(intent.symbol, cid)
            except Exception:
                current = None
            if current is not None:
                self.apply_order_update(current)
                self._update_lifecycle_proof(
                    submitted=True,
                    mode_active=self._lifecycle_proof_requested(intent),
                    requested=self._lifecycle_proof_requested(intent),
                    submit_source="exchange_query_repair",
                )
                ledger_records, gaps = self._ledger_records_from_order(current, intent)
                return LiveExecutionResult(
                    status="filled_maker" if self._is_filled(current) else "rejected",
                    reason=str(exc),
                    order=current,
                    ledger_records=ledger_records,
                    gaps=gaps,
                    metadata=self._result_metadata(
                        extra={
                            "execution_blocker": {
                                "code": f"{'maker' if post_only else 'marketable_limit'}_reject:{exc}",
                                "source": "exchange_submit_exception_with_rest_query",
                            }
                        }
                    ),
                )
            self._lifecycle.rejected(symbol=intent.symbol, order_key=cid, error=str(exc))
            self._update_lifecycle_proof(
                submitted=True,
                mode_active=self._lifecycle_proof_requested(intent),
                requested=self._lifecycle_proof_requested(intent),
                exchange_acknowledged=False,
                terminal_observed=True,
                last_terminal_state="REJECTED",
                last_reason=str(exc),
                submit_source="local_submit",
                reject_source="exchange_submit_exception",
            )
            out = self._reject_guard(f"{'maker' if post_only else 'marketable_limit'}_reject:{exc}", cid=cid)
            out.metadata = self._result_metadata(
                extra={
                    "execution_blocker": {
                        "code": f"{'maker' if post_only else 'marketable_limit'}_reject:{exc}",
                        "source": "exchange_submit_exception",
                    }
                }
            )
            return out

        if self._is_filled(placed):
            ledger_records, gaps = self._ledger_records_from_order(placed, intent)
            return LiveExecutionResult(
                status=success_status,
                order=placed,
                ledger_records=ledger_records,
                gaps=gaps,
                metadata=self._result_metadata(),
            )

        effective_timeout_s = max(0, int(self.settings.execution.maker_timeout_s if timeout_s is None else timeout_s))
        deadline = time.time() + effective_timeout_s
        while time.time() < deadline:
            current = self._query_existing(intent.symbol, cid)
            if current and self._is_filled(current):
                self.apply_order_update(current)
                ledger_records, gaps = self._ledger_records_from_order(current, intent)
                return LiveExecutionResult(
                    status=success_status,
                    order=current,
                    ledger_records=ledger_records,
                    gaps=gaps,
                    metadata=self._result_metadata(),
                )
            time.sleep(0.25)

        try:
            self._lifecycle.cancel_requested(symbol=intent.symbol, order_key=cid)
            self.connector.cancel_order(intent.symbol, cid)
            self.apply_order_update({"clientOrderId": cid, "symbol": intent.symbol, "status": "CANCELED"})
        except Exception as exc:
            self._lifecycle.cancel_rejected(symbol=intent.symbol, order_key=cid, error=str(exc))
            if self._is_rate_limit_error(str(exc)):
                out = self._rate_limit_guard(f"cancel_rate_limit:{exc}", cid=cid)
                out.metadata = self._result_metadata()
                return out
        self._lifecycle.timed_out(symbol=intent.symbol, order_key=cid)
        self._update_lifecycle_proof(
            terminal_observed=True,
            last_terminal_state="CANCELLED",
            last_reason=timeout_reason,
        )
        return LiveExecutionResult(
            status="timeout",
            reason=timeout_reason,
            order={"clientOrderId": cid, "symbol": intent.symbol},
            metadata=self._result_metadata(),
        )

    def _query_existing(self, symbol: str, client_order_id: str):
        try:
            current = self.connector.query_order(symbol, client_order_id)
            if current is not None:
                self._update_lifecycle_proof(rest_query_confirmed=True, last_reason="rest_query_confirmed")
            return current
        except Exception as exc:
            msg = str(exc).lower()
            if "not found" in msg or "unknown" in msg:
                return None
            raise

    def execute_readonly(self, intent: OrderIntent) -> LiveExecutionResult:
        if self.settings.execution_mode_enum() != ExecutionMode.LIVE_READONLY:
            return LiveExecutionResult(status="error", reason="not_readonly_mode")
        preview_error, preview_meta = self._pre_submit_validate_intent(intent)
        preview = {
            "symbol": intent.symbol,
            "side": intent.side,
            "target_notional": intent.target_notional,
            "book": self.connector.book_ticker(intent.symbol),
            "validation_error": preview_error,
            "validation": preview_meta,
        }
        return LiveExecutionResult(status="readonly_preview", order=preview)

    def _is_filled(self, order: dict[str, Any]) -> bool:
        return str(order.get("status", "")).upper() in {"FILLED", "PARTIALLY_FILLED", "EXECUTED", "CLOSED"}

    def execute_intent(self, intent: OrderIntent) -> LiveExecutionResult:
        self._refresh_user_stream_state()
        now = time.time()
        proof_mode = self._lifecycle_proof_requested(intent)
        if proof_mode:
            self._update_lifecycle_proof(
                requested=True,
                mode_active=True,
                reconciliation_complete=False,
                terminal_observed=False,
                submitted=False,
                exchange_acknowledged=False,
                rest_query_confirmed=False,
                last_reason="proof_requested",
                submit_source="",
                reject_source="",
            )
        if self.killed:
            return LiveExecutionResult(status="killed", reason=self.kill_reason or "kill_switch_active")
        if self.flatten_only and not self._reduce_only(intent):
            return LiveExecutionResult(status="blocked", reason="flatten_only")
        if self.safe_mode and not self._reduce_only(intent):
            return LiveExecutionResult(status="blocked", reason="safe_mode")
        if now < self.cooldown_until_s:
            return LiveExecutionResult(status="blocked", reason="cooldown")
        ordering_ok, ordering_reason = self._ordering_authorized()
        if not ordering_ok:
            self.request_kill(ordering_reason)
            return LiveExecutionResult(status="killed", reason=ordering_reason)
        self._ensure_user_stream_connected(wait_s=0.25)

        pre_submit_error, validation = self._pre_submit_validate_intent(intent)
        if pre_submit_error is not None:
            if str(pre_submit_error).startswith("insufficient_free_quote"):
                affordability = dict(validation.get("affordability", {}) or {})
                return LiveExecutionResult(
                    status="blocked",
                    reason=pre_submit_error,
                    metadata=self._result_metadata(
                        extra={
                            "execution_blocker": {
                                "code": pre_submit_error,
                                "source": "local_affordability_guard",
                                **affordability,
                                "free_quote_balance": affordability.get("quote_free_balance", 0.0),
                            }
                        }
                    ),
                )
            self.request_kill(pre_submit_error)
            return LiveExecutionResult(status="killed", reason=pre_submit_error)

        cid = self._client_order_id(intent.symbol, intent.side, now, 0)
        self._evict_dedupes(now)
        fp = self._intent_fingerprint(intent)
        if fp in self._recent_intents:
            return LiveExecutionResult(status="deduped", reason="intent_fingerprint_dedupe", order={"fingerprint": fp})
        if cid in self._recent_cids:
            return LiveExecutionResult(status="deduped", reason="local_dedupe", order={"clientOrderId": cid})

        existing = self._query_existing(intent.symbol, cid)
        if existing is not None:
            self.apply_order_update(existing)
            self._recent_cids[cid] = now
            self._recent_intents[fp] = now
            ledger_records, gaps = self._ledger_records_from_order(existing, intent)
            return LiveExecutionResult(status="deduped", order=existing, ledger_records=ledger_records, gaps=gaps, metadata=self._result_metadata())
        qty = float(validation["qty"])
        maker_price = float(validation["maker_price"])
        if proof_mode:
            open_orders = self.connector.open_orders()
            if isinstance(open_orders, list) and open_orders:
                return LiveExecutionResult(
                    status="blocked",
                    reason="lifecycle_proof_open_orders_present",
                    metadata=self._result_metadata(),
                )
            active_states = {
                str(item.get("state", "")).lower()
                for item in self.lifecycle_snapshot()
                if isinstance(item, dict)
            }
            if active_states - {"filled", "cancelled", "canceled", "rejected", "expired", "closed"}:
                return LiveExecutionResult(
                    status="blocked",
                    reason="lifecycle_proof_non_terminal_lifecycle_present",
                    metadata=self._result_metadata(),
                )
        self._lifecycle.submit(symbol=intent.symbol, order_key=cid, metadata={"side": intent.side, "requested_order_style": self._requested_order_style(intent)})
        requested_order_style = self._requested_order_style(intent)
        if proof_mode:
            requested_order_style = "passive_limit"
            self._update_lifecycle_proof(submitted=True, last_client_order_id=cid, last_reason="proof_submit")
        if requested_order_style == "marketable_limit":
            return self._submit_limit_order(
                intent=intent,
                cid=cid,
                now=now,
                fp=fp,
                qty=qty,
                price=float(validation["conservative_price"]),
                post_only=False,
                success_status="filled_marketable_limit",
                timeout_reason="marketable_limit_timeout",
            )

        maker_result = self._submit_limit_order(
            intent=intent,
            cid=cid,
            now=now,
            fp=fp,
            qty=qty,
            price=maker_price,
            post_only=True,
            success_status="filled_maker",
            timeout_reason="lifecycle_proof_timeout" if proof_mode else "maker_timeout",
            timeout_s=self._lifecycle_proof_timeout_s() if proof_mode else None,
        )
        if maker_result.status != "timeout":
            maker_result.metadata.setdefault("lifecycle_proof", self.lifecycle_proof_summary())
            maker_result.metadata.setdefault("capability_evidence", self.capability_evidence())
            return maker_result

        if proof_mode:
            maker_result.metadata.setdefault("lifecycle_proof", self.lifecycle_proof_summary())
            maker_result.metadata.setdefault("capability_evidence", self.capability_evidence())
            return maker_result

        if str(intent.side).lower() == "sell":
            refreshed_error, refreshed_validation = self._pre_submit_validate_intent(intent)
            if refreshed_error is not None:
                self.request_kill(refreshed_error)
                return LiveExecutionResult(status="killed", reason=refreshed_error)
            taker_cid = self._client_order_id(intent.symbol, intent.side, now, 1)
            self._lifecycle.submit(symbol=intent.symbol, order_key=taker_cid, metadata={"side": intent.side, "fallback": True, "requested_order_style": "marketable_limit"})
            return self._submit_limit_order(
                intent=intent,
                cid=taker_cid,
                now=now,
                fp=fp,
                qty=float(refreshed_validation["qty"]),
                price=float(refreshed_validation["conservative_price"]),
                post_only=False,
                success_status="filled_marketable_limit",
                timeout_reason="sell_marketable_limit_timeout",
            )

        if not self._taker_fallback_edge_ok(intent):
            return LiveExecutionResult(
                status="timeout",
                reason="maker_timeout_edge_le_cost",
                order=maker_result.order,
                metadata=self._result_metadata(),
            )

        taker_cid = self._client_order_id(intent.symbol, intent.side, now, 1)
        fallback_order = {
            "symbol": intent.symbol,
            "side": str(intent.side).upper(),
            "quantity": f"{qty:.8f}",
            "newClientOrderId": taker_cid,
            "type": "MARKET",
        }
        try:
            self._lifecycle.submit(symbol=intent.symbol, order_key=taker_cid, metadata={"side": intent.side, "fallback": True})
            out = self.connector.place_order(fallback_order)
            self.apply_order_update(out)
            self._recent_cids[taker_cid] = now
            self._recent_intents[fp] = now
            ledger_records, gaps = self._ledger_records_from_order(out, intent)
            return LiveExecutionResult(
                status="filled_taker_fallback",
                order=out,
                ledger_records=ledger_records,
                gaps=gaps,
                metadata=self._result_metadata(),
            )
        except Exception as exc:
            self._lifecycle.rejected(symbol=intent.symbol, order_key=taker_cid, error=str(exc))
            out = self._reject_guard(f"taker_reject:{exc}", cid=taker_cid)
            out.metadata = self._result_metadata(
                extra={
                    "execution_blocker": {
                        "code": f"taker_reject:{exc}",
                        "source": "taker_fallback_submit_exception",
                    }
                }
            )
            return out

    def _cancel_open_orders_best_effort(self) -> None:
        try:
            orders = self.connector.open_orders()
        except Exception:
            return
        if not isinstance(orders, list):
            return
        for o in orders:
            symbol = str(o.get("symbol", ""))
            cid = str(o.get("clientOrderId", o.get("clOrdId", o.get("orderId", ""))))
            if not symbol or not cid:
                continue
            try:
                self.connector.cancel_order(symbol, cid)
            except Exception:
                continue

    def flatten_symbol(self, symbol: str, max_attempts: int = 3, reason: str = "flatten_symbol") -> tuple[bool, str]:
        if symbol not in self.settings.universe:
            return False, f"flatten_symbol_not_in_universe:{symbol}"
        return self._flatten_symbols([symbol], max_attempts=max_attempts, reason=reason)

    def flatten_scope(
        self,
        *,
        scope: str = "all",
        symbol: str | None = None,
        max_attempts: int = 3,
        reason: str = "flatten_scope",
    ) -> tuple[bool, str]:
        if scope == "symbol":
            if not symbol:
                return False, "flatten_scope_symbol_required"
            return self.flatten_symbol(symbol, max_attempts=max_attempts, reason=reason)
        if scope not in {"all", "portfolio"}:
            return False, f"flatten_scope_unsupported:{scope}"
        return self._flatten_symbols(list(self.settings.universe), max_attempts=max_attempts, reason=reason)

    def _flatten_symbols(self, symbols: list[str], max_attempts: int = 3, reason: str = "flatten_all_positions") -> tuple[bool, str]:
        ordering_ok, ordering_reason = self._ordering_authorized()
        if not ordering_ok:
            return False, ordering_reason
        self._cancel_open_orders_best_effort()
        for _ in range(max_attempts):
            non_zero: list[tuple[str, float]] = []
            for symbol in symbols:
                try:
                    bal = self.connector.base_balance(symbol)
                except Exception:
                    continue
                free_qty = float(bal.get("free", 0.0) or 0.0)
                if free_qty > 1e-9:
                    non_zero.append((symbol, free_qty))
            if not non_zero:
                return True, "flat"
            for symbol, qty in non_zero:
                try:
                    qty_norm = self.connector.normalize_amount(symbol, qty)
                    if qty_norm <= 0.0:
                        continue
                    self.connector.place_order(
                        {
                            "symbol": symbol,
                            "side": "SELL",
                            "type": "MARKET",
                            "quantity": f"{qty_norm:.8f}",
                            "newClientOrderId": self._client_order_id(symbol, "sell", time.time(), 999),
                        }
                    )
                except Exception:
                    continue
            time.sleep(0.5)
        for symbol in self.settings.universe:
            if symbol not in symbols:
                continue
            try:
                bal = self.connector.base_balance(symbol)
            except Exception:
                continue
            if float(bal.get("free", 0.0) or 0.0) > 1e-9:
                self._flatten_history.append(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "action": "flatten_failed",
                        "reason": reason,
                        "scope": "symbol" if len(symbols) == 1 else "all",
                        "symbols": list(symbols),
                    }
                )
                return False, "flatten_failed"
        self._flatten_history.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "action": "flattened",
                "reason": reason,
                "scope": "symbol" if len(symbols) == 1 else "all",
                "symbols": list(symbols),
            }
        )
        return True, "flat"

    def flatten_all_positions(self, max_attempts: int = 3) -> tuple[bool, str]:
        return self._flatten_symbols(list(self.settings.universe), max_attempts=max_attempts, reason="flatten_all_positions")

    def emergency_kill_and_flatten(self, max_attempts: int = 3) -> tuple[bool, str]:
        self.request_kill("emergency")
        return self.flatten_all_positions(max_attempts=max_attempts)

    def reconcile_live_state(
        self,
        internal_exposure: float,
        open_orders_state_ok: bool = True,
        cash_ok: bool = True,
    ) -> tuple[bool, str]:
        balance_ok, balance_reason = self._balance_state_ok()
        effective_cash_ok = bool(cash_ok and balance_ok)
        positions = self.connector.position_risk()
        exchange_exposure = 0.0
        for p in positions:
            amt = abs(float(p.get("positionAmt", p.get("size", p.get("qty", 0.0)))))
            mark = abs(float(p.get("markPrice", p.get("mark", p.get("price", 0.0)))))
            exchange_exposure += amt * mark
        report = self.recon.reconcile_live_report(
            exchange_exposure=exchange_exposure,
            internal_exposure=internal_exposure,
            open_orders_state_ok=open_orders_state_ok,
            cash_ok=effective_cash_ok,
        )
        reason = report.code
        if report.code == "live_cash_mismatch" and not balance_ok:
            reason = f"{reason}:{balance_reason}"
        if not report.ok:
            self.request_kill("reconciliation_mismatch")
        return report.ok, reason

    def _balance_state_ok(self) -> tuple[bool, str]:
        try:
            rows = self.connector.balances()
        except Exception as exc:
            return False, f"balance_fetch_error:{exc}"
        if not isinstance(rows, list) or not rows:
            return False, "balance_empty"
        total = 0.0
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("balance", "equity", "availableBalance"):
                if key not in row:
                    continue
                try:
                    total += max(0.0, float(row.get(key, 0.0)))
                    break
                except Exception:
                    continue
        if total <= 0.0:
            return False, "balance_non_positive"
        return True, "ok"

    def reconcile_and_flatten_on_mismatch(
        self,
        internal_exposure: float,
        open_orders_state_ok: bool = True,
        cash_ok: bool = True,
        max_flatten_attempts: int = 3,
    ) -> tuple[bool, str]:
        ok, reason = self.reconcile_live_state(
            internal_exposure=internal_exposure,
            open_orders_state_ok=open_orders_state_ok,
            cash_ok=cash_ok,
        )
        if ok:
            return True, reason
        closed, flat_reason = self.flatten_all_positions(max_attempts=max_flatten_attempts)
        if closed:
            return False, f"{reason};flattened"
        return False, f"{reason};{flat_reason}"
