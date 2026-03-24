from __future__ import annotations

from pathlib import Path

import pytest

from autonomous_investment_robot.config.settings import (
    DoctrineSettings,
    ExecutionSettings,
    HarmonySettings,
    LiveUnlockSettings,
    MarketWatchSettings,
    RiskLimits,
    RobotSettings,
    SafetySettings,
    StorageSettings,
    TCOSettings,
)
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotTradeRow
from autonomous_investment_robot.services.execution.live_kraken_spot_service import LiveKrakenSpotService
from autonomous_investment_robot.services.policy.service import OrderIntent


class FakeKrakenSpotConnector:
    def __init__(self) -> None:
        self.supports_live_trading = True
        self._has_credentials = True
        self.bid = 110.0
        self.ask = 110.1
        self.balance_total = 1.0
        self.balance_free = 1.0
        self.orders: dict[str, dict] = {}
        self.placed_payloads: list[dict] = []
        self.preview_ok = True
        self.trade_rows = [
            KrakenSpotTradeRow(
                trade_id="buy-1",
                order_id="buy-order-1",
                symbol="BTC/USD",
                side="buy",
                base_qty=1.0,
                quote_cost=100.0,
                fee_quote=0.0,
                price=100.0,
                timestamp_ms=1_700_000_000_000,
                raw={},
            )
        ]

    @property
    def has_credentials(self) -> bool:
        return self._has_credentials

    def verify_live_permissions(self):
        return True, "private_api_verified"

    def exchange_info(self):
        return {"symbols": [{"symbol": "BTC/USD", "active": True, "spot": True, "id": "XXBTZUSD"}]}

    def market_constraints(self, symbol):  # noqa: ARG002
        return {
            "symbol": "BTC/USD",
            "active": True,
            "spot": True,
            "min_order_size": 0.0001,
            "min_notional": 10.0,
            "quantity_step": 0.00000001,
            "price_tick": 0.1,
            "maker_assumption": "post_only_supported",
            "taker_assumption": "marketable_limit_or_market",
            "reduce_only_supported": False,
            "post_only_supported": True,
            "replace_supported": False,
            "expire_supported": True,
            "confidence": "exchange_market_metadata",
            "market_id": "XXBTZUSD",
            "base": "BTC",
            "quote": "USD",
        }

    def book_ticker(self, symbol):  # noqa: ARG002
        return {
            "symbol": "BTC/USD",
            "bidPrice": str(self.bid),
            "askPrice": str(self.ask),
            "bidQty": "2",
            "askQty": "2",
            "timestamp": 1_700_000_000_000,
        }

    def balances(self):
        return [
            {
                "asset": "BTC",
                "balance": str(self.balance_total),
                "availableBalance": str(self.balance_free),
                "usedBalance": str(max(0.0, self.balance_total - self.balance_free)),
                "equity": str(self.balance_total),
            }
        ]

    def base_balance(self, symbol):  # noqa: ARG002
        return {"total": self.balance_total, "free": self.balance_free, "used": max(0.0, self.balance_total - self.balance_free)}

    def trade_history(self, symbol, *, offset=0, limit=50):  # noqa: ARG002
        return list(self.trade_rows[offset : offset + limit])

    def normalize_amount(self, symbol, amount):  # noqa: ARG002
        return round(float(amount), 8)

    def normalize_price(self, symbol, price):  # noqa: ARG002
        return round(float(price), 8)

    def validate_order_preview(self, *, symbol, side, amount, price, post_only=False):  # noqa: ARG002
        return (True, "validated") if self.preview_ok else (False, "preview_failed")

    def query_order(self, symbol, client_order_id):  # noqa: ARG002
        return self.orders.get(client_order_id)

    def place_order(self, payload):
        self.placed_payloads.append(dict(payload))
        cid = str(payload["newClientOrderId"])
        side = str(payload["side"]).upper()
        qty = float(payload["quantity"])
        if side == "SELL":
            self.balance_total = max(0.0, self.balance_total - qty)
            self.balance_free = max(0.0, self.balance_free - qty)
        elif side == "BUY":
            self.balance_total += qty
            self.balance_free += qty
        order = {
            "clientOrderId": cid,
            "orderId": f"order-{len(self.orders) + 1}",
            "status": "FILLED",
            "symbol": str(payload["symbol"]),
            "side": side,
            "executedQty": payload["quantity"],
            "avgPrice": str(self.ask if side == "BUY" else self.bid),
            "filledNotional": str(float(payload["quantity"]) * (self.ask if side == "BUY" else self.bid)),
            "raw": {"order_id": f"order-{len(self.orders) + 1}"},
        }
        self.orders[cid] = order
        return order

    def cancel_order(self, symbol, client_order_id):  # noqa: ARG002
        order = self.orders[client_order_id]
        order["status"] = "CANCELED"
        return order

    def open_orders(self):
        return []

    def position_risk(self, symbol=None):  # noqa: ARG002
        return []


def _limits() -> RiskLimits:
    return RiskLimits(
        max_daily_loss_pct=1.0,
        max_weekly_loss_pct=2.0,
        max_drawdown_pct=2.0,
        max_position_notional=150.0,
        max_exposure_notional=150.0,
        max_symbol_exposure_notional=150.0,
        max_cluster_exposure_notional=150.0,
        max_orders_per_min=4,
        leverage=0,
        target_portfolio_vol=0.05,
        cvar_limit_pct=1.0,
        stress_loss_limit_pct=2.0,
        max_spread_bps=18.0,
        min_depth_notional=30000.0,
        stale_data_seconds=10.0,
        min_margin_buffer=2.0,
        max_funding_cost_per_day=0.0,
        max_oi_spike_pct=0.0,
        max_liquidation_spike=0.0,
        divergence_threshold_bps=10.0,
        crowding_score_kill=12.0,
    )


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, mode: str = "live", maker_timeout_s: int = 1) -> RobotSettings:
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    return RobotSettings(
        provider_whitelist=["kraken_spot"],
        canary_mode=True,
        execution=ExecutionSettings(mode=mode, provider_id="kraken_spot", maker_timeout_s=maker_timeout_s, fee_bps=30.0, slippage_bps=8.0),
        safety=SafetySettings(
            live_unlock=LiveUnlockSettings(
                enable_live_trading=True,
                ack_i_understand_risks=True,
                require_testnet_passed=False,
            )
        ),
        doctrine=DoctrineSettings(
            target_provider="kraken_spot",
            product_target="spot",
            long_only=True,
            never_open_new_short_exposure=True,
            minimum_sell_net_profit_bps=120.0,
            enforce_cost_basis_sell_block=True,
            enforce_net_profit_sell_block=True,
            block_non_reduce_only_sells=True,
        ),
        harmony=HarmonySettings(enabled=True, default_order_cadence_s=5.0),
        market_watch=MarketWatchSettings(enabled=True),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=60.0, max_impact_bps=25.0),
        storage=StorageSettings(run_dir=str(tmp_path / "spot_run")),
        universe=["BTC/USD"],
    )


def _sell_intent(target_notional: float, *, reduce_only: bool = True) -> OrderIntent:
    return OrderIntent(
        symbol="BTC/USD",
        side="sell",
        target_notional=target_notional,
        why={
            "reduce_only": reduce_only,
            "profitability": {"net_edge_bps": 250.0},
            "doctrine_target": {"provider": "kraken_spot", "product": "spot"},
            "market_watch": {"action": "continue"},
            "market_integrity": {"action": "continue"},
        },
    )


def _buy_intent(target_notional: float, *, order_style: str = "passive_limit") -> OrderIntent:
    return OrderIntent(
        symbol="BTC/USD",
        side="buy",
        target_notional=target_notional,
        why={
            "doctrine_target": {"provider": "kraken_spot", "product": "spot", "long_only": True},
            "market_watch": {"action": "continue"},
            "market_integrity": {"action": "continue"},
            "execution_plan": {"order_style": order_style},
        },
    )


def test_kraken_spot_preflight_passes_with_doctrine_safe_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=FakeKrakenSpotConnector())

    ok, reason = svc.preflight()

    assert ok is True
    assert reason == "ok"


def test_kraken_spot_execute_requires_successful_preflight(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=FakeKrakenSpotConnector())

    out = svc.execute_intent(_sell_intent(55.0))

    assert out.status == "killed"
    assert out.reason == "preflight_not_completed"


def test_kraken_spot_flatten_requires_successful_preflight(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=FakeKrakenSpotConnector())

    closed, reason = svc.flatten_all_positions()

    assert closed is False
    assert reason == "preflight_not_completed"


def test_kraken_spot_freeze_requires_successful_preflight(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=FakeKrakenSpotConnector())

    frozen, reason = svc.freeze_new_openings("operator_freeze")

    assert frozen is False
    assert reason == "preflight_not_completed"


def test_kraken_spot_execute_blocks_non_reduce_sell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=FakeKrakenSpotConnector())
    assert svc.preflight() == (True, "ok")

    out = svc.execute_intent(_sell_intent(55.0, reduce_only=False))

    assert out.status == "killed"
    assert out.reason == "long_only_non_reduce_sell_block"


def test_kraken_spot_execute_blocks_sell_below_cost_basis(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    fake.bid = 90.0
    fake.ask = 90.2
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)
    assert svc.preflight() == (True, "ok")

    out = svc.execute_intent(_sell_intent(45.0))

    assert out.status == "killed"
    assert out.reason.startswith("sell_below_cost_basis:")


def test_kraken_spot_execute_blocks_sell_below_net_profit_floor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    fake.bid = 101.0
    fake.ask = 101.2
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)
    assert svc.preflight() == (True, "ok")

    out = svc.execute_intent(_sell_intent(50.5))

    assert out.status == "killed"
    assert out.reason.startswith("sell_net_profit_floor_breach:")


def test_kraken_spot_execute_fails_closed_when_inventory_truth_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)
    assert svc.preflight() == (True, "ok")
    fake.balance_total = 1.2
    fake.balance_free = 1.2

    out = svc.execute_intent(_sell_intent(55.0))

    assert out.status == "killed"
    assert out.reason.startswith("inventory_truth_missing:")


def test_kraken_spot_execute_allows_reduce_only_profitable_sell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    fake.bid = 110.0
    fake.ask = 110.1
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)
    assert svc.preflight() == (True, "ok")

    out = svc.execute_intent(_sell_intent(55.0))

    assert out.status == "filled_maker"
    assert out.order is not None
    assert out.order["symbol"] == "BTC/USD"


def test_kraken_spot_supports_symbol_flatten_and_freeze_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)
    assert svc.preflight() == (True, "ok")

    frozen, freeze_reason = svc.freeze_new_openings("operator_freeze")
    closed, flat_reason = svc.flatten_symbol("BTC/USD", reason="operator_symbol_flatten")

    assert frozen is True
    assert freeze_reason == "operator_freeze"
    assert svc.flatten_only is True
    assert closed is True
    assert flat_reason == "flat"


def test_kraken_spot_execute_honors_marketable_limit_order_style(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)
    assert svc.preflight() == (True, "ok")

    out = svc.execute_intent(_buy_intent(55.0, order_style="marketable_limit"))

    assert out.status == "filled_marketable_limit"
    assert fake.placed_payloads
    assert fake.placed_payloads[0]["type"] == "LIMIT"
    assert fake.placed_payloads[0].get("postOnly", False) is False
    assert float(fake.placed_payloads[0]["price"]) == pytest.approx(fake.ask)


def test_kraken_spot_sell_timeout_uses_aggressive_limit_not_market_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class TimeoutKrakenSpotConnector(FakeKrakenSpotConnector):
        def place_order(self, payload):
            self.placed_payloads.append(dict(payload))
            cid = str(payload["newClientOrderId"])
            order = {
                "clientOrderId": cid,
                "orderId": f"order-{len(self.orders) + 1}",
                "status": "NEW",
                "symbol": str(payload["symbol"]),
                "side": str(payload["side"]),
                "executedQty": "0",
                "avgPrice": "0",
                "filledNotional": "0",
                "raw": {"order_id": f"order-{len(self.orders) + 1}"},
            }
            self.orders[cid] = order
            return order

    fake = TimeoutKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path, maker_timeout_s=0), run_id="r1", connector=fake)
    assert svc.preflight() == (True, "ok")

    out = svc.execute_intent(_sell_intent(55.0))

    assert out.status == "timeout"
    assert out.reason == "sell_marketable_limit_timeout"
    assert len(fake.placed_payloads) == 2
    assert fake.placed_payloads[0].get("postOnly", False) is True
    assert fake.placed_payloads[1]["type"] == "LIMIT"
    assert fake.placed_payloads[1].get("postOnly", False) is False
