from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MarketType(str, Enum):
    SPOT = "spot"
    MARGIN = "margin"
    PERP = "perp"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class IntentType(str, Enum):
    OPEN = "open"
    CLOSE = "close"
    HEDGE = "hedge"
    MAKER_PROBE = "maker_probe"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"


class TimeInForce(str, Enum):
    GTC = "gtc"
    IOC = "ioc"
    POST_ONLY = "post_only"


class OrderState(str, Enum):
    NEW = "new"
    ACK = "ack"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(slots=True)
class StrategyIntent:
    symbol: str
    market_type: MarketType
    side: Side
    intent_type: IntentType
    quantity: float
    price: float | None = None
    post_only: bool = True
    reduce_only: bool = False
    leverage: float = 1.0
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    market_type: MarketType
    side: Side
    quantity: float
    order_type: OrderType
    price: float | None
    post_only: bool
    reduce_only: bool
    leverage: float
    client_order_id: str
    tif: TimeInForce = TimeInForce.GTC
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrderRecord:
    client_order_id: str
    exchange_order_id: str | None
    symbol: str
    market_type: MarketType
    side: Side
    order_type: OrderType
    quantity: float
    price: float | None
    state: OrderState
    created_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FillRecord:
    client_order_id: str
    exchange_order_id: str | None
    symbol: str
    market_type: MarketType
    side: Side
    quantity: float
    price: float
    fee_quote: float
    fee_rate: float
    liquidity_role: str
    funding_quote: float = 0.0
    interest_quote: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class PositionLot:
    lot_id: str
    symbol: str
    market_type: MarketType
    position_side: PositionSide
    quantity_open: float
    entry_price: float
    entry_notional_quote: float
    open_fee_quote: float
    funding_quote: float = 0.0
    interest_quote: float = 0.0
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class PositionSnapshot:
    symbol: str
    market_type: MarketType
    long_qty: float = 0.0
    short_qty: float = 0.0
    avg_long_entry: float = 0.0
    avg_short_entry: float = 0.0
    realized_pnl_quote: float = 0.0
    unrealized_pnl_quote: float = 0.0


@dataclass(slots=True)
class ProfitGateDecision:
    allowed: bool
    reason: str
    required_price: float | None = None
    required_price_tick_adjusted: float | None = None
    effective_profit_target: float = 0.02
    expected_net_return: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MarketSnapshot:
    symbol: str
    bid: float
    ask: float
    mark: float | None = None
    index: float | None = None
    last: float | None = None
    bid_size: float = 0.0
    ask_size: float = 0.0
    funding_rate: float | None = None
    open_interest: float | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class DataHealth:
    healthy: bool
    reason: str
    stale_streams: list[str] = field(default_factory=list)
    last_update_by_stream: dict[str, datetime] = field(default_factory=dict)
