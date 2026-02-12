from __future__ import annotations

import json
from pathlib import Path


class OpsService:
    def __init__(self, run_dir: str) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.metrics: dict[str, float] = {}

    def set_metric(self, name: str, value: float) -> None:
        self.metrics[name] = value

    def inc_metric(self, name: str, value: float = 1.0) -> None:
        self.metrics[name] = self.metrics.get(name, 0.0) + value

    def emit_alert(self, name: str, reason: str) -> None:
        self.audit_event("alert", {"name": name, "reason": reason})

    def audit_event(self, event_type: str, payload: dict) -> None:
        p = self.run_dir / "audit.log"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event_type": event_type, "payload": payload}, sort_keys=True) + "\n")

    def export_prometheus(self) -> str:
        p = self.run_dir / "metrics.prom"
        lines = [f"{k} {v}" for k, v in sorted(self.metrics.items())]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(p)
