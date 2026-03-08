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

from autonomous_investment_robot.config.settings import KrakenSpotExecutionSettings


class KrakenConnectorError(RuntimeError):
    pass


class KrakenAuthError(KrakenConnectorError):
    pass


class KrakenPermissionError(KrakenConnectorError):
    pass


class KrakenRateLimitError(KrakenConnectorError):
    pass


class KrakenTemporaryLockoutError(KrakenRateLimitError):
    pass


class KrakenOrderError(KrakenConnectorError):
    pass


class KrakenInsufficientFundsError(KrakenOrderError):
    pass


class KrakenInvalidNonceError(KrakenConnectorError):
    pass


class KrakenNetworkError(KrakenConnectorError):
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


class KrakenSpotConnector:
    provider_id = "kraken_spot"

    def __init__(self, settings: KrakenSpotExecutionSettings) -> None:
        self.settings = settings
        self._api_key = os.getenv(settings.api_key_env, "")
        self._api_secret = os.getenv(settings.api_secret_env, "")
        self._rate = _RateLimiter(max(0.1, settings.rate_limit_rps))
        self._nonce_lock = Lock()
        self._last_nonce = 0

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key and self._api_secret)

    @staticmethod
    def sign_payload(api_path: str, nonce: str, payload: str, api_secret_b64: str) -> str:
        secret = base64.b64decode(api_secret_b64)
        encoded = (nonce + payload).encode("utf-8")
        digest = hashlib.sha256(encoded).digest()
        message = api_path.encode("utf-8") + digest
        signature = hmac.new(secret, message, hashlib.sha512).digest()
        return base64.b64encode(signature).decode("utf-8")

    def _signed_headers(self, api_path: str, params: dict[str, Any]) -> dict[str, str]:
        if not self.has_credentials:
            raise KrakenAuthError("Missing Kraken API credentials")
        nonce = str(self._next_nonce())
        post_data = urlencode({"nonce": nonce, **params})
        sig = self.sign_payload(api_path=api_path, nonce=nonce, payload=post_data, api_secret_b64=self._api_secret)
        return {
            "API-Key": self._api_key,
            "API-Sign": sig,
            "Content-Type": "application/x-www-form-urlencoded",
        }, {"nonce": nonce, **params}

    def _classify_error(self, text: str) -> Exception:
        t = text.lower()
        if "permission denied" in t:
            return KrakenPermissionError(f"Kraken permission error: {text}")
        if (
            "eapi:invalid key" in t
            or "eapi:invalid signature" in t
            or "401" in t
            or "403" in t
            or "incorrect padding" in t
            or "invalid base64" in t
            or "non-base64 digit found" in t
        ):
            return KrakenAuthError(f"Kraken auth error: {text}")
        if "temporary lockout" in t:
            return KrakenTemporaryLockoutError(f"Kraken temporary lockout: {text}")
        if "invalid nonce" in t or "eapi:invalid nonce" in t:
            return KrakenInvalidNonceError(f"Kraken invalid nonce: {text}")
        if "rate limit" in t or "too many requests" in t or "429" in t:
            return KrakenRateLimitError(f"Kraken rate limit: {text}")
        if (
            "nodename nor servname provided" in t
            or "name or service not known" in t
            or "temporary failure in name resolution" in t
            or "network is unreachable" in t
            or "connection refused" in t
            or "timed out" in t
            or "connection reset" in t
        ):
            return KrakenNetworkError(f"Kraken network error: {text}")
        if "insufficient funds" in t:
            return KrakenInsufficientFundsError(f"Kraken insufficient funds: {text}")
        if "eorder:" in t:
            return KrakenOrderError(f"Kraken order error: {text}")
        return KrakenConnectorError(text)

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None, private: bool = False) -> Any:
        params = params or {}
        url = f"{self.settings.rest_base_url.rstrip('/')}{path}"
        headers = {}
        payload: bytes | None = None
        if private:
            headers, full_params = self._signed_headers(path, params)
            payload = urlencode(full_params).encode("utf-8")
        elif params:
            if method == "GET":
                url = f"{url}?{urlencode(params)}"
            else:
                payload = urlencode(params).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"

        delay = self.settings.backoff_base_ms / 1000.0
        for attempt in range(self.settings.max_retries + 1):
            self._rate.wait()
            req = Request(url=url, method=method, headers=headers, data=payload)
            try:
                with urlopen(req, timeout=self.settings.request_timeout_s) as response:
                    raw = response.read().decode("utf-8")
                    data = json.loads(raw) if raw else {}
                    errors = data.get("error", []) if isinstance(data, dict) else []
                    if errors:
                        raise self._classify_error(";".join(errors))
                    return data.get("result", data)
            except KrakenInvalidNonceError:
                if attempt >= self.settings.max_retries:
                    raise
                # Regenerate signed payload with a newer nonce and retry quickly.
                time.sleep(0.05 * (attempt + 1))
                if private:
                    headers, full_params = self._signed_headers(path, params)
                    payload = urlencode(full_params).encode("utf-8")
                continue
            except (KrakenConnectorError, KrakenAuthError, KrakenRateLimitError, KrakenOrderError):
                raise
            except Exception as exc:  # pragma: no cover
                if attempt >= self.settings.max_retries:
                    raise self._classify_error(str(exc)) from exc
                sleep_s = min(self.settings.backoff_max_ms / 1000.0, delay * (2**attempt))
                sleep_s = sleep_s * (1.0 + random.uniform(-0.1, 0.1))
                time.sleep(max(0.01, sleep_s))
        raise KrakenConnectorError(f"Kraken request failed {method} {path}")

    def _next_nonce(self) -> int:
        now_ms = int(time.time() * 1000)
        with self._nonce_lock:
            if now_ms <= self._last_nonce:
                now_ms = self._last_nonce + 1
            self._last_nonce = now_ms
            return now_ms

    def verify_live_permissions(self) -> tuple[bool, str]:
        diag = self.diagnose_private_api_access()
        ok = bool(diag.get("ok", False))
        scope = str(diag.get("scope", "unknown") or "unknown")
        cls = str(diag.get("classification", "unknown_error") or "unknown_error")
        reason = str(diag.get("reason", "") or "")
        if ok:
            if cls == "ok":
                return True, "ok"
            if cls.endswith("_override"):
                return True, f"permissions_unverified_operator_override:{scope}:{cls}:{reason}"
            return True, f"permissions_verified:{scope}:{cls}"
        if cls == "missing_credentials":
            return False, "missing_credentials"
        if cls == "invalid_permissions":
            return False, f"kraken_permission_denied:{scope}"
        if cls == "invalid_credentials":
            return False, f"kraken_auth_error:{scope}"
        if cls == "temporary_lockout":
            return False, f"kraken_temporary_lockout:{scope}"
        if cls == "invalid_nonce":
            return False, f"kraken_invalid_nonce:{scope}"
        if cls == "network_unreachable":
            return False, f"kraken_network_unreachable:{scope}"
        if cls == "rate_limit":
            return False, f"kraken_rate_limit:{scope}"
        return False, f"permission_check_failed:{scope}:{reason}"

    @staticmethod
    def _classify_private_scope_error(exc: Exception | str) -> tuple[str, str]:
        """Classify private-endpoint failures into deterministic startup blockers."""

        detail = str(exc).strip().replace("\n", " ")
        txt = detail.lower()
        if "temporary lockout" in txt:
            return "temporary_lockout", detail
        if "permission denied" in txt:
            return "invalid_permissions", detail
        if (
            "invalid key" in txt
            or "invalid signature" in txt
            or "authentication" in txt
            or "incorrect padding" in txt
            or "invalid base64" in txt
            or "non-base64 digit found" in txt
        ):
            return "invalid_credentials", detail
        if "invalid nonce" in txt:
            return "invalid_nonce", detail
        if "rate limit" in txt or "too many requests" in txt or "429" in txt:
            return "rate_limit", detail
        if (
            "nodename nor servname provided" in txt
            or "name or service not known" in txt
            or "temporary failure in name resolution" in txt
            or "network is unreachable" in txt
            or "connection refused" in txt
            or "timed out" in txt
            or "connection reset" in txt
        ):
            return "network_unreachable", detail
        return "unknown_error", detail

    def diagnose_private_api_access(self) -> dict[str, Any]:
        """
        Diagnose required Kraken private scopes for live trading startup.
        Returns machine-readable classification used by preflight and scripts.
        """

        if not self.has_credentials:
            return {
                "ok": False,
                "scope": "credentials",
                "classification": "missing_credentials",
                "reason": "missing_credentials",
                "allow_unknown_permissions": bool(self.settings.allow_unknown_permissions),
            }
        # Validate required private scopes used by live execution.
        required_checks = [
            ("balance", self.balance),
            ("open_orders", self.open_orders),
        ]
        for scope, fn in required_checks:
            try:
                fn()
            except Exception as exc:
                classification, detail = self._classify_private_scope_error(exc)
                if classification in {"invalid_permissions", "invalid_credentials", "invalid_nonce"}:
                    return {
                        "ok": False,
                        "scope": scope,
                        "classification": classification,
                        "reason": detail,
                        "allow_unknown_permissions": bool(self.settings.allow_unknown_permissions),
                    }
                if self.settings.allow_unknown_permissions:
                    return {
                        "ok": True,
                        "scope": scope,
                        "classification": f"{classification}_override",
                        "reason": detail,
                        "allow_unknown_permissions": True,
                    }
                return {
                    "ok": False,
                    "scope": scope,
                    "classification": classification,
                    "reason": detail,
                    "allow_unknown_permissions": False,
                }
        return {
            "ok": True,
            "scope": "all",
            "classification": "ok",
            "reason": "ok",
            "allow_unknown_permissions": bool(self.settings.allow_unknown_permissions),
        }

    # Public
    def asset_pairs(self) -> dict[str, Any]:
        return self._request("GET", "/0/public/AssetPairs")

    def ticker(self, pair: str | None = None) -> dict[str, Any]:
        params = {"pair": pair} if pair else {}
        return self._request("GET", "/0/public/Ticker", params=params)

    def ohlc(self, pair: str, interval: int = 1) -> dict[str, Any]:
        return self._request("GET", "/0/public/OHLC", params={"pair": pair, "interval": interval})

    def depth(self, pair: str, count: int = 25) -> dict[str, Any]:
        return self._request("GET", "/0/public/Depth", params={"pair": pair, "count": count})

    # Private
    def balance(self) -> dict[str, Any]:
        return self._request("POST", "/0/private/Balance", private=True)

    def open_orders(self) -> dict[str, Any]:
        return self._request("POST", "/0/private/OpenOrders", private=True)

    def closed_orders(self, start: int | None = None) -> dict[str, Any]:
        p = {"start": start} if start is not None else {}
        return self._request("POST", "/0/private/ClosedOrders", params=p, private=True)

    def trades_history(self, start: int | None = None) -> dict[str, Any]:
        p = {"start": start} if start is not None else {}
        return self._request("POST", "/0/private/TradesHistory", params=p, private=True)

    def trade_volume(self, pair: str | None = None, fee_info: bool = True) -> dict[str, Any]:
        p: dict[str, Any] = {"fee-info": "true" if fee_info else "false"}
        if pair:
            p["pair"] = pair
        return self._request("POST", "/0/private/TradeVolume", params=p, private=True)

    def add_order(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/0/private/AddOrder", params=params, private=True)

    def query_orders(self, txid: str | list[str]) -> dict[str, Any]:
        ids = txid if isinstance(txid, str) else ",".join(txid)
        return self._request("POST", "/0/private/QueryOrders", params={"txid": ids}, private=True)

    def cancel_order(self, txid: str) -> dict[str, Any]:
        return self._request("POST", "/0/private/CancelOrder", params={"txid": txid}, private=True)

    def cancel_all(self) -> dict[str, Any]:
        return self._request("POST", "/0/private/CancelAll", private=True)
