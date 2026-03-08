from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os
import time
from pathlib import Path
from typing import Any


def _env_csv(name: str, default: str) -> list[str]:
    raw = str(os.getenv(name, default) or default).strip()
    if not raw:
        return []
    return [x.strip().upper() for x in raw.split(",") if x.strip()]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    if not math.isfinite(out):
        return float(default)
    return float(out)


@dataclass
class KrakenUniverseConfig:
    mode: str = "kraken_spot_auto_top"
    max_pairs: int = 25
    rotate_every_s: float = 180.0
    quote_allowlist: list[str] | None = None
    denylist_tokens: list[str] | None = None
    min_24h_vol_quote: float = 500000.0
    max_spread_bps: float = 35.0
    cache_ttl_s: float = 1800.0


@dataclass
class KrakenUniverseCandidate:
    symbol: str
    base: str
    quote: str
    bid: float
    ask: float
    spread_bps: float
    vol_24h_quote: float
    liquidity_score: float
    source: str = "kraken_ticker"


class KrakenUniverseService:
    def __init__(
        self,
        *,
        run_dir: str,
        connector: Any | None = None,
        config: KrakenUniverseConfig | None = None,
        fixed_universe: list[str] | None = None,
    ) -> None:
        self.connector = connector
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.run_dir / "universe_cache.json"
        self.config = config or KrakenUniverseConfig(
            mode=str(os.getenv("AUTONOMOUS_UNIVERSE_MODE", "kraken_spot_auto_top") or "kraken_spot_auto_top").strip().lower(),
            max_pairs=max(1, int(float(os.getenv("AUTONOMOUS_UNIVERSE_MAX_PAIRS", "25") or "25"))),
            rotate_every_s=max(10.0, _safe_float(os.getenv("AUTONOMOUS_UNIVERSE_ROTATE_EVERY_S", "180"), 180.0)),
            quote_allowlist=_env_csv("AUTONOMOUS_UNIVERSE_QUOTE_ALLOWLIST", "USD,EUR"),
            denylist_tokens=_env_csv("AUTONOMOUS_UNIVERSE_DENYLIST", "USDT,DAI,USDC"),
            min_24h_vol_quote=max(0.0, _safe_float(os.getenv("AUTONOMOUS_UNIVERSE_MIN_24H_VOL_QUOTE", "500000"), 500000.0)),
            max_spread_bps=max(0.1, _safe_float(os.getenv("AUTONOMOUS_UNIVERSE_MAX_SPREAD_BPS", "35"), 35.0)),
            cache_ttl_s=max(30.0, _safe_float(os.getenv("AUTONOMOUS_UNIVERSE_CACHE_TTL_S", "1800"), 1800.0)),
        )
        self.fixed_universe = [str(s).upper().replace("/", "") for s in (fixed_universe or []) if str(s).strip()]
        self._last_refresh_ts: float = 0.0
        self._candidates: list[KrakenUniverseCandidate] = []
        self._banned_symbols: dict[str, float] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        self._last_refresh_ts = _safe_float(raw.get("saved_ts", 0.0))
        banned = raw.get("banned_symbols", {})
        if isinstance(banned, dict):
            for k, v in banned.items():
                self._banned_symbols[str(k).upper()] = _safe_float(v)
        rows = raw.get("candidates", [])
        out: list[KrakenUniverseCandidate] = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    out.append(
                        KrakenUniverseCandidate(
                            symbol=str(row.get("symbol", "")).upper(),
                            base=str(row.get("base", "")).upper(),
                            quote=str(row.get("quote", "")).upper(),
                            bid=_safe_float(row.get("bid", 0.0)),
                            ask=_safe_float(row.get("ask", 0.0)),
                            spread_bps=_safe_float(row.get("spread_bps", 0.0)),
                            vol_24h_quote=_safe_float(row.get("vol_24h_quote", 0.0)),
                            liquidity_score=_safe_float(row.get("liquidity_score", 0.0)),
                            source=str(row.get("source", "kraken_ticker") or "kraken_ticker"),
                        )
                    )
                except Exception:
                    continue
        self._candidates = out

    def _save_cache(self) -> None:
        payload = {
            "saved_ts": float(time.time()),
            "mode": self.config.mode,
            "candidates": [asdict(x) for x in self._candidates],
            "banned_symbols": dict(sorted(self._banned_symbols.items())),
        }
        try:
            self.cache_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _first_float(value: Any) -> float:
        if isinstance(value, list):
            if not value:
                return 0.0
            return _safe_float(value[0], 0.0)
        return _safe_float(value, 0.0)

    @staticmethod
    def _last_float(value: Any) -> float:
        if isinstance(value, list):
            if not value:
                return 0.0
            return _safe_float(value[-1], 0.0)
        return _safe_float(value, 0.0)

    def _ticker_rows(self, ticker: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(ticker, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for symbol, row in ticker.items():
            if not isinstance(row, dict):
                continue
            sym = str(symbol).upper().replace("/", "")
            if not sym:
                continue
            out[sym] = row
        return out

    def _pair_rows(self, pairs: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(pairs, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for key, row in pairs.items():
            if not isinstance(row, dict):
                continue
            status = str(row.get("status", "online") or "online").lower()
            if status not in {"online", "tradable"}:
                continue
            base = str(row.get("base", "") or "").upper()
            quote = str(row.get("quote", "") or "").upper()
            sym = str(key).upper().replace("/", "")
            alt = str(row.get("altname", "") or "").upper().replace("/", "")
            ws = str(row.get("wsname", "") or "").upper().replace("/", "")
            symbol = alt or ws or sym
            if not symbol:
                continue
            meta = dict(row)
            meta["_symbol"] = symbol
            meta["_base"] = base
            meta["_quote"] = quote
            out[symbol] = meta
            out.setdefault(sym, meta)
        return out

    def note_runtime_error(self, symbol: str, error_text: str) -> None:
        txt = str(error_text or "").lower()
        if "restricted" not in txt and "not available" not in txt and "unknown asset pair" not in txt:
            return
        sym = str(symbol or "").upper().replace("/", "")
        if not sym:
            return
        self._banned_symbols[sym] = time.time()
        self._save_cache()

    def refresh_if_needed(self, now_ts: float | None = None, *, force: bool = False) -> None:
        now = time.time() if now_ts is None else float(now_ts)
        if not force and self._candidates and (now - self._last_refresh_ts) <= self.config.cache_ttl_s:
            return
        if self.connector is None:
            return
        try:
            pairs = self.connector.asset_pairs()
            ticker = self.connector.ticker()
        except Exception:
            return
        pair_rows = self._pair_rows(pairs)
        ticker_rows = self._ticker_rows(ticker)
        allow_quotes = set(self.config.quote_allowlist or [])
        deny = set(self.config.denylist_tokens or [])
        out: list[KrakenUniverseCandidate] = []
        for symbol, row in pair_rows.items():
            base = str(row.get("_base", "") or "").upper()
            quote = str(row.get("_quote", "") or "").upper()
            if allow_quotes and quote not in allow_quotes:
                continue
            if any(tok and (tok in base or tok in quote or tok in symbol) for tok in deny):
                continue
            if symbol in self._banned_symbols:
                continue
            trow = ticker_rows.get(symbol) or ticker_rows.get(str(row.get("altname", "") or "").upper().replace("/", ""))
            if not isinstance(trow, dict):
                continue
            bid = self._first_float(trow.get("b"))
            ask = self._first_float(trow.get("a"))
            if bid <= 0.0 or ask <= 0.0:
                continue
            mid = (bid + ask) / 2.0
            spread_bps = ((ask - bid) / max(mid, 1e-12)) * 10000.0
            vol_base = self._last_float(trow.get("v"))
            vol_quote = max(0.0, vol_base * mid)
            if vol_quote < self.config.min_24h_vol_quote:
                continue
            if spread_bps > self.config.max_spread_bps:
                continue
            liquidity_score = (vol_quote / 1_000_000.0) - (spread_bps / 10_000.0)
            out.append(
                KrakenUniverseCandidate(
                    symbol=symbol,
                    base=base,
                    quote=quote,
                    bid=bid,
                    ask=ask,
                    spread_bps=spread_bps,
                    vol_24h_quote=vol_quote,
                    liquidity_score=liquidity_score,
                )
            )
        out.sort(key=lambda x: (x.liquidity_score, x.vol_24h_quote), reverse=True)
        self._candidates = out
        self._last_refresh_ts = now
        self._save_cache()

    def _candidates_symbols(self) -> list[str]:
        return [x.symbol for x in self._candidates if x.symbol]

    def select_active(self, now_ts: float | None = None) -> list[str]:
        now = time.time() if now_ts is None else float(now_ts)
        self.refresh_if_needed(now_ts=now)
        mode = self.config.mode
        if mode == "fixed":
            return list(dict.fromkeys(self.fixed_universe))
        symbols = self._candidates_symbols()
        if mode == "kraken_spot_auto_all":
            return symbols
        if mode != "kraken_spot_auto_top":
            return symbols[: max(1, self.config.max_pairs)]
        if not symbols:
            return []
        n = max(1, self.config.max_pairs)
        if len(symbols) <= n:
            return symbols
        rotate_window = max(10.0, float(self.config.rotate_every_s))
        windows = max(1, int(math.ceil(len(symbols) / max(1, n))))
        bucket = int(now // rotate_window)
        idx = bucket % windows
        start = idx * n
        out = symbols[start : start + n]
        if len(out) < n:
            out.extend(symbols[: (n - len(out))])
        return out

