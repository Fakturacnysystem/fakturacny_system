from autonomous_investment_robot.services.ops.modifiers import build_modifiers_pipeline


def test_liquidity_map_reason_not_added_when_neutral() -> None:
    m = build_modifiers_pipeline(
        fatal_stop=False,
        rate_limit_cooldown=False,
        blackout_pause_buy=False,
        spread_spike_active=False,
        spread_spike_edge_add_bps=0.0,
        spread_spike_size_scale=1.0,
        liquidity_edge_add_bps=0.0,
        liquidity_size_scale=1.0,
        liquidity_child_orders=None,
        ws_unhealthy=False,
        soft_pause_buy=True,
    )
    assert "liquidity_map" not in m.reason_tags
    assert "soft_pause_buy" in m.reason_tags


def test_liquidity_map_reason_added_when_restrictive() -> None:
    m = build_modifiers_pipeline(
        fatal_stop=False,
        rate_limit_cooldown=False,
        blackout_pause_buy=False,
        spread_spike_active=False,
        spread_spike_edge_add_bps=0.0,
        spread_spike_size_scale=1.0,
        liquidity_edge_add_bps=4.0,
        liquidity_size_scale=0.8,
        liquidity_child_orders=2,
        ws_unhealthy=False,
        soft_pause_buy=False,
    )
    assert "liquidity_map" in m.reason_tags
    assert m.edge_add_bps >= 4.0
    assert m.size_scale <= 0.8
    assert m.max_child_orders_override == 2
