from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autonomous_investment_robot.services.execution.live_kraken_futures_service import LiveKrakenFuturesService
from autonomous_investment_robot.services.execution.live_kraken_spot_service import LiveKrakenSpotService


@dataclass
class LiveExecutionResult:
    status: str
    reason: str = ""
    order: dict[str, Any] | None = None


class LiveKrakenRouterService:
    """Routes Kraken live operations across spot and futures services by symbol."""

    def __init__(
        self,
        *,
        spot_service: LiveKrakenSpotService | None,
        futures_service: LiveKrakenFuturesService | None,
        discovered_instruments: list[dict[str, Any]] | None = None,
    ) -> None:
        self.spot_service = spot_service
        self.futures_service = futures_service
        self._symbol_market_type: dict[str, str] = {}
        self._symbol_venue: dict[str, str] = {}
        self.register_discovery(discovered_instruments or [])

    def register_discovery(self, instruments: list[dict[str, Any]]) -> None:
        for row in instruments:
            if not isinstance(row, dict):
                continue
            symbol = self._norm_symbol(row.get("symbol", ""))
            if not symbol:
                continue
            market_type = str(row.get("market_type", "spot") or "spot").strip().lower()
            venue = str(row.get("venue", "kraken") or "kraken").strip().lower()
            if market_type == "perp":
                self._symbol_market_type[symbol] = "perp"
                self._symbol_venue[symbol] = "kraken_futures"
            else:
                self._symbol_market_type.setdefault(symbol, "spot")
                self._symbol_venue.setdefault(symbol, "kraken_spot")

    def _norm_symbol(self, symbol: Any) -> str:
        return str(symbol or "").strip().upper()

    def market_type_for_symbol(self, symbol: str) -> str:
        key = self._norm_symbol(symbol)
        return self._symbol_market_type.get(key, "spot")

    def venue_for_symbol(self, symbol: str) -> str:
        key = self._norm_symbol(symbol)
        return self._symbol_venue.get(key, "kraken_spot")

    def _service_for_symbol(self, symbol: str) -> Any:
        market_type = self.market_type_for_symbol(symbol)
        if market_type == "perp" and self.futures_service is not None:
            return self.futures_service
        if self.spot_service is not None:
            return self.spot_service
        if self.futures_service is not None:
            return self.futures_service
        raise RuntimeError("no_live_kraken_service_configured")

    def connectors_for_symbol(self, symbol: str) -> dict[str, Any]:
        svc = self._service_for_symbol(symbol)
        venue = self.venue_for_symbol(symbol)
        return {venue: svc}

    def preflight(self) -> tuple[bool, str]:
        checked: list[str] = []
        if self.spot_service is not None:
            has_spot = any(v == "spot" for v in self._symbol_market_type.values()) or not self._symbol_market_type
            if has_spot:
                ok, reason = self.spot_service.preflight()
                checked.append(f"spot:{reason}")
                if not ok:
                    return False, reason
        if self.futures_service is not None:
            has_perp = any(v == "perp" for v in self._symbol_market_type.values())
            if has_perp:
                ok, reason = self.futures_service.preflight()
                checked.append(f"perp:{reason}")
                if not ok:
                    return False, reason
        if not checked:
            return False, "no_service_enabled"
        return True, "ok"

    def execute_readonly(self, intent: Any) -> LiveExecutionResult:
        symbol = self._norm_symbol(getattr(intent, "symbol", ""))
        svc = self._service_for_symbol(symbol)
        out = svc.execute_readonly(intent)
        return LiveExecutionResult(status=str(out.status), reason=str(getattr(out, "reason", "")), order=getattr(out, "order", None))

    def execute_intent(self, intent: Any) -> LiveExecutionResult:
        symbol = self._norm_symbol(getattr(intent, "symbol", ""))
        svc = self._service_for_symbol(symbol)
        out = svc.execute_intent(intent)
        return LiveExecutionResult(status=str(out.status), reason=str(getattr(out, "reason", "")), order=getattr(out, "order", None))

    def market_snapshot(self, symbol: str, *, max_age_s: float | None = None, force_refresh: bool = False) -> dict[str, Any]:
        svc = self._service_for_symbol(symbol)
        return svc.market_snapshot(symbol, max_age_s=max_age_s, force_refresh=force_refresh)

    def sync_fill_ledger(self, symbol: str, mark_price: float) -> dict[str, Any]:
        svc = self._service_for_symbol(symbol)
        return svc.sync_fill_ledger(symbol, mark_price)

    def reconcile_live_state(self, internal_exposure: float) -> tuple[bool, str]:
        # Multi-symbol exposure reconciliation is handled per-symbol in live loop.
        return True, "multi_venue_reconcile_delegated"

    def request_kill(self, reason: str = "operator_kill") -> None:
        if self.spot_service is not None:
            self.spot_service.request_kill(reason)
        if self.futures_service is not None:
            self.futures_service.request_kill(reason)

    def flatten_all_positions(self) -> tuple[bool, str]:
        ok = True
        reasons: list[str] = []
        if self.spot_service is not None:
            s_ok, s_reason = self.spot_service.flatten_all_positions()
            ok = ok and s_ok
            reasons.append(f"spot:{s_reason}")
        if self.futures_service is not None:
            f_ok, f_reason = self.futures_service.flatten_all_positions()
            ok = ok and f_ok
            reasons.append(f"perp:{f_reason}")
        if not reasons:
            return False, "no_service_enabled"
        return ok, ";".join(reasons)

    def set_exits_only_mode(self, *, reason: str, duration_s: float = 180.0) -> None:
        if self.spot_service is not None and hasattr(self.spot_service, "set_exits_only_mode"):
            try:
                self.spot_service.set_exits_only_mode(reason=reason, duration_s=duration_s)
            except Exception:
                pass
        if self.futures_service is not None and hasattr(self.futures_service, "set_exits_only_mode"):
            try:
                self.futures_service.set_exits_only_mode(reason=reason, duration_s=duration_s)
            except Exception:
                pass

    def clear_exits_only_mode(self) -> None:
        if self.spot_service is not None and hasattr(self.spot_service, "clear_exits_only_mode"):
            try:
                self.spot_service.clear_exits_only_mode()
            except Exception:
                pass
        if self.futures_service is not None and hasattr(self.futures_service, "clear_exits_only_mode"):
            try:
                self.futures_service.clear_exits_only_mode()
            except Exception:
                pass

    def set_health_ok(self, ok: bool) -> None:
        if self.spot_service is not None and hasattr(self.spot_service, "set_health_ok"):
            try:
                self.spot_service.set_health_ok(ok)
            except Exception:
                pass
        if self.futures_service is not None and hasattr(self.futures_service, "set_health_ok"):
            try:
                self.futures_service.set_health_ok(ok)
            except Exception:
                pass

    def _available_quote_balance(self, symbol: str) -> tuple[str, float]:
        svc = self._service_for_symbol(symbol)
        if hasattr(svc, "_available_quote_balance"):
            return svc._available_quote_balance(symbol)
        return "USD", 0.0

    def close(self) -> None:
        if self.futures_service is not None:
            try:
                if hasattr(self.futures_service, "close"):
                    self.futures_service.close()
            except Exception:
                pass
