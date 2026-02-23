from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenConnectorError, KrakenSpotConnector


@dataclass
class LiveExecutionResult:
    status: str
    reason: str = ""
    order: dict[str, Any] | None = None


class KrakenMinOrderGuard:
    def __init__(self, connector: KrakenSpotConnector) -> None:
        self.connector = connector
        self._cache: dict[str, dict[str, Any]] = {}

    def load_pairs(self) -> dict[str, dict[str, Any]]:
        if self._cache:
            return self._cache
        raw = self.connector.asset_pairs()
        self._cache = raw if isinstance(raw, dict) else {}
        return self._cache

    def validate(self, pair: str, volume: float, price: float, available_quote: float) -> tuple[bool, str]:
        pairs = self.load_pairs()
        meta = pairs.get(pair, {})
        ordermin = float(meta.get("ordermin", 0.0) or 0.0)
        pair_decimals = int(meta.get("pair_decimals", 8) or 8)
        lot_decimals = int(meta.get("lot_decimals", 8) or 8)
        if volume < ordermin:
            return False, "min_order_block"
        if round(volume, lot_decimals) != volume:
            return False, "qty_precision_block"
        if round(price, pair_decimals) != price:
            return False, "price_precision_block"
        if volume * price > available_quote:
            return False, "insufficient_balance_block"
        return True, "ok"


class LiveKrakenSpotService:
    def __init__(self, settings: RobotSettings, run_id: str, connector: KrakenSpotConnector | None = None) -> None:
        self.settings = settings
        self.run_id = run_id
        self.connector = connector or KrakenSpotConnector(settings.execution.kraken_spot)
        self.safe_mode = False
        self.killed = False
        self.kill_reason = ""
        self.min_guard = KrakenMinOrderGuard(self.connector)

    def preflight(self) -> tuple[bool, str]:
        if self.settings.execution_mode_enum() == ExecutionMode.LIVE_READONLY:
            return True, "readonly"
        ok_perm, reason_perm = self.connector.verify_live_permissions()
        if not ok_perm:
            return False, reason_perm
        if "kraken_spot" not in self.settings.provider_whitelist:
            return False, "provider_not_whitelisted"
        if not self.connector.has_credentials:
            return False, "missing_credentials"
        return True, "ok"

    def execute_readonly(self, intent) -> LiveExecutionResult:
        symbol = intent.symbol
        t = self.connector.ticker(symbol)
        return LiveExecutionResult(status="readonly_preview", order={"symbol": symbol, "ticker": t.get(symbol, t), "target_notional": getattr(intent, "target_notional", 0.0)})

    def execute_intent(self, intent) -> LiveExecutionResult:
        if self.killed:
            return LiveExecutionResult(status="killed", reason=self.kill_reason or "kill_switch_active")
        if self.safe_mode:
            return LiveExecutionResult(status="blocked", reason="safe_mode")
        # long-only opens; sells are allowed for exit/flatten paths handled elsewhere
        if str(intent.side).lower() != "buy":
            return LiveExecutionResult(status="blocked", reason="long_only_mode")
        return LiveExecutionResult(status="blocked", reason="spot_live_execution_not_enabled_in_this_build")

    def request_kill(self, reason: str = "operator_kill") -> None:
        self.killed = True
        self.safe_mode = True
        self.kill_reason = reason

    def flatten_all_positions(self) -> tuple[bool, str]:
        if self.killed is False:
            self.request_kill("emergency")
        try:
            self.connector.cancel_all()
        except Exception:
            pass
        bal = self.connector.balance()
        pairs = self.min_guard.load_pairs()
        quote_ccy = "ZUSD"
        for asset, amount in bal.items() if isinstance(bal, dict) else []:
            if asset in {quote_ccy, "USD", "ZEUR", "ZEUR"}:
                continue
            qty = float(amount or 0.0)
            if qty <= 0:
                continue
            pair = next((p for p, m in pairs.items() if m.get("base") == asset and m.get("quote") in {quote_ccy, "USD"}), "")
            if not pair:
                continue
            try:
                self.connector.add_order({"pair": pair, "type": "sell", "ordertype": "market", "volume": f"{qty:.8f}"})
                time.sleep(0.2)
            except KrakenConnectorError:
                continue
        return True, "flatten_best_effort"
