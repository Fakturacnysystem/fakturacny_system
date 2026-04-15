from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class MarketMicrostructureService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def analyze(self, *, symbol: str, market: Any, execution_result: Any | None = None) -> dict[str, Any]:
        features = dict(getattr(market, "features", {}) or {})
        book = dict(getattr(market, "book", {}) or {})
        spread_bps = float(book.get("spread_bps", features.get("spread_proxy", 0.0) * 10000.0) or 0.0)
        depth_notional = float(book.get("depth_notional", features.get("depth_notional", 0.0)) or 0.0)
        realized_vol = float(features.get("realized_vol", 0.0) or 0.0)
        flow_imbalance = float(features.get("flow_imbalance", 0.0) or 0.0)
        liveliness = float(features.get("book_liveliness_score", 0.0) or 0.0)
        repeat_count = float(features.get("book_repeat_count", 0.0) or 0.0)
        staleness = float(features.get("seconds_since_distinct_book_change", 0.0) or 0.0)
        microstructure_quality = max(
            0.0,
            min(
                1.0,
                (1.0 - min(spread_bps / max(float(self.settings.market_watch.entry_block_max_spread_bps), 1.0), 1.0)) * 0.30
                + min(depth_notional / max(float(self.settings.market_watch.liquidity_map_min_depth_notional), 1.0), 1.0) * 0.30
                + min(liveliness, 1.0) * 0.20
                + (1.0 - min(repeat_count / 8.0, 1.0)) * 0.10
                + (1.0 - min(staleness / 20.0, 1.0)) * 0.10
            ),
        )
        venue_behavior = {
            "symbol": symbol,
            "maker_friendliness": max(0.0, min(1.0, 1.0 - spread_bps / 40.0)),
            "depth_resilience": max(0.0, min(1.0, depth_notional / max(float(self.settings.market_watch.liquidity_map_min_depth_notional), 1.0))),
            "volatility_stress": max(0.0, min(1.0, realized_vol / max(float(self.settings.regime.panic_vol), 1e-6))),
            "microstructure_quality": microstructure_quality,
            "flow_imbalance": flow_imbalance,
            "execution_degradation": 1.0 if execution_result is not None and str(getattr(execution_result, "status", "")).lower() in {"rejected", "error"} else 0.0,
        }
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "spread_bps": spread_bps,
            "depth_notional": depth_notional,
            "realized_volatility": realized_vol,
            "book_liveliness_score": liveliness,
            "microstructure_quality_score": microstructure_quality,
            "spread_stress": max(0.0, min(1.0, spread_bps / max(float(self.settings.market_watch.entry_block_max_spread_bps), 1.0))),
            "depth_stress": 1.0 - max(0.0, min(1.0, depth_notional / max(float(self.settings.market_watch.entry_block_min_depth_notional), 1.0))),
            "liquidity_quality": max(0.0, min(1.0, depth_notional / max(float(self.settings.market_watch.liquidity_map_min_depth_notional), 1.0))),
            "momentum_persistence": max(0.0, min(1.0, abs(float(features.get("ret_3", 0.0) or 0.0)) / max(float(self.settings.regime.trend_ret3_abs), 1e-6))),
            "stale_book_seconds": staleness,
            "venue_behavior_profile": venue_behavior,
        }

