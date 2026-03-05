#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

try:
    import yaml  # pip install pyyaml
except ImportError as e:  # pragma: no cover
    raise SystemExit("Missing dependency: pyyaml. Install: pip install pyyaml") from e

try:
    import requests  # pip install requests
except ImportError as e:  # pragma: no cover
    raise SystemExit("Missing dependency: requests. Install: pip install requests") from e


KRAKEN_API = "https://api.kraken.com"

# Exclusions for stablecoins and fiat bases.
EXCLUDE_BASE = {"USDT", "USDC", "DAI", "EUR", "USD"}
EXCLUDE_QUOTE = {"USDT", "USDC", "DAI"}

DEFAULT_MAJORS = {"XBT", "ETH", "SOL", "XRP", "ADA", "DOT", "LINK"}


def kraken_get(path: str, params: dict[str, Any] | None = None, timeout: float = 10.0) -> dict[str, Any]:
    r = requests.get(f"{KRAKEN_API}{path}", params=params or {}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Kraken error: {data['error']}")
    result = data.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected Kraken response for {path}")
    return result


def split_pair(meta: dict[str, Any]) -> tuple[str, str] | None:
    # Kraken format varies; wsname/base/quote are the most reliable fields.
    wsname = str(meta.get("wsname", "") or "")
    if "/" in wsname:
        base, quote = wsname.split("/", 1)
        return base.upper(), quote.upper()

    base = str(meta.get("base", "") or "").upper()
    quote = str(meta.get("quote", "") or "").upper()
    if base and quote:
        # Kraken internals often carry X/Z prefixes (e.g., XXBT, ZEUR).
        if len(base) >= 4 and base[0] in {"X", "Z"}:
            base = base[1:]
        if len(quote) >= 4 and quote[0] in {"X", "Z"}:
            quote = quote[1:]
        return base, quote

    alt = str(meta.get("altname", "") or "")
    if "/" in alt:
        base, quote = alt.split("/", 1)
        return base.upper(), quote.upper()
    return None


def _score_candidates(candidates: list[tuple[str, str]], max_pairs: int) -> list[str]:
    tick: dict[str, Any] = {}
    batch_size = 40
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]
        pair_param = ",".join(k for k, _ in batch)
        res = kraken_get("/0/public/Ticker", params={"pair": pair_param})
        tick.update(res)

    scored: list[tuple[float, str]] = []
    for key, out_symbol in candidates:
        t = tick.get(key)
        if not isinstance(t, dict):
            continue
        try:
            bid = float(t["b"][0])
            ask = float(t["a"][0])
            last = float(t["c"][0])
            vol_base_24h = float(t["v"][1])  # 24h base volume
        except Exception:
            continue
        if bid <= 0 or ask <= 0 or last <= 0:
            continue

        mid = (bid + ask) / 2.0
        spread_bps = ((ask - bid) / max(mid, 1e-12)) * 10000.0
        vol_quote_24h = vol_base_24h * last

        # Profit proxy: high turnover + low spread.
        score = math.log1p(vol_quote_24h) / (1.0 + (spread_bps / 20.0))
        scored.append((score, out_symbol))

    scored.sort(reverse=True, key=lambda x: x[0])
    out = [sym for _, sym in scored[:max_pairs]]
    return out


def pick_pairs(quote: str, majors_only: bool, max_pairs: int, use_slash: bool) -> list[str]:
    pairs = kraken_get("/0/public/AssetPairs")
    candidates: list[tuple[str, str]] = []
    for key, meta_raw in pairs.items():
        if not isinstance(meta_raw, dict):
            continue
        pair = split_pair(meta_raw)
        if pair is None:
            continue
        base, q = pair
        if q != quote.upper():
            continue
        if base in EXCLUDE_BASE or q in EXCLUDE_QUOTE:
            continue
        if majors_only and base not in DEFAULT_MAJORS:
            continue
        if str(meta_raw.get("status", "online")) != "online":
            continue

        out_symbol = f"{base}/{q}" if use_slash else f"{base}{q}"
        candidates.append((key, out_symbol))

    if not candidates:
        return []

    return _score_candidates(candidates, max_pairs=max_pairs)


def pick_pairs_auto_quote(quote: str, majors_only: bool, max_pairs: int, use_slash: bool) -> list[str]:
    if quote.upper() != "AUTO":
        out = pick_pairs(quote, majors_only, max_pairs, use_slash)
        if not out:
            raise RuntimeError("No pairs selected. Try --no-majors-only or different --quote.")
        return out

    # Prefer EUR first, then USD. Keep best non-empty universe.
    options = ["EUR", "USD"]
    best: list[str] = []
    for q in options:
        curr = pick_pairs(q, majors_only, max_pairs, use_slash)
        if len(curr) > len(best):
            best = curr
        if len(curr) >= max_pairs:
            return curr
    if not best:
        raise RuntimeError("No pairs selected in AUTO mode. Try --no-majors-only.")
    return best


def set_universe(cfg: dict[str, Any], universe: list[str]) -> None:
    if isinstance(cfg.get("universe"), list):
        cfg["universe"] = universe
        return
    policy = cfg.get("policy")
    if isinstance(policy, dict) and isinstance(policy.get("universe"), list):
        policy["universe"] = universe
        return
    cfg["universe"] = universe


def infer_slash_mode(cfg: dict[str, Any]) -> bool | None:
    universe = cfg.get("universe")
    if not isinstance(universe, list) or not universe:
        return None
    first = str(universe[0] or "")
    if not first:
        return None
    return "/" in first


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("in_config")
    ap.add_argument("--out", required=True)
    ap.add_argument("--quote", choices=["EUR", "USD", "AUTO"], default="AUTO")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument(
        "--majors-only",
        dest="majors_only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Limit to majors set (default: true). Use --no-majors-only to include all bases.",
    )
    ap.add_argument("--noslash", action="store_true", help="Force output symbols like XBTEUR.")
    ap.add_argument("--slash", action="store_true", help="Force output symbols like XBT/EUR.")
    args = ap.parse_args()
    if args.noslash and args.slash:
        raise SystemExit("Use only one of --noslash or --slash.")
    return args


def main() -> None:
    args = parse_args()
    cfg = yaml.safe_load(Path(args.in_config).read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise SystemExit("Config root must be a dict")
    if args.top <= 0:
        raise SystemExit("--top must be > 0")

    inferred_slash = infer_slash_mode(cfg)
    if args.noslash:
        use_slash = False
    elif args.slash:
        use_slash = True
    elif inferred_slash is not None:
        use_slash = inferred_slash
    else:
        use_slash = False

    universe = pick_pairs_auto_quote(
        quote=args.quote,
        majors_only=bool(args.majors_only),
        max_pairs=int(args.top),
        use_slash=use_slash,
    )
    set_universe(cfg, universe)

    Path(args.out).write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print("Wrote:", args.out)
    print("Universe:", universe)


if __name__ == "__main__":
    main()
