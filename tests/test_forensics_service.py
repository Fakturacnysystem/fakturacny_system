from datetime import datetime, timezone
from pathlib import Path

from autonomous_investment_robot.core.contracts import TradeForensicsContext, TruthConfidence, TruthConfidenceLevel, TruthConfidenceSnapshot
from autonomous_investment_robot.services.execution.service import Fill
from autonomous_investment_robot.services.forensics_service.service import ForensicsService


def test_forensics_service_records_attribution_and_loss_autopsy(tmp_path):
    svc = ForensicsService(str(tmp_path))
    fill = Fill(
        venue="paper",
        order_id="ord-1",
        fill_id="fill-1",
        symbol="BTCUSDT",
        side="buy",
        notional=100.0,
        fee=1.5,
        slippage_cost=0.5,
        latency_ms=100,
        status="filled",
    )

    record, autopsy = svc.analyze_trade(
        context=TradeForensicsContext(
            symbol="BTCUSDT",
            ts=datetime.now(timezone.utc),
            venue="paper",
            order_id="ord-1",
            side="buy",
            regime_label="trend",
            expected_edge_bps=25.0,
        ),
        fills=[fill],
        filled_notional=100.0,
        realized_pnl=-8.0,
    )

    assert record.breakdown.directional_pnl == -6.0
    assert record.execution_costs.fee_cost == 1.5
    assert record.execution_costs.slippage_cost == 0.5
    assert record.breakdown.execution_vs_signal_gap is not None
    assert record.metadata["exit_hierarchy_reason"] == "tactical_discretionary_exit"
    assert autopsy is not None
    assert "thesis_failed" in autopsy.dominant_failure_modes
    assert (tmp_path / "pnl_attribution.jsonl").exists()
    assert (tmp_path / "loss_autopsy.jsonl").exists()
    assert (tmp_path / "post_trade_summary.jsonl").exists()
    assert (tmp_path / "loss_review_summary.jsonl").exists()
    assert (tmp_path / "trade_episode_memory.jsonl").exists()
    assert (tmp_path / "analog_trade_lookup.jsonl").exists()
    assert (tmp_path / "counterfactual_review.jsonl").exists()
    assert (tmp_path / "calibration_profile.json").exists()


def test_forensics_service_marks_truth_degradation_as_partial(tmp_path):
    svc = ForensicsService(str(tmp_path))
    truth = TruthConfidenceSnapshot(
        ts=datetime.now(timezone.utc),
        fill_truth_confidence=TruthConfidence("fill_truth_confidence", TruthConfidenceLevel.AUTHORITATIVE, "ok"),
        fee_truth_confidence=TruthConfidence("fee_truth_confidence", TruthConfidenceLevel.PROXY, "fee_window_proxy"),
        realized_pnl_confidence=TruthConfidence("realized_pnl_confidence", TruthConfidenceLevel.UNAVAILABLE, "missing_realized"),
        balance_truth_confidence=TruthConfidence("balance_truth_confidence", TruthConfidenceLevel.AUTHORITATIVE, "ok"),
        exposure_truth_confidence=TruthConfidence("exposure_truth_confidence", TruthConfidenceLevel.AUTHORITATIVE, "ok"),
        market_data_truth_confidence=TruthConfidence("market_data_truth_confidence", TruthConfidenceLevel.AUTHORITATIVE, "ok"),
    )
    fill = Fill(
        venue="binance_um_perps",
        order_id="ord-2",
        fill_id="fill-2",
        symbol="BTCUSDT",
        side="sell",
        notional=50.0,
        fee=0.25,
        slippage_cost=0.1,
        latency_ms=50,
        status="filled",
    )

    record, autopsy = svc.analyze_trade(
        context=TradeForensicsContext(
            symbol="BTCUSDT",
            ts=datetime.now(timezone.utc),
            venue="binance_um_perps",
            order_id="ord-2",
            side="sell",
            regime_label="range",
            expected_edge_bps=10.0,
            truth_confidence=truth,
        ),
        fills=[fill],
        filled_notional=50.0,
        realized_pnl=3.0,
    )

    assert record.partial is True
    assert {warning.domain for warning in record.truth_warnings} == {"fee_truth_confidence", "realized_pnl_confidence"}
    assert autopsy is None
    assert (tmp_path / "trade_episode_memory.jsonl").exists()


def test_record_runtime_anomaly_persists_forensic_artifact(tmp_path):
    svc = ForensicsService(str(tmp_path))

    report = svc.record_runtime_anomaly(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        venue="kraken_derivatives",
        category="reconciliation",
        reason="live_realized_pnl_mismatch",
        evidence={"delta": 5.0},
    )

    assert report.category == "reconciliation"
    assert report.reason == "live_realized_pnl_mismatch"
    assert report.runtime_degradation_context["truth_warning_count"] == 0
    assert Path(tmp_path / "loss_autopsy.jsonl").exists()
    assert Path(tmp_path / "loss_review_summary.jsonl").exists()
