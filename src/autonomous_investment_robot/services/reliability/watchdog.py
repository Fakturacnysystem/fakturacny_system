from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import time
from pathlib import Path
from typing import Any


@dataclass
class WatchdogConfig:
    enabled: bool = True
    poll_interval_s: float = 2.0
    stall_timeout_s: float = 45.0
    restart_backoff_s: float = 5.0
    max_restarts: int = 0  # 0 means unlimited
    heartbeat_filename: str = "health.json"
    state_filename: str = "watchdog_state.json"


@dataclass
class WatchdogState:
    restart_count: int = 0
    last_restart_ts: float = 0.0
    last_restart_reason: str = ""
    child_pid: int = 0
    running: bool = False
    child_started_ts: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WatchdogSupervisor:
    """Filesystem-backed watchdog state and heartbeat checks.

    Designed to be used by CLI supervisor loops and process managers.
    """

    def __init__(self, run_dir: str, config: WatchdogConfig | None = None) -> None:
        self.config = config or WatchdogConfig()
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.heartbeat_path = self.run_dir / self.config.heartbeat_filename
        self.state_path = self.run_dir / self.config.state_filename
        self.state = self._load_state()

    def _load_state(self) -> WatchdogState:
        if not self.state_path.exists():
            return WatchdogState()
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            return WatchdogState(
                restart_count=int(raw.get("restart_count", 0) or 0),
                last_restart_ts=float(raw.get("last_restart_ts", 0.0) or 0.0),
                last_restart_reason=str(raw.get("last_restart_reason", "") or ""),
                child_pid=int(raw.get("child_pid", 0) or 0),
                running=bool(raw.get("running", False)),
                child_started_ts=float(raw.get("child_started_ts", 0.0) or 0.0),
            )
        except Exception:
            return WatchdogState()

    def persist_state(self) -> None:
        self.state_path.write_text(json.dumps(self.state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def can_restart(self) -> bool:
        limit = int(self.config.max_restarts)
        if limit <= 0:
            return True
        return self.state.restart_count < limit

    def mark_child_started(self, pid: int) -> None:
        self.state.child_pid = int(pid)
        self.state.running = True
        self.state.child_started_ts = time.time()
        self.persist_state()

    def mark_child_stopped(self) -> None:
        self.state.running = False
        self.state.child_pid = 0
        self.state.child_started_ts = 0.0
        self.persist_state()

    def register_restart(self, reason: str) -> None:
        self.state.restart_count += 1
        self.state.last_restart_reason = str(reason or "")
        self.state.last_restart_ts = time.time()
        self.persist_state()

    def heartbeat_age_s(self, now_ts: float | None = None) -> float:
        now = time.time() if now_ts is None else float(now_ts)
        if not self.heartbeat_path.exists():
            if bool(self.state.running) and self.state.child_started_ts > 0.0:
                return max(0.0, now - float(self.state.child_started_ts))
            return float("inf")
        try:
            payload = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
            ts = float(payload.get("last_progress_ts", payload.get("ts", 0.0)) or 0.0)
            if ts <= 0.0:
                return float("inf")
            # Guard startup against stale heartbeat files from previous child runs.
            # If watchdog just started a new child and heartbeat timestamp predates it,
            # treat heartbeat age from child_started_ts until first fresh heartbeat arrives.
            if bool(self.state.running) and self.state.child_started_ts > 0.0 and ts < float(self.state.child_started_ts):
                return max(0.0, now - float(self.state.child_started_ts))
            return max(0.0, now - ts)
        except Exception:
            return float("inf")

    def stalled(self, now_ts: float | None = None) -> bool:
        if not bool(self.config.enabled):
            return False
        age = self.heartbeat_age_s(now_ts=now_ts)
        return age > max(1.0, float(self.config.stall_timeout_s))

    def health(self, now_ts: float | None = None) -> dict[str, Any]:
        now = time.time() if now_ts is None else float(now_ts)
        age = self.heartbeat_age_s(now_ts=now)
        ok = True if not bool(self.config.enabled) else (not self.stalled(now_ts=now))
        heartbeat_payload: dict[str, Any] = {}
        if self.heartbeat_path.exists():
            try:
                raw = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    heartbeat_payload = raw
            except Exception:
                heartbeat_payload = {}
        shield_reason_codes = heartbeat_payload.get("shield_reason_codes", [])
        if not isinstance(shield_reason_codes, list):
            shield_reason_codes = []
        shield_context = {
            "mode": str(heartbeat_payload.get("shield_mode", "") or ""),
            "reason_codes": [str(code) for code in shield_reason_codes if str(code)],
            "source": str(heartbeat_payload.get("shield_source", "") or ""),
            "risk_safe_mode": bool(heartbeat_payload.get("risk_safe_mode", False)),
            "risk_kill_switch": bool(heartbeat_payload.get("risk_kill_switch", False)),
        }
        return {
            "ok": ok,
            "running": bool(self.state.running),
            "child_pid": int(self.state.child_pid),
            "restart_count": int(self.state.restart_count),
            "last_restart_reason": str(self.state.last_restart_reason),
            "last_restart_ts": float(self.state.last_restart_ts),
            "heartbeat_age_s": age,
            "stall_timeout_s": float(self.config.stall_timeout_s),
            "heartbeat_path": str(self.heartbeat_path),
            "state_path": str(self.state_path),
            "shield_context": shield_context,
        }
