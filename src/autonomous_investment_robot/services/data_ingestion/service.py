from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time


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
    def load_events(self, path: str) -> list[dict]:
        if not path:
            return []
        p = Path(path)
        if not p.exists():
            return []
        text = p.read_text(encoding="utf-8").strip()
        if not text:
            return []
        if p.suffix.lower() == ".jsonl":
            out: list[dict] = []
            for line in text.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if isinstance(row, dict):
                    out.append(row)
            return out
        payload = json.loads(text)
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            items = payload.get("events")
            if isinstance(items, list):
                return [row for row in items if isinstance(row, dict)]
            return [payload]
        return []

    def resolve_recording_run_id(self, run_dir: str, run_id: str | None = None) -> str | None:
        if run_id:
            return run_id
        root = Path(run_dir) / "recordings"
        if not root.exists():
            return None
        candidates = [p for p in root.iterdir() if p.is_dir()]
        if not candidates:
            return None
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        return latest.name

    def recordings_index(self, run_dir: str, run_id: str) -> dict:
        p = Path(run_dir) / "recordings" / run_id / "market.index.json"
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def replay_recordings_meta(self, run_dir: str, run_id: str) -> dict:
        p = Path(run_dir) / "recordings" / run_id / "market.meta.json"
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def recordings_health(self, run_dir: str, run_id: str) -> dict:
        from autonomous_investment_robot.services.data_qa.service import DataQAService

        qa = DataQAService()
        p = Path(run_dir) / "recordings" / run_id / "market.jsonl"
        if not p.exists():
            return {"ok": False, "issues": ["missing_market_jsonl"], "events": 0}
        issues: list[str] = []
        events = 0
        agg_prev: dict[str, int] = {}
        now_ms = int(time.time() * 1000)
        by_stream: dict[str, int] = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events += 1
            try:
                row = json.loads(line)
            except Exception:
                issues.append("invalid_json")
                continue
            ok_schema, reason_schema = qa.ws_schema_guard(row)
            if not ok_schema:
                issues.append(reason_schema)
                continue
            stream = row.get("stream", "")
            by_stream[stream] = by_stream.get(stream, 0) + 1
            data = row.get("data", row)
            evt_ms = int(data.get("E", data.get("T", 0)) or 0)
            ok_ts, reason_ts = qa.timestamp_sanity(evt_ms, now_ms=now_ms, max_past_ms=20 * 365 * 24 * 3600 * 1000)
            if not ok_ts:
                issues.append(reason_ts)
            if data.get("e") == "aggTrade":
                agg_id = data.get("a")
                symbol = str(data.get("s", ""))
                if isinstance(agg_id, int):
                    gap, reason_gap = qa.ws_gap_detector(agg_prev.get(symbol), agg_id)
                    if gap and reason_gap == "gap_detected":
                        issues.append(f"aggtrade_gap:{symbol}")
                    agg_prev[symbol] = agg_id

        uniq_issues = sorted(set(issues))
        return {
            "ok": len(uniq_issues) == 0 and events > 0,
            "issues": uniq_issues,
            "events": events,
            "streams": by_stream,
        }

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

    def replay_recordings(self, run_dir: str, run_id: str, symbol: str, source: str = "recordings") -> list[IngestedBar]:
        p = Path(run_dir) / "recordings" / run_id / "market.jsonl"
        if not p.exists():
            return []
        out: list[IngestedBar] = []
        close = 0.0
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            data = row.get("data", row)
            if str(data.get("s", symbol)).upper() != symbol.upper():
                continue
            evt = int(data.get("E", data.get("T", 0)))
            ts = datetime.fromtimestamp(evt / 1000.0, tz=timezone.utc) if evt > 0 else datetime.now(timezone.utc)
            if data.get("e") == "aggTrade":
                close = float(data.get("p", close or 0.0))
            if close <= 0:
                continue
            out.append(
                IngestedBar(
                    source=source,
                    symbol=symbol,
                    ts=ts,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=float(data.get("q", 0.0)),
                    mark_price=float(data.get("p", close)) if data.get("e") == "markPriceUpdate" else close,
                    index_price=float(data.get("i", close)) if data.get("e") == "markPriceUpdate" else close,
                    funding_rate=float(data.get("r", 0.0)) if data.get("e") == "markPriceUpdate" else 0.0,
                    secondary_price=float(data.get("i", close)) if data.get("e") == "markPriceUpdate" else close,
                )
            )
        return out
