import os

import pytest

from autonomous_investment_robot.config.settings import (
    BinanceExecutionSettings,
    ExecutionSettings,
    LiveUnlockSettings,
    RiskLimits,
    RobotSettings,
    SafetySettings,
    TCOSettings,
)
from autonomous_investment_robot.services.execution.live_binance_service import LiveBinanceService
from autonomous_investment_robot.services.policy.service import OrderIntent


class FakeConnector:
    def __init__(self):
        self.orders = {}
        self.place_calls = 0
        self.cancel_calls = 0
        self.fail_place = False
        self.fail_with_rate_limit = False
        self.next_order_status = "NEW"
        self.positions = []
        self._open_orders = []

    @property
    def has_credentials(self):
        return True

    def verify_live_permissions(self):
        return True, "ok"

    def exchange_info(self):
        return {"symbols": [{"symbol": "BTCUSDT"}]}

    def set_leverage(self, symbol, leverage):
        return {"symbol": symbol, "leverage": leverage}

    def book_ticker(self, symbol):
        return {"bidPrice": "100.0", "askPrice": "100.1", "bidQty": "10", "askQty": "10"}

    def query_order(self, symbol, client_order_id):
        if client_order_id in self.orders:
            return self.orders[client_order_id]
        raise RuntimeError("not found")

    def place_order(self, params):
        self.place_calls += 1
        if self.fail_with_rate_limit:
            raise RuntimeError("429 Too many requests")
        if self.fail_place:
            raise RuntimeError("reject")
        cid = params["newClientOrderId"]
        if params.get("type") == "MARKET":
            order = {"clientOrderId": cid, "status": "FILLED"}
        else:
            order = {"clientOrderId": cid, "status": self.next_order_status}
        self.orders[cid] = order
        return order

    def cancel_order(self, symbol, client_order_id):
        self.cancel_calls += 1
        return {"status": "CANCELED"}

    def open_orders(self, symbol=None):  # noqa: ARG002
        return list(self._open_orders)

    def position_risk(self, symbol=None):
        return self.positions

    def balances(self):
        return [{"asset": "USDT", "walletBalance": "100.0", "availableBalance": "100.0"}]

    def user_trades(self, symbol, order_id=None, start_time=None, limit=1000, **kwargs):  # noqa: ARG002
        rows = []
        for order in self.orders.values():
            if not isinstance(order, dict):
                continue
            if str(order.get("status", "")).upper() != "FILLED":
                continue
            current_order_id = str(order.get("orderId", "order-1"))
            if order_id is not None and current_order_id != str(order_id):
                continue
            rows.append(
                {
                    "id": f"trade-{current_order_id}",
                    "orderId": current_order_id,
                    "symbol": symbol,
                    "side": str(order.get("side", "BUY")).upper(),
                    "price": str(order.get("avgPrice", "100.0")),
                    "qty": str(order.get("executedQty", "0.1")),
                    "quoteQty": str(order.get("cumQuote", "10.0")),
                    "commission": str(order.get("commission", "0.02")),
                    "realizedPnl": str(order.get("realizedPnl", "1.5")),
                    "time": 1700000000000,
                }
            )
        return rows[:limit]

    def income_history(self, symbol=None, income_type=None, start_time=None, limit=1000, **kwargs):  # noqa: ARG002
        if income_type == "REALIZED_PNL":
            return [{"symbol": symbol or "BTCUSDT", "incomeType": "REALIZED_PNL", "income": "1.5"}][:limit]
        return []


def _settings(mode="live_testnet"):
    return RobotSettings(
        provider_whitelist=["binance_um_perps"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode=mode,
            binance=BinanceExecutionSettings(
                allow_unknown_permissions=True,
                maker_timeout_s=0,
                taker_fallback=True,
            ),
        ),
        safety=SafetySettings(
            live_unlock=LiveUnlockSettings(
                enable_live_trading=True,
                ack_i_understand_risks=True,
                require_testnet_passed=False,
                canary_required_before_full=True,
            )
        ),
        risk=RiskLimits(
            max_daily_loss_pct=5.0,
            max_drawdown_pct=10.0,
            max_position_notional=1000.0,
            max_exposure_notional=2000.0,
            max_orders_per_min=10,
            leverage=0,
            max_spread_bps=20.0,
            min_depth_notional=100.0,
            stale_data_seconds=60.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=3.0,
            max_liquidation_spike=100000.0,
            divergence_threshold_bps=30.0,
            crowding_score_kill=25.0,
        ),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )


def test_live_unlock_fail_closed_when_flags_false(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    with pytest.raises(ValueError):
        RobotSettings(
            provider_whitelist=["binance_um_perps"],
            execution=ExecutionSettings(mode="live_testnet"),
            safety=SafetySettings(
                live_unlock=LiveUnlockSettings(
                    enable_live_trading=False,
                    ack_i_understand_risks=False,
                    require_testnet_passed=False,
                )
            ),
            risk=_settings().risk,
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        )


def test_live_fails_when_secrets_missing(monkeypatch):
    monkeypatch.delenv("EXCHANGE_API_KEY", raising=False)
    monkeypatch.delenv("EXCHANGE_API_SECRET", raising=False)
    with pytest.raises(ValueError):
        _settings()


def test_preflight_fails_when_connector_credentials_are_missing(monkeypatch):
    class NoCredsConnector(FakeConnector):
        @property
        def has_credentials(self):
            return False

    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    svc = LiveBinanceService(_settings(), run_id="r1", connector=NoCredsConnector())

    ok, reason = svc.preflight()

    assert ok is False
    assert reason == "missing_credentials"


def test_preflight_fails_closed_on_permission_denied(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.verify_live_permissions = lambda: (False, "permission_denied")  # type: ignore[assignment]
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    ok, reason = svc.preflight()

    assert ok is False
    assert reason == "permission_denied"


def test_live_binance_capability_evidence_tracks_runtime_signals(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    svc = LiveBinanceService(_settings(), run_id="r1", connector=FakeConnector())

    ok, reason = svc.preflight()
    assert ok is True
    assert reason == "ok"

    svc.capture_market_integrity_evidence({"bidPrice": "100.0", "askPrice": "100.1", "bidQty": "10", "askQty": "10"}, 1000.0)
    svc.capture_market_integrity_evidence({"bidPrice": "100.0", "askPrice": "100.1", "bidQty": "10", "askQty": "10"}, 1065.0)
    evidence = svc.capability_evidence(now_dt=1125.0)

    assert evidence["auth_validated"] is True
    assert evidence["public_market_data_connected"] is True
    assert evidence["book_repeat_count"] >= 1
    assert evidence["seconds_since_distinct_book_change"] >= 60.0


def test_preflight_fails_when_account_mode_is_not_supported(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    settings = _settings()
    settings.execution.binance.account_mode = "hedge"
    svc = LiveBinanceService(settings, run_id="r1", connector=FakeConnector())

    ok, reason = svc.preflight()

    assert ok is False
    assert reason == "account_mode_not_supported"


def test_preflight_fails_when_balance_state_is_invalid(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.balances = lambda: []  # type: ignore[assignment]
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    ok, reason = svc.preflight()

    assert ok is False
    assert reason.startswith("balance_state_invalid:")


def test_preflight_fails_closed_on_invalid_symbol_mapping(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    settings = _settings()
    settings.universe = ["BTC/EUR"]
    svc = LiveBinanceService(settings, run_id="r1", connector=FakeConnector())

    ok, reason = svc.preflight()

    assert ok is False
    assert reason == "symbol_missing:BTC/EUR"


def test_idempotency_client_order_id_is_deterministic(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    svc = LiveBinanceService(_settings(), run_id="r1", connector=FakeConnector())
    a = svc._client_order_id("BTCUSDT", "buy", 1700000000.0, 0)
    b = svc._client_order_id("BTCUSDT", "buy", 1700000000.0, 0)
    assert a == b
    assert len(a) == 32


def test_retry_like_reentry_never_double_places(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    monkeypatch.setattr("autonomous_investment_robot.services.execution.live_binance_service.time.time", lambda: 1700000000.0)
    intent = OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={})
    first = svc.execute_intent(intent)
    placed_after_first = fake.place_calls
    second = svc.execute_intent(intent)

    assert first.status in {"filled_maker", "filled_taker_fallback", "timeout", "deduped"}
    assert second.status == "deduped"
    assert fake.place_calls == placed_after_first


def test_execute_intent_kills_on_invalid_book_data(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.book_ticker = lambda symbol: {"bidPrice": "0", "askPrice": "100.1", "bidQty": "10", "askQty": "10"}  # type: ignore[assignment]
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    result = svc.execute_intent(OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={}))

    assert result.status == "killed"
    assert result.reason == "book_invalid:0.0:100.1"
    assert svc.killed is True


def test_reject_storm_triggers_kill_and_cooldown(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.fail_place = True
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)
    intent = OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={})

    last = None
    for _ in range(7):
        last = svc.execute_intent(intent)
    assert last is not None
    assert last.status == "killed"
    assert svc.safe_mode is True


def test_order_updates_reject_out_of_order_status(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    svc = LiveBinanceService(_settings(), run_id="r1", connector=FakeConnector())

    ok1, reason1 = svc.apply_order_update({"clientOrderId": "cid-1", "status": "FILLED"})
    ok2, reason2 = svc.apply_order_update({"clientOrderId": "cid-1", "status": "NEW"})

    assert (ok1, reason1) == (True, "ok")
    assert (ok2, reason2) == (False, "out_of_order_order_update")


def test_fill_updates_reject_duplicates(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    svc = LiveBinanceService(_settings(), run_id="r1", connector=FakeConnector())

    ok1, reason1 = svc.apply_fill_update({"fill_id": "fill-1", "notional": 10.0})
    ok2, reason2 = svc.apply_fill_update({"fill_id": "fill-1", "notional": 10.0})

    assert (ok1, reason1) == (True, "ok")
    assert (ok2, reason2) == (False, "duplicate_fill_update")


def test_execute_intent_emits_normalized_live_fill_record_when_order_has_execution_fields(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()

    def _place_order(params):
        cid = params["newClientOrderId"]
        if params.get("type") == "MARKET":
            order = {
                "clientOrderId": cid,
                "orderId": "order-1",
                "status": "FILLED",
                "symbol": "BTCUSDT",
                "side": params["side"].lower(),
                "executedQty": "0.1",
                "avgPrice": "100.0",
                "cumQuote": "10.0",
                "commission": "0.02",
                "realizedPnl": "1.5",
            }
            fake.orders[cid] = order
            return order
        order = {"clientOrderId": cid, "orderId": "order-1", "status": "NEW", "symbol": "BTCUSDT"}
        fake.orders[cid] = order
        return order

    fake.place_order = _place_order  # type: ignore[assignment]
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    result = svc.execute_intent(OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={}))

    assert result.status == "filled_taker_fallback"
    assert len(result.ledger_records) == 1
    record = result.ledger_records[0]
    assert record.fill.notional == 10.0
    assert record.fee_authoritative is True
    assert record.realized_pnl_authoritative is True
    assert record.gaps == []


def test_authoritative_realized_pnl_uses_income_history(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    svc = LiveBinanceService(_settings(), run_id="r1", connector=FakeConnector())

    realized, gaps = svc.authoritative_realized_pnl("BTCUSDT", since_ms=1700000000000)

    assert realized == 1.5
    assert gaps == []


def test_authoritative_unrealized_pnl_uses_position_fields(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.positions = [{"symbol": "BTCUSDT", "positionAmt": "0.1", "markPrice": "100.0", "unRealizedProfit": "3.5"}]
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    truth, gaps = svc.authoritative_unrealized_pnl("BTCUSDT")

    assert truth is not None
    assert truth.confidence == "authoritative"
    assert truth.venue_value == 3.5
    assert gaps == []


def test_maker_timeout_falls_back_to_taker(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.next_order_status = "NEW"
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    result = svc.execute_intent(OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={}))
    assert result.status == "filled_taker_fallback"
    assert fake.cancel_calls >= 1


def test_flatten_only_blocks_new_orders(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    svc = LiveBinanceService(_settings(), run_id="r1", connector=FakeConnector())
    svc.enter_flatten_only("restart_state_confidence_insufficient")

    result = svc.execute_intent(OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={}))

    assert result.status == "blocked"
    assert result.reason == "flatten_only"


def test_reconciliation_mismatch_sets_safe_mode_and_flatten(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.positions = [{"symbol": "BTCUSDT", "positionAmt": "1.0", "markPrice": "100.0"}]
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    ok, _ = svc.reconcile_live_state(internal_exposure=1.0)
    assert ok is False
    assert svc.safe_mode is True

    fake.positions = [{"symbol": "BTCUSDT", "positionAmt": "1.0", "markPrice": "100.0"}]

    def _position_risk(symbol=None):
        if fake.positions:
            out = fake.positions
            fake.positions = []
            return out
        return []

    fake.position_risk = _position_risk
    closed, reason = svc.flatten_all_positions(max_attempts=2)
    assert closed is True
    assert reason == "flat"


def test_reconciliation_fails_closed_when_balance_state_unavailable(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.positions = []
    fake.balances = lambda: []  # type: ignore[assignment]
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    ok, reason = svc.reconcile_live_state(internal_exposure=0.0)
    assert ok is False
    assert reason.startswith("live_cash_mismatch")
    assert svc.safe_mode is True


def test_rate_limit_storm_triggers_kill(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.fail_with_rate_limit = True
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)
    intent = OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={})
    last = None
    for _ in range(5):
        last = svc.execute_intent(intent)
    assert last is not None
    assert last.status == "killed"
    assert last.reason == "rate_limit_storm"
    assert svc.killed is True
    assert svc.safe_mode is True


def test_flatten_cancels_open_orders_best_effort(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake._open_orders = [{"symbol": "BTCUSDT", "clientOrderId": "abc"}]
    fake.positions = []
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)
    closed, reason = svc.flatten_all_positions()
    assert closed is True
    assert reason == "flat"
    assert fake.cancel_calls >= 1


def test_flatten_tolerates_cancel_failures(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake._open_orders = [{"symbol": "BTCUSDT", "clientOrderId": "abc"}]
    fake.cancel_order = lambda symbol, client_order_id: (_ for _ in ()).throw(RuntimeError("cancel_failed"))  # type: ignore[assignment]
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    closed, reason = svc.flatten_all_positions()

    assert closed is True
    assert reason == "flat"


def test_reconcile_and_flatten_on_mismatch(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.positions = [{"symbol": "BTCUSDT", "positionAmt": "1.0", "markPrice": "100.0"}]
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    calls = {"n": 0}

    def _position_risk(symbol=None):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"symbol": "BTCUSDT", "positionAmt": "1.0", "markPrice": "100.0"}]
        return []

    fake.position_risk = _position_risk
    ok, reason = svc.reconcile_and_flatten_on_mismatch(internal_exposure=0.0, max_flatten_attempts=2)
    assert ok is False
    assert "flattened" in reason
    assert svc.killed is True


@pytest.mark.integration
def test_testnet_minimal_order_cycle_opt_in(monkeypatch):
    if os.getenv("RUN_TESTNET", "0") != "1":
        pytest.skip("set RUN_TESTNET=1 to run integration testnet test")
    pytest.skip("integration skeleton: configure real testnet credentials and endpoint")
