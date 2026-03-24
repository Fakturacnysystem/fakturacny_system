from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import MarketWatchReport


class MarketWatchService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def _window_active(self, now_dt: datetime) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        windows = list(getattr(self.settings.market_watch, "blackout_windows", []) or [])
        if not windows:
            return False, reasons
        current = now_dt.astimezone(timezone.utc).strftime("%H:%M")
        for window in windows:
            if not isinstance(window, dict):
                continue
            start = str(window.get("start", ""))
            end = str(window.get("end", ""))
            label = str(window.get("label", "blackout"))
            if not start or not end:
                continue
            if start <= end:
                active = start <= current < end
            else:
                active = current >= start or current < end
            if active:
                reasons.append(f"blackout:{label}")
        return bool(reasons), reasons

    def evaluate(
        self,
        *,
        symbol: str,
        ts: datetime,
        snapshot: Any,
        forecast: Any,
        regime_assessment: Any | None = None,
        market_integrity: Any | None = None,
    ) -> MarketWatchReport:
        if not bool(getattr(self.settings.market_watch, "enabled", False)):
            return MarketWatchReport(symbol=symbol, ts=ts, action="continue", score=1.0, reasons=["market_watch_disabled"])

        reasons: list[str] = []
        blackout_active, blackout_reasons = self._window_active(ts)
        reasons.extend(blackout_reasons)
        spread_bps = float(getattr(snapshot, "spread_bps", 0.0) or 0.0)
        depth_notional = float(getattr(snapshot, "depth_notional", 0.0) or 0.0)
        block_spread = float(getattr(self.settings.market_watch, "entry_block_max_spread_bps", 35.0) or 35.0)
        degrade_spread = float(getattr(self.settings.market_watch, "entry_degrade_max_spread_bps", 20.0) or 20.0)
        block_depth = float(getattr(self.settings.market_watch, "entry_block_min_depth_notional", 10000.0) or 10000.0)
        degrade_depth = float(getattr(self.settings.market_watch, "entry_degrade_min_depth_notional", 25000.0) or 25000.0)
        liquidity_floor = float(getattr(self.settings.market_watch, "liquidity_map_min_depth_notional", degrade_depth) or degrade_depth)

        spread_score = 1.0
        liquidity_score = 1.0
        if spread_bps >= block_spread:
            spread_score = 0.0
            reasons.append("spread_block_threshold_breached")
        elif spread_bps >= degrade_spread:
            spread_score = 0.45
            reasons.append("spread_degraded")

        if depth_notional <= 0.0:
            liquidity_score = 0.0
            reasons.append("depth_unavailable")
        elif depth_notional < block_depth:
            liquidity_score = 0.0
            reasons.append("depth_block_threshold_breached")
        elif depth_notional < max(degrade_depth, liquidity_floor):
            liquidity_score = 0.45
            reasons.append("liquidity_map_degraded")

        score = max(0.0, min(1.0, 0.45 * spread_score + 0.55 * liquidity_score))
        action = "continue"
        if blackout_active and bool(getattr(self.settings.market_watch, "block_new_entries_on_blackout", True)):
            action = "block_entries"
        elif score <= 0.20:
            action = "block_entries"
        elif score < 0.70:
            action = "degrade"

        regime_label = str(getattr(regime_assessment, "label", "") or "")
        if regime_label in {"liquidity_vacuum", "news_chaos", "dead_market"}:
            action = "block_entries" if action == "continue" else action
            reasons.append(f"regime_watch:{regime_label}")

        if market_integrity is not None:
            integrity_action = str(getattr(market_integrity, "action", "continue") or "continue")
            if integrity_action in {"flatten_only", "halt"}:
                action = "block_entries"
                reasons.append("market_integrity_blocks_entries")

        return MarketWatchReport(
            symbol=symbol,
            ts=ts,
            action=action,
            score=score,
            blackout_active=blackout_active,
            liquidity_score=liquidity_score,
            spread_score=spread_score,
            reasons=sorted(set(reasons)),
            metadata={
                "spread_bps": spread_bps,
                "depth_notional": depth_notional,
                "forecast_regime": str(getattr(forecast, "regime", "")),
                "forecast_liquidity_regime": str(getattr(forecast, "liquidity_regime", "")),
            },
        )
