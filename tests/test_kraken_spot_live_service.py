import os

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
from autonomous_investment_robot.services.policy.service import OrderIntent


class _FakeKrakenSpotConnector:
    def __init__(self) -> None:
        self._has_credentials = True
        self.add_calls = 0
        self.fail_rate_limit = False
        self.fail_insufficient = False
        self._balance = {"ZUSD": "1000.0", "XXBT": "0.0"}

    @property
    def has_credentials(self):
        return self._has_credentials

    def verify_live_permissions(self):
        return True, "ok"

    def asset_pairs(self):
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
        return {"XBTUSD": {"a": ["50000.0"], "b": ["49990.0"], "c": ["50000.0"], "v": ["0", "1000000"]}}

    def balance(self):
        return dict(self._balance)

    def add_order(self, params):
        self.add_calls += 1
        if self.fail_rate_limit:
            from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenRateLimitError

            raise KrakenRateLimitError("429 rate limit")
        if self.fail_insufficient:
            from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenInsufficientFundsError

            raise KrakenInsufficientFundsError("insufficient funds")
        return {"descr": {"order": "buy"}, "txid": [f"T{self.add_calls}"]}

    def cancel_all(self):
        return {"count": 0}


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


def test_execute_intent_submits_market_buy(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeKrakenSpotConnector()
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert out.status == "submitted"
    assert out.reason == "spot_order_submitted"
    assert out.order is not None
    assert out.order["txid"] == "T1"
    assert fake.add_calls == 1


def test_execute_intent_blocks_small_order(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=_FakeKrakenSpotConnector())
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=0.01, why={}))
    assert out.status == "blocked"
    assert out.reason == "min_order_block"


def test_execute_intent_blocks_insufficient_balance(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeKrakenSpotConnector()
    fake._balance = {"ZUSD": "1.0"}
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    out = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert out.status == "blocked"
    assert out.reason == "insufficient_balance_block"


def test_rate_limit_storm_kills_service(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeKrakenSpotConnector()
    fake.fail_rate_limit = True
    svc = LiveKrakenSpotService(_settings(dry_run=False), run_id="r1", connector=fake)
    last = None
    for _ in range(5):
        last = svc.execute_intent(OrderIntent(symbol="XBTUSD", side="buy", target_notional=100.0, why={}))
    assert last is not None
    assert last.status == "killed"
    assert last.reason == "rate_limit_storm"
    assert svc.killed is True
