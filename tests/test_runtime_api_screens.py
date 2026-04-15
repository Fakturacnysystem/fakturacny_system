from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from autonomous_investment_robot.services.runtime_api.service import (
    QuoteSnapshot,
    RuntimeApiService,
    RuntimeApiServiceConfig,
)

REPO = Path(__file__).resolve().parent.parent


def _quote_fetcher(provider_id: str, symbol: str) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol=symbol,
        venue=provider_id,
        bid=100.0,
        ask=100.2,
        latency_ms=21,
        ts="2026-03-31T15:20:23+00:00",
    )


def _service(run_id: str) -> RuntimeApiService:
    return RuntimeApiService(
        RuntimeApiServiceConfig(
            repo_root=REPO,
            run_id=run_id,
            artifact_stale_after_seconds=999_999,
        ),
        now=lambda: datetime(2026, 3, 31, 20, 0, 0, tzinfo=UTC),
        quote_fetcher=_quote_fetcher,
    )


def test_brain_payload_surfaces_pipeline_and_explainability_for_readonly_run() -> None:
    payload = _service("kraken_spot_readonly_analysis").brain()

    assert payload["runId"] == "kraken_spot_readonly_analysis"
    assert payload["runtimeIdentity"]["runSelectionMode"] == "pinned"
    assert payload["runtimeIdentity"]["pinIntegrityStatus"] == "ok"
    assert payload["selectedSymbol"] == "BTC/USD"
    assert len(payload["pipeline"]) >= 8
    assert any(step["id"] == "execution_eligibility" for step in payload["pipeline"])
    assert "decision_explainability.json" in payload["decisionReplay"]["linkedArtifacts"]
    assert payload["evidenceNotes"]
    assert "opportunityRanking" in payload


def test_shield_payload_surfaces_guard_matrix_and_truth_notes() -> None:
    payload = _service("kraken_spot_readonly_analysis").shield()

    assert payload["runId"] == "kraken_spot_readonly_analysis"
    assert payload["trustVerdict"] in {"caution", "unsafe", "trusted"}
    assert payload["runtimeIdentity"]["pinIntegrityStatus"] == "ok"
    assert any(item["label"] == "Runtime identity" for item in payload["runtimeSafety"])
    assert any(guard["name"] == "Readonly mode" for guard in payload["guardMatrix"])
    assert any(guard["name"] == "Spread guard" for guard in payload["guardMatrix"])
    assert payload["userStream"]["status"] in {"connected", "partial", "disconnected", "unavailable"}
    assert payload["truthNotes"]
    assert "performanceControl" in payload
    assert payload["performanceControl"]["promotionStatus"] == "blocked_rollback_triggered"
    assert payload["performanceControl"]["recoveryMode"] == "inactive"
    assert payload["performanceControl"]["authorityBoundary"] == "readonly_no_live_orders"
    assert payload["performanceControl"]["targetPlausibility"] == "implausible_under_current_capital_envelope"
    assert payload["performanceControl"]["rollbackRisk"] == "high"


def test_execution_payload_reconstructs_orders_and_preserves_missing_fill_honesty() -> None:
    payload = _service("kraken_spot_tiny_live").execution()

    assert payload["runId"] == "kraken_spot_tiny_live"
    assert payload["runtimeIdentity"]["runSelectionMode"] == "pinned"
    assert len(payload["orders"]) >= 1
    statuses = {order["status"] for order in payload["orders"]}
    assert "pending" in statuses
    assert any(status in statuses for status in {"rejected", "timed out", "filled"})
    timed_out_or_rejected = next(
        order for order in payload["orders"] if order["status"] in {"rejected", "timed out"}
    )
    assert timed_out_or_rejected["rejectionReason"]
    assert payload["accountSnapshot"]["exchangeBalance"] is not None
    assert payload["venueTelemetry"]["userStreamStatus"] in {"connected", "partial"}
    assert payload["venueTelemetry"]["lifecycleStatus"]
    assert any(metric["label"] == "Fill rate" and metric["value"] is None for metric in payload["summary"])
    assert any("No events_fills.jsonl artifact present" in note for note in payload["dataNotes"])
    assert "alphaTelemetry" in payload


def test_execution_payload_surfaces_phase2_review_when_artifacts_exist() -> None:
    payload = _service("kraken_spot_readonly_analysis").execution()

    assert payload["phase2Review"]["operatorSummary"]
    assert payload["phase2Review"]["executionTruth"]["partial"] is True
    assert payload["phase2Review"]["edgeTruth"]["partial"] is True
    assert payload["phase2Review"]["exitTruth"]["partial"] is True
    assert "phase2_operator_summary.json" in payload["phase2Review"]["linkedArtifacts"]
