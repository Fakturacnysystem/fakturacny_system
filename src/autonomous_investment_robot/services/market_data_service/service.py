from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt

from autonomous_investment_robot.core.contracts import MarketHealthSnapshot, MarketSnapshot


class MarketDataService:
    def build_live_snapshot(
        self,
        symbol: str,
        book: dict[str, object],
        *,
        recent_mids: list[float] | None = None,
        ts: datetime | None = None,
    ) -> MarketSnapshot:
        event_ts = ts or datetime.now(timezone.utc)
        bid = float(book.get("bidPrice", 0.0))
        ask = float(book.get("askPrice", 0.0))
        bid_qty = float(book.get("bidQty", 0.0))
        ask_qty = float(book.get("askQty", 0.0))
        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0
        spread_bps = ((ask - bid) / max(mid, 1e-9)) * 10000.0 if mid > 0 else 0.0
        depth_notional = float(book.get("depthNotional", 0.0) or 0.0)
        if depth_notional <= 0.0:
            depth_notional = (bid * max(bid_qty, 0.0)) + (ask * max(ask_qty, 0.0))
        flow_imbalance = (bid_qty - ask_qty) / max(bid_qty + ask_qty, 1e-9)
        mids = (recent_mids or []) + ([mid] if mid > 0 else [])
        realized_vol = 0.0
        if len(mids) >= 2:
            mean = sum(mids) / len(mids)
            realized_vol = sqrt(sum((px - mean) ** 2 for px in mids) / len(mids)) / max(mean, 1e-9)
        return MarketSnapshot(
            symbol=symbol,
            ts=event_ts,
            bid=bid,
            ask=ask,
            mid=mid,
            spread_bps=spread_bps,
            depth_notional=depth_notional,
            orderbook_imbalance=flow_imbalance,
            flow_imbalance=flow_imbalance,
            realized_vol=realized_vol,
            mark_price=mid,
            secondary_price=mid,
            metadata={"bid_qty": bid_qty, "ask_qty": ask_qty},
        )

    def snapshot_features(self, snapshot: MarketSnapshot, recent_mids: list[float] | None = None) -> dict[str, float]:
        mids = recent_mids or [snapshot.mid]
        ret_1 = 0.0 if len(mids) < 2 else (mids[-1] / max(mids[-2], 1e-9) - 1.0)
        ret_3 = 0.0 if len(mids) < 4 else (mids[-1] / max(mids[-4], 1e-9) - 1.0)
        metadata = dict(snapshot.metadata or {})
        return {
            "history_points": float(len(mids)),
            "ret_1": ret_1,
            "ret_3": ret_3,
            "realized_vol": snapshot.realized_vol,
            "atr_proxy": snapshot.spread_bps / 10000.0,
            "spread_proxy": snapshot.spread_bps / 10000.0,
            "funding_rate": 0.0,
            "oi": 0.0,
            "liquidations": 0.0,
            "depth_notional": snapshot.depth_notional,
            "orderbook_imbalance": snapshot.orderbook_imbalance,
            "microprice_proxy": snapshot.mid,
            "flow_imbalance": snapshot.flow_imbalance,
            "mark_price": snapshot.mark_price,
            "spot_price_proxy": snapshot.secondary_price,
            "book_repeat_count": float(metadata.get("book_repeat_count", 0.0) or 0.0),
            "seconds_since_distinct_book_change": float(metadata.get("seconds_since_distinct_book_change", 0.0) or 0.0),
            "book_liveliness_score": float(metadata.get("book_liveliness_score", 0.0) or 0.0),
            "public_market_data_connected": 1.0 if bool(metadata.get("public_market_data_connected", False)) else 0.0,
        }

    def assess_health(
        self,
        snapshot: MarketSnapshot,
        *,
        stale_seconds: float,
        stale_threshold_seconds: float,
        min_depth_notional: float,
        max_spread_bps: float,
        sequence_ok: bool = True,
        checksum_ok: bool = True,
    ) -> MarketHealthSnapshot:
        reasons: list[str] = []
        feed_stale = stale_seconds > stale_threshold_seconds
        if feed_stale:
            reasons.append("stale_feed")
        if not sequence_ok:
            reasons.append("sequence_gap")
        if not checksum_ok:
            reasons.append("checksum_mismatch")
        if snapshot.depth_notional < min_depth_notional:
            reasons.append("liquidity_too_thin")
        if snapshot.spread_bps > max_spread_bps:
            reasons.append("spread_too_wide")

        symbol_health = 1.0
        exchange_health = 1.0
        market_quality = 1.0
        if feed_stale:
            symbol_health -= 0.5
        if not sequence_ok or not checksum_ok:
            exchange_health -= 0.35
        if snapshot.depth_notional < min_depth_notional:
            market_quality -= 0.45
        if snapshot.spread_bps > max_spread_bps:
            market_quality -= 0.35

        return MarketHealthSnapshot(
            symbol=snapshot.symbol,
            ts=snapshot.ts,
            feed_stale=feed_stale,
            sequence_ok=sequence_ok,
            checksum_ok=checksum_ok,
            symbol_health_score=max(0.0, symbol_health),
            exchange_health_score=max(0.0, exchange_health),
            market_quality_score=max(0.0, market_quality),
            reasons=reasons,
            metadata={"stale_seconds": stale_seconds},
        )
