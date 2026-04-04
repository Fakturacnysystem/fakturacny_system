from __future__ import annotations

from collections import defaultdict


def cluster_pairs(symbols: list[str]) -> dict[str, list[str]]:
    clusters: dict[str, list[str]] = defaultdict(list)
    for symbol in symbols:
        normalized = symbol.replace("-", "/").upper()
        if "/" in normalized:
            base, quote = normalized.split("/", 1)
        else:
            base, quote = normalized[:3], normalized[3:]
        key = f"{quote}:{base[0] if base else 'X'}"
        clusters[key].append(symbol)
    return dict(sorted((cluster, sorted(items)) for cluster, items in clusters.items()))

