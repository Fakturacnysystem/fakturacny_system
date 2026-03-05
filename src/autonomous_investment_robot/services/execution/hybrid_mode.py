from __future__ import annotations

import json
import os


def parse_hybrid_symbols() -> set[str]:
    raw = str(os.getenv("AUTONOMOUS_HYBRID_SYMBOLS", "") or "").strip()
    if not raw:
        return set()
    out: set[str] = set()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            for s in parsed:
                sym = str(s or "").strip().upper()
                if sym:
                    out.add(sym)
            return out
    except Exception:
        pass
    for token in raw.split(","):
        sym = token.strip().upper()
        if sym:
            out.add(sym)
    return out


def symbol_live_in_hybrid(symbol: str, live_symbols: set[str]) -> bool:
    if not live_symbols:
        return True
    return str(symbol or "").strip().upper() in live_symbols
