from __future__ import annotations

import json

from autonomous_investment_robot.universe_gateway.projections import UniverseProjectionStore
from autonomous_investment_robot.universe_gateway.query_service import UniverseQueryService


def test_query_service_compat_and_api_payloads(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "runtime_health.json").write_text(json.dumps({"status": "running", "mode": "Canary"}), encoding="utf-8")
    (run_dir / "dashboard_snapshot.json").write_text(json.dumps({"equity": 1000, "pnl": 30, "drawdown_pct": -2.1}), encoding="utf-8")
    (run_dir / "audit.log").write_text(json.dumps({"event_type": "heartbeat", "reason": "ok"}) + "\n", encoding="utf-8")

    store = UniverseProjectionStore(dsn=f"sqlite:///{tmp_path / 'gw.db'}")
    svc = UniverseQueryService(run_dir=str(run_dir), projections=store)

    assert svc.health_payload()["ok"] is True
    assert svc.status_payload()["runtime_health"]["status"] == "running"

    capital = svc.api_capital_state()
    assert capital["equity"] == 1000.0
    assert "survivability_score" in capital

    telemetry_rows = svc.api_telemetry_events(limit=10)["rows"]
    assert telemetry_rows


def test_query_service_uses_health_report_and_snapshot_fallbacks(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "health.json").write_text(
        json.dumps({"status": "ok", "mode": "paper", "provider": "paper_sim_provider", "reason": "paper_backtest_complete", "symbol": "BTCUSDT"}),
        encoding="utf-8",
    )
    (run_dir / "report.json").write_text(
        json.dumps([{"equity": 1.25, "drawdown_pct": 1.8, "pnl": 0.14}]),
        encoding="utf-8",
    )
    (run_dir / "dashboard_snapshot.json").write_text(
        json.dumps(
            {
                "groups": {
                    "execution": {
                        "orders_submitted_total": 4,
                        "fills_confirmed_total": 2,
                        "orders_rejected_total": 1,
                        "reject_rate": 0.25,
                    },
                    "execution_qa": {"latency_p50_ms": 18.0},
                    "costs": {"slippage_bps": 1.5},
                    "risk": {"drawdown": 1.8, "exposure_notional": 42.0},
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "compliance_engine_report.json").write_text(
        json.dumps({"allowed": True, "reason": "authorized", "provider": "paper_sim_provider"}),
        encoding="utf-8",
    )
    (run_dir / "mastermind_status.json").write_text(
        json.dumps({"ok": True, "invariant_breach": False}),
        encoding="utf-8",
    )

    store = UniverseProjectionStore(dsn=f"sqlite:///{tmp_path / 'gw2.db'}")
    svc = UniverseQueryService(run_dir=str(run_dir), projections=store)

    system = svc.api_system_status()
    capital = svc.api_capital_state()
    execution = svc.api_execution_stats()
    audit = svc.api_audit_runtime()

    assert system["mode"] == "Paper"
    assert system["provider"] == "paper_sim_provider"
    assert capital["equity"] == 1.25
    assert capital["allocation"] == 42.0
    assert execution["submitted_orders"] == 4
    assert execution["filled_orders"] == 2
    assert execution["rejected_orders"] == 1
    assert execution["latency"] == 18.0
    assert execution["slippage"] == 1.5
    assert audit["gate_status"] == "open"


def test_query_service_resolves_live_target_and_reports_paper_fallback(tmp_path, monkeypatch) -> None:
    runs = tmp_path / "runs"
    latest = runs / "latest"
    live = runs / "kraken_spot_live_profit_full_throttle"
    ops = tmp_path / "ops"
    latest.mkdir(parents=True, exist_ok=True)
    live.mkdir(parents=True, exist_ok=True)
    ops.mkdir(parents=True, exist_ok=True)

    (latest / "health.json").write_text(json.dumps({"mode": "paper", "status": "ok"}), encoding="utf-8")
    (live / "health.json").write_text(
        json.dumps({"mode": "paper", "status": "starting", "reason": "manual_gate_pending", "provider": "paper_sim_provider"}),
        encoding="utf-8",
    )
    (live / "runtime_config.effective.yaml").write_text(
        "mode: live\nexecution:\n  mode: live\n",
        encoding="utf-8",
    )
    (live / "dashboard_snapshot.json").write_text(json.dumps({"equity": 1.0}), encoding="utf-8")
    (ops / "live_operator_confirmation.txt").write_text("I_CONFIRM_LIVE_TRADING\n", encoding="utf-8")
    (ops / "live_governance_approval.json").write_text(
        json.dumps({"artifact_id": "approval-1", "approved": True, "approver": "tester", "stage": "limited_live_ready"}),
        encoding="utf-8",
    )
    (tmp_path / "runs" / "preflight_live.json").write_text(json.dumps({"ok": True}), encoding="utf-8")

    monkeypatch.setenv("AUTONOMOUS_UNIVERSE_RUN_SELECTION", "live")
    monkeypatch.setenv("AUTONOMOUS_LIVE_GO", "1")
    monkeypatch.setenv("AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE", str(ops / "live_operator_confirmation.txt"))
    monkeypatch.setenv("AUTONOMOUS_LIVE_OPERATOR_APPROVAL_ARTIFACT_FILE", str(ops / "live_governance_approval.json"))

    store = UniverseProjectionStore(dsn=f"sqlite:///{tmp_path / 'gw3.db'}")
    svc = UniverseQueryService(run_dir=str(latest), projections=store)

    environment = svc.api_system_environment()
    audit = svc.api_audit_runtime()

    assert environment["target_mode"] == "live"
    assert environment["runtime_mode"] == "paper"
    assert environment["resolved_run_dir"].endswith("kraken_spot_live_profit_full_throttle")
    assert audit["manual_gate_status"] == "open"
    assert audit["operator_approval_status"] == "approved"
    assert audit["readiness_stage"] == "paper_fallback"


def test_query_service_normalizes_latest_audit_projection(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "health.json").write_text(json.dumps({"status": "ok", "mode": "live"}), encoding="utf-8")

    store = UniverseProjectionStore(dsn=f"sqlite:///{tmp_path / 'gw4.db'}")
    store.upsert_latest(
        domain="audit",
        payload={
            "event_id": "evt-1",
            "timestamp": "2026-03-13T08:00:00Z",
            "payload": {
                "system_state": "running",
                "hard_invariants_status": "clean",
                "drift_status": "strict",
                "gate_status": "open",
                "readiness_stage": "operational",
            },
        },
    )

    svc = UniverseQueryService(run_dir=str(run_dir), projections=store)
    audit = svc.api_audit_runtime()

    assert audit["system_state"] == "running"
    assert audit["gate_status"] == "open"
    assert audit["readiness_stage"] == "operational"
