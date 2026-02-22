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

    def ws_schema_guard(self, row: dict) -> tuple[bool, str]:
        if not isinstance(row, dict):
            return False, "schema_not_object"
        if "data" in row:
            if "stream" not in row:
                return False, "schema_missing:stream"
            data = row.get("data")
            if not isinstance(data, dict):
                return False, "schema_missing:data_object"
            ok, reason = self.schema_guard(data, ["e", "s"])
            return ok, reason
        ok, reason = self.schema_guard(row, ["e", "s"])
        return ok, reason

    def ws_gap_detector(self, prev_seq: int | None, next_seq: int | None) -> tuple[bool, str]:
        if prev_seq is None or next_seq is None:
            return False, "missing_seq"
        if next_seq <= prev_seq:
            return True, "non_monotonic_seq"
        if next_seq > prev_seq + 1:
            return True, "gap_detected"
        return False, "ok"

    def timestamp_sanity(self, ts_ms: int, *, now_ms: int, max_future_ms: int = 5_000, max_past_ms: int = 7 * 24 * 3600 * 1000) -> tuple[bool, str]:
        if ts_ms <= 0:
            return False, "invalid_timestamp"
        if ts_ms > now_ms + max_future_ms:
            return False, "timestamp_in_future"
        if ts_ms < now_ms - max_past_ms:
            return False, "timestamp_too_old"
        return True, "ok"

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
