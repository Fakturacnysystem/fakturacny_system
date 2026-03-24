from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any


class EventStore:
    def __init__(self, run_dir: str) -> None:
        self.base = Path(run_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.seq_by_stream: dict[str, int] = self._seed_sequences()

    def _seed_sequences(self) -> dict[str, int]:
        seeded: dict[str, int] = {}
        for path in self.base.glob("events_*.jsonl"):
            stream = path.stem.replace("events_", "", 1)
            seeded[stream] = self.last_seq(stream)
        return seeded

    def next_seq(self, stream: str) -> int:
        self.seq_by_stream[stream] = self.seq_by_stream.get(stream, 0) + 1
        return self.seq_by_stream[stream]

    def append(self, stream: str, event: Any) -> None:
        p = self.base / f"events_{stream}.jsonl"
        with p.open("a", encoding="utf-8") as fh:
            row = asdict(event) if hasattr(event, "__dataclass_fields__") else event
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    def load(self, stream: str) -> list[dict[str, Any]]:
        p = self.base / f"events_{stream}.jsonl"
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

    def last_seq(self, stream: str) -> int:
        rows = self.load(stream)
        if not rows:
            return 0
        return max(int(row.get("seq", 0)) for row in rows if isinstance(row, dict))

    def latest(self, stream: str) -> dict[str, Any] | None:
        rows = self.load(stream)
        return rows[-1] if rows else None
