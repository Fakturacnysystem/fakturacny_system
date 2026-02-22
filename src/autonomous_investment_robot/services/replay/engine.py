from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from autonomous_investment_robot.services.replay.events import MarketEvent, make_event


@dataclass
class ReplayResult:
    count: int
    source: str


class ReplayEngine:
    def from_csv(self, csv_path: str, symbol: str, venue: str = "fixture") -> list[MarketEvent]:
        events: list[MarketEvent] = []
        with Path(csv_path).open("r", encoding="utf-8") as fh:
            for i, row in enumerate(csv.DictReader(fh), start=1):
                payload = {k: row[k] for k in row.keys() if k != "ts"}
                ev = make_event(MarketEvent, "MARKET_BAR", symbol=symbol, venue=venue, seq=i, payload=payload)
                events.append(ev)
        return events
