from datetime import datetime, timezone

from autonomous_investment_robot.core.contracts import CapabilityEvidence, MarketHealthSnapshot, MarketIntegrityEvidence, MarketSnapshot, ProviderCapabilityMatrix
from autonomous_investment_robot.services.health_service.service import HealthService
from autonomous_investment_robot.services.market_integrity_service.service import MarketIntegrityService
from autonomous_investment_robot.services.shared_venue_limit_governor.service import SharedVenueLimitGovernor
from autonomous_investment_robot.services.venue_capability_registry.service import VenueCapabilityRegistry


def _snapshot(*, spread_bps: float = 5.0, depth_notional: float = 1000.0) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        bid=100.0,
        ask=100.05,
        mid=100.025,
        spread_bps=spread_bps,
        depth_notional=depth_notional,
    )


def _market_health(
    *,
    feed_stale: bool = False,
    sequence_ok: bool = True,
    checksum_ok: bool = True,
    exchange_health_score: float = 0.95,
    market_quality_score: float = 0.90,
    reasons: list[str] | None = None,
) -> MarketHealthSnapshot:
    return MarketHealthSnapshot(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        feed_stale=feed_stale,
        sequence_ok=sequence_ok,
        checksum_ok=checksum_ok,
        symbol_health_score=0.95,
        exchange_health_score=exchange_health_score,
        market_quality_score=market_quality_score,
        reasons=[] if reasons is None else reasons,
    )


def _capability(*, user_stream_confidence: str = "user_stream_plus_rest_repair", lifecycle_completeness: str = "strong_without_replace") -> ProviderCapabilityMatrix:
    return ProviderCapabilityMatrix(
        provider_id="binance_um_perps",
        unrealized_pnl_truth_support="partial_when_field_absent",
        realized_pnl_truth_support="exchange_history_authoritative_when_available",
        lifecycle_completeness=lifecycle_completeness,
        replace_supported=False,
        expire_supported=True,
        fee_truth_confidence="exchange_history_authoritative_when_available",
        user_stream_confidence=user_stream_confidence,
    )


def test_market_integrity_service_degrades_on_thin_book():
    status = MarketIntegrityService().assess(
        symbol="BTCUSDT",
        provider_id="binance_um_perps",
        snapshot=_snapshot(depth_notional=25.0),
        market_health=_market_health(market_quality_score=0.35, reasons=["liquidity_too_thin"]),
        capability=_capability(),
    )

    assert status.action == "degrade"
    assert status.score < 0.5
    assert "liquidity_too_thin" in status.reasons


def test_market_integrity_service_flattens_when_feed_is_stale_and_user_stream_is_partial():
    status = MarketIntegrityService().assess(
        symbol="BTCUSDT",
        provider_id="kraken_derivatives",
        snapshot=_snapshot(),
        market_health=_market_health(feed_stale=True, exchange_health_score=0.5, reasons=["stale_feed"]),
        capability=_capability(user_stream_confidence="rest_history_only"),
    )

    assert status.action == "flatten_only"
    assert "capability_mismatch_under_exchange_stress" in status.reasons


def test_shared_venue_limit_governor_caps_size_and_escalates_on_capability_mismatch():
    integrity = MarketIntegrityService().assess(
        symbol="BTCUSDT",
        provider_id="kraken_derivatives",
        snapshot=_snapshot(),
        market_health=_market_health(feed_stale=True, exchange_health_score=0.5, reasons=["stale_feed"]),
        capability=_capability(user_stream_confidence="rest_history_only"),
    )

    decision = SharedVenueLimitGovernor().evaluate(
        symbol="BTCUSDT",
        provider_id="kraken_derivatives",
        market_integrity=integrity,
        capability=_capability(user_stream_confidence="rest_history_only"),
    )

    assert decision.action == "flatten_only"
    assert decision.reduce_only_only is True
    assert decision.size_multiplier == 0.0
    assert "capability_mismatch_under_stress" in decision.reasons


def test_health_service_governor_respects_venue_limit_flatten_only():
    health = HealthService()
    integrity = MarketIntegrityService().assess(
        symbol="BTCUSDT",
        provider_id="kraken_derivatives",
        snapshot=_snapshot(),
        market_health=_market_health(feed_stale=True, exchange_health_score=0.5, reasons=["stale_feed"]),
        capability=_capability(user_stream_confidence="rest_history_only"),
    )
    venue_limit = SharedVenueLimitGovernor().evaluate(
        symbol="BTCUSDT",
        provider_id="kraken_derivatives",
        market_integrity=integrity,
        capability=_capability(user_stream_confidence="rest_history_only"),
    )
    snapshot = health.evaluate(
        market_health=_market_health(),
        risk_mode="normal",
        reconciliation_ok=True,
        market_integrity_status=integrity,
    )

    decision = health.govern(
        symbol="BTCUSDT",
        health_snapshot=snapshot,
        rollout_stage="normal_live",
        market_integrity_status=integrity,
        venue_limit_decision=venue_limit,
    )

    assert decision.action == "force_flatten_only"
    assert decision.forced_risk_mode == "flatten-only"


def test_market_integrity_service_uses_dynamic_integrity_and_capability_evidence():
    now = datetime.now(timezone.utc)
    status = MarketIntegrityService().assess(
        symbol="BTCUSDT",
        provider_id="binance_um_perps",
        snapshot=_snapshot(),
        market_health=_market_health(),
        capability=_capability(),
        integrity_evidence=MarketIntegrityEvidence(
            symbol="BTCUSDT",
            provider_id="binance_um_perps",
            ts=now,
            feed_age_seconds=12.0,
            sequence_ok=False,
            checksum_ok=True,
            gap_count=2,
            checksum_mismatch_count=0,
            evidence_confidence="weak",
            reasons=["sequence_gap_evidence"],
            partial=True,
        ),
        capability_evidence=CapabilityEvidence(
            provider_id="binance_um_perps",
            ts=now,
            evidence_freshness_seconds=10.0,
            user_stream_connected=False,
            lifecycle_snapshot_count=0,
            sequence_ok=False,
            checksum_ok=True,
            reasons=["user_stream_not_connected", "lifecycle_snapshot_absent"],
            partial=True,
        ),
    )

    assert status.action == "flatten_only"
    assert status.confidence == "weak"
    assert "dynamic_sequence_gap" in status.reasons
    assert "capability_evidence_partial" in status.reasons


def test_market_integrity_service_uses_runtime_metadata_flags():
    now = datetime.now(timezone.utc)
    status = MarketIntegrityService().assess(
        symbol="BTCUSDT",
        provider_id="binance_um_perps",
        snapshot=_snapshot(),
        market_health=_market_health(),
        capability=_capability(),
        integrity_evidence=MarketIntegrityEvidence(
            symbol="BTCUSDT",
            provider_id="binance_um_perps",
            ts=now,
            feed_age_seconds=5.0,
            sequence_ok=True,
            checksum_ok=True,
            evidence_confidence="partial",
            partial=True,
            metadata={
                "public_market_data_connected": False,
                "book_repeat_count": 6,
                "seconds_since_distinct_book_change": 120.0,
            },
        ),
        capability_evidence=CapabilityEvidence(
            provider_id="binance_um_perps",
            ts=now,
            evidence_freshness_seconds=2.0,
            user_stream_connected=True,
            lifecycle_snapshot_count=1,
            sequence_ok=True,
            checksum_ok=True,
            partial=False,
            metadata={
                "private_api_healthy": False,
                "auth_validated": False,
                "has_credentials": True,
                "public_market_data_connected": False,
            },
        ),
    )

    assert status.action == "flatten_only"
    assert "public_market_data_unproven" in status.reasons
    assert "book_repeating_without_change" in status.reasons
    assert "book_change_stale" in status.reasons
    assert "private_api_health_degraded" in status.reasons
    assert "auth_validation_unproven" in status.reasons


def test_venue_capability_registry_prefers_dynamic_live_capability_evidence():
    now = datetime.now(timezone.utc)
    live = type(
        "FakeLive",
        (),
        {
            "user_stream_connected": True,
            "supports_replace": False,
            "supports_expire": True,
            "market_integrity_evidence": lambda self, now_dt=None: {"ts": now_dt or now, "sequence_ok": True, "checksum_ok": True},
            "lifecycle_snapshot": lambda self: [{"state": "working"}],
            "capability_evidence": lambda self, now_dt=None: {
                "ts": now_dt or now,
                "user_stream_connected": True,
                "lifecycle_snapshot_count": 1,
                "sequence_ok": True,
                "checksum_ok": True,
                "replace_support_evidence": "dynamic",
                "expire_support_evidence": "dynamic",
                "auth_validated": True,
                "private_api_healthy": True,
                "public_market_data_connected": True,
                "book_repeat_count": 0,
                "seconds_since_distinct_book_change": 1.0,
                "has_credentials": True,
            },
        },
    )()

    registry = VenueCapabilityRegistry()
    matrix = registry.resolve("binance_um_perps", live=live, connector=object(), now=now)
    evidence = registry.last_evidence("binance_um_perps")

    assert matrix.user_stream_confidence == "user_stream_plus_rest_repair"
    assert evidence is not None
    assert evidence.partial is False
    assert evidence.metadata["auth_validated"] is True
