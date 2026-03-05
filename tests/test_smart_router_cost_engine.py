from autonomous_investment_robot.services.execution.cost_engine import CostEngineService
from autonomous_investment_robot.services.execution.smart_router import SmartOrderRouter, VenueCandidate


def test_smart_router_prefers_positive_net_route():
    router = SmartOrderRouter()
    decision = router.pick_route(
        side="buy",
        notional=500.0,
        expected_edge_bps=30.0,
        candidates=[
            VenueCandidate(
                venue="kraken_spot",
                bid=100.0,
                ask=100.2,
                depth_notional=200_000.0,
                fee_bps=12.0,
                latency_ms=40.0,
                stale_s=0.1,
                queue_ahead_notional=200.0,
                maker_rebate_bps=1.0,
            ),
            VenueCandidate(
                venue="binance_spot",
                bid=100.0,
                ask=100.3,
                depth_notional=150_000.0,
                fee_bps=14.0,
                latency_ms=120.0,
                stale_s=0.2,
                queue_ahead_notional=1200.0,
                maker_rebate_bps=0.0,
            ),
        ],
    )
    assert decision is not None
    assert decision.expected_net_edge_bps > 0.0
    assert decision.venue in {"kraken_spot", "binance_spot"}


def test_smart_router_returns_none_for_negative_edge():
    router = SmartOrderRouter()
    decision = router.pick_route(
        side="buy",
        notional=500.0,
        expected_edge_bps=0.2,
        candidates=[
            VenueCandidate(
                venue="kraken_spot",
                bid=100.0,
                ask=100.4,
                depth_notional=10_000.0,
                fee_bps=20.0,
                latency_ms=60.0,
                stale_s=0.2,
            )
        ],
    )
    assert decision is None


def test_cost_engine_and_slicing_outputs_are_reasonable():
    cost = CostEngineService()
    est = cost.estimate(
        notional=2000.0,
        depth_notional=100_000.0,
        spread_bps=4.0,
        fee_bps=10.0,
        slippage_bps=3.0,
        maker=True,
    )
    assert est.total_bps > 0.0
    ratio = cost.cost_to_alpha_ratio(alpha_bps=20.0, cost_bps=est.total_bps)
    assert ratio >= 0.0

    router = SmartOrderRouter()
    slices = router.plan_slices(target_notional=1000.0, depth_notional=50_000.0, max_child_orders=4, max_participation_rate=0.1)
    assert len(slices) <= 4
    assert abs(sum(slices) - 1000.0) < 1e-6
