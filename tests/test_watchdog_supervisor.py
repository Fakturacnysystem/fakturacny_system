from __future__ import annotations

import json
import time

from autonomous_investment_robot.services.reliability import WatchdogConfig, WatchdogSupervisor


def test_watchdog_stall_detection_and_health(tmp_path) -> None:
    cfg = WatchdogConfig(stall_timeout_s=5.0, poll_interval_s=1.0)
    sup = WatchdogSupervisor(run_dir=str(tmp_path), config=cfg)

    # No heartbeat yet means stale.
    assert sup.stalled(now_ts=100.0) is True

    heartbeat_path = tmp_path / cfg.heartbeat_filename
    heartbeat_path.write_text(json.dumps({"last_progress_ts": 98.0}), encoding="utf-8")
    assert sup.stalled(now_ts=100.0) is False

    health = sup.health(now_ts=100.0)
    assert health["ok"] is True
    assert health["heartbeat_age_s"] == 2.0


def test_watchdog_restart_state_persists(tmp_path) -> None:
    cfg = WatchdogConfig(max_restarts=1)
    sup = WatchdogSupervisor(run_dir=str(tmp_path), config=cfg)

    assert sup.can_restart() is True
    sup.mark_child_started(12345)
    sup.register_restart("heartbeat_stalled")
    sup.mark_child_stopped()
    assert sup.can_restart() is False

    # Reload from disk and verify persisted state.
    sup2 = WatchdogSupervisor(run_dir=str(tmp_path), config=cfg)
    assert sup2.state.restart_count == 1
    assert sup2.state.last_restart_reason == "heartbeat_stalled"
    assert sup2.state.running is False
    assert sup2.state.child_pid == 0
    assert sup2.state.last_restart_ts <= time.time()


def test_watchdog_disabled_never_stalls(tmp_path) -> None:
    cfg = WatchdogConfig(enabled=False, stall_timeout_s=1.0)
    sup = WatchdogSupervisor(run_dir=str(tmp_path), config=cfg)

    # No heartbeat should not matter when watchdog is disabled.
    assert sup.stalled(now_ts=100.0) is False
    health = sup.health(now_ts=100.0)
    assert health["ok"] is True


def test_watchdog_grace_period_before_first_heartbeat(tmp_path) -> None:
    cfg = WatchdogConfig(stall_timeout_s=30.0, poll_interval_s=1.0)
    sup = WatchdogSupervisor(run_dir=str(tmp_path), config=cfg)

    # Child started but has not written first heartbeat yet.
    sup.mark_child_started(999)
    started = sup.state.child_started_ts
    assert started > 0.0
    assert sup.stalled(now_ts=started + 10.0) is False
    assert sup.stalled(now_ts=started + 31.0) is True
