from datetime import datetime, timezone
import os

import pytest

from autonomous_investment_robot.config.settings import (
    ExecutionSettings,
    KrakenExecutionSettings,
    LiveUnlockSettings,
    RiskLimits,
    RobotSettings,
    SafetySettings,
    TCOSettings,
)
from autonomous_investment_robot.services.execution.live_kraken_service import LiveKrakenService
from autonomous_investment_robot.services.policy.service import OrderIntent


class FakeKrakenConnector:
    def __init__(self):
        self._has_credentials = True
        self.supports_live_trading = False
        self.orders = {}
        self.positions = []
        self._open_orders = []
        self.place_calls = 0
        self.cancel_calls = 0
        self.fail_place = False
        self.fail_with_rate_limit = False
        self.next_order_status = "NEW"

    @property
    def has_credentials(self):
        return self._has_credentials

    def verify_live_permissions(self):
        return True, "ok"

    def exchange_info(self):
        return {"symbols": [{"symbol": "PI_XBTUSD"}, {"symbol": "BTCUSDT"}]}

    def book_ticker(self, symbol):
        return {"bidPrice": "100", "askPrice": "101", "bidQty": "1", "askQty": "1", "symbol": symbol}

    def query_order(self, symbol, client_order_id):  # noqa: ARG002
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
        status = "FILLED" if params.get("type") == "MARKET" else self.next_order_status
        out = {"clientOrderId": cid, "status": status, "symbol": params.get("symbol")}
        self.orders[cid] = out
        return out

    def cancel_order(self, symbol, client_order_id):  # noqa: ARG002
        self.cancel_calls += 1
        return {"status": "CANCELED"}

    def open_orders(self, symbol=None):  # noqa: ARG002
        return list(self._open_orders)

    def position_risk(self, symbol=None):  # noqa: ARG002
        return list(self.positions)

    def balances(self):
        return [{"asset": "USD", "balance": "100.0", "availableBalance": "100.0", "equity": "100.0"}]

    def fills(self, last_fill_time=None):  # noqa: ARG002
        return []

    def execution_events(self, since=None, before=None, count=None, sort="desc", continuation_token=None):  # noqa: ARG002
        events = []
        for order in self.orders.values():
            if not isinstance(order, dict):
                continue
            if str(order.get("status", "")).upper() != "FILLED":
                continue
            order_id = str(order.get("orderId", order.get("order_id", "order-1")))
            client_id = str(order.get("clientOrderId", "cid-1"))
            exec_id = str(order.get("exec_id", f"exec-{order_id}"))
            events.append(
                {
                    "event": {
                        "Execution": {
                            "execution": {
                                "order_id": order_id,
                                "clientId": client_id,
                                "exec_id": exec_id,
                                "symbol": str(order.get("symbol", "PI_XBTUSD")),
                                "side": str(order.get("side", "buy")),
                                "cost": str(order.get("cumQuote", "10.0")),
                                "fees": [{"asset": "USD", "qty": str(order.get("fee", "0.03"))}],
                            }
                        }
                    }
                }
            )
        return {"elements": events}

    def account_log(self, since=None, before=None, from_id=None, to_id=None, sort="desc"):  # noqa: ARG002
        logs = []
        for order in self.orders.values():
            if not isinstance(order, dict):
                continue
            if str(order.get("status", "")).upper() != "FILLED":
                continue
            order_id = str(order.get("orderId", order.get("order_id", "order-1")))
            exec_id = str(order.get("exec_id", f"exec-{order_id}"))
            logs.append(
                {
                    "execution": exec_id,
                    "contract": str(order.get("symbol", "PI_XBTUSD")),
                    "fee": float(order.get("fee", "0.03")),
                    "realized_pnl": float(order.get("closedPnl", "2.5")),
                }
            )
        return logs


def _limits() -> RiskLimits:
    return RiskLimits(
        max_daily_loss_pct=1.0,
        max_weekly_loss_pct=2.0,
        max_drawdown_pct=2.0,
        max_position_notional=10.0,
        max_exposure_notional=10.0,
        max_symbol_exposure_notional=10.0,
        max_cluster_exposure_notional=10.0,
        max_orders_per_min=5,
        leverage=0,
        cvar_limit_pct=1.0,
        stress_loss_limit_pct=2.0,
        max_spread_bps=10.0,
        min_depth_notional=10.0,
        stale_data_seconds=10.0,
        min_margin_buffer=2.0,
        max_funding_cost_per_day=1.0,
        max_oi_spike_pct=1.0,
        max_liquidation_spike=1.0,
        divergence_threshold_bps=10.0,
        crowding_score_kill=10.0,
    )


def test_kraken_live_readonly_preflight_passes_without_credentials():
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        execution=ExecutionSettings(mode="live_readonly", provider_id="kraken_derivatives"),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=FakeKrakenConnector())
    ok, reason = svc.preflight()
    assert ok is True
    assert reason == "readonly"


def test_kraken_live_testnet_is_fail_closed_until_trading_impl(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode="live_testnet",
            provider_id="kraken_derivatives",
            kraken=KrakenExecutionSettings(allow_unknown_permissions=True),
        ),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=FakeKrakenConnector())
    ok, reason = svc.preflight()
    assert ok is False
    assert reason == "kraken_live_trading_not_implemented"


def test_kraken_readonly_preview_uses_connector_book():
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        execution=ExecutionSettings(mode="live_readonly", provider_id="kraken_derivatives"),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=FakeKrakenConnector())
    out = svc.execute_readonly(OrderIntent(symbol="PI_XBTUSD", side="buy", target_notional=10.0, why={}))
    assert out.status == "readonly_preview"
    assert out.order is not None
    assert out.order["book"]["bidPrice"] == "100"


def test_kraken_live_preflight_passes_when_connector_supports_trading(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode="live_testnet",
            provider_id="kraken_derivatives",
            maker_timeout_s=0,
            kraken=KrakenExecutionSettings(allow_unknown_permissions=True),
        ),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)
    ok, reason = svc.preflight()
    assert ok is True
    assert reason == "ok"


def test_kraken_capability_evidence_tracks_runtime_signals(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    svc = LiveKrakenService(
        RobotSettings(
            provider_whitelist=["kraken_derivatives"],
            canary_mode=True,
            execution=ExecutionSettings(
                mode="live_testnet",
                provider_id="kraken_derivatives",
                kraken=KrakenExecutionSettings(allow_unknown_permissions=True),
            ),
            safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
            risk=_limits(),
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        ),
        run_id="r1",
        connector=fake,
    )

    ok, reason = svc.preflight()
    assert ok is True
    assert reason == "ok"

    svc.capture_market_integrity_evidence({"bidPrice": "100", "askPrice": "101", "bidQty": "1", "askQty": "1"}, datetime.now(timezone.utc))
    svc.capture_market_integrity_evidence({"bidPrice": "100", "askPrice": "101", "bidQty": "1", "askQty": "1"}, datetime.now(timezone.utc))
    evidence = svc.capability_evidence(now_dt=datetime.now(timezone.utc))

    assert evidence["auth_validated"] is True
    assert evidence["public_market_data_connected"] is True
    assert evidence["book_repeat_count"] >= 1


def test_kraken_preflight_fails_when_connector_credentials_are_missing(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake._has_credentials = False
    fake.supports_live_trading = True
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode="live_testnet",
            provider_id="kraken_derivatives",
            kraken=KrakenExecutionSettings(allow_unknown_permissions=True),
        ),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)

    ok, reason = svc.preflight()

    assert ok is False
    assert reason == "missing_credentials"


def test_kraken_preflight_fails_closed_on_permission_denied(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake.verify_live_permissions = lambda: (False, "permission_denied")  # type: ignore[assignment]
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode="live_testnet",
            provider_id="kraken_derivatives",
            kraken=KrakenExecutionSettings(allow_unknown_permissions=True),
        ),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)

    ok, reason = svc.preflight()

    assert ok is False
    assert reason == "permission_denied"


def test_kraken_preflight_fails_when_balance_state_is_invalid(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake.balances = lambda: []  # type: ignore[assignment]
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode="live_testnet",
            provider_id="kraken_derivatives",
            kraken=KrakenExecutionSettings(allow_unknown_permissions=True),
        ),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)

    ok, reason = svc.preflight()

    assert ok is False
    assert reason.startswith("balance_state_invalid:")


def test_kraken_preflight_fails_closed_on_invalid_symbol_mapping(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        universe=["BTC/EUR"],
        execution=ExecutionSettings(
            mode="live_testnet",
            provider_id="kraken_derivatives",
            kraken=KrakenExecutionSettings(allow_unknown_permissions=True),
        ),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)

    ok, reason = svc.preflight()

    assert ok is False
    assert reason == "symbol_missing:BTC/EUR"


def test_kraken_execute_intent_kills_on_invalid_book_data(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake.book_ticker = lambda symbol: {"bidPrice": "0", "askPrice": "101", "bidQty": "1", "askQty": "1", "symbol": symbol}  # type: ignore[assignment]
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)

    result = svc.execute_intent(OrderIntent(symbol="PI_XBTUSD", side="buy", target_notional=10.0, why={}))

    assert result.status == "killed"
    assert result.reason == "book_invalid:0.0:101.0"
    assert svc.killed is True


def test_kraken_rate_limit_storm_triggers_kill(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake.fail_with_rate_limit = True
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives", maker_timeout_s=0),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)
    intent = OrderIntent(symbol="PI_XBTUSD", side="buy", target_notional=10.0, why={})
    last = None
    for _ in range(5):
        last = svc.execute_intent(intent)
    assert last is not None
    assert last.status == "killed"
    assert last.reason == "rate_limit_storm"
    assert svc.killed is True
    assert svc.safe_mode is True


def test_kraken_order_updates_reject_out_of_order_status(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)

    ok1, reason1 = svc.apply_order_update({"clientOrderId": "cid-1", "status": "FILLED"})
    ok2, reason2 = svc.apply_order_update({"clientOrderId": "cid-1", "status": "NEW"})

    assert (ok1, reason1) == (True, "ok")
    assert (ok2, reason2) == (False, "out_of_order_order_update")


def test_kraken_fill_updates_reject_duplicates(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)

    ok1, reason1 = svc.apply_fill_update({"fill_id": "fill-1", "notional": 10.0})
    ok2, reason2 = svc.apply_fill_update({"fill_id": "fill-1", "notional": 10.0})

    assert (ok1, reason1) == (True, "ok")
    assert (ok2, reason2) == (False, "duplicate_fill_update")


def test_kraken_execute_intent_emits_normalized_live_fill_record_when_order_has_execution_fields(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True

    def _place_order(params):
        cid = params["newClientOrderId"]
        if params.get("type") == "MARKET":
            order = {
                "clientOrderId": cid,
                "orderId": "order-1",
                "status": "FILLED",
                "symbol": "PI_XBTUSD",
                "side": params["side"].lower(),
                "filledSize": "0.1",
                "avgPrice": "100.0",
                "cumQuote": "10.0",
                "fee": "0.03",
                "closedPnl": "2.5",
                "exec_id": "exec-order-1",
            }
            fake.orders[cid] = order
            return order
        order = {"clientOrderId": cid, "orderId": "order-1", "status": "NEW", "symbol": "PI_XBTUSD"}
        fake.orders[cid] = order
        return order

    fake.place_order = _place_order  # type: ignore[assignment]
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives", maker_timeout_s=0),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)

    result = svc.execute_intent(OrderIntent(symbol="PI_XBTUSD", side="buy", target_notional=10.0, why={}))

    assert result.status == "filled_taker_fallback"
    assert len(result.ledger_records) == 1
    record = result.ledger_records[0]
    assert record.fill.notional == 10.0
    assert record.fee_authoritative is True
    assert record.realized_pnl_authoritative is True
    assert record.gaps == []


def test_kraken_authoritative_realized_pnl_uses_account_log(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake.orders["cid-1"] = {
        "clientOrderId": "cid-1",
        "orderId": "order-1",
        "status": "FILLED",
        "symbol": "PI_XBTUSD",
        "side": "buy",
        "cumQuote": "10.0",
        "fee": "0.03",
        "closedPnl": "2.5",
        "exec_id": "exec-order-1",
    }
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)

    realized, gaps = svc.authoritative_realized_pnl("PI_XBTUSD", since_ms=1700000000000)

    assert realized == 2.5
    assert gaps == []


def test_kraken_authoritative_unrealized_pnl_degrades_to_proxy_without_venue_field(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake.positions = [{"symbol": "PI_XBTUSD", "positionAmt": "0.1", "markPrice": "100.0", "entryPrice": "95.0"}]
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode="live_testnet",
            provider_id="kraken_derivatives",
            maker_timeout_s=0,
            kraken=KrakenExecutionSettings(allow_unknown_permissions=True),
        ),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)

    truth, gaps = svc.authoritative_unrealized_pnl("PI_XBTUSD")

    assert truth is not None
    assert truth.confidence == "proxy"
    assert truth.venue_value == 0.5
    assert gaps == ["derived_from_position_mark_and_entry"]


def test_kraken_reconcile_and_flatten_mismatch(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake.positions = [{"symbol": "PI_XBTUSD", "positionAmt": "1.0", "markPrice": "100.0"}]
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives", maker_timeout_s=0),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)
    ok, _ = svc.reconcile_live_state(internal_exposure=1.0)
    assert ok is False
    assert svc.safe_mode is True
    assert svc.killed is True

    calls = {"n": 0}

    def _position_risk(symbol=None):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"symbol": "PI_XBTUSD", "positionAmt": "1.0", "markPrice": "100.0"}]
        return []

    fake.position_risk = _position_risk
    ok2, reason2 = svc.reconcile_and_flatten_on_mismatch(internal_exposure=1.0, max_flatten_attempts=2)
    assert ok2 is False
    assert "flattened" in reason2


def test_kraken_reconcile_fails_closed_when_balance_unavailable(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake.positions = []
    fake.balances = lambda: []  # type: ignore[assignment]
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)
    ok, reason = svc.reconcile_live_state(internal_exposure=0.0)
    assert ok is False
    assert reason.startswith("live_cash_mismatch")
    assert svc.safe_mode is True


def test_kraken_flatten_cancels_open_orders_best_effort(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake._open_orders = [{"symbol": "PI_XBTUSD", "clientOrderId": "abc"}]
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)
    closed, reason = svc.flatten_all_positions()
    assert closed is True
    assert reason == "flat"
    assert fake.cancel_calls >= 1


def test_kraken_flatten_only_blocks_new_orders(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)
    svc.enter_flatten_only("restart_state_confidence_insufficient")

    result = svc.execute_intent(OrderIntent(symbol="PI_XBTUSD", side="buy", target_notional=10.0, why={}))

    assert result.status == "blocked"
    assert result.reason == "flatten_only"


def test_kraken_flatten_tolerates_cancel_failures(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake._open_orders = [{"symbol": "PI_XBTUSD", "clientOrderId": "abc"}]
    fake.cancel_order = lambda symbol, client_order_id: (_ for _ in ()).throw(RuntimeError("cancel_failed"))  # type: ignore[assignment]
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)

    closed, reason = svc.flatten_all_positions()

    assert closed is True
    assert reason == "flat"
