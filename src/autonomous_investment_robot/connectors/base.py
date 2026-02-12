from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ConnectorConfig:
    name: str
    ws_url: str = "UNSPECIFIED"
    rest_url: str = "UNSPECIFIED"
    api_key_env: str = "UNSPECIFIED"
    reconnect_backoff_s: list[int] | None = None
    stale_after_s: int = 10


class MarketConnector(Protocol):
    config: ConnectorConfig

    def connect(self) -> None: ...

    def poll_fallback(self) -> list[dict]: ...

    def is_stale(self, now_ts: float, last_ts: float) -> bool: ...
