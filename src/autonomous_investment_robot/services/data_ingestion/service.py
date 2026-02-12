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
    mark_price: float = 0.0
    index_price: float = 0.0
    funding_rate: float = 0.0
    oi: float = 0.0
    liquidations: float = 0.0
    depth_notional: float = 0.0
    spread_bps: float = 0.0
    secondary_price: float = 0.0


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
                        mark_price=float(row.get("mark_price", row["close"])),
                        index_price=float(row.get("index_price", row["close"])),
                        funding_rate=float(row.get("funding_rate", 0.0)),
                        oi=float(row.get("oi", 0.0)),
                        liquidations=float(row.get("liquidations", 0.0)),
                        depth_notional=float(row.get("depth_notional", 0.0)),
                        spread_bps=float(row.get("spread_bps", 0.0)),
                        secondary_price=float(row.get("secondary_price", row["close"])),
                    )
                )
        return bars
