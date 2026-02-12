from autonomous_investment_robot.connectors.base import ConnectorConfig


class BaseCexConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config

    def connect(self) -> None:
        return None

    def poll_fallback(self) -> list[dict]:
        return []

    def is_stale(self, now_ts: float, last_ts: float) -> bool:
        return (now_ts - last_ts) > self.config.stale_after_s


class BinanceConnector(BaseCexConnector):
    """Implements snapshot + buffered delta + sequence checks (skeleton)."""


class CoinbaseConnector(BaseCexConnector):
    """Advanced Trade WS market/user separation + REST book levels (skeleton)."""


class KrakenConnector(BaseCexConnector):
    """WS book channel with checksum/sequence checks (skeleton)."""


class OkxConnector(BaseCexConnector):
    """Public/private WS + subscription limits (skeleton)."""


class BybitConnector(BaseCexConnector):
    """Orderbook snapshot/delta rules with u/seq timestamps (skeleton)."""


class DeribitConnector(BaseCexConnector):
    """JSON-RPC WS/HTTPS/FIX test/prod environment support (skeleton)."""


class HyperliquidConnector(BaseCexConnector):
    """Mainnet/testnet WS with robust reconnect + snapshot refresh (skeleton)."""
