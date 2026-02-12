from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any


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

    def audit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        p = self.run_dir / "audit.log"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event_type": event_type, "payload": payload}, sort_keys=True) + "\n")

    def track_config(self, config_data: dict[str, Any]) -> str:
        serialized = json.dumps(config_data, sort_keys=True)
        cfg_hash = sha256(serialized.encode("utf-8")).hexdigest()
        p = self.run_dir / "config_history.jsonl"
        prev = None
        if p.exists():
            lines = [x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
            if lines:
                prev = json.loads(lines[-1])
        diff = {"changed": True if prev is None else prev.get("hash") != cfg_hash}
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"hash": cfg_hash, "config": config_data, "diff": diff}, sort_keys=True) + "\n")
        return cfg_hash

    def export_prometheus(self) -> str:
        p = self.run_dir / "metrics.prom"
        lines = [f"{k} {v}" for k, v in sorted(self.metrics.items())]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(p)
