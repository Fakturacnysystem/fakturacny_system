from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from autonomous_investment_robot.config.settings import (
    DoctrineSettings,
    ExecutionSettings,
    KrakenSpotExecutionSettings,
    HarmonySettings,
    LiveUnlockSettings,
    MarketWatchSettings,
    RolloutStage,
    RiskLimits,
    RobotSettings,
    SafetySettings,
    StorageSettings,
    TCOSettings,
)
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotTradeRow
from autonomous_investment_robot.core.contracts import UnrealizedPnlTruth
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
        self.quote_total = 1000.0
        self.quote_free = 1000.0
        self.orders: dict[str, dict] = {}
        self.placed_payloads: list[dict] = []
        self.preview_ok = True
        self.place_error: Exception | None = None
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
            },
            {
                "asset": "USD",
                "balance": str(self.quote_total),
                "availableBalance": str(self.quote_free),
                "usedBalance": str(max(0.0, self.quote_total - self.quote_free)),
                "equity": str(self.quote_total),
            },
        ]

    def base_balance(self, symbol):  # noqa: ARG002
        return {"total": self.balance_total, "free": self.balance_free, "used": max(0.0, self.balance_total - self.balance_free)}

    def quote_balance(self, symbol):  # noqa: ARG002
        return {
            "asset": "USD",
            "total": self.quote_total,
            "free": self.quote_free,
            "used": max(0.0, self.quote_total - self.quote_free),
        }

    def trade_history(self, symbol, *, offset=0, limit=50):  # noqa: ARG002
        return list(self.trade_rows[offset : offset + limit])

    def trade_history_page(self, symbol, *, offset=0, limit=50):  # noqa: ARG002
        from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotTradeHistoryPage

        return KrakenSpotTradeHistoryPage(
            rows=list(self.trade_rows[offset : offset + limit]),
            fetched_count=max(0, min(limit, len(self.trade_rows) - offset)),
            total_count=len(self.trade_rows),
        )

    def symbol_from_market_id(self, market_id):  # noqa: ARG002
        return "BTC/USD"

    def normalize_amount(self, symbol, amount):  # noqa: ARG002
        return round(float(amount), 8)

    def normalize_price(self, symbol, price):  # noqa: ARG002
        return round(float(price), 8)

    def validate_order_preview(
        self,
        *,
        symbol,
        side,
        amount,
        price,
        post_only=False,
        client_order_id="",
        time_in_force="",
        expire_seconds=None,
    ):  # noqa: ARG002
        return (True, "validated") if self.preview_ok else (False, "preview_failed")

    def query_order(self, symbol, client_order_id):  # noqa: ARG002
        return self.orders.get(client_order_id)

    def place_order(self, payload):
        self.placed_payloads.append(dict(payload))
        if self.place_error is not None:
            raise self.place_error
        cid = str(payload["newClientOrderId"])
        side = str(payload["side"]).upper()
        qty = float(payload["quantity"])
        if side == "SELL":
            self.balance_total = max(0.0, self.balance_total - qty)
            self.balance_free = max(0.0, self.balance_free - qty)
            proceeds = qty * self.bid
            self.quote_total += proceeds
            self.quote_free += proceeds
        elif side == "BUY":
            cost = qty * float(payload.get("price", self.ask) or self.ask)
            self.quote_total = max(0.0, self.quote_total - cost)
            self.quote_free = max(0.0, self.quote_free - cost)
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

    def open_orders(self, symbol=None):  # noqa: ARG002
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


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    mode: str = "live",
    maker_timeout_s: int = 1,
    lifecycle_proof_enabled: bool = False,
    lifecycle_proof_timeout_s: int = 3,
    lifecycle_proof_max_notional: float = 12.0,
    lifecycle_proof_min_free_quote_reserve_pct: float | None = None,
) -> RobotSettings:
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    return RobotSettings(
        provider_whitelist=["kraken_spot"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode=mode,
            provider_id="kraken_spot",
            maker_timeout_s=maker_timeout_s,
            fee_bps=30.0,
            slippage_bps=8.0,
            kraken_spot=KrakenSpotExecutionSettings(
                lifecycle_proof_enabled=lifecycle_proof_enabled,
                lifecycle_proof_timeout_s=lifecycle_proof_timeout_s,
                lifecycle_proof_max_notional=lifecycle_proof_max_notional,
                lifecycle_proof_min_free_quote_reserve_pct=lifecycle_proof_min_free_quote_reserve_pct,
            ),
        ),
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


def _proof_buy_intent(target_notional: float) -> OrderIntent:
    return OrderIntent(
        symbol="BTC/USD",
        side="buy",
        target_notional=target_notional,
        why={
            "doctrine_target": {"provider": "kraken_spot", "product": "spot", "long_only": True},
            "market_watch": {"action": "continue"},
            "market_integrity": {"action": "continue"},
            "execution_plan": {"order_style": "passive_limit"},
            "lifecycle_proof": {
                "enabled": True,
                "mode": "tiny_live_bounded_lifecycle_proof",
                "proof_target_notional": target_notional,
            },
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


def test_kraken_spot_prepare_tiny_live_canary_uses_passive_gtd_preview(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    settings = _settings(monkeypatch, tmp_path)
    settings.canary_mode = False
    settings.rollout_stage_override = RolloutStage.TINY_LIVE.value
    svc = LiveKrakenSpotService(settings, run_id="r1", connector=fake)
    assert svc.preflight() == (True, "ok")

    plan = svc.prepare_tiny_live_canary(symbol="BTC/USD", passive_offset_bps=100.0, expiry_seconds=15)

    assert plan["ok"] is True
    assert plan["preview_ok"] is True
    assert plan["symbol"] == "BTC/USD"
    assert plan["side"] == "buy"
    assert plan["post_only"] is True
    assert plan["time_in_force"] == "GTD"
    assert plan["expiry_seconds"] == 15
    assert plan["price"] < fake.bid
    assert plan["qty"] * plan["price"] >= plan["min_notional"]
    assert str(plan["client_order_id"]).startswith("tlc")


def test_kraken_spot_submit_tiny_live_canary_submits_once_with_gtd_and_cancels_cleanup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class CanaryConnector(FakeKrakenSpotConnector):
        def __init__(self) -> None:
            super().__init__()
            self.query_counts: dict[str, int] = {}

        def place_order(self, payload):
            self.placed_payloads.append(dict(payload))
            cid = str(payload["newClientOrderId"])
            order = {
                "clientOrderId": cid,
                "orderId": f"order-{len(self.orders) + 1}",
                "status": "NEW",
                "symbol": str(payload["symbol"]),
                "side": str(payload["side"]).upper(),
                "executedQty": "0",
                "avgPrice": "0",
                "filledNotional": "0",
                "raw": {"order_id": f"order-{len(self.orders) + 1}"},
            }
            self.orders[cid] = order
            return dict(order)

        def query_order(self, symbol, client_order_id):  # noqa: ARG002
            order = dict(self.orders.get(client_order_id, {}))
            count = self.query_counts.get(client_order_id, 0) + 1
            self.query_counts[client_order_id] = count
            if count >= 2 and order:
                order["status"] = "CANCELED"
                self.orders[client_order_id] = dict(order)
            return order or None

    fake = CanaryConnector()
    settings = _settings(monkeypatch, tmp_path)
    settings.canary_mode = False
    settings.rollout_stage_override = RolloutStage.TINY_LIVE.value
    svc = LiveKrakenSpotService(settings, run_id="r1", connector=fake)
    assert svc.preflight() == (True, "ok")
    plan = svc.prepare_tiny_live_canary(symbol="BTC/USD", passive_offset_bps=100.0, expiry_seconds=1)

    result = svc.submit_tiny_live_canary(plan)

    assert result.status == "submitted"
    assert result.order is not None
    assert result.order["clientOrderId"] == plan["client_order_id"]
    assert fake.placed_payloads[0]["postOnly"] is True
    assert fake.placed_payloads[0]["timeInForce"] == "GTD"
    assert fake.placed_payloads[0]["expireSeconds"] == 1
    snapshot = svc.lifecycle_snapshot()
    states = {str(item.get("state", "")).lower() for item in snapshot if isinstance(item, dict)}
    assert "cancelled" in states or "canceled" in states


def test_authoritative_inventory_state_uses_local_user_stream_fast_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FastPathConnector(FakeKrakenSpotConnector):
        def trade_history_page(self, symbol, *, offset=0, limit=50):  # noqa: ARG002
            raise AssertionError("exchange_trade_history_should_not_be_used")

    fake = FastPathConnector()
    fake.trade_rows = []
    fake.balance_total = 0.00018
    fake.balance_free = 0.00018
    settings = _settings(monkeypatch, tmp_path)
    svc = LiveKrakenSpotService(settings, run_id="r1", connector=fake)
    local_rows = [
        KrakenSpotTradeRow(
            trade_id="local-buy-1",
            order_id="local-order-1",
            symbol="BTC/USD",
            side="buy",
            base_qty=0.00018,
            quote_cost=10.0,
            fee_quote=0.0,
            price=55555.55,
            timestamp_ms=1_700_000_000_000,
            raw={"source": "kraken_private_ws_ownTrades"},
        )
    ]
    monkeypatch.setattr(svc, "_local_user_stream_trade_rows", lambda symbol: list(local_rows))

    state = svc._authoritative_inventory_state("BTC/USD")

    assert state["ok"] is True
    assert state["reason"] == "local_user_stream_inventory_truth"
    assert state["history_source"] == "kraken_private_ws_ownTrades"
    assert state["balance_total_qty"] == pytest.approx(0.00018)


def test_authoritative_inventory_state_uses_local_conservative_fallback_before_exchange_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FastPathConnector(FakeKrakenSpotConnector):
        def trade_history_page(self, symbol, *, offset=0, limit=50):  # noqa: ARG002
            raise AssertionError("exchange_trade_history_should_not_be_used")

    fake = FastPathConnector()
    fake.trade_rows = []
    fake.balance_total = 0.00017936
    fake.balance_free = 0.00017936
    settings = _settings(monkeypatch, tmp_path)
    svc = LiveKrakenSpotService(settings, run_id="r1", connector=fake)
    local_rows = [
        KrakenSpotTradeRow(
            trade_id="buy-1",
            order_id="order-1",
            symbol="BTC/USD",
            side="buy",
            base_qty=0.00030,
            quote_cost=15.0,
            fee_quote=0.0,
            price=50000.0,
            timestamp_ms=1_700_000_000_000,
            raw={"source": "kraken_private_ws_ownTrades"},
        ),
        KrakenSpotTradeRow(
            trade_id="sell-1",
            order_id="order-2",
            symbol="BTC/USD",
            side="sell",
            base_qty=0.00040,
            quote_cost=20.0,
            fee_quote=0.0,
            price=50000.0,
            timestamp_ms=1_700_000_000_100,
            raw={"source": "kraken_private_ws_ownTrades"},
        ),
    ]
    monkeypatch.setattr(svc, "_local_user_stream_trade_rows", lambda symbol: list(local_rows))

    state = svc._authoritative_inventory_state("BTC/USD")

    assert state["ok"] is True
    assert state["reason"] == "conservative_buy_basis_fallback"
    assert state["history_source"] == "kraken_private_ws_ownTrades"
    assert state["basis_conservative"] is True
    assert state["balance_total_qty"] == pytest.approx(0.00017936)


def test_authoritative_fill_history_prefers_local_user_stream_when_since_ms_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FastPathConnector(FakeKrakenSpotConnector):
        def trade_history_page(self, symbol, *, offset=0, limit=50):  # noqa: ARG002
            raise AssertionError("exchange_trade_history_should_not_be_used")

    fake = FastPathConnector()
    fake.trade_rows = []
    settings = _settings(monkeypatch, tmp_path)
    svc = LiveKrakenSpotService(settings, run_id="r1", connector=fake)
    local_rows = [
        KrakenSpotTradeRow(
            trade_id="local-buy-1",
            order_id="local-order-1",
            symbol="BTC/USD",
            side="buy",
            base_qty=0.00018,
            quote_cost=10.0,
            fee_quote=0.0,
            price=55555.55,
            timestamp_ms=1_700_000_000_000,
            raw={"source": "kraken_private_ws_ownTrades"},
        )
    ]
    monkeypatch.setattr(svc, "_local_user_stream_trade_rows", lambda symbol: list(local_rows))

    records, gaps = svc.authoritative_fill_history("BTC/USD", side="buy", since_ms=1_699_999_999_000)

    assert gaps == []
    assert len(records) == 1
    assert records[0].fill.fill_id == "local-buy-1"


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


def test_kraken_spot_flat_account_reports_authoritative_zero_unrealized_even_with_broken_history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    fake.balance_total = 0.0
    fake.balance_free = 0.0
    fake.trade_rows = [
        KrakenSpotTradeRow(
            trade_id="sell-1",
            order_id="sell-order-1",
            symbol="BTC/USD",
            side="sell",
            base_qty=1.0,
            quote_cost=110.0,
            fee_quote=0.1,
            price=110.0,
            timestamp_ms=1_700_000_000_100,
            raw={},
        )
    ]
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)

    truth, gaps = svc.authoritative_unrealized_pnl("BTC/USD")

    assert gaps == []
    assert truth is not None
    assert isinstance(truth, UnrealizedPnlTruth)
    assert truth.source == "spot_balance_flat"
    assert truth.confidence == "authoritative"
    assert truth.venue_value == pytest.approx(0.0)
    assert truth.reason == "no_open_spot_inventory"


def test_kraken_spot_buy_fill_history_does_not_depend_on_sell_side_fifo_reconstruction(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    fake.trade_rows = [
        KrakenSpotTradeRow(
            trade_id="buy-1",
            order_id="buy-order-1",
            symbol="BTC/USD",
            side="buy",
            base_qty=0.5,
            quote_cost=50.0,
            fee_quote=0.05,
            price=100.0,
            timestamp_ms=1_700_000_000_000,
            raw={},
        ),
        KrakenSpotTradeRow(
            trade_id="sell-1",
            order_id="sell-order-1",
            symbol="BTC/USD",
            side="sell",
            base_qty=1.0,
            quote_cost=110.0,
            fee_quote=0.1,
            price=110.0,
            timestamp_ms=1_700_000_000_100,
            raw={},
        ),
    ]
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)

    records, gaps = svc.authoritative_fill_history("BTC/USD", side="buy", since_ms=1_700_000_000_000)

    assert gaps == []
    assert len(records) == 1
    assert records[0].fill.fill_id == "buy-1"
    assert records[0].fill.side == "buy"


def test_kraken_spot_buy_fill_history_returns_empty_without_gap_for_empty_window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)

    records, gaps = svc.authoritative_fill_history("BTC/USD", side="buy", since_ms=1_800_000_000_000)

    assert records == []
    assert gaps == []


def test_kraken_spot_sparse_trade_history_paginates_by_raw_page_size(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class SparsePagedConnector(FakeKrakenSpotConnector):
        def __init__(self) -> None:
            super().__init__()
            self.balance_total = 0.4
            self.balance_free = 0.4

        def trade_history(self, symbol, *, offset=0, limit=50):  # noqa: ARG002
            raise AssertionError("trade_history should not be used when trade_history_page is available")

        def trade_history_page(self, symbol, *, offset=0, limit=50):  # noqa: ARG002
            from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotTradeHistoryPage

            if offset == 0:
                return KrakenSpotTradeHistoryPage(
                    rows=[
                        KrakenSpotTradeRow(
                            trade_id="sell-1",
                            order_id="sell-order-1",
                            symbol="BTC/USD",
                            side="sell",
                            base_qty=0.2,
                            quote_cost=24.0,
                            fee_quote=0.1,
                            price=120.0,
                            timestamp_ms=1_700_000_000_100,
                            raw={},
                        )
                    ],
                    fetched_count=50,
                    total_count=100,
                )
            if offset == 50:
                return KrakenSpotTradeHistoryPage(
                    rows=[
                        KrakenSpotTradeRow(
                            trade_id="buy-1",
                            order_id="buy-order-1",
                            symbol="BTC/USD",
                            side="buy",
                            base_qty=0.6,
                            quote_cost=60.0,
                            fee_quote=0.2,
                            price=100.0,
                            timestamp_ms=1_700_000_000_000,
                            raw={},
                        )
                    ],
                    fetched_count=20,
                    total_count=100,
                )
            return KrakenSpotTradeHistoryPage(rows=[], fetched_count=0, total_count=100)

    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=SparsePagedConnector())

    inventory = svc._authoritative_inventory_state("BTC/USD")  # type: ignore[attr-defined]

    assert inventory["ok"] is True
    assert inventory["remaining_qty"] == pytest.approx(0.4)


def test_kraken_spot_inventory_truth_merges_current_run_own_trade_rows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    fake.balance_total = 0.0001782
    fake.balance_free = 0.0001782
    fake.trade_rows = []
    fake.symbol_from_market_id = lambda market_id: "XBT/USD"  # type: ignore[attr-defined]
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)
    svc._runtime_event_store.append(  # type: ignore[attr-defined]
        "user_stream",
        {
            "type": "message",
            "payload": [
                {
                    "TCBFUM-N5AZB-3NUXHW": {
                        "ordertxid": "OLTL46-BDPDW-SGE72N",
                        "pair": "XBT/USD",
                        "type": "buy",
                        "vol": "0.00017820",
                        "cost": "11.99963",
                        "fee": "0.03000",
                        "price": "67337.99",
                        "time": 1_775_344_927.335805,
                    }
                },
                "ownTrades",
                {"sequence": 7, "channelName": "ownTrades"},
            ],
        },
    )

    inventory = svc._authoritative_inventory_state("BTC/USD")  # type: ignore[attr-defined]

    assert inventory["ok"] is True
    assert inventory["remaining_qty"] == pytest.approx(0.0001782)
    assert inventory["avg_cost_quote"] == pytest.approx((11.99963 + 0.03) / 0.0001782)


def test_kraken_spot_inventory_truth_uses_conservative_buy_basis_fallback_when_fifo_window_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeKrakenSpotConnector()
    fake.balance_total = 0.2
    fake.balance_free = 0.2
    fake.trade_rows = [
        KrakenSpotTradeRow(
            trade_id="sell-1",
            order_id="sell-order-1",
            symbol="BTC/USD",
            side="sell",
            base_qty=0.4,
            quote_cost=44.0,
            fee_quote=0.1,
            price=110.0,
            timestamp_ms=1_700_000_000_100,
            raw={},
        ),
        KrakenSpotTradeRow(
            trade_id="buy-1",
            order_id="buy-order-1",
            symbol="BTC/USD",
            side="buy",
            base_qty=0.1,
            quote_cost=10.0,
            fee_quote=0.01,
            price=100.0,
            timestamp_ms=1_700_000_000_200,
            raw={},
        ),
        KrakenSpotTradeRow(
            trade_id="buy-2",
            order_id="buy-order-2",
            symbol="BTC/USD",
            side="buy",
            base_qty=0.2,
            quote_cost=24.0,
            fee_quote=0.02,
            price=120.0,
            timestamp_ms=1_700_000_000_300,
            raw={},
        ),
    ]
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)

    inventory = svc._authoritative_inventory_state("BTC/USD")  # type: ignore[attr-defined]

    assert inventory["ok"] is True
    assert inventory["reason"] == "conservative_buy_basis_fallback"
    assert inventory["basis_conservative"] is True
    assert inventory["remaining_qty"] == pytest.approx(0.2)
    assert inventory["avg_cost_quote"] == pytest.approx((24.0 + 0.02) / 0.2)


def test_kraken_spot_capability_evidence_treats_missing_book_timestamp_as_connected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)

    svc.capture_market_integrity_evidence(
        {"bidPrice": "100", "askPrice": "101", "bidQty": "1", "askQty": "1", "timestamp": None},
        datetime.now(timezone.utc),
    )
    payload = svc.capability_evidence(now_dt=datetime.now(timezone.utc))

    assert payload["public_market_data_connected"] is True
    assert isinstance(payload["ts"], str)


def test_kraken_spot_user_stream_seeded_capability_evidence_drops_stale_snapshot_absent_reason(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)

    svc._handle_user_stream_state_change(  # type: ignore[attr-defined]
        {
            "connected": True,
            "open_orders_seeded": True,
            "own_trades_seeded": False,
            "subscribed_channels": ["openOrders", "ownTrades"],
        }
    )
    payload = svc.capability_evidence(now_dt=datetime.now(timezone.utc))

    assert payload["user_stream_connected"] is True
    assert payload["lifecycle_snapshot_seeded"] is True
    assert "user_stream_not_connected" not in payload["reasons"]
    assert "lifecycle_snapshot_absent" not in payload["reasons"]
    assert "lifecycle_proof_incomplete" in payload["classifications"]["promotion_blocker"]


def test_kraken_spot_user_stream_queue_updates_lifecycle_mirror(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)

    svc._queue_user_stream_order_update(  # type: ignore[attr-defined]
        {
            "clientOrderId": "cid-1",
            "orderId": "oid-1",
            "status": "NEW",
            "symbol": "BTC/USD",
            "raw": {"source": "kraken_private_ws_openOrders", "userref": "123"},
        }
    )
    snapshot = svc.lifecycle_snapshot()
    transitions = svc.drain_lifecycle_transitions()

    assert snapshot
    assert snapshot[0]["state"] == "accepted"
    assert transitions
    assert transitions[0]["source"] == "exchange_order_update"


def test_kraken_spot_rehydrate_state_replays_lifecycle_transition_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)

    result = svc.rehydrate_state(
        [
            {
                "event_type": "ORDER_LIFECYCLE_TRANSITION",
                "payload": {
                    "symbol": "BTC/USD",
                    "order_key": "cid-1",
                    "to_state": "timed_out",
                    "source": "local_timeout",
                    "ts": "2026-04-04T22:00:00+00:00",
                    "metadata": {"raw": {"orderId": "ord-1", "clientOrderId": "cid-1"}},
                },
            }
        ],
        [],
    )

    assert result["orders"] == 0
    assert result["lifecycle_transitions"] == 1
    snapshot = svc.lifecycle_snapshot()
    assert snapshot
    assert snapshot[0]["state"] == "timed_out"
    assert snapshot[0]["order_id"] == "ord-1"


def test_kraken_spot_rehydrate_state_promotes_timed_out_lifecycle_to_filled_when_fill_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)

    result = svc.rehydrate_state(
        [
            {
                "event_type": "ORDER_LIFECYCLE_TRANSITION",
                "payload": {
                    "symbol": "BTC/USD",
                    "order_key": "cid-1",
                    "to_state": "timed_out",
                    "source": "local_timeout",
                    "ts": "2026-04-04T22:00:00+00:00",
                    "metadata": {"raw": {"orderId": "ord-1", "clientOrderId": "cid-1"}},
                },
            }
        ],
        [
            {
                "event_type": "FILL_REHYDRATED_FROM_EXCHANGE",
                "payload": {
                    "fill_id": "fill-1",
                    "order_id": "ord-1",
                    "clientOrderId": "cid-1",
                    "symbol": "BTC/USD",
                    "filledNotional": 11.99933,
                    "notional": 11.99933,
                },
            }
        ],
    )

    assert result["fills"] == 1
    snapshot = svc.lifecycle_snapshot()
    assert snapshot
    assert snapshot[0]["state"] == "filled"
    assert snapshot[0]["order_id"] == "ord-1"


def test_kraken_spot_prepare_tiny_live_canary_uses_min_order_size_when_min_notional_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeKrakenSpotConnector()
    fake.quote_total = 50.0
    fake.quote_free = 50.0

    original_constraints = fake.market_constraints

    def constraints_without_cost_floor(symbol):  # noqa: ARG001
        payload = dict(original_constraints(symbol))
        payload["min_notional"] = 0.0
        payload["min_order_size"] = 0.0001
        return payload

    fake.market_constraints = constraints_without_cost_floor  # type: ignore[method-assign]
    settings = _settings(monkeypatch, tmp_path)
    settings.rollout_stage_override = RolloutStage.TINY_LIVE.value
    svc = LiveKrakenSpotService(settings, run_id="r1", connector=fake)
    assert svc.preflight() == (True, "ok")

    plan = svc.prepare_tiny_live_canary(symbol="BTC/USD", passive_offset_bps=100.0, expiry_seconds=15)

    assert plan["ok"] is True
    assert float(plan["qty"]) >= 0.0001
    assert float(plan["validation_target_notional"]) > 0.0


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


def test_kraken_spot_lifecycle_proof_mode_stays_post_only_and_bounded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    svc = LiveKrakenSpotService(
        _settings(
            monkeypatch,
            tmp_path,
            lifecycle_proof_enabled=True,
            lifecycle_proof_timeout_s=0,
        ),
        run_id="r1",
        connector=fake,
    )
    assert svc.preflight() == (True, "ok")

    out = svc.execute_intent(_proof_buy_intent(12.0))

    assert out.status == "timeout"
    assert out.reason == "lifecycle_proof_timeout"
    assert len(fake.placed_payloads) == 1
    assert fake.placed_payloads[0]["type"] == "LIMIT"
    assert fake.placed_payloads[0].get("postOnly", False) is True
    assert out.metadata["lifecycle_proof"]["requested"] is True
    assert out.metadata["lifecycle_proof"]["terminal_observed"] is True


def test_kraken_spot_capability_evidence_requires_reconciliation_for_full_lifecycle_proof(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(
        _settings(monkeypatch, tmp_path, lifecycle_proof_enabled=True),
        run_id="r1",
        connector=fake,
    )
    assert svc.preflight() == (True, "ok")

    out = svc.execute_intent(_proof_buy_intent(12.0))
    assert out.status == "filled_maker"

    evidence_before = svc.capability_evidence(now_dt=datetime.now(timezone.utc))
    assert evidence_before["rest_lifecycle_proven"] is False

    summary = svc.record_lifecycle_reconciliation(
        result_status=out.status,
        fill_truth_ok=True,
        gap_reasons=[],
    )
    evidence_after = svc.capability_evidence(now_dt=datetime.now(timezone.utc))

    assert summary["reconciliation_complete"] is True
    assert summary["upgrade_eligible"] is True
    assert evidence_after["rest_lifecycle_proven"] is True
    assert evidence_after["lifecycle_reconciliation_complete"] is True


def test_kraken_spot_buy_blocks_when_quote_free_balance_cannot_cover_reserve(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    fake.quote_total = 20.0
    fake.quote_free = 15.9
    svc = LiveKrakenSpotService(_settings(monkeypatch, tmp_path), run_id="r1", connector=fake)
    assert svc.preflight() == (True, "ok")

    out = svc.execute_intent(_buy_intent(12.0))

    assert out.status == "blocked"
    assert out.reason == "insufficient_free_quote_after_reserve"
    assert fake.placed_payloads == []
    blocker = out.metadata["execution_blocker"]
    assert blocker["source"] == "local_affordability_guard"
    assert blocker["quote_asset"] == "USD"
    assert blocker["free_quote_balance"] == pytest.approx(15.9)
    assert blocker["required_quote"] > 0.0
    assert blocker["reserve_floor_quote"] == pytest.approx(4.0)
    assert blocker["reserve_policy_source"] == "policy_default"
    assert blocker["configured_minimum_reserve_pct"] == pytest.approx(0.2)
    assert blocker["applied_minimum_reserve_pct"] == pytest.approx(0.2)


def test_kraken_spot_lifecycle_proof_can_override_quote_reserve_for_tiny_live(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    fake.quote_total = 20.0
    fake.quote_free = 19.0086
    svc = LiveKrakenSpotService(
        _settings(
            monkeypatch,
            tmp_path,
            lifecycle_proof_enabled=True,
            lifecycle_proof_min_free_quote_reserve_pct=0.0,
        ),
        run_id="r1",
        connector=fake,
    )
    assert svc.preflight() == (True, "ok")

    out = svc.execute_intent(_proof_buy_intent(12.0))

    assert out.status == "filled_maker"
    assert len(fake.placed_payloads) == 1
    assert out.metadata["lifecycle_proof"]["requested"] is True
    assert out.metadata["lifecycle_proof"]["exchange_acknowledged"] is True


def test_kraken_spot_submit_reject_marks_lifecycle_terminal_without_exchange_ack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeKrakenSpotConnector()
    fake.place_error = RuntimeError('kraken {"error":["EOrder:Insufficient funds"]}')
    svc = LiveKrakenSpotService(
        _settings(monkeypatch, tmp_path, lifecycle_proof_enabled=True),
        run_id="r1",
        connector=fake,
    )
    assert svc.preflight() == (True, "ok")

    out = svc.execute_intent(_proof_buy_intent(12.0))

    assert out.status == "rejected"
    assert out.reason.startswith('maker_reject:kraken {"error":["EOrder:Insufficient funds"]}')
    proof = out.metadata["lifecycle_proof"]
    assert proof["submitted"] is True
    assert proof["exchange_acknowledged"] is False
    assert proof["terminal_observed"] is True
    assert proof["last_terminal_state"] == "REJECTED"
    assert proof["submit_source"] == "local_submit"
    assert proof["reject_source"] == "exchange_submit_exception"
    blocker = out.metadata["execution_blocker"]
    assert blocker["source"] == "exchange_submit_exception"
