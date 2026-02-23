from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector


class KrakenSpotMarketPoller:
    def __init__(self, connector: KrakenSpotConnector, run_dir: str, symbols: list[str]) -> None:
        self.connector = connector
        self.run_dir = Path(run_dir)
        self.symbols = symbols

    def record(self, run_id: str, duration_seconds: int, poll_interval_seconds: float = 1.0) -> dict[str, Any]:
        base = self.run_dir / "recordings" / run_id
        base.mkdir(parents=True, exist_ok=True)
        market = base / "market.jsonl"
        meta = base / "market.meta.json"
        idx = base / "market.index.json"
        streams: dict[str, int] = {}
        events = 0
        deadline = time.time() + max(1, int(duration_seconds))
        with market.open("a", encoding="utf-8") as fh:
            while time.time() < deadline:
                now_ms = int(time.time() * 1000)
                for symbol in self.symbols:
                    data = self.connector.ticker(symbol)
                    row = data.get(symbol) if isinstance(data, dict) else None
                    if not row and isinstance(data, dict) and data:
                        row = next(iter(data.values()))
                    if not isinstance(row, dict):
                        continue
                    bid = float((row.get("b") or [0])[0]) if isinstance(row.get("b"), list) else float(row.get("b", 0.0))
                    ask = float((row.get("a") or [0])[0]) if isinstance(row.get("a"), list) else float(row.get("a", 0.0))
                    last = float((row.get("c") or [0])[0]) if isinstance(row.get("c"), list) else float(row.get("c", 0.0))
                    vol = float((row.get("v") or [0, 0])[-1]) if isinstance(row.get("v"), list) else float(row.get("v", 0.0))
                    evt = {
                        "stream": f"{symbol.lower()}@ticker",
                        "data": {"e": "ticker", "E": now_ms, "s": symbol, "b": str(bid), "a": str(ask), "p": str(last), "q": str(vol)},
                    }
                    fh.write(json.dumps(evt, sort_keys=True) + "\n")
                    events += 1
                    streams[evt["stream"]] = streams.get(evt["stream"], 0) + 1
                fh.flush()
                time.sleep(max(0.2, float(poll_interval_seconds)))
        meta.write_text(json.dumps({"schema_version": 1, "format": "kraken_spot_market_jsonl", "written_at": datetime.now(timezone.utc).isoformat()}, sort_keys=True), encoding="utf-8")
        idx.write_text(json.dumps({"events": events, "schema_version": 1, "streams": streams}, sort_keys=True), encoding="utf-8")
        return {"events_recorded": events, "record_path": str(market)}
