from __future__ import annotations

from dataclasses import dataclass

from autonomous_investment_robot.services.execution.live_kraken_router_service import LiveKrakenRouterService


@dataclass
class _Result:
    status: str
    reason: str = ""
    order: dict | None = None


class _FakeSpot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def preflight(self):
        return True, "spot_ok"

    def execute_intent(self, intent):
        self.calls.append(("execute_intent", intent.symbol))
        return _Result(status="spot_submitted", reason="spot")

    def execute_readonly(self, intent):
        return _Result(status="spot_readonly")

    def market_snapshot(self, symbol, max_age_s=None, force_refresh=False):  # noqa: ARG002
        return {"pair": symbol, "bid": 10.0, "ask": 10.2, "mid": 10.1, "ts": 1.0}

    def sync_fill_ledger(self, symbol, mark_price):  # noqa: ARG002
        return {"symbol": symbol, "position_qty": 0.0}

    def request_kill(self, reason="operator_kill"):  # noqa: ARG002
        return None

    def flatten_all_positions(self):
        return True, "spot_flat"

    def _available_quote_balance(self, symbol):  # noqa: ARG002
        return "USD", 100.0


class _FakePerp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def preflight(self):
        return True, "perp_ok"

    def execute_intent(self, intent):
        self.calls.append(("execute_intent", intent.symbol))
        return _Result(status="perp_submitted", reason="perp")

    def execute_readonly(self, intent):
        return _Result(status="perp_readonly")

    def market_snapshot(self, symbol, max_age_s=None, force_refresh=False):  # noqa: ARG002
        return {"pair": symbol, "bid": 100.0, "ask": 100.5, "mid": 100.25, "ts": 2.0}

    def sync_fill_ledger(self, symbol, mark_price):  # noqa: ARG002
        return {"symbol": symbol, "position_qty": 1.0}

    def request_kill(self, reason="operator_kill"):  # noqa: ARG002
        return None

    def flatten_all_positions(self):
        return False, "perp_blocked"

    def _available_quote_balance(self, symbol):  # noqa: ARG002
        return "USD", 50.0


class _Intent:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.side = "buy"
        self.target_notional = 10.0
        self.why = {}


def test_router_routes_perp_symbol_to_futures_service() -> None:
    spot = _FakeSpot()
    perp = _FakePerp()
    router = LiveKrakenRouterService(
        spot_service=spot,
        futures_service=perp,
        discovered_instruments=[
            {"symbol": "ETHEUR", "market_type": "spot", "market_class": "crypto_spot", "venue": "kraken"},
            {"symbol": "PI_XBTUSD", "market_type": "perp", "venue": "kraken_futures"},
        ],
    )

    out_spot = router.execute_intent(_Intent("ETHEUR"))
    out_perp = router.execute_intent(_Intent("PI_XBTUSD"))

    assert out_spot.status == "spot_submitted"
    assert out_perp.status == "perp_submitted"
    assert spot.calls == [("execute_intent", "ETHEUR")]
    assert perp.calls == [("execute_intent", "PI_XBTUSD")]
    assert router.venue_for_symbol("PI_XBTUSD") == "kraken_futures"
    assert router.market_type_for_symbol("PI_XBTUSD") == "perp"
    assert router.market_class_for_symbol("ETHEUR") == "crypto_spot"


def test_router_flatten_aggregates_subservice_results() -> None:
    router = LiveKrakenRouterService(
        spot_service=_FakeSpot(),
        futures_service=_FakePerp(),
        discovered_instruments=[{"symbol": "PI_XBTUSD", "market_type": "perp", "venue": "kraken_futures"}],
    )

    ok, reason = router.flatten_all_positions()
    assert ok is False
    assert "spot:spot_flat" in reason
    assert "perp:perp_blocked" in reason


def test_router_preflight_only_requires_configured_market_types() -> None:
    class _FailPerp(_FakePerp):
        def preflight(self):
            return False, "missing_futures_credentials"

    router_spot_only = LiveKrakenRouterService(
        spot_service=_FakeSpot(),
        futures_service=_FailPerp(),
        discovered_instruments=[{"symbol": "ETHEUR", "market_type": "spot", "venue": "kraken"}],
    )
    ok_spot, _ = router_spot_only.preflight()
    assert ok_spot is True

    router_with_perp = LiveKrakenRouterService(
        spot_service=_FakeSpot(),
        futures_service=_FailPerp(),
        discovered_instruments=[{"symbol": "PI_XBTUSD", "market_type": "perp", "venue": "kraken_futures"}],
    )
    ok_perp, reason_perp = router_with_perp.preflight()
    assert ok_perp is False
    assert reason_perp == "missing_futures_credentials"


def test_router_exposes_market_class_summary() -> None:
    router = LiveKrakenRouterService(
        spot_service=_FakeSpot(),
        futures_service=_FakePerp(),
        discovered_instruments=[
            {"symbol": "TSLAXUSD", "market_type": "spot", "market_class": "xstock", "venue": "kraken"},
            {"symbol": "SPYXUSD", "market_type": "spot", "market_class": "xstock_etf", "venue": "kraken"},
            {"symbol": "PI_XBTUSD", "market_type": "perp", "market_class": "crypto_perp", "venue": "kraken_futures"},
        ],
    )
    summary = router.market_classes_summary()
    assert summary.get("xstock", 0) == 1
    assert summary.get("xstock_etf", 0) == 1
    assert router.market_class_for_symbol("PI_XBTUSD") == "crypto_perp"
