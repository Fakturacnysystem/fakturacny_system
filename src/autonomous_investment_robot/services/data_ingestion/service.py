from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class IngestedBar:
    source: str
    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class DataIngestionService:
    def replay_csv(self, symbol: str, csv_path: str, source: str = "fixture") -> list[IngestedBar]:
        bars: list[IngestedBar] = []
        with open(csv_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ts = datetime.fromisoformat(row["ts"].replace("Z", "+00:00")).astimezone(timezone.utc)
                bars.append(
                    IngestedBar(
                        source=source,
                        symbol=symbol,
                        ts=ts,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    )
                )
        return bars
