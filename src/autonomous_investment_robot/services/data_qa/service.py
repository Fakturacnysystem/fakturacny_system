from __future__ import annotations

from datetime import timedelta
from time import time

from autonomous_investment_robot.services.data_ingestion.service import IngestedBar


class DataQAService:
    def validate_replay(self, bars: list[IngestedBar], max_gap: timedelta = timedelta(hours=2)) -> tuple[bool, list[str]]:
        issues: list[str] = []
        if not bars:
            return False, ["empty_replay"]
        for i in range(1, len(bars)):
            if bars[i].ts <= bars[i - 1].ts:
                issues.append("non_monotonic_timestamp")
            if bars[i].ts - bars[i - 1].ts > max_gap:
                issues.append("gap_detected")
        return len(issues) == 0, issues

    def divergence_breaker(self, bar: IngestedBar, threshold_bps: float) -> bool:
        if bar.secondary_price == 0:
            return False
        div = abs(bar.mark_price - bar.secondary_price) / bar.mark_price * 10000
        return div > threshold_bps

    def schema_guard(self, row: dict, required_cols: list[str]) -> tuple[bool, str]:
        missing = [c for c in required_cols if c not in row]
        return (len(missing) == 0, "ok" if not missing else f"schema_missing:{','.join(missing)}")

    def outlier_squash(self, value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    def validate_live_bar(self, bar: IngestedBar, stale_after_s: float, divergence_threshold_bps: float) -> tuple[bool, str]:
        now_s = time()
        lag_s = now_s - bar.ts.timestamp()
        if lag_s > stale_after_s:
            return False, "stale_data"
        if bar.mark_price <= 0 or bar.secondary_price <= 0:
            return False, "schema_mismatch"
        div_bps = abs(bar.mark_price - bar.secondary_price) / bar.mark_price * 10000
        if div_bps > divergence_threshold_bps:
            return False, "cross_feed_divergence"
        return True, "ok"
