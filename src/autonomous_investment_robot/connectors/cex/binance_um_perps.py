from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from autonomous_investment_robot.config.settings import BinanceExecutionSettings


class BinanceConnectorError(RuntimeError):
    pass


class BinanceAuthError(BinanceConnectorError):
    pass


@dataclass
class _RateLimiter:
    rps: float
    _next_ts: float = 0.0
    _lock: Lock = field(default_factory=Lock)

    def wait(self) -> None:
        if self.rps <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if now < self._next_ts:
                time.sleep(self._next_ts - now)
                now = time.monotonic()
            self._next_ts = now + (1.0 / self.rps)


class BinanceUMPerpsConnector:
    provider_id = "binance_um_perps"

    def __init__(self, settings: BinanceExecutionSettings) -> None:
        self.settings = settings
        self._api_key = os.getenv(settings.api_key_env, "")
        self._api_secret = os.getenv(settings.api_secret_env, "")
        self._rate = _RateLimiter(max(0.1, settings.rate_limit_rps))

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key and self._api_secret)

    def _timestamp_ms(self) -> int:
        return int(time.time() * 1000)

    def _signed_query(self, params: dict[str, Any]) -> str:
        payload = urlencode(params)
        sig = hmac.new(self._api_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}&signature={sig}"

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        if params is None:
            params = {}

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        query = ""
        payload: bytes | None = None

        if signed:
            if not self.has_credentials:
                raise BinanceAuthError("Missing Binance API credentials")
            headers["X-MBX-APIKEY"] = self._api_key
            signed_params = {
                **params,
                "timestamp": self._timestamp_ms(),
                "recvWindow": int(self.settings.recv_window_ms),
            }
            query = self._signed_query(signed_params)
        elif params:
            query = urlencode(params)

        url = f"{self.settings.rest_base_url.rstrip('/')}{path}"
        if method in {"GET", "DELETE"}:
            if query:
                url = f"{url}?{query}"
        elif query:
            payload = query.encode("utf-8")

        delay = self.settings.backoff_base_ms / 1000.0
        for attempt in range(self.settings.max_retries + 1):
            self._rate.wait()
            req = Request(url=url, method=method, headers=headers, data=payload)
            try:
                with urlopen(req, timeout=self.settings.request_timeout_s) as response:
                    raw = response.read().decode("utf-8")
                    if not raw:
                        return {}
                    return json.loads(raw)
            except Exception as exc:  # pragma: no cover - network-less tests mock this.
                text = str(exc)
                if "401" in text or "403" in text:
                    raise BinanceAuthError(f"Binance auth error: {text}") from exc
                if attempt >= self.settings.max_retries:
                    raise BinanceConnectorError(f"Binance request failed {method} {path}: {text}") from exc
                sleep_s = min(self.settings.backoff_max_ms / 1000.0, delay * (2**attempt))
                sleep_s = sleep_s * (1.0 + random.uniform(-0.1, 0.1))
                time.sleep(max(0.01, sleep_s))

        raise BinanceConnectorError(f"Binance request failed {method} {path}")

    def verify_live_permissions(self) -> tuple[bool, str]:
        # Futures key permissions are not exposed in all account endpoints.
        # We fail closed unless operator explicitly allows unknown permissions.
        if self.settings.allow_unknown_permissions:
            return True, "permissions_unverified_operator_override"
        return (
            False,
            "Cannot verify trade-only/no-withdraw key permissions via API. "
            "Set allow_unknown_permissions=true only after manual verification.",
        )

    # Public endpoints
    def server_time(self) -> dict[str, Any]:
        return self._request("GET", "/fapi/v1/time")

    def exchange_info(self) -> dict[str, Any]:
        return self._request("GET", "/fapi/v1/exchangeInfo")

    def depth(self, symbol: str, limit: int = 100) -> dict[str, Any]:
        return self._request("GET", "/fapi/v1/depth", params={"symbol": symbol, "limit": limit})

    def book_ticker(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/fapi/v1/ticker/bookTicker", params={"symbol": symbol})

    def premium_index(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/fapi/v1/premiumIndex", params={"symbol": symbol})

    def agg_trades(self, symbol: str, limit: int = 500) -> list[dict[str, Any]]:
        return self._request("GET", "/fapi/v1/aggTrades", params={"symbol": symbol, "limit": limit})

    def open_interest(self, symbol: str, period: str = "5m", limit: int = 1) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            "/futures/data/openInterest",
            params={"symbol": symbol, "period": period, "limit": limit},
        )

    # Signed endpoints
    def balances(self) -> list[dict[str, Any]]:
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def position_risk(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", "/fapi/v2/positionRisk", params=params, signed=True)

    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        return self._request("POST", "/fapi/v1/leverage", params={"symbol": symbol, "leverage": leverage}, signed=True)

    def place_order(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def query_order(self, symbol: str, client_order_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/fapi/v1/order",
            params={"symbol": symbol, "origClientOrderId": client_order_id},
            signed=True,
        )

    def cancel_order(self, symbol: str, client_order_id: str) -> dict[str, Any]:
        return self._request(
            "DELETE",
            "/fapi/v1/order",
            params={"symbol": symbol, "origClientOrderId": client_order_id},
            signed=True,
        )

    def open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)

    def create_listen_key(self) -> dict[str, Any]:
        return self._request("POST", "/fapi/v1/listenKey", signed=True)

    def keepalive_listen_key(self, listen_key: str) -> dict[str, Any]:
        return self._request("PUT", "/fapi/v1/listenKey", params={"listenKey": listen_key}, signed=True)

    def close_listen_key(self, listen_key: str) -> dict[str, Any]:
        return self._request("DELETE", "/fapi/v1/listenKey", params={"listenKey": listen_key}, signed=True)
