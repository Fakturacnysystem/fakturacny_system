from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from autonomous_investment_robot.services.runtime_api.service import (
    QuoteSnapshot,
    RuntimeApiError,
    RuntimeApiService,
    RuntimeApiServiceConfig,
)
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnectorError

REPO = Path(__file__).resolve().parent.parent
RUNS_LATEST = REPO / "runs" / "latest"

ARTIFACTS = [
    "MANUAL_REVIEW_REQUIRED.json",
    "config_manifest.json",
    "decision_doctrine_summary.jsonl",
    "events_positions.jsonl",
    "events_risk.jsonl",
    "events_truth.jsonl",
    "fills.json",
    "harmony_boot_report.json",
    "harmony_report.json",
    "human_escalation_journal.jsonl",
    "mastermind_journal.jsonl",
    "mastermind_summary.jsonl",
    "order_plans.json",
    "portfolio_ledger.json",
    "provider_capabilities.json",
    "provider_capability_journal.jsonl",
    "reconciliation_journal.jsonl",
    "report.json",
    "capital_strategy_summary.jsonl",
    "position_morphing_journal.jsonl",
    "truth_ownership.json",
]


def _quote_fetcher(provider_id: str, symbol: str) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol=symbol,
        venue=provider_id,
        bid=66_400.0,
        ask=66_401.0,
        latency_ms=24,
        ts="2026-03-29T15:58:30+00:00",
    )


def _service(tmp_path: Path) -> RuntimeApiService:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    for name in ARTIFACTS:
        shutil.copy2(RUNS_LATEST / name, run_dir / name)
    return RuntimeApiService(
        RuntimeApiServiceConfig(
            repo_root=tmp_path,
            run_dir=run_dir,
            artifact_stale_after_seconds=600,
        ),
        now=lambda: datetime(2026, 3, 29, 16, 0, 0, tzinfo=UTC),
        quote_fetcher=_quote_fetcher,
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_summary_uses_real_artifacts_and_live_quote_snapshot(tmp_path: Path) -> None:
    service = _service(tmp_path)

    payload = service.summary()

    assert payload["providerId"] == "binance_um_perps"
    assert payload["mode"] == "paper"
    assert payload["restHealthy"] is True
    assert payload["avgLatencyMs"] == 24.0
    assert payload["stateKind"] == "degraded"
    assert payload["reasonCode"] == "manual_review_required"
    assert payload["runtimeIdentity"]["runSelectionMode"] == "pinned"
    assert payload["runtimeIdentity"]["runResolutionSource"] == "explicit_run_dir"
    assert payload["runtimeIdentity"]["pinIntegrityStatus"] == "ok"
    assert payload["runtimeIdentity"]["driftStatus"] == "locked"
    assert "performance" in payload
    assert set(payload["performance"].keys()) >= {"capitalUtilizationPct", "netExpectancyBps", "fillRate", "makerRatio", "targetGap"}


def test_execution_surfaces_phase2_truth_when_artifacts_exist(tmp_path: Path) -> None:
    service = _service(tmp_path)
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "phase2_operator_summary.json",
        {
            "ts": "2026-03-29T15:59:00+00:00",
            "execution_truth": {"sample_count": 4},
            "edge_truth": {"edge_capture_efficiency": 82.5},
            "exit_truth": {"exit_efficiency": 0.74},
        },
    )
    _write_json(
        run_dir / "phase2_execution_truth_review.json",
        {
            "ts": "2026-03-29T15:59:01+00:00",
            "realized_slippage_bps": 5.2,
            "slippage_gap_bps": 1.4,
            "delay_gap_ms": 320.0,
            "feedback_confidence": 0.75,
            "feedback_sample_count": 6,
            "partial": False,
        },
    )
    _write_json(
        run_dir / "phase2_edge_capture_review.json",
        {
            "ts": "2026-03-29T15:59:02+00:00",
            "edge_capture_efficiency": 82.5,
            "forecast_net_edge_bps": 148.0,
            "realized_net_edge_bps": 122.1,
            "partial": False,
        },
    )
    _write_json(
        run_dir / "phase2_exit_effectiveness_review.json",
        {
            "ts": "2026-03-29T15:59:03+00:00",
            "exit_efficiency": 0.74,
            "expected_hold_minutes": 42.0,
            "realized_hold_minutes": 38.0,
            "partial": False,
        },
    )

    payload = service.execution()

    edge_metric = next(item for item in payload["summary"] if item["label"] == "Edge capture efficiency")
    slippage_metric = next(item for item in payload["summary"] if item["label"] == "Slippage gap vs forecast")
    delay_metric = next(item for item in payload["summary"] if item["label"] == "Fill delay gap vs forecast")
    exit_metric = next(item for item in payload["summary"] if item["label"] == "Exit efficiency")

    assert edge_metric["value"] == 82.5
    assert slippage_metric["value"] == 1.4
    assert delay_metric["value"] == 320.0
    assert exit_metric["value"] == 0.74
    assert payload["phase2Review"]["executionTruth"]["feedback_sample_count"] == 6
    assert payload["phase2Review"]["calibration"]["feedbackConfidence"] == 0.75
    assert payload["phase2Review"]["calibration"]["partial"] is False
    assert "phase2_execution_truth_review.json" in payload["phase2Review"]["linkedArtifacts"]
    assert "phase2_edge_capture_review.json" in payload["linkedArtifacts"]


def test_execution_marks_missing_phase2_truth_explicitly_when_unavailable(tmp_path: Path) -> None:
    service = _service(tmp_path)

    payload = service.execution()

    assert payload["phase2Review"]["executionTruth"] == {}
    assert payload["phase2Review"]["edgeTruth"] == {}
    assert payload["phase2Review"]["exitTruth"] == {}
    assert payload["phase2Review"]["calibration"]["partial"] is True
    assert any("No phase2_execution_truth_review.json artifact present" in note for note in payload["dataNotes"])
    assert any("No phase2_edge_capture_review.json artifact present" in note for note in payload["dataNotes"])
    assert any("No phase2_exit_effectiveness_review.json artifact present" in note for note in payload["dataNotes"])


def test_shield_derives_operator_safe_performance_status_from_partial_artifacts(tmp_path: Path) -> None:
    service = _service(tmp_path)

    payload = service.shield()

    assert payload["performanceControl"]["promotionStatus"] is None
    assert payload["performanceControl"]["recoveryMode"] is None
    assert payload["performanceControl"]["authorityBoundary"] == "legacy_live_path_only"


def test_decisions_and_alerts_surface_runtime_risk_state(tmp_path: Path) -> None:
    service = _service(tmp_path)

    decisions = service.decisions()
    alerts = service.alerts()

    assert decisions["items"]
    assert decisions["items"][-1]["riskVerdict"] == "block"
    assert any(alert["module"] == "human-escalation" for alert in alerts["items"])
    assert any(alert["module"] == "truth-ownership" for alert in alerts["items"])


def test_control_and_incident_note_are_append_only_audit_writes(tmp_path: Path) -> None:
    service = _service(tmp_path)
    auth = "Operator ops.mh:session-01"

    control = service.control(
        "freeze",
        {"reasonCode": "operator_freeze", "reasonText": "manual escalation"},
        auth,
    )
    note = service.write_incident_note(
        {
            "runId": "latest",
            "operatorId": "ops.mh",
            "note": "freeze requested pending runtime acknowledgement",
            "severity": "SEV-1",
            "tags": ["manual-review"],
        },
        auth,
    )

    outbox_lines = (tmp_path / "run" / "rcc_control_outbox.jsonl").read_text(encoding="utf-8").splitlines()
    note_lines = (tmp_path / "run" / "rcc_incident_notes.jsonl").read_text(encoding="utf-8").splitlines()

    assert control["accepted"] is True
    assert control["status"] == "queued"
    assert control["effectiveState"] == "awaiting_runtime_ack"
    assert len(outbox_lines) == 1

    assert note["accepted"] is True
    assert note["noteId"]
    assert len(note_lines) == 1


def test_missing_pinned_run_dir_raises_explicit_not_found(tmp_path: Path) -> None:
    service = RuntimeApiService(
        RuntimeApiServiceConfig(
            repo_root=tmp_path,
            run_dir=tmp_path / "does-not-exist",
            artifact_stale_after_seconds=600,
        ),
        now=lambda: datetime(2026, 3, 29, 16, 0, 0, tzinfo=UTC),
        quote_fetcher=_quote_fetcher,
    )

    with pytest.raises(RuntimeApiError, match="run_not_found:"):
        service.summary()


def test_missing_pinned_run_id_does_not_silently_fallback_to_latest(tmp_path: Path) -> None:
    latest_dir = tmp_path / "runs" / "latest"
    latest_dir.mkdir(parents=True)
    for name in ARTIFACTS:
        shutil.copy2(RUNS_LATEST / name, latest_dir / name)

    service = RuntimeApiService(
        RuntimeApiServiceConfig(
            repo_root=tmp_path,
            run_id="target-live-run",
            artifact_stale_after_seconds=600,
        ),
        now=lambda: datetime(2026, 3, 29, 16, 0, 0, tzinfo=UTC),
        quote_fetcher=_quote_fetcher,
    )

    with pytest.raises(RuntimeApiError, match="run_not_found:"):
        service.summary()


def test_run_id_selection_resolves_pinned_run_without_drift(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "target-live-run"
    run_dir.mkdir(parents=True)
    for name in ARTIFACTS:
        shutil.copy2(RUNS_LATEST / name, run_dir / name)

    service = RuntimeApiService(
        RuntimeApiServiceConfig(
            repo_root=tmp_path,
            run_id="target-live-run",
            artifact_stale_after_seconds=600,
        ),
        now=lambda: datetime(2026, 3, 29, 16, 0, 0, tzinfo=UTC),
        quote_fetcher=_quote_fetcher,
    )

    payload = service.summary()

    assert payload["runId"] == "target-live-run"
    assert payload["runtimeIdentity"]["runSelectionMode"] == "pinned"
    assert payload["runtimeIdentity"]["runResolutionSource"] == "explicit_run_id"
    assert payload["runtimeIdentity"]["runPath"].endswith("/target-live-run")
    assert payload["runtimeIdentity"]["pinIntegrityStatus"] == "ok"
    assert payload["runtimeIdentity"]["driftStatus"] == "locked"


def test_runs_catalog_and_select_run_surface_explicit_selection_state(tmp_path: Path) -> None:
    alpha = tmp_path / "runs" / "alpha-live"
    beta = tmp_path / "runs" / "beta-live"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)
    for run_dir in [alpha, beta]:
        for name in ARTIFACTS:
            shutil.copy2(RUNS_LATEST / name, run_dir / name)

    service = RuntimeApiService(
        RuntimeApiServiceConfig(
            repo_root=tmp_path,
            run_id="alpha-live",
            artifact_stale_after_seconds=600,
        ),
        now=lambda: datetime(2026, 3, 29, 16, 0, 0, tzinfo=UTC),
        quote_fetcher=_quote_fetcher,
    )

    catalog = service.runs()
    assert catalog["selectionMode"] == "pinned"
    assert catalog["resolvedRunId"] == "alpha-live"
    assert any(item["runId"] == "alpha-live" and item["current"] for item in catalog["items"])

    response = service.select_run({"mode": "pinned", "runId": "beta-live"})
    assert response["accepted"] is True
    assert response["selectionMode"] == "pinned"
    assert response["runId"] == "beta-live"
    assert response["runtimeIdentity"]["pinIntegrityStatus"] == "ok"
    assert response["runtimeIdentity"]["driftStatus"] == "locked"

    latest = service.select_run({"mode": "latest"})
    assert latest["accepted"] is True
    assert latest["selectionMode"] == "latest"


def test_unresolved_selection_payload_preserves_requested_missing_target(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "alpha-live"
    run_dir.mkdir(parents=True)
    for name in ARTIFACTS:
        shutil.copy2(RUNS_LATEST / name, run_dir / name)

    service = RuntimeApiService(
        RuntimeApiServiceConfig(
            repo_root=tmp_path,
            run_id="alpha-live",
            artifact_stale_after_seconds=600,
        ),
        now=lambda: datetime(2026, 3, 29, 16, 0, 0, tzinfo=UTC),
        quote_fetcher=_quote_fetcher,
    )

    payload = service.unresolved_selection_payload(
        "run_not_found:/tmp/missing",
        {"mode": "pinned", "runId": "definitely-missing-run"},
    )

    assert payload["runtimeIdentity"]["runId"] == "definitely-missing-run"
    assert payload["runtimeIdentity"]["runPath"].endswith("/definitely-missing-run")
    assert payload["runtimeIdentity"]["pinIntegrityStatus"] == "unresolved"


def test_summary_degrades_honestly_when_quote_connector_init_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    for name in ARTIFACTS:
        shutil.copy2(RUNS_LATEST / name, run_dir / name)
    for name in ["MANUAL_REVIEW_REQUIRED.json", "events_risk.jsonl", "truth_ownership.json"]:
        (run_dir / name).unlink(missing_ok=True)
    for name in ["kraken_spot_operator_summary.json", "kraken_spot_replay_summary.json"]:
        (run_dir / name).write_text("{}", encoding="utf-8")

    manifest_path = run_dir / "config_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_record = manifest[0] if isinstance(manifest, list) else manifest
    manifest_record["provider_id"] = "kraken_spot"
    manifest_record["universe"] = ["BTC/USD"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    class BrokenKrakenSpotConnector:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise KrakenSpotConnectorError("ccxt_unavailable")

    monkeypatch.setattr(
        "autonomous_investment_robot.services.runtime_api.service.KrakenSpotConnector",
        BrokenKrakenSpotConnector,
    )

    service = RuntimeApiService(
        RuntimeApiServiceConfig(
            repo_root=tmp_path,
            run_dir=run_dir,
            artifact_stale_after_seconds=600,
        ),
        now=lambda: datetime(2026, 3, 29, 16, 0, 0, tzinfo=UTC),
    )

    payload = service.summary()

    assert payload["stateKind"] == "partial"
    assert payload["reasonCode"] == "market_quote_degraded"
    assert payload["restHealthy"] is False


def test_summary_uses_authoritative_artifact_quotes_and_replay_reconstruction_when_live_quotes_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    (run_dir / "config_manifest.json").write_text(
        json.dumps(
            {
                "provider_id": "kraken_spot",
                "runtime_mode": "live",
                "universe": ["BTC/USD"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (run_dir / "report.json").write_text(json.dumps({"equity": 34.338}), encoding="utf-8")
    (run_dir / "kraken_spot_operator_summary.json").write_text(
        json.dumps(
            {
                "symbol": "BTC/USD",
                "market_context": {
                    "symbol": "BTC/USD",
                    "market_integrity": {
                        "symbol": "BTC/USD",
                        "metadata": {
                            "spread_bps": 0.0149,
                        },
                    },
                },
                "performance_architecture": {
                    "execution_alpha": {
                        "cost_model": {
                            "metadata": {
                                "mid_price": 66953.35,
                            }
                        }
                    }
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (run_dir / "events_truth.jsonl").write_text(
        json.dumps(
            {
                "event_type": "TRUTH_CONFIDENCE_SNAPSHOT",
                "payload": {
                    "market_data_truth_confidence": {
                        "domain": "market_data_truth_confidence",
                        "level": "authoritative",
                        "reason": "market_data_integrity_ok",
                    }
                },
                "ts": "2026-03-29T15:58:30+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    market_integrity = {
        "symbol": "BTC/USD",
        "ts": "2026-03-29T15:58:30+00:00",
        "action": "continue",
        "metadata": {
            "spread_bps": 0.0149,
            "integrity_evidence": {"feed_age_seconds": 0.0},
            "capability_evidence": {"freshness_seconds": 0.0, "user_stream_connected": True},
        },
    }
    market_watch = {
        "symbol": "BTC/USD",
        "ts": "2026-03-29T15:58:30+00:00",
        "action": "continue",
        "metadata": {
            "spread_bps": 0.0149,
            "dead_market_reasoning": {
                "public_market_data_connected": True,
                "seconds_since_distinct_book_change": 0.0,
            },
        },
    }
    (run_dir / "market_integrity_journal.jsonl").write_text(json.dumps(market_integrity) + "\n", encoding="utf-8")
    (run_dir / "market_watch_journal.jsonl").write_text(json.dumps(market_watch) + "\n", encoding="utf-8")
    (run_dir / "market_context_summary.jsonl").write_text(
        json.dumps({"symbol": "BTC/USD", "market_integrity": market_integrity, "market_watch": market_watch}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "reconciliation_report.jsonl").write_text(
        json.dumps({"ok": True, "code": "reconciled", "ts": "2026-03-29T15:58:30+00:00"}) + "\n",
        encoding="utf-8",
    )

    class BrokenKrakenSpotConnector:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise KrakenSpotConnectorError("ccxt_unavailable")

    monkeypatch.setattr(
        "autonomous_investment_robot.services.runtime_api.service.KrakenSpotConnector",
        BrokenKrakenSpotConnector,
    )

    service = RuntimeApiService(
        RuntimeApiServiceConfig(
            repo_root=tmp_path,
            run_dir=run_dir,
            artifact_stale_after_seconds=600,
        ),
        now=lambda: datetime(2026, 3, 29, 16, 0, 0, tzinfo=UTC),
    )

    payload = service.summary()
    symbols = service.symbols()
    health = service.health()

    assert payload["stateKind"] == "healthy"
    assert payload["reasonCode"] is None
    assert payload["restHealthy"] is True
    assert symbols["items"][0]["source"] == "runtime_artifacts"
    assert symbols["items"][0]["bid"] > 0
    assert symbols["items"][0]["ask"] > symbols["items"][0]["bid"]
    assert health["artifactFallbackActive"] is False
