import os
import time

from autonomous_investment_robot.config.settings import (
    ExecutionSettings,
    KrakenSpotExecutionSettings,
    LiveUnlockSettings,
    RiskLimits,
    RobotSettings,
    SafetySettings,
    TCOSettings,
)
from autonomous_investment_robot.services.execution.live_kraken_spot_service import LiveKrakenSpotService
from autonomous_investment_robot.services.execution.profit_gate import PositionLot
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenRateLimitError


class _FakeKrakenSpotConnector:
    def __init__(self) -> None:
        self._has_credentials = True
        self.add_calls = 0
        self.add_params = []
        self.cancel_calls = 0
        self.query_calls = 0
        self.trades_history_calls = 0
        self.trade_volume_calls = 0
        self.fail_rate_limit = False
        self.fail_eapi_rate_limit = False
        self.fail_temporary_lockout = False
        self.fail_balance_temporary_lockout = False
        self.fail_trades_temporary_lockout = False
        self.rate_limit_failures_remaining = 0
        self.fail_insufficient = False
        self.never_fill_maker = False
        self.bid = 49990.0
        self.ask = 50000.0
        self.bid_qty = 2.0
        self.ask_qty = 1.5
        self._balance = {"ZUSD": "1000.0", "XXBT": "0.0"}
        self._orders = {}
        self._trades_history = {}
        self._trade_volume = {"fees": {"XBTUSD": {"fee": "0.26"}}}
        self.asset_pairs_calls = 0

    @property
    def has_credentials(self):
        return self._has_credentials

    def verify_live_permissions(self):
        return True, "ok"

    def asset_pairs(self):
        self.asset_pairs_calls += 1
        return {
            "XBTUSD": {
                "ordermin": "0.0001",
                "pair_decimals": 1,
                "lot_decimals": 8,
                "base": "XXBT",
                "quote": "ZUSD",
            }
        }

    def ticker(self, pair=None):  # noqa: ARG002
        return {
            "XBTUSD": {
                "a": [str(self.ask), str(self.ask_qty)],
                "b": [str(self.bid), str(self.bid_qty)],
                "c": [str(self.ask)],
                "v": ["0", "1000000"],
            }
        }

    def balance(self):
        if self.fail_balance_temporary_lockout:
            raise RuntimeError("EGeneral:Temporary lockout")
        return dict(self._balance)

    def add_order(self, params):
        self.add_calls += 1
        self.add_params.append(dict(params))
        if self.fail_temporary_lockout:
            raise RuntimeError("EGeneral:Temporary lockout")
        if self.fail_eapi_rate_limit:
            from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenRateLimitError

            raise KrakenRateLimitError("EAPI:Rate limit exceeded")
        if self.fail_rate_limit or self.rate_limit_failures_remaining > 0:
            if self.rate_limit_failures_remaining > 0:
                self.rate_limit_failures_remaining -= 1
            from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenRateLimitError

            raise KrakenRateLimitError("429 rate limit")
        if self.fail_insufficient:
            from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenInsufficientFundsError

            raise KrakenInsufficientFundsError("insufficient funds")
        txid = f"T{self.add_calls}"
        self._orders[txid] = {"status": "open", "vol_exec": "0.0", "params": dict(params)}
        # Simulate immediate fill for maker unless explicitly disabled.
        if params.get("ordertype") == "limit" and params.get("oflags") == "post" and not self.never_fill_maker:
            self._orders[txid]["status"] = "closed"
            self._orders[txid]["vol_exec"] = params.get("volume", "0.0")
        return {"descr": {"order": "buy"}, "txid": [txid]}

    def query_orders(self, txid):
        self.query_calls += 1
        return {txid: self._orders.get(txid, {"status": "closed", "vol_exec": "0.0"})}

    def cancel_order(self, txid):
        self.cancel_calls += 1
        if txid in self._orders:
            self._orders[txid]["status"] = "canceled"
        return {"count": 1}

    def cancel_all(self):
        return {"count": 0}

    def open_orders(self):
        out = {}
        for txid, row in self._orders.items():
            if str(row.get("status", "")).lower() != "open":
                continue
            params = row.get("params", {})
            out[txid] = {
                "status": "open",
                "vol": params.get("volume", "0.0"),
                "vol_exec": row.get("vol_exec", "0.0"),
                "opentm": row.get("opentm", time.time()),
                "descr": {
                    "pair": params.get("pair", "XBTUSD"),
                    "type": params.get("type", ""),
                    "price": params.get("price", "0.0"),
                },
            }
        return {"open": out}

    def trades_history(self, start=None):  # noqa: ARG002
        self.trades_history_calls += 1
        if self.fail_trades_temporary_lockout:
            raise RuntimeError("EGeneral:Temporary lockout")
        return dict(self._trades_history)

    def trade_volume(self, pair=None, fee_info=True):  # noqa: ARG002
        self.trade_volume_calls += 1
        return dict(self._trade_volume)


def _settings(dry_run: bool = True) -> RobotSettings:
    return RobotSettings(
        provider_whitelist=["kraken_spot"],
        canary_mode=True,
        explicit_live_enable=True,
        ack_live_risks=True,
        execution=ExecutionSettings(
            mode="live_testnet",
            fee_bps=16.0,
            slippage_bps=8.0,
            kraken_spot=KrakenSpotExecutionSettings(allow_unknown_permissions=True, dry_run_long_only=dry_run),
        ),
        safety=SafetySettings(
            live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)
        ),
        risk=RiskLimits(
            max_daily_loss_pct=1.0,
            max_weekly_loss_pct=2.0,
            max_drawdown_pct=2.0,
            max_position_notional=1000.0,
            max_exposure_notional=1000.0,
            max_symbol_exposure_notional=1000.0,
            max_cluster_exposure_notional=1000.0,
            max_orders_per_min=10,
            leverage=0,
            max_spread_bps=50.0,
            min_depth_notional=0.0,
            stale_data_seconds=10.0,
            min_margin_buffer=1.0,
            max_funding_cost_per_day=0.0,
            max_oi_spike_pct=0.0,
            max_liquidation_spike=0.0,
            divergence_threshold_bps=50.0,
            crowding_score_kill=50.0,
        ),
        tco=TCOSettings(max_total_cost_bps=50.0, max_impact_bps=20.0),
    )


def test_execute_intent_dry_run_blocks_with_order_preview(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    svc = LiveKrakenSpotService(_settings(dry_run=True), run_id="r1", connector=_FakeKrakenSpotConnector())
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert out.status == "blocked"
    assert out.reason == "spot_live_execution_dry_run"
    assert out.order is not None
    assert out.order["pair"] == "XBTUSD"


def test_market_snapshot_includes_top_of_book_quantities(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=_FakeKrakenSpotConnector())
    snap = svc.market_snapshot("XBTUSD", force_refresh=True)
    assert snap["bid"] > 0.0
    assert snap["ask"] > 0.0
    assert snap["bid_qty"] == 2.0
    assert snap["ask_qty"] == 1.5


def test_execute_intent_submits_market_buy(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert out.status in {"filled_maker", "filled_taker_fallback", "submitted"}
    assert out.order is not None
    assert out.order["txid"] == "T1"
    assert fake.add_calls == 1


def test_execute_intent_maker_timeout_blocks_if_edge_not_ok(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_FEE_AWARE_SIZING", "false")
    fake = _FakeKrakenSpotConnector()
    fake.never_fill_maker = True
    s = _settings(dry_run=False)
    s.execution.maker_timeout_s = 1
    svc = LiveKrakenSpotService(s, run_id="r1", connector=fake)
    intent = OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={"components": [{"edge_bps": 1.0, "cost_total_bps": 2.0}]})
    out = svc.execute_intent(intent)
    assert out.status == "timeout"
    assert out.reason == "maker_timeout_edge_le_cost"
    assert fake.cancel_calls >= 1


def test_execute_intent_maker_timeout_falls_back_when_edge_ok(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_FEE_AWARE_SIZING", "false")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_MAKER_ONLY", "false")
    fake = _FakeKrakenSpotConnector()
    fake.never_fill_maker = True
    s = _settings(dry_run=False)
    s.execution.maker_timeout_s = 1
    svc = LiveKrakenSpotService(s, run_id="r1", connector=fake)
    intent = OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={"components": [{"edge_bps": 5.0, "cost_total_bps": 2.0}]})
    out = svc.execute_intent(intent)
    assert out.status == "filled_taker_fallback"
    assert fake.add_calls >= 2


def test_execute_intent_maker_timeout_does_not_fallback_when_taker_disabled(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_KRAKEN_TAKER_FALLBACK", "false")
    monkeypatch.setenv("AUTONOMOUS_FEE_AWARE_SIZING", "false")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_MAKER_ONLY", "false")
    fake = _FakeKrakenSpotConnector()
    fake.never_fill_maker = True
    s = _settings(dry_run=False)
    s.execution.maker_timeout_s = 1
    svc = LiveKrakenSpotService(s, run_id="r1", connector=fake)
    intent = OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={"components": [{"edge_bps": 5.0, "cost_total_bps": 2.0}]})
    out = svc.execute_intent(intent)
    assert out.status == "timeout"
    assert out.reason == "maker_timeout_taker_disabled"
    assert fake.add_calls == 1


def test_execute_intent_small_buy_is_raised_to_exchange_minimum(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=_FakeKrakenSpotConnector())
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=0.01, why={}))
    assert out.status in {"filled_maker", "submitted", "filled_taker_fallback"}
    assert out.order is not None
    assert out.order["notional"] >= 4.99


def test_execute_intent_blocks_insufficient_balance(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1.0"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert out.status == "blocked"
    assert out.reason == "insufficient_balance_block"


def test_rate_limit_error_enters_cooldown_without_killing_service(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_KRAKEN_RATE_LIMIT_STORM", "1")
    monkeypatch.setenv("AUTONOMOUS_RATE_LIMIT_COOLDOWN_S", "0.25")
    monkeypatch.setenv("AUTONOMOUS_KRAKEN_EXEC_RETRY_ATTEMPTS", "1")
    fake = _FakeKrakenSpotConnector()
    fake.fail_rate_limit = True
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    first = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert first.status == "blocked"
    assert first.reason == "rate_limit_cooldown"
    assert svc.killed is False
    assert fake.add_calls == 1

    second = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert second.status == "blocked"
    assert second.reason == "rate_limit_cooldown"
    assert fake.add_calls == 1
    assert svc.killed is False

    import time

    time.sleep(0.5)
    third = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert third.status == "blocked"
    assert third.reason == "rate_limit_cooldown"
    assert fake.add_calls == 2
    assert svc.killed is False


def test_execute_intent_sell_is_capped_to_available_base(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.002"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.002
    ledger.avg_entry_price = 45000.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="sell", target_notional=500.0, why={}))
    assert out.status in {"submitted_limit_floor"}
    assert out.order is not None
    assert out.order["volume"] <= 0.002


def test_inventory_aware_sell_skips_when_no_base_balance(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.0"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="sell", target_notional=100.0, why={}))
    assert out.status == "skipped"
    assert out.reason == "insufficient_base_balance_block"
    assert fake.add_calls == 0


def test_sell_profit_lock_skips_when_bid_below_entry_plus_cost(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", "true")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS", "50")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.01"}
    fake.bid = 50000.0
    fake.ask = 50010.0
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.01
    ledger.avg_entry_price = 50100.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="sell", target_notional=100.0, why={}))
    assert out.status == "skipped"
    assert out.reason == "profit_lock_sell_below_entry"
    assert out.order is not None
    assert out.order["required_profit_bps"] == 200.0
    assert fake.add_calls == 0


def test_sell_profit_lock_uses_target_then_min_profit_after_hold_window(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", "true")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS", "200")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS", "500")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_TARGET_HOLD_S", "90")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.01"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.01
    ledger.avg_entry_price = 100.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")
    intent = OrderIntent(symbol="XBTUSD", side="sell", target_notional=1.0, why={})

    ledger.position_open_ts = time.time()
    blocked, details = svc._sell_profit_lock_violation(pair="XBTUSD", bid=103.0, ask=103.2, intent=intent)
    assert blocked is True
    assert details["required_profit_bps"] == 500.0

    ledger.position_open_ts = time.time() - 120.0
    blocked_after_hold, details_after_hold = svc._sell_profit_lock_violation(pair="XBTUSD", bid=103.0, ask=103.2, intent=intent)
    assert blocked_after_hold is False
    assert details_after_hold["required_profit_bps"] == 200.0


def test_sell_profit_lock_fatal_intent_still_blocked_by_profit_gate(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", "true")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS", "200")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK_FATAL_BYPASS", "true")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.01"}
    fake.bid = 50000.0
    fake.ask = 50010.0
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.01
    ledger.avg_entry_price = 50100.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")
    out = svc.execute_intent(
        OrderIntent(
            symbol="XBTUSD",
            side="sell",
            target_notional=100.0,
            why={"risk": {"decision_reason": "daily_loss_kill"}},
        )
    )
    assert out.status == "skipped"
    assert out.reason == "profit_lock_sell_below_entry"
    assert out.order is not None
    assert out.order["required_profit_bps"] >= 200.0
    assert fake.add_calls == 0


def test_fatal_intent_never_bypasses_profit_gate(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", "true")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS", "200")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK_FATAL_BYPASS", "true")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.01"}
    fake.bid = 50000.0
    fake.ask = 50010.0
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.01
    ledger.avg_entry_price = 51000.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")
    out = svc.execute_intent(
        OrderIntent(
            symbol="XBTUSD",
            side="sell",
            target_notional=100.0,
            why={"governance": {"decision_fatal": True}, "risk": {"decision_reason": "fatal"}},
        )
    )
    assert out.status == "skipped"
    assert out.reason == "profit_lock_sell_below_entry"
    assert fake.add_calls == 0


def test_flatten_all_positions_never_sells_if_profit_gate_blocks(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", "true")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.01"}
    fake.bid = 50000.0
    fake.ask = 50010.0
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.01
    ledger.avg_entry_price = 51000.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")

    closed, reason = svc.flatten_all_positions()

    assert closed is False
    assert reason == "profit_gate_block_open_positions"
    assert fake.add_calls == 0


def test_flatten_all_positions_sells_only_profit_gate_eligible_qty(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", "true")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.01"}
    fake.bid = 50000.0
    fake.ask = 50010.0
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.01
    ledger.avg_entry_price = 50400.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")
    ledger.lots = [
        PositionLot(qty=0.004, entry_price=48000.0),
        PositionLot(qty=0.006, entry_price=52000.0),
    ]

    closed, reason = svc.flatten_all_positions()

    assert closed is True
    assert reason == "flatten_best_effort"
    assert fake.add_calls == 1
    assert fake.add_params
    sent_qty = float(fake.add_params[-1]["volume"])
    assert sent_qty > 0.0
    assert sent_qty <= 0.00400001


def test_trade_volume_fee_profile_refresh_updates_fee_bps(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeKrakenSpotConnector()
    fake._trade_volume = {"fees": {"XBTUSD": {"fee": "0.40"}}}

    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)

    assert fake.trade_volume_calls >= 1
    assert svc._entry_fee_bps >= 40.0
    assert svc._exit_fee_bps >= 40.0


def test_sell_profit_lock_blocks_bootstrapped_unknown_cost_basis(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", "true")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_REQUIRE_COST_BASIS", "true")
    monkeypatch.setenv("AUTONOMOUS_BOOTSTRAP_BALANCE_POSITION", "true")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.01"}
    fake.bid = 50000.0
    fake.ask = 50010.0
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="sell", target_notional=100.0, why={}))
    assert out.status == "skipped"
    assert out.reason == "profit_lock_sell_below_entry"
    assert out.order is not None
    assert out.order["profit_lock_reason"] == "bootstrapped_without_trade_history"
    assert fake.add_calls == 0


def test_sell_uses_balance_buffer_to_avoid_oversell(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_SELL_BALANCE_BUFFER", "0.95")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.002"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.002
    ledger.avg_entry_price = 45000.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="sell", target_notional=500.0, why={}))
    assert out.status in {"submitted_limit_floor"}
    assert out.order is not None
    assert out.order["volume"] <= 0.0019 + 1e-12
    assert fake.add_params[-1]["ordertype"] == "limit"


def test_sell_uses_limit_floor_price_from_profit_gate(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_POST_ONLY", "true")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.01"}
    fake.bid = 50000.0
    fake.ask = 50010.0
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.01
    ledger.avg_entry_price = 45000.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")

    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="sell", target_notional=100.0, why={}))
    assert out.status == "submitted_limit_floor"
    assert out.order is not None
    assert float(out.order["price"]) >= float(out.order["required_exit_price"])
    assert fake.add_params[-1]["ordertype"] == "limit"
    assert fake.add_params[-1].get("type") == "sell"


def test_pairs_cache_ttl_refresh(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_CONSTRAINTS_TTL_S", "60")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)

    _ = svc.min_guard.load_pairs()
    _ = svc.min_guard.load_pairs()
    assert fake.asset_pairs_calls == 1

    svc.min_guard._cache_ts = time.time() - 120.0
    _ = svc.min_guard.load_pairs()
    assert fake.asset_pairs_calls == 2


def test_stale_snapshot_blocks_sell(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_STALE_SELL_BLOCK", "true")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.01"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    svc._ticker_cache["XBTUSD"] = {
        "pair": "XBTUSD",
        "bid": 49990.0,
        "ask": 50000.0,
        "bid_qty": 1.0,
        "ask_qty": 1.0,
        "mid": 49995.0,
        "spread_bps": 2.0,
        "ts": time.time() - 120.0,
    }

    def _broken_ticker(_pair=None):
        raise RuntimeError("feed down")

    fake.ticker = _broken_ticker  # type: ignore[method-assign]
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="sell", target_notional=100.0, why={}))
    assert out.status == "blocked"
    assert out.reason == "stale_market_data_sell_block"
    assert fake.add_calls == 0


def test_flatten_all_positions_never_market_sells_below_gate(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", "true")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.01"}
    fake.bid = 50000.0
    fake.ask = 50010.0
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.01
    ledger.avg_entry_price = 45000.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")

    closed, reason = svc.flatten_all_positions()
    assert closed is True
    assert reason in {"flatten_best_effort", "partial_flatten_profit_gate_block"}
    assert fake.add_calls >= 1
    assert all(p.get("ordertype") == "limit" for p in fake.add_params)


def test_entry_ladder_submits_multiple_post_only_orders(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_LADDER_ENABLED", "true")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_LADDER_STEPS", "4")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_LADDER_MIN_NOTIONAL", "10")
    monkeypatch.setenv("AUTONOMOUS_FEE_AWARE_SIZING", "false")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "2000.0", "XXBT": "0.0"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=400.0, why={"components": [{"edge_bps": 50.0, "cost_total_bps": 1.0}]}))
    assert out.status == "submitted_ladder"
    assert out.order is not None
    assert out.order["ladder_steps_submitted"] >= 2
    assert fake.add_calls >= 2
    for p in fake.add_params:
        assert p.get("ordertype") == "limit"
        assert p.get("type") == "buy"
        assert p.get("oflags") == "post"


def test_exit_repricing_anti_churn_skips_small_move(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_EXIT_CANCEL_REPLACE_MIN_MOVE_TICKS", "5")
    monkeypatch.setenv("AUTONOMOUS_EXIT_REPRICE_INTERVAL_S", "1")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.01"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.01
    ledger.avg_entry_price = 45000.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")
    fake._orders["OPEN1"] = {
        "status": "open",
        "vol_exec": "0.0",
        "opentm": time.time(),
        "params": {
            "pair": "XBTUSD",
            "type": "sell",
            "volume": "0.01000000",
            "price": "51000.0",
        },
    }
    svc._maybe_reprice_exit_orders("XBTUSD", bid=50000.0, ask=50010.0)
    assert fake.cancel_calls == 0


def test_exit_repricing_respects_cancel_replace_budget(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_EXIT_CANCEL_REPLACE_MIN_MOVE_TICKS", "1")
    monkeypatch.setenv("AUTONOMOUS_MAX_CANCEL_REPLACE_PER_MIN", "1")
    monkeypatch.setenv("AUTONOMOUS_EXIT_REPRICE_INTERVAL_S", "1")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.02"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.02
    ledger.avg_entry_price = 44000.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")
    now = time.time()
    fake._orders["OPEN1"] = {
        "status": "open",
        "vol_exec": "0.0",
        "opentm": now - 100.0,
        "params": {"pair": "XBTUSD", "type": "sell", "volume": "0.01000000", "price": "30000.0"},
    }
    fake._orders["OPEN2"] = {
        "status": "open",
        "vol_exec": "0.0",
        "opentm": now - 100.0,
        "params": {"pair": "XBTUSD", "type": "sell", "volume": "0.01000000", "price": "30000.0"},
    }

    svc._maybe_reprice_exit_orders("XBTUSD", bid=50000.0, ask=50010.0)
    assert fake.cancel_calls <= 1


def test_rate_limit_throttling_extends_cooldown(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_ENDPOINT_RATE_LIMIT_BUDGET", "1")
    monkeypatch.setenv("AUTONOMOUS_ENDPOINT_RETRY_BUDGET", "1")
    monkeypatch.setenv("AUTONOMOUS_RATE_LIMIT_COOLDOWN_S", "1")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)

    def _raise_rl():
        raise KrakenRateLimitError("429 rate limit")

    t0 = time.time()
    try:
        svc._call_with_retry(_raise_rl, "throttle_test")
    except KrakenRateLimitError:
        pass
    first_until = svc.rate_limit_cooldown_until_s
    assert first_until >= t0 + 1.0

    try:
        svc._call_with_retry(_raise_rl, "throttle_test")
    except KrakenRateLimitError:
        pass
    second_until = svc.rate_limit_cooldown_until_s
    assert second_until >= first_until


def test_sell_invariant_guard_trips_safe_mode_on_invalid_required_ratio(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ok, reason = svc._enforce_sell_profit_invariant(
        pair="XBTUSD",
        bid=50000.0,
        ask=50010.0,
        qty=0.001,
        gate_details={"required_net_profit_ratio": 0.01},
        slippage_bps=8.0,
    )
    assert ok is False
    assert reason == "sell_invariant_required_ratio_below_floor"
    assert svc.safe_mode is True


def test_execute_intent_buy_caps_size_to_available_quote(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "10.0", "XXBT": "0.0"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=1000.0, why={}))
    assert out.status in {"filled_maker", "submitted", "filled_taker_fallback"}
    assert out.order is not None
    assert out.order["notional"] <= 9.86


def test_adaptive_execution_can_override_config_to_maker(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_FEE_AWARE_SIZING", "false")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_MAKER_ONLY", "false")
    fake = _FakeKrakenSpotConnector()
    fake.bid = 49950.0
    fake.ask = 50050.0
    s = _settings(dry_run=False)
    s.execution.maker_preference = False
    svc = LiveKrakenSpotService(s, run_id="r1", connector=fake)
    intent = OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={"components": [{"edge_bps": 20.0, "cost_total_bps": 1.0}]})
    out = svc.execute_intent(intent)
    assert out.status == "filled_maker"
    assert out.order is not None
    assert out.order["execution_mode_reason"] == "adaptive_maker_override"


def test_adaptive_execution_uses_taker_on_tight_spread(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_FEE_AWARE_SIZING", "false")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_MAKER_ONLY", "false")
    fake = _FakeKrakenSpotConnector()
    fake.bid = 49999.0
    fake.ask = 50000.0
    s = _settings(dry_run=False)
    s.execution.maker_preference = True
    svc = LiveKrakenSpotService(s, run_id="r1", connector=fake)
    intent = OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={"components": [{"edge_bps": 20.0, "cost_total_bps": 1.0}]})
    out = svc.execute_intent(intent)
    assert out.status == "submitted"
    assert out.order is not None
    assert out.order["execution_mode_reason"] == "tight_spread_taker"


def test_sync_fill_ledger_updates_position_and_execution_qa(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_TRADES_HISTORY_LOOKBACK_S", "3600")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert out.order is not None
    txid = out.order.get("txid", "")
    import time

    fake._trades_history = {
        "TR1": {
            "pair": "XBTUSD",
            "type": "buy",
            "vol": "0.002",
            "price": "50010.0",
            "fee": "0.02",
            "time": str(time.time()),
            "ordertxid": txid,
        }
    }
    snap = svc.sync_fill_ledger("XBTUSD", mark_price=50020.0)
    assert snap["position_qty"] > 0.0
    assert snap["exposure_notional"] > 0.0
    qa = snap["execution_qa"]
    assert qa["orders_attempted"] >= 1.0
    assert qa["orders_filled"] >= 1.0
    assert qa["fill_probability"] > 0.0
    assert snap["min_trade_notional_quote"] >= 4.99


def test_sync_fill_ledger_can_bootstrap_position_from_base_balance(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_BOOTSTRAP_BALANCE_POSITION", "true")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "0.0", "XXBT": "0.0015"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    snap = svc.sync_fill_ledger("XBTUSD", mark_price=50000.0)
    assert snap["position_qty"] == 0.0015
    assert snap["exposure_notional"] > 0.0


def test_sync_fill_ledger_does_not_bootstrap_when_disabled(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.delenv("AUTONOMOUS_BOOTSTRAP_BALANCE_POSITION", raising=False)
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "0.0", "XXBT": "0.0015"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    snap = svc.sync_fill_ledger("XBTUSD", mark_price=50000.0)
    assert snap["position_qty"] == 0.0


def test_safe_profit_defaults_are_loaded(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.delenv("AUTONOMOUS_ENTRY_FEE_BPS", raising=False)
    monkeypatch.delenv("AUTONOMOUS_EXIT_FEE_BPS", raising=False)
    monkeypatch.delenv("AUTONOMOUS_PROFIT_GATE_SLIPPAGE_BPS", raising=False)
    monkeypatch.delenv("AUTONOMOUS_ENTRY_MAKER_ONLY", raising=False)
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=_FakeKrakenSpotConnector())
    assert svc._entry_fee_bps >= 30.0
    assert svc._exit_fee_bps >= 30.0
    assert svc._slippage_bps_profit_gate >= 15.0
    assert svc._entry_maker_only is True


def test_aggressive_hf_profile_defaults_are_loaded(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_PROFILE", "aggressive_hf")
    monkeypatch.delenv("AUTONOMOUS_ENTRY_LADDER_STEPS", raising=False)
    monkeypatch.delenv("AUTONOMOUS_ENTRY_LADDER_MAX_BPS", raising=False)
    monkeypatch.delenv("AUTONOMOUS_EXIT_REPRICE_INTERVAL_S", raising=False)
    monkeypatch.delenv("AUTONOMOUS_MAX_CANCEL_REPLACE_PER_MIN", raising=False)
    monkeypatch.delenv("AUTONOMOUS_MAX_OPEN_ORDERS_GLOBAL", raising=False)
    monkeypatch.delenv("AUTONOMOUS_MAX_OPEN_ORDERS_PER_SYMBOL", raising=False)
    monkeypatch.delenv("AUTONOMOUS_CANCEL_REPLACE_BUDGET_PER_SYMBOL_PER_MIN", raising=False)
    monkeypatch.delenv("AUTONOMOUS_SPREAD_HIGH_BPS", raising=False)
    monkeypatch.delenv("AUTONOMOUS_BOOK_MIN_DEPTH_QUOTE", raising=False)
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=_FakeKrakenSpotConnector())
    assert svc._entry_ladder_steps == 3
    assert svc._entry_ladder_max_bps == 10.0
    assert svc._exit_reprice_interval_s == 10.0
    assert svc._max_cancel_replace_per_min == 60
    assert svc._max_open_orders_global == 120
    assert svc._max_open_orders_per_symbol == 8
    assert svc._cancel_replace_budget_per_symbol_per_min == 12
    assert svc._no_trade_zone_spread_bps == 40.0
    assert svc._book_min_depth_quote == 120.0


def test_probe_distance_ticks_is_applied_to_maker_probe_buy(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_LADDER_ENABLED", "false")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(
        OrderIntent(
            symbol="XBTUSD",
            side="buy",
            target_notional=100.0,
            why={
                "scheduler_probe": True,
                "probe_distance_ticks": 3,
                "execution_route": {"order_type": "maker"},
            },
        )
    )
    assert out.status in {"filled_maker", "submitted"}
    assert fake.add_calls >= 1
    sent_price = float(fake.add_params[0]["price"])
    assert abs(sent_price - 49990.3) < 1e-9


def test_buy_blocks_when_open_order_caps_reached(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_MAX_OPEN_ORDERS_GLOBAL", "1")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_MAKER_ONLY", "false")
    fake = _FakeKrakenSpotConnector()
    fake._orders["OPEN1"] = {
        "status": "open",
        "vol_exec": "0.0",
        "params": {"pair": "XBTUSD", "type": "buy", "volume": "0.001", "price": "49000.0"},
    }
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert out.status == "blocked"
    assert out.reason == "max_open_orders_global"


def test_expected_fill_probability_gate_blocks_low_depth_buy(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_EXPECTED_FILL_PROB_GATE", "true")
    monkeypatch.setenv("AUTONOMOUS_BOOK_MIN_DEPTH_QUOTE", "50000")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_MAKER_ONLY", "false")
    fake = _FakeKrakenSpotConnector()
    fake.bid_qty = 0.001
    fake.ask_qty = 0.001
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert out.status == "blocked"
    assert out.reason in {"expected_fill_probability_low", "no_trade_zone"}


def test_exit_repricing_respects_min_time_between_reprices(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_EXIT_REPRICE_INTERVAL_S", "1")
    monkeypatch.setenv("AUTONOMOUS_EXIT_MIN_TIME_BETWEEN_REPRICE_S", "60")
    monkeypatch.setenv("AUTONOMOUS_EXIT_CANCEL_REPLACE_MIN_MOVE_TICKS", "1")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1000.0", "XXBT": "0.02"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.02
    ledger.avg_entry_price = 44000.0
    ledger.bootstrapped_from_balance = True
    ledger.trade_ids.add("seed")
    now = time.time()
    fake._orders["OPEN1"] = {
        "status": "open",
        "vol_exec": "0.0",
        "opentm": now - 100.0,
        "params": {"pair": "XBTUSD", "type": "sell", "volume": "0.02000000", "price": "30000.0"},
    }
    svc._maybe_reprice_exit_orders("XBTUSD", bid=50000.0, ask=50010.0)
    first_cancel_calls = fake.cancel_calls
    assert first_cancel_calls <= 1
    svc._maybe_reprice_exit_orders("XBTUSD", bid=50000.0, ask=50010.0)
    assert fake.cancel_calls == first_cancel_calls


def test_sync_fill_ledger_does_not_bootstrap_dust_below_ordermin(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_BOOTSTRAP_BALANCE_POSITION", "true")
    monkeypatch.setenv("AUTONOMOUS_BOOTSTRAP_REQUIRE_TRADEABLE", "true")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "0.0", "XXBT": "0.00005"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    snap = svc.sync_fill_ledger("XBTUSD", mark_price=50000.0)
    assert snap["position_qty"] == 0.0
    assert snap["exposure_notional"] == 0.0


def test_pretrade_guard_blocks_exposure_breach(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    s = _settings(dry_run=False)
    s.risk.max_exposure_notional = 100.0
    s.risk.max_position_notional = 100.0
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(s, run_id="r1", connector=fake)
    ledger = svc._ledger_for("XBTUSD")
    ledger.position_qty = 0.002
    ledger.avg_entry_price = 50000.0
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert out.status == "blocked"
    assert out.reason == "pretrade_exposure_notional"


def test_sell_inventory_below_min_order_skips_when_notional_too_small(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_SPOT_DUST_ACCUMULATOR", "true")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "0.0", "XXBT": "0.0001"}
    original_asset_pairs = fake.asset_pairs

    def _asset_pairs_with_costmin():
        out = original_asset_pairs()
        out["XBTUSD"]["costmin"] = "8.0"
        return out

    fake.asset_pairs = _asset_pairs_with_costmin  # type: ignore[method-assign]
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="sell", target_notional=5.0, why={}))
    assert out.status == "skipped"
    assert out.reason == "inventory_below_min_order"
    assert out.order is not None
    assert "exchange_constraints" in out.order
    assert fake.add_calls == 0


def test_execute_intent_rate_limit_cooldown_then_succeeds(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_RATE_LIMIT_COOLDOWN_S", "0.25")
    monkeypatch.setenv("AUTONOMOUS_KRAKEN_EXEC_RETRY_ATTEMPTS", "1")
    fake = _FakeKrakenSpotConnector()
    fake.rate_limit_failures_remaining = 1
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    first = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert first.status == "blocked"
    assert first.reason == "rate_limit_cooldown"
    assert fake.add_calls == 1

    second = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert second.status == "blocked"
    assert second.reason == "rate_limit_cooldown"
    assert fake.add_calls == 1

    import time

    time.sleep(0.5)
    third = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert third.status in {"filled_maker", "submitted", "filled_taker_fallback"}
    assert fake.add_calls == 2


def test_execute_intent_enforces_eapi_rate_limit_cooldown(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_RATE_LIMIT_COOLDOWN_S", "5")
    monkeypatch.setenv("AUTONOMOUS_KRAKEN_RATE_LIMIT_STORM", "1")
    monkeypatch.setenv("AUTONOMOUS_KRAKEN_EXEC_RETRY_ATTEMPTS", "1")
    fake = _FakeKrakenSpotConnector()
    fake.fail_eapi_rate_limit = True
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    first = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert first.status == "blocked"
    assert first.reason == "rate_limit_cooldown"
    assert fake.add_calls == 1
    assert svc.killed is False

    fake.fail_eapi_rate_limit = False
    second = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert second.status == "blocked"
    assert second.reason == "rate_limit_cooldown"
    assert fake.add_calls == 1
    assert fake.cancel_calls == 0
    assert svc.killed is False


def test_execute_intent_temporary_lockout_enters_extended_cooldown(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_RATE_LIMIT_COOLDOWN_S", "0.25")
    monkeypatch.setenv("AUTONOMOUS_KRAKEN_TEMP_LOCKOUT_COOLDOWN_S", "1.0")
    monkeypatch.setenv("AUTONOMOUS_KRAKEN_EXEC_RETRY_ATTEMPTS", "1")
    fake = _FakeKrakenSpotConnector()
    fake.fail_temporary_lockout = True
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)

    first = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert first.status == "blocked"
    assert first.reason == "rate_limit_cooldown"
    assert fake.add_calls == 1
    assert svc._temporary_lockout_until_s >= time.time()

    fake.fail_temporary_lockout = False
    second = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert second.status == "blocked"
    assert second.reason == "rate_limit_cooldown"
    assert fake.add_calls == 1

    time.sleep(1.1)
    third = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert third.status in {"filled_maker", "submitted", "filled_taker_fallback"}
    assert fake.add_calls == 2


def test_sync_fill_ledger_temporary_lockout_uses_snapshot_fallback(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_KRAKEN_TEMP_LOCKOUT_COOLDOWN_S", "1.0")
    fake = _FakeKrakenSpotConnector()
    fake.fail_trades_temporary_lockout = True
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)

    snap = svc.sync_fill_ledger("XBTUSD", mark_price=50000.0)
    assert isinstance(snap, dict)
    assert "position_qty" in snap
    assert fake.trades_history_calls == 1
    assert svc.rate_limit_cooldown_until_s >= time.time()

    _ = svc.sync_fill_ledger("XBTUSD", mark_price=50000.0)
    assert fake.trades_history_calls == 1


def test_sync_fill_ledger_respects_min_interval(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_TRADES_SYNC_MIN_INTERVAL_S", "999")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    _ = svc.sync_fill_ledger("XBTUSD", mark_price=50000.0)
    _ = svc.sync_fill_ledger("XBTUSD", mark_price=50010.0)
    assert fake.trades_history_calls == 1


def test_sync_fill_ledger_ignores_old_history_before_since_ts(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_TRADES_HISTORY_LOOKBACK_S", "0")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    fake._trades_history = {
        "OLD": {
            "pair": "XBTUSD",
            "type": "buy",
            "vol": "0.001",
            "price": "50000.0",
            "fee": "0.01",
            "time": "1700000000.0",
        }
    }
    snap = svc.sync_fill_ledger("XBTUSD", mark_price=50000.0)
    assert snap["position_qty"] == 0.0


def test_execute_intent_respects_router_taker_hint(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_MAKER_ONLY", "false")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(
        OrderIntent(
            symbol="XBTUSD",
            side="buy",
            target_notional=100.0,
            why={"execution_route": {"order_type": "taker"}},
        )
    )
    assert out.status in {"submitted", "filled_taker_fallback", "filled_maker"}
    assert out.order is not None
    assert out.order.get("execution_mode") == "taker"


def test_execute_intent_blocks_taker_when_disabled(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_KRAKEN_TAKER_FALLBACK", "false")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_MAKER_ONLY", "false")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(
        OrderIntent(
            symbol="XBTUSD",
            side="buy",
            target_notional=100.0,
            why={"execution_route": {"order_type": "taker"}},
        )
    )
    assert out.status == "blocked"
    assert out.reason == "taker_disabled"
    assert fake.add_calls == 0


def test_entry_block_auto_recovers_after_cooldown(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_NO_NEW_ENTRIES_AFTER_FAILED_PROBES_N", "1")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_BLOCK_COOLDOWN_S", "60")
    monkeypatch.setenv("AUTONOMOUS_ENTRY_MAKER_ONLY", "false")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)

    svc._record_probe_result(is_probe=True, success=False, reason="hard_failure")
    assert svc._entries_blocked_until_health_ok is True

    svc._entries_blocked_until_ts = time.time() - 1.0
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={"scheduler_probe": True}))
    assert out.status in {"filled_maker", "filled_taker_fallback", "submitted", "submitted_ladder"}
    assert svc._entries_blocked_until_health_ok is False


def test_trades_snapshot_permission_denied_fallback(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)

    def _raise_permission(_start=None):  # noqa: ARG001
        raise RuntimeError("EGeneral:Permission denied")

    fake.trades_history = _raise_permission  # type: ignore[method-assign]
    snap = svc._trades_snapshot(force_refresh=True)
    assert isinstance(snap, dict)
    assert snap == {}
