from autonomous_investment_robot.config.settings import ExecutionSettings, RiskLimits, RobotSettings, StorageSettings, TCOSettings
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator


class _FakeConnector:
    def __init__(self, *, positions=None, open_orders=None):
        self._positions = positions or []
        self._open_orders = open_orders or []

    def position_risk(self, symbol=None):  # noqa: ARG002
        return list(self._positions)

    def open_orders(self, symbol=None):  # noqa: ARG002
        return list(self._open_orders)


class _FakeLive:
    def __init__(self, connector):
        self.connector = connector

    def rehydrate_state(self, order_events, fill_events):
        return {"orders": len(order_events), "fills": len(fill_events)}


def _limits() -> RiskLimits:
    return RiskLimits(
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
    )


def _settings(tmp_path) -> RobotSettings:
    return RobotSettings(
        provider_whitelist=["binance_um_perps"],
        execution=ExecutionSettings(mode="live_readonly"),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        storage=StorageSettings(run_dir=str(tmp_path)),
    )


def test_rehydrate_live_state_is_insufficient_without_local_history(tmp_path):
    orchestrator = RobotOrchestrator(_settings(tmp_path))
    live = _FakeLive(_FakeConnector(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "markPrice": "100.0"}]))

    confidence, details = orchestrator._rehydrate_live_state(live, "BTCUSDT")

    assert confidence == "insufficient"
    assert details["reason"] == "exchange_exposure_without_local_history"


def test_rehydrate_live_state_is_trusted_when_local_and_exchange_match(tmp_path):
    orchestrator = RobotOrchestrator(_settings(tmp_path))
    orchestrator.event_store.append(
        "fills",
        {
            "payload": {
                "venue": "paper",
                "order_id": "o1",
                "fill_id": "f1",
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100.0,
                "fee": 0.2,
                "slippage_cost": 0.1,
                "status": "filled_partial_maker",
            }
        },
    )
    orchestrator.event_store.append(
        "positions",
        {"payload": {"symbol": "BTCUSDT", "exposure_notional": 100.0}},
    )
    live = _FakeLive(_FakeConnector(positions=[{"symbol": "BTCUSDT", "positionAmt": "1.0", "markPrice": "100.0"}]))

    confidence, details = orchestrator._rehydrate_live_state(live, "BTCUSDT")

    assert confidence == "trusted"
    assert details["reason"] == "rehydrated"


def test_recover_live_state_detects_orphan_order_and_requests_flatten_only(tmp_path):
    orchestrator = RobotOrchestrator(_settings(tmp_path))
    live = _FakeLive(_FakeConnector(open_orders=[{"symbol": "BTCUSDT", "clientOrderId": "cid-1", "status": "NEW"}]))
    live.connector.cancel_order = lambda symbol, order_id: None

    decision = orchestrator._recover_live_state(live, "BTCUSDT", "trusted")

    assert decision.action == "flatten_only"
    assert decision.orphan_orders == 1


def test_recover_live_state_uses_safe_mode_boot_on_open_local_order(tmp_path):
    orchestrator = RobotOrchestrator(_settings(tmp_path))
    orchestrator.event_store.append(
        "orders",
        {"payload": {"clientOrderId": "cid-1", "orderId": "o-1", "status": "NEW", "symbol": "BTCUSDT"}},
    )
    live = _FakeLive(_FakeConnector())

    decision = orchestrator._recover_live_state(live, "BTCUSDT", "trusted")

    assert decision.outcome == "safe_mode_boot"
    assert decision.action == "degrade"
