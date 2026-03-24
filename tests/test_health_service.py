from datetime import datetime, timezone

from autonomous_investment_robot.core.contracts import MarketHealthSnapshot, MarketIntegrityStatus, TruthConfidence, TruthConfidenceLevel, TruthConfidenceSnapshot, VenueLimitDecision
from autonomous_investment_robot.services.health_service.service import HealthService


def _market_health() -> MarketHealthSnapshot:
    return MarketHealthSnapshot(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        feed_stale=False,
        sequence_ok=True,
        checksum_ok=True,
        symbol_health_score=0.95,
        exchange_health_score=0.95,
        market_quality_score=0.9,
        reasons=[],
    )


def test_health_service_degrades_on_latency_and_reject_pressure():
    snapshot = HealthService().evaluate(
        market_health=_market_health(),
        risk_mode="normal",
        reconciliation_ok=True,
        order_reject_burst=3,
        abnormal_latency_ms=1200.0,
        slippage_drift_bps=12.0,
    )

    assert snapshot.action == "degrade"
    assert "reject_burst" in snapshot.reasons
    assert "abnormal_latency" in snapshot.reasons
    assert "slippage_drift" in snapshot.reasons


def test_health_service_halts_and_flattens_on_compounded_failures():
    snapshot = HealthService().evaluate(
        market_health=_market_health(),
        risk_mode="defensive",
        reconciliation_ok=False,
        api_error_burst=5,
        order_reject_burst=5,
        abnormal_latency_ms=1500.0,
        slippage_drift_bps=25.0,
        unexplained_pnl_deviation_pct=1.5,
        anomaly_pressure=0.8,
    )

    assert snapshot.action == "halt_and_flatten"
    assert snapshot.health_score <= 0.2
    assert "reconciliation_bad" in snapshot.reasons
    assert "api_error_burst" in snapshot.reasons


def _truth_snapshot(level: TruthConfidenceLevel = TruthConfidenceLevel.AUTHORITATIVE) -> TruthConfidenceSnapshot:
    ts = datetime.now(timezone.utc)
    return TruthConfidenceSnapshot(
        ts=ts,
        fill_truth_confidence=TruthConfidence("fill_truth_confidence", level, "test"),
        fee_truth_confidence=TruthConfidence("fee_truth_confidence", level, "test"),
        realized_pnl_confidence=TruthConfidence("realized_pnl_confidence", level, "test"),
        balance_truth_confidence=TruthConfidence("balance_truth_confidence", level, "test"),
        exposure_truth_confidence=TruthConfidence("exposure_truth_confidence", level, "test"),
        market_data_truth_confidence=TruthConfidence("market_data_truth_confidence", level, "test"),
    )


def test_health_governor_caps_canary_live_size():
    svc = HealthService()
    snapshot = svc.evaluate(
        market_health=_market_health(),
        risk_mode="normal",
        reconciliation_ok=True,
    )

    decision = svc.govern(symbol="BTCUSDT", health_snapshot=snapshot, rollout_stage="canary_live")

    assert decision.action == "continue"
    assert decision.size_multiplier == 0.10


def test_health_governor_forces_flatten_only_on_truth_gap():
    svc = HealthService()
    snapshot = svc.evaluate(
        market_health=_market_health(),
        risk_mode="normal",
        reconciliation_ok=True,
    )

    decision = svc.govern(
        symbol="BTCUSDT",
        health_snapshot=snapshot,
        rollout_stage="normal_live",
        truth_confidence=_truth_snapshot(TruthConfidenceLevel.UNAVAILABLE),
    )

    assert decision.action == "force_flatten_only"
    assert decision.forced_risk_mode == "flatten-only"


def test_health_governor_respects_market_integrity_and_venue_limit_degradation():
    svc = HealthService()
    snapshot = svc.evaluate(
        market_health=_market_health(),
        risk_mode="normal",
        reconciliation_ok=True,
        market_integrity_status=MarketIntegrityStatus(
            symbol="BTCUSDT",
            provider_id="binance_um_perps",
            ts=datetime.now(timezone.utc),
            score=0.4,
            action="degrade",
            confidence="strong",
            reasons=["liquidity_too_thin"],
        ),
    )

    decision = svc.govern(
        symbol="BTCUSDT",
        health_snapshot=snapshot,
        rollout_stage="normal_live",
        market_integrity_status=MarketIntegrityStatus(
            symbol="BTCUSDT",
            provider_id="binance_um_perps",
            ts=datetime.now(timezone.utc),
            score=0.4,
            action="degrade",
            confidence="strong",
            reasons=["liquidity_too_thin"],
        ),
        venue_limit_decision=VenueLimitDecision(
            symbol="BTCUSDT",
            provider_id="binance_um_perps",
            ts=datetime.now(timezone.utc),
            action="degrade",
            size_multiplier=0.25,
            reasons=["user_stream_confidence_partial"],
        ),
    )

    assert decision.action == "force_degraded"
    assert decision.size_multiplier == 0.25
