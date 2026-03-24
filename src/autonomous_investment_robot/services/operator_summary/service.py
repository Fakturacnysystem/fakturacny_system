from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


class OperatorSummaryCoordinator:
    def __init__(self, run_dir: str, observability: Any | None = None) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.observability = observability

    def _serialize(self, payload: Any) -> Any:
        if is_dataclass(payload):
            payload = asdict(payload)
        return json.loads(json.dumps(payload, sort_keys=True, default=str))

    def emit(self, *, summary: dict[str, Any]) -> str:
        path = self.run_dir / "kraken_spot_operator_summary.json"
        serializable = self._serialize(summary)
        path.write_text(json.dumps(serializable, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        if self.observability is not None:
            route = getattr(self.observability, "route_operator_summary_bundle", None)
            if callable(route):
                route(serializable)
            else:
                self.observability.journal("kraken_spot_operator_summary", serializable)
        return str(path)
