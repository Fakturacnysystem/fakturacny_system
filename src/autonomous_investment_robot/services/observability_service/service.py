from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from autonomous_investment_robot.services.ops.service import OpsService


class ObservabilityService:
    def __init__(self, run_dir: str, ops: OpsService) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.ops = ops

    def journal(self, channel: str, payload: Any) -> None:
        if is_dataclass(payload):
            serializable = asdict(payload)
        else:
            serializable = payload
        serializable = json.loads(json.dumps(serializable, sort_keys=True, default=str))
        self.ops.audit_event(channel, serializable)
        out = self.run_dir / f"{channel}.jsonl"
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(serializable, sort_keys=True, default=str) + "\n")
