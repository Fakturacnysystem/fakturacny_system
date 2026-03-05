from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class KrakenFixSettings:
    enabled: bool = False
    host: str = "fix.kraken.com"
    port: int = 0
    sender_comp_id: str = ""
    target_comp_id: str = ""
    username: str = ""
    password_env: str = "KRAKEN_FIX_PASSWORD"
    heartbeat_interval_s: int = 30


class KrakenFixAdapter:
    """Interface-complete FIX adapter stub.

    The project keeps this disabled by default. Implement transport/session details
    behind this interface when FIX access is enabled in production.
    """

    def __init__(self, settings: KrakenFixSettings | None = None) -> None:
        self.settings = settings or KrakenFixSettings()
        self.connected = False

    def connect(self) -> None:
        if not self.settings.enabled:
            raise RuntimeError("Kraken FIX adapter disabled (set enabled=true to activate implementation)")
        raise NotImplementedError("FIX transport/session is not implemented in this build")

    def disconnect(self) -> None:
        self.connected = False

    def send_new_order(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self.connected:
            raise RuntimeError("FIX not connected")
        raise NotImplementedError("send_new_order not implemented")

    def cancel_order(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self.connected:
            raise RuntimeError("FIX not connected")
        raise NotImplementedError("cancel_order not implemented")

    def replace_order(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self.connected:
            raise RuntimeError("FIX not connected")
        raise NotImplementedError("replace_order not implemented")

    def health(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.settings.enabled),
            "connected": bool(self.connected),
            "host": self.settings.host,
            "port": self.settings.port,
        }
