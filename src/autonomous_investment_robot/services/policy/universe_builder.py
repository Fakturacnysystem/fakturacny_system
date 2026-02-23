from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from autonomous_investment_robot.config.settings import UniverseBuilderSettings


@dataclass
class UniverseTiers:
    watch: list[str]
    candidate: list[str]
    trade: list[str]


class KrakenSpotUniverseBuilder:
    def __init__(self, settings: UniverseBuilderSettings) -> None:
        self.settings = settings

    def build(self, asset_pairs: dict, ticker: dict) -> UniverseTiers:
        tradable = []
        for pair, meta in asset_pairs.items():
            if str(meta.get("status", "online")).lower() not in {"online", "tradable"}:
                continue
            if ".d" in pair.lower() or pair.lower().endswith(".d"):
                continue
            t = ticker.get(pair, {}) if isinstance(ticker, dict) else {}
            bid = float((t.get("b") or [0])[0]) if isinstance(t.get("b"), list) else float(t.get("b", 0.0))
            ask = float((t.get("a") or [0])[0]) if isinstance(t.get("a"), list) else float(t.get("a", 0.0))
            vol = float((t.get("v") or [0, 0])[-1]) if isinstance(t.get("v"), list) else float(t.get("v", 0.0))
            if bid <= 0 or ask <= 0:
                spread_bps = 10_000.0
            else:
                spread_bps = ((ask - bid) / ((ask + bid) / 2.0)) * 10_000
            tradable.append((pair, vol, spread_bps))

        tradable.sort(key=lambda x: x[1], reverse=True)
        watch = [p for p, _, _ in tradable[: self.settings.top_n_target]]
        candidate = [p for p, vol, spread in tradable if vol >= self.settings.min_24h_quote_volume and spread <= self.settings.max_spread_bps]
        candidate = candidate[: self.settings.candidate_max]
        trade = candidate[: self.settings.trade_max_positions]
        return UniverseTiers(watch=watch, candidate=candidate, trade=trade)

    def write_helpers(self, run_dir: str, tiers: UniverseTiers) -> None:
        base = Path(run_dir)
        base.mkdir(parents=True, exist_ok=True)
        (base / "symbols_watch_1000.txt").write_text("\n".join(tiers.watch) + "\n", encoding="utf-8")
        (base / "symbols_trade_candidates.txt").write_text("\n".join(tiers.candidate) + "\n", encoding="utf-8")
