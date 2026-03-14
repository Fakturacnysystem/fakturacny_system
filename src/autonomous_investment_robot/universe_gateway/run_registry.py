from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autonomous_investment_robot.config.settings import _load_yaml_like


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    except Exception:
        return {}
    return {}


def _read_config(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            payload = _load_yaml_like(str(path))
            if isinstance(payload, dict):
                return dict(payload)
    except Exception:
        return {}
    return {}


def _normalize_mode(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value in {"paper", "sim", "simulation"}:
        return "paper"
    if value in {"readonly", "read_only", "live_readonly", "monitor", "monitoring"}:
        return "readonly"
    if value in {"canary", "live_testnet", "testnet"}:
        return "canary"
    if value in {"live", "production", "prod", "main", "promoted"}:
        return "live"
    return value or "unknown"


@dataclass(frozen=True)
class UniverseRunCandidate:
    run_path: Path
    updated_at: float
    runtime_mode: str
    target_mode: str
    status: str
    provider: str
    reason: str
    run_id: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_dir": str(self.run_path),
            "updated_at": self.updated_at,
            "runtime_mode": self.runtime_mode,
            "target_mode": self.target_mode,
            "status": self.status,
            "provider": self.provider,
            "reason": self.reason,
            "run_id": self.run_id,
            "source": self.source,
        }


@dataclass(frozen=True)
class UniverseRunResolution:
    requested_mode: str
    run_path: Path
    project_root: Path
    runtime_mode: str
    target_mode: str
    updated_at: float
    source: str
    candidates: tuple[UniverseRunCandidate, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_mode": self.requested_mode,
            "resolved_run_dir": str(self.run_path),
            "resolved_runtime_mode": self.runtime_mode,
            "resolved_target_mode": self.target_mode,
            "updated_at": self.updated_at,
            "source": self.source,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def _classify_target_mode(name: str, runtime: dict[str, Any], config: dict[str, Any]) -> str:
    lowered = name.lower()
    execution = config.get("execution", {}) if isinstance(config.get("execution"), dict) else {}
    config_mode = _normalize_mode(config.get("mode"))
    execution_mode = _normalize_mode(execution.get("mode"))

    if "readonly" in lowered or execution_mode == "readonly":
        return "readonly"
    if "canary" in lowered or bool(config.get("canary_mode", False)) or execution_mode == "canary":
        return "canary"
    if config_mode == "live" or execution_mode == "live" or "live" in lowered:
        return "live"
    runtime_mode = _normalize_mode(runtime.get("mode"))
    if runtime_mode in {"paper", "readonly", "canary", "live"}:
        return runtime_mode
    return "paper" if "paper" in lowered else "unknown"


def _classify_runtime_mode(name: str, runtime: dict[str, Any], config: dict[str, Any], target_mode: str) -> str:
    runtime_mode = _normalize_mode(runtime.get("mode"))
    if runtime_mode in {"paper", "readonly", "canary", "live"}:
        return runtime_mode
    config_mode = _normalize_mode(config.get("mode"))
    if config_mode in {"paper", "readonly", "canary", "live"}:
        return config_mode
    return target_mode


def _candidate_from_dir(run_path: Path) -> UniverseRunCandidate | None:
    if not run_path.exists() or not run_path.is_dir():
        return None
    runtime = _read_json(run_path / "runtime_health.json")
    health = _read_json(run_path / "health.json")
    status_payload = dict(health)
    status_payload.update(runtime)
    config = _read_config(run_path / "runtime_config.effective.yaml")
    target_mode = _classify_target_mode(run_path.name, status_payload, config)
    runtime_mode = _classify_runtime_mode(run_path.name, status_payload, config, target_mode)
    mtimes = [
        path.stat().st_mtime
        for path in (
            run_path / "runtime_health.json",
            run_path / "health.json",
            run_path / "dashboard_snapshot.json",
            run_path / "watchdog_state.json",
            run_path / "runtime_config.effective.yaml",
        )
        if path.exists()
    ]
    if not mtimes and not any((run_path / name).exists() for name in ("audit.log", "event_bus.jsonl", "report.json")):
        return None
    updated_at = max(mtimes or [run_path.stat().st_mtime])
    return UniverseRunCandidate(
        run_path=run_path,
        updated_at=updated_at,
        runtime_mode=runtime_mode,
        target_mode=target_mode,
        status=str(status_payload.get("status", "unknown") or "unknown"),
        provider=str(status_payload.get("provider", "") or ""),
        reason=str(status_payload.get("reason", "") or ""),
        run_id=str(status_payload.get("run_id", run_path.name) or run_path.name),
        source="scan",
    )


def _score_candidate(candidate: UniverseRunCandidate, requested_mode: str) -> tuple[int, int, float]:
    requested = _normalize_mode(requested_mode)
    exact_target = 1 if candidate.target_mode == requested else 0
    exact_runtime = 1 if candidate.runtime_mode == requested else 0

    if requested == "auto":
        live_bias = 1 if candidate.runtime_mode in {"live", "canary", "readonly"} else 0
        return (live_bias, exact_target + exact_runtime, candidate.updated_at)
    if requested == "live":
        return (exact_target, exact_runtime, candidate.updated_at)
    if requested == "canary":
        return (exact_target, exact_runtime, candidate.updated_at)
    if requested == "readonly":
        return (exact_target, exact_runtime, candidate.updated_at)
    if requested == "paper":
        return (exact_runtime, exact_target, candidate.updated_at)
    return (exact_target + exact_runtime, exact_runtime, candidate.updated_at)


def resolve_run_directory(*, run_dir: str, selection_mode: str = "auto") -> UniverseRunResolution:
    explicit = Path(run_dir).expanduser()
    explicit = explicit.resolve() if explicit.exists() else explicit

    if explicit.name == "runs":
        runs_root = explicit
        project_root = explicit.parent
    elif explicit.parent.name == "runs":
        runs_root = explicit.parent
        project_root = runs_root.parent
    else:
        runs_root = explicit.parent / "runs"
        if not runs_root.exists():
            runs_root = explicit.parent
        project_root = runs_root.parent if runs_root.name == "runs" else explicit.parent

    candidates: list[UniverseRunCandidate] = []
    seen: set[Path] = set()
    for path in [explicit, *(sorted(runs_root.iterdir(), reverse=True) if runs_root.exists() else [])]:
        if not path.exists() or not path.is_dir():
            continue
        real_path = path.resolve()
        if real_path in seen:
            continue
        seen.add(real_path)
        candidate = _candidate_from_dir(real_path)
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        fallback_path = explicit if explicit.exists() else explicit.parent
        return UniverseRunResolution(
            requested_mode=_normalize_mode(selection_mode),
            run_path=fallback_path,
            project_root=project_root,
            runtime_mode="unknown",
            target_mode="unknown",
            updated_at=0.0,
            source="fallback",
            candidates=tuple(),
        )

    requested = _normalize_mode(selection_mode)
    if requested == "auto":
        filtered = list(candidates)
    elif requested == "paper":
        filtered = [c for c in candidates if c.runtime_mode == "paper" or c.target_mode == "paper"]
    else:
        filtered = [c for c in candidates if c.target_mode == requested or c.runtime_mode == requested]
    if not filtered:
        filtered = list(candidates)

    winner = max(filtered, key=lambda candidate: _score_candidate(candidate, requested))
    explicit_resolved = explicit.resolve() if explicit.exists() else explicit
    source = "explicit" if winner.run_path == explicit_resolved else f"scan:{requested}"
    return UniverseRunResolution(
        requested_mode=requested,
        run_path=winner.run_path,
        project_root=project_root,
        runtime_mode=winner.runtime_mode,
        target_mode=winner.target_mode,
        updated_at=winner.updated_at,
        source=source,
        candidates=tuple(sorted(candidates, key=lambda item: item.updated_at, reverse=True)[:12]),
    )
