from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("KrakenSpotConnector")


class KrakenSpotConnectorError(RuntimeError):
    pass


class KrakenSpotTradingBlocked(KrakenSpotConnectorError):
    pass


class KrakenSpotConnector:
    """
    Legacy side-channel helper kept only for readonly balance/dashboard access.

    Tracked launch-gated runtime does not implement Kraken SPOT trading. Any
    trading attempt through this connector must fail closed.
    """

    def __init__(
        self,
        *,
        api_key_env: str = "KRAKEN_SPOT_API_KEY",
        api_secret_env: str = "KRAKEN_SPOT_API_SECRET",
    ) -> None:
        api_key = os.getenv(api_key_env, "").strip() or os.getenv("KRAKEN_API_KEY", "").strip()
        api_secret = os.getenv(api_secret_env, "").strip() or os.getenv("KRAKEN_API_SECRET", "").strip()
        if not api_key or not api_secret:
            raise KrakenSpotConnectorError("missing_credentials")

        try:
            import ccxt  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional runtime package
            raise KrakenSpotConnectorError("ccxt_unavailable") from exc

        self.exchange = ccxt.kraken(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            }
        )

    def get_account_summary(self) -> tuple[float, float]:
        try:
            balance = self.exchange.fetch_balance()
            info = balance.get("info", {}) if isinstance(balance, dict) else {}
            equity = float(info.get("eb", 0.0))
            free_margin = float(info.get("mf", 0.0))
            return equity, free_margin
        except Exception as exc:
            logger.error("Kraken SPOT balance fetch failed: %s", exc)
            return 0.0, 0.0

    def execute_margin_order(self, symbol: str, side: str, amount_eur: float, leverage: float) -> Any:  # noqa: ARG002
        raise KrakenSpotTradingBlocked("kraken_spot_trading_unsupported_in_tracked_runtime")
