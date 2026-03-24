from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


class ReplayReportingCoordinator:
    def __init__(self, run_dir: str, observability: Any | None = None) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.observability = observability

    def _serialize(self, payload: Any) -> Any:
        if is_dataclass(payload):
            payload = asdict(payload)
        return json.loads(json.dumps(payload, sort_keys=True, default=str))

    def _write_json(self, name: str, payload: Any) -> str:
        path = self.run_dir / name
        path.write_text(json.dumps(self._serialize(payload), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        return str(path)

    def _journal_manifest(self, channel: str, payload: Any) -> None:
        if self.observability is None:
            return
        route = getattr(self.observability, "route_activation_manifest", None)
        if callable(route):
            route(channel, payload)
        else:
            self.observability.journal(channel, payload)

    def emit(
        self,
        *,
        summary: dict[str, Any],
        capability_matrix: list[dict[str, Any]],
        activated: dict[str, Any],
        still_gated: dict[str, Any],
        doctrine_blocked: dict[str, Any],
        artifact_index: dict[str, Any],
    ) -> dict[str, str]:
        paths = {
            "kraken_spot_replay_summary": self._write_json("kraken_spot_replay_summary.json", summary),
            "capability_unlock_matrix": self._write_json("kraken_spot_capability_unlock_matrix.json", capability_matrix),
            "activated_capabilities": self._write_json("activated_capabilities.json", activated),
            "still_gated_capabilities": self._write_json("still_gated_capabilities.json", still_gated),
            "doctrine_blocked_capabilities": self._write_json("doctrine_blocked_capabilities.json", doctrine_blocked),
            "artifact_index": self._write_json("artifact_index.json", artifact_index),
        }
        if self.observability is not None:
            route = getattr(self.observability, "route_replay_summary", None)
            if callable(route):
                route(summary)
            else:
                self.observability.journal("kraken_spot_replay_summary", summary)
        self._journal_manifest("capability_unlock_matrix", capability_matrix)
        self._journal_manifest("activated_capabilities", activated)
        self._journal_manifest("still_gated_capabilities", still_gated)
        self._journal_manifest("doctrine_blocked_capabilities", doctrine_blocked)
        self._journal_manifest("artifact_index", artifact_index)
        return paths
