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

from autonomous_investment_robot.config.settings import KrakenExecutionSettings


class KrakenConnectorError(RuntimeError):
    pass


class KrakenAuthError(KrakenConnectorError):
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


class KrakenDerivativesConnector:
    provider_id = "kraken_derivatives"
    supports_live_trading = True

    def __init__(self, settings: KrakenExecutionSettings) -> None:
        self.settings = settings
        self._api_key = os.getenv(settings.api_key_env, "")
        self._api_secret = os.getenv(settings.api_secret_env, "")
        self._rate = _RateLimiter(max(0.1, settings.rate_limit_rps))

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key and self._api_secret)

    def _nonce(self) -> str:
        return str(int(time.time() * 1000))

    @staticmethod
    def _signature_endpoint_path(path: str) -> str:
        idx = path.find("/api/")
        return path[idx:] if idx >= 0 else path

    def _authent(self, endpoint_path: str, post_data: str, nonce: str) -> str:
        secret = base64.b64decode(self._api_secret)
        payload = (post_data + nonce + endpoint_path).encode("utf-8")
        mac = hmac.new(secret, payload, hashlib.sha512).digest()
        return base64.b64encode(mac).decode("ascii")

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        params = dict(params or {})
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload: bytes | None = None
        query = ""

        if params:
            clean = {}
            for k, v in params.items():
                if isinstance(v, bool):
                    clean[k] = "true" if v else "false"
                else:
                    clean[k] = v
            query = urlencode(clean)

        if signed:
            if not self.has_credentials:
                raise KrakenAuthError("Missing Kraken API credentials")
            nonce = self._nonce()
            endpoint_path = self._signature_endpoint_path(path)
            headers["APIKey"] = self._api_key
            headers["Nonce"] = nonce
            headers["Authent"] = self._authent(endpoint_path, query, nonce)

        url = f"{self.settings.rest_base_url.rstrip('/')}{path}"
        if method in {"GET", "DELETE"}:
            if query:
                url = f"{url}?{query}"
        elif query:
            payload = query.encode("utf-8")

        delay = 0.2
        for attempt in range(4):
            self._rate.wait()
            req = Request(url=url, method=method, headers=headers, data=payload)
            try:
                with urlopen(req, timeout=self.settings.request_timeout_s) as response:
                    raw = response.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except Exception as exc:  # pragma: no cover
                text = str(exc)
                if "401" in text or "403" in text:
                    raise KrakenAuthError(f"Kraken auth error: {text}") from exc
                if attempt >= 3:
                    raise KrakenConnectorError(f"Kraken request failed {method} {path}: {text}") from exc
                time.sleep(max(0.05, delay * (1.0 + random.uniform(-0.1, 0.1))))
                delay = min(3.0, delay * 2.0)

        raise KrakenConnectorError(f"Kraken request failed {method} {path}")

    def _ok(self, data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        result = str(data.get("result", "")).lower()
        if result in {"success", "ok"}:
            return True
        # some public endpoints omit result and return payload arrays/keys directly
        return "error" not in data

    def _raise_if_error(self, data: Any, context: str) -> None:
        if self._ok(data):
            return
        if isinstance(data, dict):
            err = data.get("error") or data.get("message") or data
        else:
            err = data
        txt = str(err)
        if "auth" in txt.lower() or "unauthorized" in txt.lower():
            raise KrakenAuthError(f"Kraken auth error: {context}: {txt}")
        raise KrakenConnectorError(f"Kraken API error {context}: {txt}")

    def verify_live_permissions(self) -> tuple[bool, str]:
        if not self.has_credentials:
            return False, "missing_credentials"
        try:
            data = self._request("GET", "/derivatives/api/v3/checkapikey", signed=True)
        except KrakenAuthError as exc:
            return False, str(exc)
        except Exception:
            if self.settings.allow_unknown_permissions:
                return True, "permissions_unverified_operator_override"
            return False, "kraken_permission_check_failed"

        if not self._ok(data):
            if self.settings.allow_unknown_permissions:
                return True, "permissions_unverified_operator_override"
            return False, "kraken_permission_check_failed"

        if self.settings.allow_unknown_permissions:
            return True, "permissions_verified_or_operator_override"

        # Kraken derivatives API key payload shapes vary; require explicit trading permission marker if present.
        candidates = []
        if isinstance(data, dict):
            for key in ("apiKey", "api_key", "data", "keyInfo"):
                val = data.get(key)
                if isinstance(val, dict):
                    candidates.append(val)
            candidates.append(data)
        text = json.dumps(candidates, sort_keys=True).lower()
        if any(token in text for token in ("trade", "order", "general-api-key", "generalapikey")):
            return True, "permissions_verified"
        return False, "kraken_permissions_unverified_set_allow_unknown_permissions_true"

    def _public_get(self, path: str) -> Any:
        data = self._request("GET", path)
        self._raise_if_error(data, path)
        return data

    # Public support
    def exchange_info(self) -> dict[str, Any]:
        data = self._public_get("/derivatives/api/v3/instruments")
        instruments = data.get("instruments", []) if isinstance(data, dict) else []
        symbols = []
        for ins in instruments:
            if not isinstance(ins, dict):
                continue
            symbol = str(ins.get("symbol", ins.get("contractSymbol", ""))).upper()
            if symbol:
                symbols.append({"symbol": symbol})
        return {"symbols": symbols}

    def book_ticker(self, symbol: str) -> dict[str, Any]:
        data = self._public_get("/derivatives/api/v3/tickers")
        tickers = data.get("tickers", []) if isinstance(data, dict) else []
        target = symbol.upper()
        for t in tickers:
            if not isinstance(t, dict):
                continue
            s = str(t.get("symbol", "")).upper()
            if s != target:
                continue
            bid = t.get("bid", t.get("bidPrice", 0))
            ask = t.get("ask", t.get("askPrice", 0))
            bid_qty = t.get("bidSize", t.get("bidQty", 0))
            ask_qty = t.get("askSize", t.get("askQty", 0))
            return {
                "symbol": target,
                "bidPrice": str(bid),
                "askPrice": str(ask),
                "bidQty": str(bid_qty),
                "askQty": str(ask_qty),
            }
        raise KrakenConnectorError(f"symbol_missing:{symbol}")

    # Signed support
    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:  # noqa: ARG002
        # Kraken futures leverage is managed by account/position mechanics; we enforce 1x via risk config.
        return {"symbol": symbol, "leverage": leverage, "status": "noop_1x"}

    def _normalize_send_status(self, data: dict[str, Any], fallback_cid: str = "") -> dict[str, Any]:
        send = data.get("sendStatus", data.get("sendstatus", {})) if isinstance(data, dict) else {}
        if not isinstance(send, dict):
            send = {}
        status = str(send.get("status", data.get("result", ""))).upper() or "NEW"
        if status in {"PLACED", "SUCCESS"}:
            status = "NEW"
        return {
            "clientOrderId": str(send.get("cliOrdId", fallback_cid)),
            "orderId": str(send.get("order_id", send.get("orderId", ""))),
            "status": status,
            "raw": data,
        }

    def place_order(self, params: dict[str, Any]) -> dict[str, Any]:
        side = str(params.get("side", "")).lower()
        order_type = str(params.get("type", "limit")).lower()
        symbol = str(params.get("symbol", ""))
        size = params.get("quantity", params.get("size", "0"))
        body: dict[str, Any] = {
            "orderType": "mkt" if order_type == "market" else "lmt",
            "symbol": symbol,
            "side": "buy" if side == "buy" else "sell",
            "size": size,
        }
        if order_type != "market":
            body["limitPrice"] = params.get("price")
            if params.get("postOnly") or str(params.get("timeInForce", "")).upper() == "GTX":
                body["postOnly"] = True
        if params.get("reduceOnly") in {True, "true", "True"}:
            body["reduceOnly"] = True
        cid = str(params.get("newClientOrderId", params.get("cliOrdId", "")))
        if cid:
            body["cliOrdId"] = cid
        data = self._request("POST", "/derivatives/api/v3/sendorder", params=body, signed=True)
        self._raise_if_error(data, "sendorder")
        return self._normalize_send_status(data, fallback_cid=cid)

    def query_order(self, symbol: str, client_order_id: str) -> dict[str, Any]:  # noqa: ARG002
        data = self._request("GET", "/derivatives/api/v3/orders/status", params={"cliOrdId": client_order_id}, signed=True)
        self._raise_if_error(data, "orders/status")
        orders = []
        if isinstance(data, dict):
            if isinstance(data.get("orders"), list):
                orders = data["orders"]
            elif isinstance(data.get("elements"), list):
                orders = data["elements"]
        for o in orders:
            if not isinstance(o, dict):
                continue
            cid = str(o.get("cliOrdId", o.get("clientOrderId", "")))
            if cid != client_order_id:
                continue
            status = str(o.get("status", "")).upper()
            if status in {"FILLED", "FULLY_EXECUTED"}:
                status = "FILLED"
            elif status in {"PARTIALLY_FILLED", "PARTIAL"}:
                status = "PARTIALLY_FILLED"
            elif not status:
                status = "NEW"
            return {
                "clientOrderId": cid,
                "orderId": str(o.get("order_id", o.get("orderId", ""))),
                "status": status,
                "raw": o,
            }
        raise KrakenConnectorError("order not found")

    def cancel_order(self, symbol: str, client_order_id: str) -> dict[str, Any]:  # noqa: ARG002
        data = self._request("POST", "/derivatives/api/v3/cancelorder", params={"cliOrdId": client_order_id}, signed=True)
        self._raise_if_error(data, "cancelorder")
        c = data.get("cancelStatus", {}) if isinstance(data, dict) else {}
        return {
            "status": str(c.get("status", "CANCELED")).upper(),
            "clientOrderId": str(c.get("cliOrdId", client_order_id)),
            "raw": data,
        }

    def position_risk(self, symbol: str | None = None) -> list[dict[str, Any]]:
        data = self._request("GET", "/derivatives/api/v3/openpositions", signed=True)
        self._raise_if_error(data, "openpositions")
        positions = data.get("openPositions", data.get("positions", [])) if isinstance(data, dict) else []
        out: list[dict[str, Any]] = []
        for p in positions if isinstance(positions, list) else []:
            if not isinstance(p, dict):
                continue
            psym = str(p.get("symbol", p.get("instrument", "")))
            if symbol and psym.upper() != symbol.upper():
                continue
            size = float(p.get("size", p.get("qty", p.get("positionAmt", 0.0))))
            side = str(p.get("side", "")).lower()
            signed_size = -abs(size) if side == "short" else abs(size)
            out.append(
                {
                    "symbol": psym,
                    "positionAmt": str(signed_size),
                    "markPrice": str(p.get("markPrice", p.get("mark", p.get("price", 0.0)))),
                    "raw": p,
                }
            )
        return out

    def open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        data = self._request("GET", "/derivatives/api/v3/openorders", signed=True)
        self._raise_if_error(data, "openorders")
        orders = data.get("openOrders", data.get("orders", [])) if isinstance(data, dict) else []
        out: list[dict[str, Any]] = []
        for o in orders if isinstance(orders, list) else []:
            if not isinstance(o, dict):
                continue
            sym = str(o.get("symbol", ""))
            if symbol and sym.upper() != symbol.upper():
                continue
            out.append(
                {
                    "symbol": sym,
                    "clientOrderId": str(o.get("cliOrdId", o.get("clientOrderId", ""))),
                    "origClientOrderId": str(o.get("cliOrdId", "")),
                    "status": str(o.get("status", "")).upper(),
                    "raw": o,
                }
            )
        return out
