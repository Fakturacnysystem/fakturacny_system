from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from autonomous_investment_robot.core.order_scheduler import OrderSubmissionScheduler
from autonomous_investment_robot.services.execution.profit_gate import ProfitGate, ProfitGateConfig
from autonomous_investment_robot.services.reliability import HealthAudit110
from autonomous_investment_robot.services.storage import SQLiteStore


class _Conn:
    def __init__(self) -> None:
        self.cancelled = 0

    def open_orders(self):
        return {"open": {}}

    def cancel_all(self):
        self.cancelled += 1
        return {"count": 0}


class _HealthyRisk:
    def __init__(self) -> None:
        self.state = SimpleNamespace(kill_switch=False, safe_mode=False)
        self.limits = object()

    def _limits_complete(self) -> bool:
        return True


class _RepairableLive:
    def __init__(self) -> None:
        self.connector = _Conn()
        self.profit_gate = ProfitGate(ProfitGateConfig(min_net_profit_ratio=0.02, default_slippage_bps=0.5))
        self._ledgers = {}
        self.refreshed = False

    def market_snapshot(self, symbol: str, max_age_s: float | None = None, force_refresh: bool = False):  # noqa: ARG002
        if force_refresh:
            self.refreshed = True
        ts = time.time() if self.refreshed else (time.time() - 120.0)
        return {
            "pair": symbol,
            "bid": 100.0,
            "ask": 101.0,
            "ts": ts,
            "mark_price": 100.0,
            "index_price": 100.0,
            "funding_rate": 0.0001,
            "open_interest": 1.0,
        }

    def _available_quote_balance(self, symbol: str):  # noqa: ARG002
        return "USD", 1000.0

    def sync_fill_ledger(self, symbol: str, mark_price: float):  # noqa: ARG002
        return {"symbol": symbol, "position_qty": 0.0}

    def reconcile_live_state(self, internal_exposure: float):  # noqa: ARG002
        return True, "ok"


class _LockedSQLite:
    def latest_submission_epoch(self):
        return time.time()

    def health(self):
        raise RuntimeError("database is locked")

    def record_audit_checkpoint(self, *, kind: str, payload: dict):  # noqa: ARG002
        raise RuntimeError("database is locked")


def _write_runtime_files(run_dir: Path, *, progress_age_s: float = 0.0, running: bool = True) -> None:
    now = time.time()
    (run_dir / "health.json").write_text(
        json.dumps({"last_progress_ts": now - max(0.0, progress_age_s), "ts": now}),
        encoding="utf-8",
    )
    (run_dir / "watchdog_state.json").write_text(
        json.dumps({"running": running, "restart_count": 0, "last_restart_ts": now - 600.0}),
        encoding="utf-8",
    )


def test_health_audit_soft_repair_recovers_stale_market_data(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_runtime_files(run_dir, progress_age_s=1.0, running=True)

    sqlite = SQLiteStore(str(run_dir))
    scheduler = OrderSubmissionScheduler(interval_s=60.0, initial_last_submission_ts=time.time())
    scheduler.record_submission(now_ts=time.time(), filled=False)

    auditor = HealthAudit110(
        run_dir=str(run_dir),
        health_threshold=85.0,
        stream_stale_after_s=2.0,
        watchdog_stall_timeout_s=45.0,
    )
    live = _RepairableLive()
    report = auditor.audit_and_repair(
        symbol="ETHEUR",
        mode="live",
        live=live,
        sqlite=sqlite,
        ops=SimpleNamespace(metrics={}),
        submission_scheduler=scheduler,
        order_submission_interval_s=60.0,
        risk_engine=_HealthyRisk(),
        latest_feed_quotes=[],
        latest_feed_quality={},
        safe_probe_submitter=None,
        now_ts=time.time(),
    )

    assert report.ok is True
    assert live.refreshed is True
    assert any("soft_refresh_snapshot" in x for x in report.repair_actions_taken)


def test_health_audit_detects_event_loop_stall(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_runtime_files(run_dir, progress_age_s=120.0, running=True)

    sqlite = SQLiteStore(str(run_dir))
    scheduler = OrderSubmissionScheduler(interval_s=60.0, initial_last_submission_ts=time.time())
    scheduler.record_submission(now_ts=time.time(), filled=False)

    auditor = HealthAudit110(run_dir=str(run_dir), watchdog_stall_timeout_s=10.0)
    report = auditor.run_once(
        symbol="ETHEUR",
        mode="live",
        live=_RepairableLive(),
        sqlite=sqlite,
        ops=SimpleNamespace(metrics={}),
        submission_scheduler=scheduler,
        order_submission_interval_s=60.0,
        risk_engine=_HealthyRisk(),
        latest_feed_quotes=[{"bid": 10.0, "ask": 10.1, "ts": time.time()}],
        latest_feed_quality={},
        auto_repair=False,
    )
    checks = {c.name: c for c in report.checks}
    assert checks["event_loop_liveness"].ok is False


def test_health_audit_detects_storage_lock(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_runtime_files(run_dir, progress_age_s=1.0, running=True)

    scheduler = OrderSubmissionScheduler(interval_s=60.0, initial_last_submission_ts=time.time())
    scheduler.record_submission(now_ts=time.time(), filled=False)

    auditor = HealthAudit110(run_dir=str(run_dir))
    report = auditor.run_once(
        symbol="ETHEUR",
        mode="live",
        live=_RepairableLive(),
        sqlite=_LockedSQLite(),
        ops=SimpleNamespace(metrics={}),
        submission_scheduler=scheduler,
        order_submission_interval_s=60.0,
        risk_engine=_HealthyRisk(),
        latest_feed_quotes=[{"bid": 10.0, "ask": 10.1, "ts": time.time()}],
        latest_feed_quality={},
        auto_repair=False,
    )
    checks = {c.name: c for c in report.checks}
    assert checks["storage_integrity"].ok is False
    assert "database is locked" in json.dumps(checks["storage_integrity"].details)


def test_health_audit_detects_rate_limit_storm(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_runtime_files(run_dir, progress_age_s=1.0, running=True)

    audit_log = run_dir / "audit.log"
    for _ in range(20):
        audit_log.write_text(
            (audit_log.read_text(encoding="utf-8") if audit_log.exists() else "")
            + json.dumps({"event_type": "fill_sync_error", "payload": {"error": "Kraken rate limit: EAPI:Rate limit exceeded"}})
            + "\n",
            encoding="utf-8",
        )

    sqlite = SQLiteStore(str(run_dir))
    scheduler = OrderSubmissionScheduler(interval_s=60.0, initial_last_submission_ts=time.time())
    scheduler.record_submission(now_ts=time.time(), filled=False)

    auditor = HealthAudit110(run_dir=str(run_dir), max_rate_limit_events_60s=5.0)
    report = auditor.run_once(
        symbol="ETHEUR",
        mode="live",
        live=_RepairableLive(),
        sqlite=sqlite,
        ops=SimpleNamespace(metrics={"rate_limit_events": 99.0}),
        submission_scheduler=scheduler,
        order_submission_interval_s=60.0,
        risk_engine=_HealthyRisk(),
        latest_feed_quotes=[{"bid": 10.0, "ask": 10.1, "ts": time.time()}],
        latest_feed_quality={},
        auto_repair=False,
    )
    checks = {c.name: c for c in report.checks}
    assert checks["rate_limit_api_health"].ok is False


def test_health_audit_repairs_stale_submission_with_safe_probe(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_runtime_files(run_dir, progress_age_s=1.0, running=True)

    sqlite = SQLiteStore(str(run_dir))
    scheduler = OrderSubmissionScheduler(interval_s=60.0, initial_last_submission_ts=time.time() - 400.0)
    scheduler.last_submission_ts = time.time() - 400.0

    probe_calls: list[str] = []

    def _probe(reason: str) -> bool:
        probe_calls.append(reason)
        scheduler.record_submission(now_ts=time.time(), filled=False)
        sqlite.record_submission(
            symbol="ETHEUR",
            status="submitted",
            reason="scheduler_probe",
            notional_quote=0.25,
            payload={"scheduler_probe": True, "audit110": True},
        )
        return True

    auditor = HealthAudit110(run_dir=str(run_dir))
    report = auditor.run_once(
        symbol="ETHEUR",
        mode="live",
        live=_RepairableLive(),
        sqlite=sqlite,
        ops=SimpleNamespace(metrics={}),
        submission_scheduler=scheduler,
        order_submission_interval_s=60.0,
        risk_engine=_HealthyRisk(),
        latest_feed_quotes=[{"bid": 10.0, "ask": 10.1, "ts": time.time()}],
        latest_feed_quality={},
        safe_probe_submitter=_probe,
        auto_repair=True,
    )
    checks = {c.name: c for c in report.checks}
    assert probe_calls == ["audit110_submission_gap"]
    assert checks["submission_cadence_60s"].ok is True
    assert checks["submission_cadence_60s"].details["auto_probe_repaired"] is True
