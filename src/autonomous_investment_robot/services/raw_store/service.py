from __future__ import annotations

import json
from pathlib import Path


class RawStoreService:
    """Immutable local object writes + append-only event logs for offline MVP."""

    def __init__(self, run_dir: str) -> None:
        self.base = Path(run_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def append_log(self, stream: str, record: dict) -> None:
        p = self.base / f"{stream}.jsonl"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def write_table(self, name: str, rows: list[dict]) -> None:
        p = self.base / f"{name}.json"
        p.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
