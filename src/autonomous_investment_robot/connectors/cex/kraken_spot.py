from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any

from autonomous_investment_robot.config.settings import KrakenSpotExecutionSettings

logger = logging.getLogger("KrakenSpotConnector")


class KrakenSpotConnectorError(RuntimeError):
    pass


class KrakenSpotTradingBlocked(KrakenSpotConnectorError):
    pass


@dataclass(frozen=True)
class KrakenSpotTradeRow:
    trade_id: str
    order_id: str
    symbol: str
    side: str
    base_qty: float
    quote_cost: float
    fee_quote: float
    price: float
    timestamp_ms: int
    raw: dict[str, Any]


@dataclass(frozen=True)
class KrakenSpotTradeHistoryPage:
    rows: list[KrakenSpotTradeRow]
    fetched_count: int
    total_count: int | None


class KrakenSpotConnector:
    provider_id = "kraken_spot"
    supports_live_trading = True

    def __init__(
        self,
        settings: KrakenSpotExecutionSettings | None = None,
        *,
        api_key_env: str | None = None,
        api_secret_env: str | None = None,
    ) -> None:
        self.settings = settings or KrakenSpotExecutionSettings()
        key_env = api_key_env or self.settings.api_key_env
        secret_env = api_secret_env or self.settings.api_secret_env
        self._api_key = os.getenv(key_env, "").strip() or os.getenv("KRAKEN_API_KEY", "").strip()
        self._api_secret = os.getenv(secret_env, "").strip() or os.getenv("KRAKEN_API_SECRET", "").strip()
        try:
            import ccxt  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise KrakenSpotConnectorError("ccxt_unavailable") from exc
        self._ccxt = ccxt
        payload = {
            "enableRateLimit": True,
            "timeout": int(float(self.settings.request_timeout_s) * 1000),
        }
        if self._api_key and self._api_secret:
            payload["apiKey"] = self._api_key
            payload["secret"] = self._api_secret
        self.exchange = ccxt.kraken(payload)
        self.exchange.options = {**getattr(self.exchange, "options", {}), "createMarketBuyOrderRequiresPrice": False}
        self._markets_loaded = False

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key and self._api_secret)

    def _require_private_access(self) -> None:
        if not self.has_credentials:
            raise KrakenSpotConnectorError("missing_credentials")

    def _load_markets(self) -> None:
        if not self._markets_loaded:
            self.exchange.load_markets()
            self._markets_loaded = True

    def _market(self, symbol: str) -> dict[str, Any]:
        self._load_markets()
        try:
            return dict(self.exchange.market(symbol))
        except Exception as exc:
            raise KrakenSpotConnectorError(f"symbol_missing:{symbol}") from exc

    def _userref(self, client_order_id: str) -> int:
        digest = hashlib.sha256(client_order_id.encode("utf-8")).hexdigest()[:8]
        return max(1, int(digest, 16))

    def client_order_userref(self, client_order_id: str) -> int:
        return self._userref(client_order_id)

    def _match_client_order(self, order: dict[str, Any], client_order_id: str) -> bool:
        info = order.get("info", {}) if isinstance(order.get("info"), dict) else {}
        userref = str(self._userref(client_order_id))
        candidates = [
            str(order.get("clientOrderId", "")),
            str(order.get("id", "")),
            str(info.get("userref", "")),
            str(info.get("cl_ord_id", "")),
        ]
        return client_order_id in candidates or userref in candidates

    def verify_live_permissions(self) -> tuple[bool, str]:
        if not self.has_credentials:
            return False, "missing_credentials"
        try:
            self.exchange.fetch_balance()
        except Exception as exc:
            return False, f"kraken_spot_private_api_unverified:{exc}"
        return True, "private_api_verified"

    def exchange_info(self) -> dict[str, Any]:
        self._load_markets()
        symbols: list[dict[str, Any]] = []
        for market in self.exchange.markets.values():
            if not isinstance(market, dict):
                continue
            if not bool(market.get("spot", False)):
                continue
            symbols.append(
                {
                    "symbol": str(market.get("symbol", "")),
                    "active": bool(market.get("active", False)),
                    "spot": True,
                    "id": str(market.get("id", "")),
                }
            )
        return {"symbols": symbols}

    def market_constraints(self, symbol: str) -> dict[str, Any]:
        market = self._market(symbol)
        limits = market.get("limits", {}) if isinstance(market.get("limits"), dict) else {}
        amount_limits = limits.get("amount", {}) if isinstance(limits.get("amount"), dict) else {}
        cost_limits = limits.get("cost", {}) if isinstance(limits.get("cost"), dict) else {}
        precision = market.get("precision", {}) if isinstance(market.get("precision"), dict) else {}
        return {
            "symbol": str(market.get("symbol", symbol)),
            "active": bool(market.get("active", False)),
            "spot": bool(market.get("spot", False)),
            "min_order_size": float(amount_limits.get("min") or 0.0),
            "min_notional": float(cost_limits.get("min") or 0.0),
            "quantity_step": float(precision.get("amount") or 0.0),
            "price_tick": float(precision.get("price") or 0.0),
            "maker_assumption": "post_only_supported",
            "taker_assumption": "marketable_limit_or_market",
            "reduce_only_supported": False,
            "post_only_supported": True,
            "replace_supported": False,
            "expire_supported": True,
            "confidence": "exchange_market_metadata",
            "market_id": str(market.get("id", "")),
            "base": str(market.get("base", "")),
            "quote": str(market.get("quote", "")),
        }

    def symbol_from_market_id(self, market_id: str) -> str:
        self._load_markets()
        normalized = str(market_id or "").strip()
        if not normalized:
            return ""
        by_id = getattr(self.exchange, "markets_by_id", {}) or {}
        direct = by_id.get(normalized)
        if isinstance(direct, list) and direct:
            market = direct[0]
            if isinstance(market, dict):
                return str(market.get("symbol", normalized))
        if isinstance(direct, dict):
            return str(direct.get("symbol", normalized))
        needle = normalized.upper()
        for market in self.exchange.markets.values():
            if not isinstance(market, dict):
                continue
            candidates = {
                str(market.get("id", "")).upper(),
                str(market.get("wsname", "")).upper(),
                str(market.get("altname", "")).upper(),
                str(market.get("symbol", "")).upper(),
            }
            if needle in candidates:
                return str(market.get("symbol", normalized))
        return normalized

    def normalize_amount(self, symbol: str, amount: float) -> float:
        self._load_markets()
        try:
            return float(self.exchange.amount_to_precision(symbol, amount))
        except Exception as exc:
            raise KrakenSpotConnectorError(f"amount_precision_failed:{exc}") from exc

    def normalize_price(self, symbol: str, price: float) -> float:
        self._load_markets()
        try:
            return float(self.exchange.price_to_precision(symbol, price))
        except Exception as exc:
            raise KrakenSpotConnectorError(f"price_precision_failed:{exc}") from exc

    def book_ticker(self, symbol: str) -> dict[str, Any]:
        try:
            order_book = self.exchange.fetch_order_book(symbol, limit=10)
        except Exception as exc:
            raise KrakenSpotConnectorError(f"book_fetch_failed:{exc}") from exc
        bids = order_book.get("bids", []) if isinstance(order_book, dict) else []
        asks = order_book.get("asks", []) if isinstance(order_book, dict) else []
        bid = bids[0][0] if bids else 0.0
        ask = asks[0][0] if asks else 0.0
        bid_qty = bids[0][1] if bids else 0.0
        ask_qty = asks[0][1] if asks else 0.0
        ts = order_book.get("timestamp") if isinstance(order_book, dict) else None
        depth_notional = 0.0
        for price, qty, *_ in bids[:10]:
            depth_notional += float(price or 0.0) * float(qty or 0.0)
        for price, qty, *_ in asks[:10]:
            depth_notional += float(price or 0.0) * float(qty or 0.0)
        return {
            "symbol": symbol,
            "bidPrice": str(bid),
            "askPrice": str(ask),
            "bidQty": str(bid_qty),
            "askQty": str(ask_qty),
            "timestamp": ts,
            "depthNotional": depth_notional,
        }

    def balances(self) -> list[dict[str, Any]]:
        self._require_private_access()
        try:
            balance = self.exchange.fetch_balance()
        except Exception as exc:
            raise KrakenSpotConnectorError(f"balance_fetch_failed:{exc}") from exc
        totals = balance.get("total", {}) if isinstance(balance, dict) else {}
        frees = balance.get("free", {}) if isinstance(balance, dict) else {}
        used = balance.get("used", {}) if isinstance(balance, dict) else {}
        rows: list[dict[str, Any]] = []
        for asset, total in totals.items():
            try:
                total_float = float(total or 0.0)
            except Exception:
                continue
            rows.append(
                {
                    "asset": str(asset),
                    "balance": str(total_float),
                    "availableBalance": str(float(frees.get(asset, 0.0) or 0.0)),
                    "usedBalance": str(float(used.get(asset, 0.0) or 0.0)),
                    "equity": str(total_float),
                }
            )
        return rows

    def base_balance(self, symbol: str) -> dict[str, float]:
        rules = self.market_constraints(symbol)
        base_asset = str(rules.get("base", ""))
        rows = self.balances()
        for row in rows:
            if str(row.get("asset", "")).upper() != base_asset.upper():
                continue
            return {
                "total": float(row.get("balance", 0.0) or 0.0),
                "free": float(row.get("availableBalance", 0.0) or 0.0),
                "used": float(row.get("usedBalance", 0.0) or 0.0),
            }
        return {"total": 0.0, "free": 0.0, "used": 0.0}

    def quote_balance(self, symbol: str) -> dict[str, float | str]:
        rules = self.market_constraints(symbol)
        quote_asset = str(rules.get("quote", ""))
        rows = self.balances()
        for row in rows:
            if str(row.get("asset", "")).upper() != quote_asset.upper():
                continue
            return {
                "asset": quote_asset,
                "total": float(row.get("balance", 0.0) or 0.0),
                "free": float(row.get("availableBalance", 0.0) or 0.0),
                "used": float(row.get("usedBalance", 0.0) or 0.0),
            }
        return {"asset": quote_asset, "total": 0.0, "free": 0.0, "used": 0.0}

    def position_risk(self, symbol: str | None = None) -> list[dict[str, Any]]:
        symbols = [symbol] if symbol else [str(row.get("symbol", "")) for row in self.exchange_info().get("symbols", []) if str(row.get("symbol", ""))]
        rows: list[dict[str, Any]] = []
        for current in symbols:
            try:
                bal = self.base_balance(current)
                qty = float(bal.get("total", 0.0) or 0.0)
                if qty <= 0.0:
                    continue
                book = self.book_ticker(current)
                bid = float(book.get("bidPrice", 0.0) or 0.0)
                ask = float(book.get("askPrice", 0.0) or 0.0)
                mark = (bid + ask) / 2.0 if bid > 0.0 and ask > 0.0 else max(bid, ask, 0.0)
                rows.append(
                    {
                        "symbol": current,
                        "positionAmt": qty,
                        "size": qty,
                        "qty": qty,
                        "markPrice": mark,
                        "mark": mark,
                        "raw": {"free": bal.get("free", 0.0), "used": bal.get("used", 0.0)},
                    }
                )
            except Exception:
                continue
        return rows

    def _normalize_order(self, order: dict[str, Any], *, client_order_id: str | None = None) -> dict[str, Any]:
        info = order.get("info", {}) if isinstance(order.get("info"), dict) else {}
        symbol = str(order.get("symbol", info.get("descr", {}).get("pair", "")))
        status = str(order.get("status", info.get("status", "open"))).upper()
        if status in {"OPEN", "PENDING"}:
            status = "NEW"
        elif status in {"CLOSED", "FILLED"}:
            status = "FILLED"
        elif status in {"CANCELED", "CANCELLED", "EXPIRED"}:
            status = "CANCELED"
        executed_qty = float(order.get("filled", info.get("vol_exec", 0.0)) or 0.0)
        avg_price = float(order.get("average", info.get("avg_price", info.get("price", 0.0))) or 0.0)
        quote_qty = abs(executed_qty * avg_price)
        return {
            "clientOrderId": str(client_order_id or order.get("clientOrderId", info.get("cl_ord_id", info.get("userref", "")))),
            "orderId": str(
                order.get("id")
                or info.get("id")
                or (info.get("txid", [""])[0] if isinstance(info.get("txid"), list) and info.get("txid") else info.get("txid", ""))
                or ""
            ),
            "status": status,
            "symbol": symbol,
            "side": str(order.get("side", info.get("descr", {}).get("type", ""))).upper(),
            "executedQty": str(executed_qty),
            "avgPrice": str(avg_price),
            "filledNotional": str(quote_qty),
            "raw": order,
        }

    def open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        self._require_private_access()
        try:
            orders = self.exchange.fetch_open_orders(symbol)
        except Exception as exc:
            raise KrakenSpotConnectorError(f"open_orders_fetch_failed:{exc}") from exc
        return [self._normalize_order(order) for order in orders or [] if isinstance(order, dict)]

    def _closed_orders(self, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self._require_private_access()
        try:
            orders = self.exchange.fetch_closed_orders(symbol, limit=limit)
        except Exception:
            return []
        return [self._normalize_order(order) for order in orders or [] if isinstance(order, dict)]

    def query_order(self, symbol: str, client_order_id: str) -> dict[str, Any] | None:
        for order in self.open_orders(symbol):
            if self._match_client_order(order, client_order_id):
                return self._normalize_order(order, client_order_id=client_order_id)
        for order in self._closed_orders(symbol, limit=50):
            if self._match_client_order(order, client_order_id):
                return self._normalize_order(order, client_order_id=client_order_id)
        return None

    def validate_order_preview(
        self,
        *,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        post_only: bool = False,
        client_order_id: str = "",
        time_in_force: str = "",
        expire_seconds: int | None = None,
    ) -> tuple[bool, str]:
        self._require_private_access()
        params: dict[str, Any] = {"validate": True}
        if client_order_id:
            params["cl_ord_id"] = client_order_id
        if post_only:
            params["postOnly"] = True
        if time_in_force:
            params["timeinforce"] = str(time_in_force)
        if expire_seconds is not None:
            params["expiretm"] = f"+{max(1, int(expire_seconds))}"
        try:
            self.exchange.create_order(symbol, "limit", side.lower(), amount, price, params)
        except Exception as exc:
            return False, str(exc)
        return True, "validated"

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_private_access()
        symbol = str(payload.get("symbol", ""))
        side = str(payload.get("side", "")).lower()
        amount = float(payload.get("quantity", 0.0) or 0.0)
        client_order_id = str(payload.get("newClientOrderId", ""))
        order_type = str(payload.get("type", "LIMIT")).lower()
        price = payload.get("price")
        params: dict[str, Any] = {}
        if client_order_id:
            params["cl_ord_id"] = client_order_id
        if bool(payload.get("postOnly", False)):
            params["postOnly"] = True
        if bool(payload.get("validate", False)):
            params["validate"] = True
        if payload.get("timeInForce"):
            params["timeinforce"] = str(payload.get("timeInForce"))
        if payload.get("expireSeconds") is not None:
            params["expiretm"] = f"+{max(1, int(payload.get('expireSeconds')))}"
        try:
            created = self.exchange.create_order(
                symbol,
                "market" if order_type == "market" else "limit",
                side,
                amount,
                None if price is None else float(price),
                params,
            )
        except Exception as exc:
            raise KrakenSpotConnectorError(f"place_order_failed:{exc}") from exc
        return self._normalize_order(created, client_order_id=client_order_id)

    def get_websockets_token(self) -> str:
        self._require_private_access()
        try:
            payload = self.exchange.privatePostGetWebSocketsToken()
        except Exception as exc:
            raise KrakenSpotConnectorError(f"websockets_token_fetch_failed:{exc}") from exc
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        token = str(result.get("token", "") or "")
        if not token:
            raise KrakenSpotConnectorError("websockets_token_missing")
        return token

    def cancel_order(self, symbol: str, client_order_id: str) -> dict[str, Any]:
        self._require_private_access()
        order = self.query_order(symbol, client_order_id)
        if order is None:
            raise KrakenSpotConnectorError(f"order_not_found:{client_order_id}")
        try:
            result = self.exchange.cancel_order(str(order.get("orderId", "")), symbol)
        except Exception as exc:
            raise KrakenSpotConnectorError(f"cancel_order_failed:{exc}") from exc
        return self._normalize_order(result if isinstance(result, dict) else {"id": order.get("orderId"), "symbol": symbol, "status": "canceled"}, client_order_id=client_order_id)

    def trade_history_page(self, symbol: str, *, offset: int = 0, limit: int = 50) -> KrakenSpotTradeHistoryPage:
        self._require_private_access()
        market = self._market(symbol)
        market_id = str(market.get("id", ""))
        try:
            payload = self.exchange.privatePostTradesHistory({"ofs": offset, "trades": True})
        except Exception as exc:
            raise KrakenSpotConnectorError(f"trade_history_fetch_failed:{exc}") from exc
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        trades = result.get("trades", {}) if isinstance(result, dict) else {}
        fetched_count = len(trades) if isinstance(trades, dict) else 0
        total_count_raw = result.get("count") if isinstance(result, dict) else None
        try:
            total_count = int(total_count_raw) if total_count_raw is not None else None
        except Exception:
            total_count = None
        rows: list[KrakenSpotTradeRow] = []
        for trade_id, row in trades.items() if isinstance(trades, dict) else []:
            if not isinstance(row, dict):
                continue
            pair = str(row.get("pair", ""))
            if pair and market_id and pair != market_id:
                continue
            try:
                rows.append(
                    KrakenSpotTradeRow(
                        trade_id=str(trade_id),
                        order_id=str(row.get("ordertxid", "")),
                        symbol=symbol,
                        side=str(row.get("type", "")).lower(),
                        base_qty=float(row.get("vol", 0.0) or 0.0),
                        quote_cost=float(row.get("cost", 0.0) or 0.0),
                        fee_quote=float(row.get("fee", 0.0) or 0.0),
                        price=float(row.get("price", 0.0) or 0.0),
                        timestamp_ms=int(float(row.get("time", 0.0) or 0.0) * 1000),
                        raw={"id": trade_id, **row},
                    )
                )
            except Exception:
                continue
        rows.sort(key=lambda item: (item.timestamp_ms, item.trade_id))
        return KrakenSpotTradeHistoryPage(rows=rows[:limit], fetched_count=fetched_count, total_count=total_count)

    def trade_history(self, symbol: str, *, offset: int = 0, limit: int = 50) -> list[KrakenSpotTradeRow]:
        return self.trade_history_page(symbol, offset=offset, limit=limit).rows

    def get_account_summary(self) -> tuple[float, float]:
        try:
            rows = self.balances()
        except Exception as exc:
            logger.error("Kraken SPOT balance fetch failed: %s", exc)
            return 0.0, 0.0
        total = 0.0
        free = 0.0
        for row in rows:
            try:
                total += max(0.0, float(row.get("balance", 0.0) or 0.0))
                free += max(0.0, float(row.get("availableBalance", 0.0) or 0.0))
            except Exception:
                continue
        return total, free

    def execute_margin_order(self, symbol: str, side: str, amount_eur: float, leverage: float) -> Any:  # noqa: ARG002
        raise KrakenSpotTradingBlocked("kraken_spot_margin_unsupported_long_only_spot_doctrine")
