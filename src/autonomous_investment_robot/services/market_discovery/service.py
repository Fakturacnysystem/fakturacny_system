from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time
from typing import Any


@dataclass
class DiscoveredInstrument:
    symbol: str
    venue: str
    market_type: str
    market_class: str
    tradeable: bool
    margin_enabled: bool = False
    optional_venue: bool = False
    base: str = ""
    quote: str = ""
    tick_size: float = 0.0
    lot_step: float = 0.0
    min_notional_quote: float = 0.0
    raw: dict[str, Any] | None = None


@dataclass
class MarketDiscoveryResult:
    ts: float
    spot_symbols: list[str]
    margin_symbols: list[str]
    perp_symbols: list[str]
    xstocks_symbols: list[str]
    xstocks_etf_symbols: list[str]
    optional_symbols: list[str]
    market_class_counts: dict[str, int]
    instruments: list[DiscoveredInstrument]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "spot_symbols": list(self.spot_symbols),
            "margin_symbols": list(self.margin_symbols),
            "perp_symbols": list(self.perp_symbols),
            "xstocks_symbols": list(self.xstocks_symbols),
            "xstocks_etf_symbols": list(self.xstocks_etf_symbols),
            "optional_symbols": list(self.optional_symbols),
            "market_class_counts": dict(self.market_class_counts),
            "errors": list(self.errors),
            "instruments": [asdict(x) for x in self.instruments],
        }


class KrakenMarketDiscoveryService:
    """Discovers Kraken spot/margin/perp instruments and persists snapshots."""

    def __init__(self, run_dir: str) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_path = self.run_dir / "market_discovery.json"

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    @staticmethod
    def _normalize_asset(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        out = raw.replace("/", "")
        if out.startswith("X") and len(out) >= 3 and out[1:].isalpha():
            return out[1:]
        if out.startswith("Z") and len(out) >= 3 and out[1:].isalpha():
            return out[1:]
        return out

    @staticmethod
    def _is_fiat_quote(quote: str) -> bool:
        return quote in {"USD", "EUR", "GBP", "CHF", "CAD"}

    @staticmethod
    def _looks_like_etf_asset(asset: str) -> bool:
        return asset in {"SPY", "QQQ", "VTI", "GLD", "SLV", "TQQQ", "DIA", "IWM"}

    def _looks_like_xstock_base(self, *, base: str, quote: str) -> bool:
        if not base or not quote:
            return False
        if not self._is_fiat_quote(quote):
            return False
        if base.endswith("X") and base[:-1].isalpha():
            return True
        return False

    def _classify_spot_market_class(self, *, symbol: str, meta: dict[str, Any]) -> str:
        base = self._normalize_asset(meta.get("base"))
        quote = self._normalize_asset(meta.get("quote"))
        altname = self._normalize_asset(meta.get("altname"))
        wsname = self._normalize_asset(meta.get("wsname"))
        category = str(meta.get("category", "") or "").strip().lower()
        tags = str(meta.get("tags", "") or "").strip().lower()
        marker = " ".join(
            x
            for x in (
                str(symbol or "").lower(),
                str(altname or "").lower(),
                str(wsname or "").lower(),
                category,
                tags,
            )
            if x
        )
        if any(tok in marker for tok in ("xstock", "equity", "stock", "share")):
            if any(tok in marker for tok in ("etf", "index fund")) or self._looks_like_etf_asset(base.rstrip("X")):
                return "xstock_etf"
            return "xstock"
        if self._looks_like_xstock_base(base=base, quote=quote):
            if self._looks_like_etf_asset(base.rstrip("X")):
                return "xstock_etf"
            return "xstock"
        return "crypto_spot"

    def _classify_perp_market_class(self, *, symbol: str, row: dict[str, Any]) -> str:
        marker = " ".join(
            str(x or "").lower()
            for x in (
                symbol,
                row.get("category", ""),
                row.get("tags", ""),
                row.get("underlying", ""),
            )
        )
        if "xstock" in marker or "equity" in marker or "stock" in marker:
            if "etf" in marker:
                return "xstock_etf_perp"
            return "xstock_perp"
        return "crypto_perp"

    def discover_spot_and_margin(self, asset_pairs: dict[str, Any], ticker: dict[str, Any] | None = None) -> list[DiscoveredInstrument]:
        out: list[DiscoveredInstrument] = []
        ticker = ticker if isinstance(ticker, dict) else {}
        for symbol, meta in asset_pairs.items() if isinstance(asset_pairs, dict) else []:
            if not isinstance(meta, dict):
                continue
            status = str(meta.get("status", "online") or "online").strip().lower()
            tradeable = status in {"online", "tradable"}
            if ".d" in str(symbol).lower() or str(symbol).lower().endswith(".d"):
                continue
            pair_decimals = self._safe_int(meta.get("pair_decimals"), 8)
            lot_decimals = self._safe_int(meta.get("lot_decimals"), 8)
            tick_size = 10 ** (-max(0, pair_decimals))
            lot_step = 10 ** (-max(0, lot_decimals))
            ordermin = self._safe_float(meta.get("ordermin"), 0.0)
            costmin = self._safe_float(meta.get("costmin"), 0.0)
            row = ticker.get(symbol, {})
            bid_raw = row.get("b", 0.0) if isinstance(row, dict) else 0.0
            ask_raw = row.get("a", 0.0) if isinstance(row, dict) else 0.0
            bid = self._safe_float(bid_raw[0] if isinstance(bid_raw, list) and bid_raw else bid_raw, 0.0)
            ask = self._safe_float(ask_raw[0] if isinstance(ask_raw, list) and ask_raw else ask_raw, 0.0)
            ref = max(0.0, (bid + ask) / 2.0) if (bid > 0.0 and ask > 0.0) else max(bid, ask, 0.0)
            min_notional_quote = max(costmin, ordermin * ref)
            leverage_buy = meta.get("leverage_buy", [])
            leverage_sell = meta.get("leverage_sell", [])
            margin_enabled = (
                isinstance(leverage_buy, list)
                and any(self._safe_float(x, 0.0) > 1.0 for x in leverage_buy)
            ) or (
                isinstance(leverage_sell, list)
                and any(self._safe_float(x, 0.0) > 1.0 for x in leverage_sell)
            )
            market_class = self._classify_spot_market_class(symbol=str(symbol), meta=meta)
            out.append(
                DiscoveredInstrument(
                    symbol=str(symbol),
                    venue="kraken",
                    market_type="spot",
                    market_class=market_class,
                    tradeable=tradeable,
                    margin_enabled=bool(margin_enabled),
                    optional_venue=False,
                    base=str(meta.get("base", "") or ""),
                    quote=str(meta.get("quote", "") or ""),
                    tick_size=tick_size,
                    lot_step=lot_step,
                    min_notional_quote=min_notional_quote,
                    raw={"status": status},
                )
            )
        return out

    def discover_perps(self, futures_instruments_payload: dict[str, Any]) -> list[DiscoveredInstrument]:
        rows = futures_instruments_payload.get("instruments", []) if isinstance(futures_instruments_payload, dict) else []
        out: list[DiscoveredInstrument] = []
        if not isinstance(rows, list):
            return out
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol", "") or row.get("product_id", "") or "").strip()
            if not symbol:
                continue
            t = str(row.get("type", "") or row.get("contractType", "") or "").lower()
            is_perp = ("perpetual" in t) or ("pi_" in symbol.lower()) or ("pf_" in symbol.lower())
            if not is_perp:
                continue
            status = str(row.get("tradeable", row.get("status", "online"))).strip().lower()
            tradeable = status in {"online", "true", "tradable", "1", "open"}
            tick_size = self._safe_float(row.get("tickSize", row.get("tick_size", 0.0)), 0.0)
            lot_step = self._safe_float(row.get("contractSize", row.get("contract_size", 0.0)), 0.0)
            market_class = self._classify_perp_market_class(symbol=symbol, row=row)
            out.append(
                DiscoveredInstrument(
                    symbol=symbol,
                    venue="kraken_futures",
                    market_type="perp",
                    market_class=market_class,
                    tradeable=tradeable,
                    margin_enabled=True,
                    optional_venue=self._is_optional_symbol(symbol=symbol, row=row) or market_class.startswith("xstock"),
                    base=str(row.get("underlying", row.get("base", "")) or ""),
                    quote=str(row.get("quote", row.get("settlementCurrency", "")) or ""),
                    tick_size=tick_size,
                    lot_step=lot_step,
                    min_notional_quote=0.0,
                    raw={"status": status},
                )
            )
        return out

    @staticmethod
    def _is_optional_symbol(symbol: str, row: dict[str, Any]) -> bool:
        s = symbol.lower()
        tags = str(row.get("tags", "") or "").lower()
        cat = str(row.get("category", "") or "").lower()
        marker = " ".join([s, tags, cat])
        return any(x in marker for x in ("xstock", "xstocks", "stock", "equity", "etf"))

    def discover(
        self,
        *,
        spot_connector: Any | None = None,
        futures_connector: Any | None = None,
        enable_spot: bool = True,
        enable_margin: bool = True,
        enable_perps: bool = True,
        enable_optional_venues: bool = True,
    ) -> MarketDiscoveryResult:
        errors: list[str] = []
        instruments: list[DiscoveredInstrument] = []

        if enable_spot and spot_connector is not None:
            try:
                asset_pairs = spot_connector.asset_pairs()
                ticker = spot_connector.ticker()
                instruments.extend(self.discover_spot_and_margin(asset_pairs, ticker))
            except Exception as exc:
                errors.append(f"spot_discovery_error:{exc}")

        if enable_perps and futures_connector is not None:
            try:
                fut_raw = futures_connector.instruments()
                instruments.extend(self.discover_perps(fut_raw))
            except Exception as exc:
                errors.append(f"perps_discovery_error:{exc}")

        spot_symbols = sorted({x.symbol for x in instruments if x.market_type == "spot" and x.tradeable})
        margin_symbols = sorted({x.symbol for x in instruments if x.market_type == "spot" and x.tradeable and x.margin_enabled}) if enable_margin else []
        perp_symbols = sorted({x.symbol for x in instruments if x.market_type == "perp" and x.tradeable})
        xstocks_symbols = sorted(
            {
                x.symbol
                for x in instruments
                if x.tradeable and x.market_class in {"xstock", "xstock_perp"}
            }
        )
        xstocks_etf_symbols = sorted(
            {
                x.symbol
                for x in instruments
                if x.tradeable and x.market_class in {"xstock_etf", "xstock_etf_perp"}
            }
        )
        optional_symbols = (
            sorted({x.symbol for x in instruments if x.tradeable and x.optional_venue})
            if enable_optional_venues
            else []
        )
        market_class_counts = dict(
            Counter(x.market_class for x in instruments if x.tradeable and str(x.market_class or "").strip())
        )

        result = MarketDiscoveryResult(
            ts=time.time(),
            spot_symbols=spot_symbols,
            margin_symbols=margin_symbols,
            perp_symbols=perp_symbols,
            xstocks_symbols=xstocks_symbols,
            xstocks_etf_symbols=xstocks_etf_symbols,
            optional_symbols=optional_symbols,
            market_class_counts=market_class_counts,
            instruments=instruments,
            errors=errors,
        )
        self.persist(result)
        return result

    def persist(self, result: MarketDiscoveryResult) -> None:
        payload = result.to_dict()
        self.snapshot_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
