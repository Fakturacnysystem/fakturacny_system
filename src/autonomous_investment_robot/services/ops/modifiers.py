from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DecisionModifiers:
    pause_buy: bool = False
    edge_add_bps: float = 0.0
    size_scale: float = 1.0
    maker_only: bool = False
    taker_allowed: bool = True
    max_child_orders_override: int | None = None
    reason_tags: list[str] = field(default_factory=list)

    def merge(self, other: "DecisionModifiers") -> "DecisionModifiers":
        self.pause_buy = self.pause_buy or other.pause_buy
        self.edge_add_bps = max(self.edge_add_bps, other.edge_add_bps)
        self.size_scale = max(0.05, min(1.0, self.size_scale * other.size_scale))
        self.maker_only = self.maker_only or other.maker_only
        self.taker_allowed = self.taker_allowed and other.taker_allowed
        if other.max_child_orders_override is not None:
            if self.max_child_orders_override is None:
                self.max_child_orders_override = other.max_child_orders_override
            else:
                self.max_child_orders_override = min(self.max_child_orders_override, other.max_child_orders_override)
        for tag in other.reason_tags:
            if tag not in self.reason_tags:
                self.reason_tags.append(tag)
        return self


def build_modifiers_pipeline(
    *,
    fatal_stop: bool,
    rate_limit_cooldown: bool,
    blackout_pause_buy: bool,
    spread_spike_active: bool,
    spread_spike_edge_add_bps: float,
    spread_spike_size_scale: float,
    liquidity_edge_add_bps: float,
    liquidity_size_scale: float,
    liquidity_child_orders: int | None,
    ws_unhealthy: bool,
    soft_pause_buy: bool,
) -> DecisionModifiers:
    m = DecisionModifiers()
    if fatal_stop:
        return DecisionModifiers(
            pause_buy=True,
            edge_add_bps=0.0,
            size_scale=0.05,
            maker_only=True,
            taker_allowed=False,
            reason_tags=["fatal_stop"],
        )
    if rate_limit_cooldown:
        m.merge(
            DecisionModifiers(
                pause_buy=True,
                maker_only=True,
                taker_allowed=False,
                size_scale=0.5,
                reason_tags=["rate_limit_cooldown"],
            )
        )
    if blackout_pause_buy:
        m.merge(DecisionModifiers(pause_buy=True, reason_tags=["blackout_pause_buy"]))
    if spread_spike_active:
        m.merge(
            DecisionModifiers(
                maker_only=True,
                taker_allowed=False,
                edge_add_bps=max(0.0, float(spread_spike_edge_add_bps)),
                size_scale=max(0.05, min(1.0, float(spread_spike_size_scale))),
                reason_tags=["spread_spike"],
            )
        )
    liquidity_edge = max(0.0, float(liquidity_edge_add_bps))
    liquidity_size = max(0.05, min(1.0, float(liquidity_size_scale)))
    liquidity_is_restrictive = (
        liquidity_edge > 0.0
        or liquidity_size < 0.999
        or liquidity_child_orders is not None
    )
    if liquidity_is_restrictive:
        m.merge(
            DecisionModifiers(
                edge_add_bps=liquidity_edge,
                size_scale=liquidity_size,
                max_child_orders_override=liquidity_child_orders,
                reason_tags=["liquidity_map"],
            )
        )
    if ws_unhealthy:
        m.merge(DecisionModifiers(pause_buy=True, maker_only=True, taker_allowed=False, reason_tags=["ws_unhealthy"]))
    if soft_pause_buy:
        m.merge(DecisionModifiers(pause_buy=True, reason_tags=["soft_pause_buy"]))
    return m
