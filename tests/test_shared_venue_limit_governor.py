from datetime import datetime, timezone

from autonomous_investment_robot.core.contracts import MarketIntegrityStatus, ProviderCapabilityMatrix
from autonomous_investment_robot.services.shared_venue_limit_governor.service import SharedVenueLimitGovernor


def test_shared_venue_limit_governor_keeps_partial_capability_as_caution_not_degrade():
    decision = SharedVenueLimitGovernor().evaluate(
        symbol="BTC/USD",
        provider_id="kraken_spot",
        market_integrity=MarketIntegrityStatus(
            symbol="BTC/USD",
            provider_id="kraken_spot",
            ts=datetime.now(timezone.utc),
            score=0.92,
            action="continue",
            confidence="strong",
            reasons=[],
        ),
        capability=ProviderCapabilityMatrix(
            provider_id="kraken_spot",
            unrealized_pnl_truth_support="spot_fifo_cost_basis_plus_live_bid",
            realized_pnl_truth_support="spot_trade_history_fifo_authoritative_when_balances_match",
            lifecycle_completeness="partial_without_snapshot",
            replace_supported=False,
            expire_supported=True,
            fee_truth_confidence="spot_trade_history_authoritative",
            user_stream_confidence="rest_history_only",
        ),
    )

    assert decision.action == "continue"
    assert decision.size_multiplier == 0.50
    assert decision.metadata["promotion_blocked"] is True
    assert decision.metadata["execution_caution_only"] is True
    assert decision.metadata["classifications"]["promotion_blocker"] == [
        "user_stream_confidence_partial",
        "lifecycle_completeness_not_strong",
    ]


def test_shared_venue_limit_governor_flattens_when_partial_capability_meets_market_stress():
    decision = SharedVenueLimitGovernor().evaluate(
        symbol="BTC/USD",
        provider_id="kraken_spot",
        market_integrity=MarketIntegrityStatus(
            symbol="BTC/USD",
            provider_id="kraken_spot",
            ts=datetime.now(timezone.utc),
            score=0.45,
            action="continue",
            confidence="partial",
            reasons=["exchange_health_weak"],
        ),
        capability=ProviderCapabilityMatrix(
            provider_id="kraken_spot",
            unrealized_pnl_truth_support="spot_fifo_cost_basis_plus_live_bid",
            realized_pnl_truth_support="spot_trade_history_fifo_authoritative_when_balances_match",
            lifecycle_completeness="partial_without_snapshot",
            replace_supported=False,
            expire_supported=True,
            fee_truth_confidence="spot_trade_history_authoritative",
            user_stream_confidence="rest_history_only",
        ),
    )

    assert decision.action == "flatten_only"
    assert decision.size_multiplier == 0.0
    assert "capability_mismatch_under_stress" in decision.reasons
