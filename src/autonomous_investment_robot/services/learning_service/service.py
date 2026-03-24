from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from autonomous_investment_robot.core.contracts import LearningRecord


class LearningService:
    def __init__(self, run_dir: str) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[LearningRecord] = []

    def record(self, record: LearningRecord) -> None:
        self.records.append(record)
        out = self.run_dir / "learning_records.jsonl"
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), sort_keys=True, default=str) + "\n")
