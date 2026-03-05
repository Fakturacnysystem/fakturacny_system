from __future__ import annotations

import base64
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


class KrakenFuturesConnectorError(RuntimeError):
    pass


class KrakenFuturesAuthError(KrakenFuturesConnectorError):
    pass


class KrakenFuturesRateLimitError(KrakenFuturesConnectorError):
    pass


class KrakenFuturesOrderError(KrakenFuturesConnectorError):
    pass


@dataclass
class KrakenFuturesSettings:
    rest_base_url: str = "https://futures.kraken.com"
    ws_base_url: str = "wss://futures.kraken.com/ws/v1"
    api_key_env: str = "KRAKEN_FUTURES_KEY"
    api_secret_env: str = "KRAKEN_FUTURES_SECRET"
    request_timeout_s: float = 10.0
    rate_limit_rps: float = 5.0
    max_retries: int = 3
    backoff_base_ms: int = 200
    backoff_max_ms: int = 3000


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


class KrakenFuturesConnector:
    provider_id = "kraken_futures"

    def __init__(self, settings: KrakenFuturesSettings | None = None) -> None:
        self.settings = settings or KrakenFuturesSettings()
        self._api_key = os.getenv(self.settings.api_key_env, "")
        self._api_secret = os.getenv(self.settings.api_secret_env, "")
        self._rate = _RateLimiter(max(0.1, self.settings.rate_limit_rps))

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key and self._api_secret)

    @staticmethod
    def _sign(endpoint: str, nonce: str, payload: str, api_secret_b64: str) -> str:
        secret = base64.b64decode(api_secret_b64)
        msg = f"{endpoint}{nonce}{payload}".encode("utf-8")
        digest = hmac.new(secret, msg, hashlib.sha512).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _headers(self, endpoint: str, params: dict[str, Any]) -> tuple[dict[str, str], str]:
        if not self.has_credentials:
            raise KrakenFuturesAuthError("Missing Kraken Futures credentials")
        nonce = str(int(time.time() * 1000))
        payload = urlencode(params)
        sig = self._sign(endpoint=endpoint, nonce=nonce, payload=payload, api_secret_b64=self._api_secret)
        headers = {
            "APIKey": self._api_key,
            "Authent": sig,
            "Nonce": nonce,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        return headers, payload

    def _classify_error(self, text: str) -> Exception:
        t = text.lower()
        if "auth" in t or "invalid key" in t or "signature" in t or "401" in t or "403" in t:
            return KrakenFuturesAuthError(text)
        if "rate limit" in t or "429" in t:
            return KrakenFuturesRateLimitError(text)
        if "insufficient" in t or "order" in t:
            return KrakenFuturesOrderError(text)
        return KrakenFuturesConnectorError(text)

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        private: bool = False,
    ) -> Any:
        params = params or {}
        url = f"{self.settings.rest_base_url.rstrip('/')}{endpoint}"
        data: bytes | None = None
        headers: dict[str, str] = {}

        if private:
            headers, encoded = self._headers(endpoint, params)
            data = encoded.encode("utf-8")
        elif params:
            if method == "GET":
                url = f"{url}?{urlencode(params)}"
            else:
                encoded = urlencode(params)
                data = encoded.encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"

        for attempt in range(self.settings.max_retries + 1):
            self._rate.wait()
            req = Request(url=url, method=method, headers=headers, data=data)
            try:
                with urlopen(req, timeout=self.settings.request_timeout_s) as response:
                    raw = response.read().decode("utf-8")
                    out = json.loads(raw) if raw else {}
                    if isinstance(out, dict) and out.get("error"):
                        raise self._classify_error(str(out.get("error")))
                    return out
            except (KrakenFuturesConnectorError, KrakenFuturesAuthError, KrakenFuturesRateLimitError, KrakenFuturesOrderError):
                raise
            except Exception as exc:  # pragma: no cover
                if attempt >= self.settings.max_retries:
                    raise self._classify_error(str(exc)) from exc
                wait_s = min(
                    self.settings.backoff_max_ms / 1000.0,
                    (self.settings.backoff_base_ms / 1000.0) * (2 ** attempt),
                )
                wait_s = wait_s * (1.0 + random.uniform(-0.1, 0.1))
                time.sleep(max(0.01, wait_s))
        raise KrakenFuturesConnectorError(f"request_failed:{endpoint}")

    # Public endpoints
    def instruments(self) -> dict[str, Any]:
        return self._request("GET", "/derivatives/api/v3/instruments")

    def tickers(self) -> dict[str, Any]:
        return self._request("GET", "/derivatives/api/v3/tickers")

    def orderbook(self, symbol: str, depth: int = 25) -> dict[str, Any]:
        return self._request("GET", "/derivatives/api/v3/orderbook", params={"symbol": symbol, "depth": depth})

    def trades(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/derivatives/api/v3/history", params={"symbol": symbol})

    # Private endpoints
    def account_overview(self) -> dict[str, Any]:
        return self._request("GET", "/derivatives/api/v3/accounts", private=True)

    def open_positions(self) -> dict[str, Any]:
        return self._request("GET", "/derivatives/api/v3/openpositions", private=True)

    def open_orders(self) -> dict[str, Any]:
        return self._request("GET", "/derivatives/api/v3/openorders", private=True)

    def send_order(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/derivatives/api/v3/sendorder", params=params, private=True)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request("POST", "/derivatives/api/v3/cancelorder", params={"order_id": order_id}, private=True)

    def cancel_all_orders(self) -> dict[str, Any]:
        return self._request("POST", "/derivatives/api/v3/cancelallorders", params={}, private=True)

    def market_snapshot(self, symbol: str) -> dict[str, Any]:
        ticks = self.tickers()
        rows = ticks.get("tickers", []) if isinstance(ticks, dict) else []
        row = next((x for x in rows if str(x.get("symbol", "")) == symbol), {}) if isinstance(rows, list) else {}
        bid = float(row.get("bid", 0.0) or 0.0)
        ask = float(row.get("ask", 0.0) or 0.0)
        mark = float(row.get("markPrice", 0.0) or 0.0)
        index = float(row.get("indexPrice", 0.0) or 0.0)
        funding = float(row.get("fundingRate", 0.0) or 0.0)
        oi = float(row.get("openInterest", 0.0) or 0.0)
        vol = float(row.get("volume24h", 0.0) or 0.0)
        return {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2.0 if bid > 0.0 and ask > 0.0 else max(mark, index, 0.0),
            "mark_price": mark,
            "index_price": index,
            "funding_rate": funding,
            "open_interest": oi,
            "volume_24h": vol,
            "ts": time.time(),
        }


class KrakenFuturesWSClient:
    """WS adapter interface for Kraken Futures feeds.

    If websocket-client is unavailable, methods raise RuntimeError with install hint.
    """

    def __init__(self, url: str = "wss://futures.kraken.com/ws/v1") -> None:
        self.url = url
        self._ws = None

    def _ensure_client(self):
        try:
            import websocket  # type: ignore

            return websocket
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("websocket-client package required for KrakenFuturesWSClient") from exc

    def connect(self) -> None:
        ws_mod = self._ensure_client()
        self._ws = ws_mod.create_connection(self.url)

    def subscribe_ticker(self, symbols: list[str]) -> None:
        if self._ws is None:
            self.connect()
        assert self._ws is not None
        self._ws.send(json.dumps({"event": "subscribe", "feed": "ticker", "product_ids": list(symbols)}))

    def subscribe_book(self, symbols: list[str]) -> None:
        if self._ws is None:
            self.connect()
        assert self._ws is not None
        self._ws.send(json.dumps({"event": "subscribe", "feed": "book", "product_ids": list(symbols)}))

    def recv(self) -> dict[str, Any]:
        if self._ws is None:
            self.connect()
        assert self._ws is not None
        raw = self._ws.recv()
        return json.loads(raw) if raw else {}

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None
