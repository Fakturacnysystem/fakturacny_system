from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib.request import Request, urlopen

from autonomous_investment_robot.config.settings import KrakenExecutionSettings


class KrakenConnectorError(RuntimeError):
    pass


class KrakenAuthError(KrakenConnectorError):
    pass


class KrakenDerivativesConnector:
    provider_id = "kraken_derivatives"
    supports_live_trading = False

    def __init__(self, settings: KrakenExecutionSettings) -> None:
        self.settings = settings
        self._api_key = os.getenv(settings.api_key_env, "")
        self._api_secret = os.getenv(settings.api_secret_env, "")

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key and self._api_secret)

    def verify_live_permissions(self) -> tuple[bool, str]:
        if self.settings.allow_unknown_permissions:
            return True, "permissions_unverified_operator_override"
        return False, "Kraken permission verification not implemented; set allow_unknown_permissions=true after manual verification."

    def _public_get(self, path: str) -> Any:
        url = f"{self.settings.rest_base_url.rstrip('/')}{path}"
        req = Request(url=url, method="GET")
        try:
            with urlopen(req, timeout=self.settings.request_timeout_s) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except Exception as exc:  # pragma: no cover
            raise KrakenConnectorError(f"Kraken request failed GET {path}: {exc}") from exc

    # Minimal readonly support
    def exchange_info(self) -> dict[str, Any]:
        # Kraken futures public instruments endpoint. We normalize shape for existing live service expectations.
        data = self._public_get("/derivatives/api/v3/instruments")
        instruments = data.get("instruments", []) if isinstance(data, dict) else []
        symbols = []
        for ins in instruments:
            symbol = str(ins.get("symbol", ins.get("contractSymbol", ""))).upper()
            if symbol:
                symbols.append({"symbol": symbol})
        return {"symbols": symbols}

    def book_ticker(self, symbol: str) -> dict[str, Any]:
        # Public tickers endpoint (futures v3)
        data = self._public_get("/derivatives/api/v3/tickers")
        tickers = data.get("tickers", []) if isinstance(data, dict) else []
        target = symbol.upper()
        for t in tickers:
            s = str(t.get("symbol", "")).upper()
            if s == target:
                bid = t.get("bid", t.get("bidPrice", 0))
                ask = t.get("ask", t.get("askPrice", 0))
                bid_qty = t.get("bidSize", t.get("bidQty", 0))
                ask_qty = t.get("askSize", t.get("askQty", 0))
                return {
                    "bidPrice": str(bid),
                    "askPrice": str(ask),
                    "bidQty": str(bid_qty),
                    "askQty": str(ask_qty),
                }
        raise KrakenConnectorError(f"symbol_missing:{symbol}")

    # Signed trading methods intentionally fail-closed until full Kraken execution path is implemented.
    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:  # noqa: ARG002
        return {"symbol": symbol, "leverage": leverage, "status": "noop_1x"}

    def place_order(self, params: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        raise KrakenConnectorError("kraken_live_trading_not_implemented")

    def query_order(self, symbol: str, client_order_id: str) -> dict[str, Any]:  # noqa: ARG002
        raise KrakenConnectorError("kraken_live_trading_not_implemented")

    def cancel_order(self, symbol: str, client_order_id: str) -> dict[str, Any]:  # noqa: ARG002
        raise KrakenConnectorError("kraken_live_trading_not_implemented")

    def position_risk(self, symbol: str | None = None) -> list[dict[str, Any]]:  # noqa: ARG002
        return []

    def open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:  # noqa: ARG002
        return []
