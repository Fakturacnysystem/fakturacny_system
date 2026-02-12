from __future__ import annotations

from datetime import datetime, timezone

from autonomous_investment_robot.core.contracts import DataEvent


class DataIngestionService:
    def ingest(self, venue: str, symbol: str, payload: dict) -> DataEvent:
        return DataEvent(venue=venue, symbol=symbol, ts=datetime.now(timezone.utc), payload=payload)
