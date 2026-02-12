from __future__ import annotations

from datetime import timedelta

from autonomous_investment_robot.services.data_ingestion.service import IngestedBar


class DataQAService:
    def validate_replay(self, bars: list[IngestedBar], max_gap: timedelta = timedelta(hours=2)) -> tuple[bool, list[str]]:
        issues: list[str] = []
        if not bars:
            issues.append("empty_replay")
            return False, issues
        for i in range(1, len(bars)):
            if bars[i].ts <= bars[i - 1].ts:
                issues.append("non_monotonic_timestamp")
                break
            if bars[i].ts - bars[i - 1].ts > max_gap:
                issues.append("gap_detected")
        return len(issues) == 0, issues
