from types import SimpleNamespace

from autonomous_investment_robot.core.contracts import MarketHealthSnapshot, TruthConfidenceLevel, UnrealizedPnlTruth
from autonomous_investment_robot.services.event_store.service import EventStore
from autonomous_investment_robot.services.execution.service import Fill
from autonomous_investment_robot.services.forensics_service.service import ForensicsService
from autonomous_investment_robot.services.live_runtime.ledger import NormalizedLiveFillRecord
from autonomous_investment_robot.services.live_runtime.service import LiveLedgerCoordinator, LiveStateCoordinator
from autonomous_investment_robot.services.observability_service.service import ObservabilityService
from autonomous_investment_robot.services.ops.service import OpsService
from autonomous_investment_robot.services.portfolio_service.service import PortfolioService
from autonomous_investment_robot.services.reconciliation.service import ReconciliationAction, ReconciliationService
from datetime import datetime, timezone


class FakeConnector:
    provider_id = "binance_um_perps"

    def __init__(self, *, balances=None, positions=None, open_orders=None):
        self._balances = balances or []
        self._positions = positions or []
        self._open_orders = open_orders or []
        self.cancelled: list[tuple[str | None, str | None]] = []

    def balances(self):
        return list(self._balances)

    def position_risk(self, symbol=None):  # noqa: ARG002
        return list(self._positions)

    def open_orders(self, symbol=None):  # noqa: ARG002
        return list(self._open_orders)

    def cancel_order(self, symbol, order_id):
        self.cancelled.append((symbol, order_id))


def test_live_state_coordinator_detects_realized_pnl_mismatch(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    portfolio.seed_account_balance(1000.0)
    portfolio.record_fill(Fill("paper", "o1", "f1", "BTCUSDT", "buy", 10.0, 0.0, 0.0, 0, "filled"))
    portfolio.record_fill(Fill("paper", "o2", "f2", "BTCUSDT", "sell", 10.0, 0.0, 0.0, 0, "filled"), realized_pnl=5.0)
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())
    live = SimpleNamespace(
        connector=FakeConnector(
            balances=[{"equity": "1015.0"}],
            positions=[],
            open_orders=[],
        )
    )

    report = coordinator.reconcile_state(live, "BTCUSDT", internal_exposure=0.0)

    assert report.code == "live_realized_pnl_proxy_mismatch"
    assert report.action == ReconciliationAction.DEGRADE


def test_live_state_coordinator_degrades_when_unrealized_truth_is_unavailable(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    portfolio.mark_to_market("BTCUSDT", 4.0)
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())
    live = SimpleNamespace(
        connector=FakeConnector(
            balances=[{"equity": "1015.0"}],
            positions=[{"symbol": "BTCUSDT", "positionAmt": "0.1"}],
            open_orders=[],
        )
    )

    report = coordinator.reconcile_state(live, "BTCUSDT", internal_exposure=0.0)

    assert report.action == ReconciliationAction.DEGRADE
    assert report.details["truth_confidence"]["unrealized_pnl_confidence"]["level"] == TruthConfidenceLevel.UNAVAILABLE.value


def test_live_state_coordinator_rehydrates_missing_exchange_fill_history(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())
    live = SimpleNamespace(
        connector=FakeConnector(
            balances=[{"equity": "1005.0"}],
            positions=[{"symbol": "BTCUSDT", "positionAmt": "0.1", "markPrice": "100.0"}],
            open_orders=[],
        ),
        rehydrate_state=lambda order_events, fill_events: {"orders": len(order_events), "fills": len(fill_events)},
        authoritative_fill_history=lambda symbol, side, since_ms=None: (
            [
                NormalizedLiveFillRecord(
                    fill=Fill("binance_um_perps", "order-1", "fill-1", symbol, "buy", 10.0, 0.02, 0.0, 0, "filled"),
                    realized_pnl=1.5,
                    fee_authoritative=True,
                    realized_pnl_authoritative=True,
                )
            ],
            [],
        ),
        authoritative_realized_pnl=lambda symbol, since_ms=None: (1.5, []),
    )

    result = coordinator.rehydrate_state(live, "BTCUSDT")

    assert result.confidence == "degraded"
    assert result.details["reason"] == "rehydrated_from_exchange_history"
    assert result.details["exchange_history_rehydrate"]["recovered"] == 1
    assert result.details["truth_confidence"]["fill_truth_confidence"]["level"] == TruthConfidenceLevel.PROXY.value
    assert portfolio.snapshot("BTCUSDT").fill_count == 1
    assert len(event_store.load("fills")) == 1


def test_live_state_coordinator_trusts_authoritative_kraken_spot_exchange_history_boot(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())

    class SpotConnector(FakeConnector):
        provider_id = "kraken_spot"

        def base_balance(self, symbol=None):  # noqa: ARG002
            return {"total": "0.00017922", "free": "0.00017922", "used": "0.0"}

        def book_ticker(self, symbol=None):  # noqa: ARG002
            return {"bidPrice": "74078.9", "askPrice": "74079.0"}

        def market_constraints(self, symbol=None):  # noqa: ARG002
            return {"min_order_size": "0.0001"}

    baseline_ts_ms = 1775382978325
    live = SimpleNamespace(
        connector=SpotConnector(
            balances=[{"equity": "10.6726187728"}],
            positions=[],
            open_orders=[],
        ),
        rehydrate_state=lambda order_events, fill_events: {"orders": len(order_events), "fills": len(fill_events)},
        authoritative_fill_history=lambda symbol, side, since_ms=None: (
            [
                NormalizedLiveFillRecord(
                    fill=Fill(
                        "kraken_spot",
                        "order-1",
                        "fill-1",
                        symbol,
                        "buy",
                        12.02963,
                        0.03,
                        0.0,
                        0,
                        "filled",
                    ),
                    realized_pnl=0.0,
                    fee_authoritative=True,
                    realized_pnl_authoritative=False,
                    metadata={"timestamp_ms": baseline_ts_ms, "price": 67029.3, "base_qty": 0.00017922},
                    truth_evidence={"source": "kraken_spot_trade_history"},
                )
            ],
            [],
        ),
        authoritative_realized_pnl=lambda symbol, since_ms=None: (0.0, []),
        authoritative_unrealized_pnl=lambda symbol: (
            UnrealizedPnlTruth(
                symbol=symbol,
                ts=datetime.now(timezone.utc),
                source="spot_trade_history_and_balance",
                confidence="authoritative",
                venue_value=1.2467904580000013,
                reason="fifo_cost_basis_and_live_bid",
                evidence={"remaining_qty": 0.00017922, "remaining_basis_quote": 12.02963, "bid": 74078.9},
            ),
            [],
        ),
    )

    result = coordinator.rehydrate_state(live, "BTC/USD")

    assert result.confidence == "trusted"
    assert result.details["reason"] == "authoritative_exchange_history_rehydrate"
    assert result.details["exchange_history_rehydrate"]["since_ms"] == baseline_ts_ms
    assert result.details["truth_confidence"]["fill_truth_confidence"]["level"] == TruthConfidenceLevel.AUTHORITATIVE.value
    assert result.details["truth_confidence"]["fee_truth_confidence"]["level"] == TruthConfidenceLevel.AUTHORITATIVE.value
    assert result.details["truth_confidence"]["realized_pnl_confidence"]["level"] == TruthConfidenceLevel.AUTHORITATIVE.value
    account_payload = event_store.load("account")[0]["payload"]
    assert account_payload["metadata"]["baseline_recorded_at_ms"] == baseline_ts_ms


def test_live_state_coordinator_skips_exchange_history_rehydrate_for_flat_boot_without_local_history(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())
    calls = {"authoritative_fill_history": 0}

    def _authoritative_fill_history(symbol, side, since_ms=None):  # noqa: ARG001
        calls["authoritative_fill_history"] += 1
        return [], ["unexpected_history_fetch"]

    live = SimpleNamespace(
        connector=FakeConnector(
            balances=[{"equity": "1000.0"}],
            positions=[],
            open_orders=[],
        ),
        rehydrate_state=lambda order_events, fill_events: {"orders": len(order_events), "fills": len(fill_events)},
        authoritative_fill_history=_authoritative_fill_history,
        authoritative_unrealized_pnl=lambda symbol: (
            UnrealizedPnlTruth(
                symbol=symbol,
                ts=datetime.now(timezone.utc),
                source="spot_balance_flat",
                confidence="authoritative",
                venue_value=0.0,
                reason="no_open_spot_inventory",
                evidence={"remaining_qty": 0.0, "tolerance_qty": 0.0001},
            ),
            [],
        ),
    )

    result = coordinator.rehydrate_state(live, "BTCUSDT")

    assert result.confidence == "trusted"
    assert result.details["reason"] == "flat_and_consistent"
    assert result.details["exchange_history_rehydrate"]["recovered"] == 0
    assert result.details["exchange_history_rehydrate"]["skipped"] == "flat_account_boot_baseline"
    assert result.details["truth_confidence"]["fill_truth_confidence"]["level"] == TruthConfidenceLevel.AUTHORITATIVE.value
    assert calls["authoritative_fill_history"] == 0


def test_truth_confidence_marks_market_data_proxy_when_health_is_missing(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())

    snapshot = coordinator.truth_confidence(
        exchange=coordinator.exchange_state(SimpleNamespace(connector=FakeConnector(balances=[{"equity": "1000.0"}], positions=[], open_orders=[])), "BTCUSDT"),
        fill_history_gaps=[],
        realized_pnl_gaps=[],
        history_since_ms=None,
        history_recovered=0,
    )

    assert snapshot.market_data_truth_confidence.level == TruthConfidenceLevel.PROXY
    assert snapshot.overall_action == "degrade"


def test_truth_confidence_defers_market_data_gate_at_boot_until_first_snapshot(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())
    exchange = coordinator.exchange_state(
        SimpleNamespace(connector=FakeConnector(balances=[{"equity": "1000.0"}], positions=[], open_orders=[])),
        "BTCUSDT",
    )

    snapshot = coordinator.truth_confidence(
        exchange=exchange,
        fill_history_gaps=[],
        realized_pnl_gaps=[],
        unrealized_truth=exchange.unrealized_pnl_truth,
        history_since_ms=None,
        history_recovered=0,
        defer_market_data_gate=True,
    )

    assert snapshot.market_data_truth_confidence.level == TruthConfidenceLevel.PROXY
    assert snapshot.market_data_truth_confidence.reason == "market_health_deferred_until_first_snapshot"
    assert snapshot.overall_action == "continue"
    assert snapshot.metadata["market_data_gate_deferred"] is True


def test_truth_confidence_treats_spot_dust_without_open_inventory_as_authoritative(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())
    exchange = coordinator.exchange_state(
        SimpleNamespace(
            connector=FakeConnector(
                balances=[{"equity": "1000.0"}],
                positions=[{"symbol": "ETH/EUR", "positionAmt": "0.0002367356", "markPrice": "1821.0"}],
                open_orders=[],
            ),
            authoritative_unrealized_pnl=lambda symbol: (
                UnrealizedPnlTruth(
                    symbol=symbol,
                    ts=datetime.now(timezone.utc),
                    source="spot_balance_flat",
                    confidence="authoritative",
                    venue_value=0.0,
                    reason="no_open_spot_inventory",
                    evidence={"remaining_qty": 0.0002367356, "tolerance_qty": 0.001},
                ),
                [],
            ),
        ),
        "ETH/EUR",
    )

    snapshot = coordinator.truth_confidence(
        exchange=exchange,
        fill_history_gaps=[],
        realized_pnl_gaps=[],
        unrealized_truth=exchange.unrealized_pnl_truth,
        history_since_ms=None,
        history_recovered=0,
        defer_market_data_gate=True,
    )

    assert snapshot.fill_truth_confidence.level == TruthConfidenceLevel.AUTHORITATIVE
    assert snapshot.fee_truth_confidence.level == TruthConfidenceLevel.AUTHORITATIVE
    assert snapshot.realized_pnl_confidence.level == TruthConfidenceLevel.AUTHORITATIVE
    assert snapshot.overall_action == "continue"


def test_truth_confidence_marks_market_data_unavailable_when_feed_is_stale(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())
    market_health = MarketHealthSnapshot(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        feed_stale=True,
        sequence_ok=True,
        checksum_ok=True,
        symbol_health_score=0.8,
        exchange_health_score=0.8,
        market_quality_score=0.8,
        reasons=["feed_stale"],
    )
    snapshot = coordinator.truth_confidence(
        exchange=coordinator.exchange_state(SimpleNamespace(connector=FakeConnector(balances=[{"equity": "1000.0"}], positions=[], open_orders=[])), "BTCUSDT"),
        market_health=market_health,
    )

    assert snapshot.market_data_truth_confidence.level == TruthConfidenceLevel.UNAVAILABLE
    assert snapshot.overall_action == "flatten_only"


def test_truth_confidence_marks_unrealized_proxy_when_derived_from_entry_and_mark(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())
    exchange = coordinator.exchange_state(
        SimpleNamespace(
            connector=FakeConnector(
                balances=[{"equity": "1000.0"}],
                positions=[{"symbol": "BTCUSDT", "positionAmt": "0.1", "markPrice": "100.0", "entryPrice": "95.0"}],
                open_orders=[],
            )
        ),
        "BTCUSDT",
    )

    snapshot = coordinator.truth_confidence(exchange=exchange, unrealized_truth=exchange.unrealized_pnl_truth)

    assert exchange.unrealized_pnl_truth.confidence == "proxy"
    assert snapshot.unrealized_pnl_confidence is not None
    assert snapshot.unrealized_pnl_confidence.level == TruthConfidenceLevel.PROXY
    assert snapshot.overall_action == "degrade"


def test_truth_confidence_marks_unrealized_unavailable_when_position_fields_are_incomplete(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())
    exchange = coordinator.exchange_state(
        SimpleNamespace(
            connector=FakeConnector(
                balances=[{"equity": "1000.0"}],
                positions=[{"symbol": "BTCUSDT", "positionAmt": "0.1"}],
                open_orders=[],
            )
        ),
        "BTCUSDT",
    )

    snapshot = coordinator.truth_confidence(exchange=exchange, unrealized_truth=exchange.unrealized_pnl_truth)

    assert exchange.unrealized_pnl_truth.confidence == "unavailable"
    assert snapshot.unrealized_pnl_confidence is not None
    assert snapshot.unrealized_pnl_confidence.level == TruthConfidenceLevel.UNAVAILABLE
    assert snapshot.overall_action == "degrade"


def test_live_state_coordinator_boot_truth_does_not_degrade_only_because_market_health_is_deferred(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())
    live = SimpleNamespace(
        connector=FakeConnector(
            balances=[{"equity": "1000.0"}],
            positions=[],
            open_orders=[],
        ),
        rehydrate_state=lambda order_events, fill_events: {"orders": len(order_events), "fills": len(fill_events)},
        authoritative_unrealized_pnl=lambda symbol: (
            UnrealizedPnlTruth(
                symbol=symbol,
                ts=datetime.now(timezone.utc),
                source="spot_balance_flat",
                confidence="authoritative",
                venue_value=0.0,
                reason="no_open_spot_inventory",
                evidence={"remaining_qty": 0.0, "tolerance_qty": 0.0001},
            ),
            [],
        ),
    )

    result = coordinator.rehydrate_state(live, "BTCUSDT")

    assert result.confidence == "trusted"
    assert result.details["truth_confidence"]["market_data_truth_confidence"]["level"] == TruthConfidenceLevel.PROXY.value
    assert result.details["truth_confidence"]["market_data_truth_confidence"]["reason"] == "market_health_deferred_until_first_snapshot"
    assert result.details["truth_confidence"]["overall_action"] == "continue"
    assert result.details["truth_confidence"]["metadata"]["market_data_gate_deferred"] is True


def test_live_ledger_coordinator_does_not_guess_exposure_without_normalized_fill(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveLedgerCoordinator(event_store, portfolio)
    live = SimpleNamespace(enter_flatten_only=lambda reason: setattr(live, "reason", reason))
    result = SimpleNamespace(status="filled_maker", order={"clientOrderId": "cid-1"}, ledger_records=[], gaps=[])

    applied = coordinator.apply_execution_result(
        symbol="BTCUSDT",
        provider_id="binance_um_perps",
        result=result,
        fallback_intent_notional=50.0,
        fallback_side="buy",
        current_exposure=0.0,
        live=live,
    )

    assert applied.fill_truth_ok is False
    assert applied.exposure_notional == 0.0
    assert "normalized_fill_missing" in applied.gap_reasons
    assert getattr(live, "reason") == "live_fill_truth_gap"


def test_live_ledger_coordinator_persists_fill_and_account_events(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    portfolio.seed_account_balance(1000.0)
    observability = ObservabilityService(str(tmp_path), OpsService(str(tmp_path)))
    coordinator = LiveLedgerCoordinator(event_store, portfolio, observability, ForensicsService(str(tmp_path), observability))
    record = NormalizedLiveFillRecord(
        fill=Fill("binance_um_perps", "order-1", "fill-1", "BTCUSDT", "buy", 10.0, 0.02, 0.0, 0, "filled"),
        realized_pnl=1.5,
        fee_authoritative=True,
        realized_pnl_authoritative=True,
        gaps=[],
        truth_evidence={"source": "user_trades", "history_window_covered": True},
    )
    result = SimpleNamespace(status="filled_maker", order={"clientOrderId": "cid-1"}, ledger_records=[record], gaps=[])

    applied = coordinator.apply_execution_result(
        symbol="BTCUSDT",
        provider_id="binance_um_perps",
        result=result,
        fallback_intent_notional=10.0,
        fallback_side="buy",
        current_exposure=0.0,
    )

    assert applied.fill_truth_ok is True
    assert applied.exposure_notional == 10.0
    assert len(event_store.load("fills")) == 1
    assert len(event_store.load("account")) == 1
    assert event_store.load("fills")[0]["payload"]["truth_evidence"]["source"] == "user_trades"
    assert (tmp_path / "fills_journal.jsonl").exists()
    assert (tmp_path / "accounting_truth_journal.jsonl").exists()
    assert (tmp_path / "pnl_attribution.jsonl").exists()


def test_live_ledger_coordinator_persists_lifecycle_transitions(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveLedgerCoordinator(event_store, portfolio, ObservabilityService(str(tmp_path), OpsService(str(tmp_path))))
    live = SimpleNamespace(
        drain_lifecycle_transitions=lambda: [
            {
                "symbol": "BTCUSDT",
                "venue": "binance_um_perps",
                "ts": datetime.now(timezone.utc),
                "order_key": "cid-1",
                "from_state": "submitted",
                "to_state": "accepted",
                "source": "exchange_order_update",
                "reason": "new",
                "accepted": True,
                "duplicate": False,
                "out_of_order": False,
                "metadata": {},
            }
        ]
    )
    result = SimpleNamespace(status="deduped", order={"clientOrderId": "cid-1"}, ledger_records=[], gaps=[])

    coordinator.apply_execution_result(
        symbol="BTCUSDT",
        provider_id="binance_um_perps",
        result=result,
        fallback_intent_notional=0.0,
        fallback_side="buy",
        current_exposure=0.0,
        live=live,
    )

    order_events = event_store.load("orders")
    assert any(event["event_type"] == "ORDER_LIFECYCLE_TRANSITION" for event in order_events)
    assert (tmp_path / "lifecycle_journal.jsonl").exists()


def test_live_ledger_coordinator_flattens_on_fee_truth_gap(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveLedgerCoordinator(event_store, portfolio)
    live = SimpleNamespace(enter_flatten_only=lambda reason: setattr(live, "reason", reason))
    record = NormalizedLiveFillRecord(
        fill=Fill("binance_um_perps", "order-1", "fill-1", "BTCUSDT", "buy", 10.0, 0.0, 0.0, 0, "filled"),
        realized_pnl=0.0,
        fee_authoritative=False,
        realized_pnl_authoritative=True,
        gaps=["fee_truth_gap"],
    )

    applied = coordinator.apply_execution_result(
        symbol="BTCUSDT",
        provider_id="binance_um_perps",
        result=SimpleNamespace(status="filled_maker", order={"clientOrderId": "cid-1"}, ledger_records=[record], gaps=[]),
        fallback_intent_notional=10.0,
        fallback_side="buy",
        current_exposure=0.0,
        live=live,
    )

    assert applied.fill_truth_ok is False
    assert getattr(live, "reason") == "live_account_truth_gap"


def test_recover_inflight_state_reports_cold_restart(tmp_path):
    event_store = EventStore(str(tmp_path))
    coordinator = LiveStateCoordinator(event_store, PortfolioService(), ReconciliationService())
    live = SimpleNamespace(connector=FakeConnector(balances=[{"equity": "1000.0"}], positions=[], open_orders=[]))

    decision = coordinator.recover_inflight_state(live, "BTCUSDT", restart_confidence="trusted", safe_mode_requested=False)

    assert decision.outcome == "cold_restart"
    assert decision.action == "continue"
    assert event_store.load("recovery")[0]["payload"]["outcome"] == "cold_restart"


def test_recover_inflight_state_sweeps_orphan_orders_and_enters_flatten_only(tmp_path):
    event_store = EventStore(str(tmp_path))
    coordinator = LiveStateCoordinator(event_store, PortfolioService(), ReconciliationService())
    connector = FakeConnector(
        balances=[{"equity": "1000.0"}],
        positions=[],
        open_orders=[{"symbol": "BTCUSDT", "clientOrderId": "cid-1", "status": "NEW"}],
    )
    live = SimpleNamespace(connector=connector, apply_order_update=lambda order: (True, "ok"))

    decision = coordinator.recover_inflight_state(live, "BTCUSDT", restart_confidence="trusted", safe_mode_requested=False)

    assert decision.outcome == "warm_restart"
    assert decision.action == "flatten_only"
    assert decision.orphan_orders == 1
    assert connector.cancelled == [("BTCUSDT", "cid-1")]


def test_recover_inflight_state_enters_safe_mode_boot_when_requested(tmp_path):
    event_store = EventStore(str(tmp_path))
    event_store.append(
        "orders",
        {"payload": {"clientOrderId": "cid-1", "orderId": "o-1", "status": "NEW", "symbol": "BTCUSDT"}},
    )
    coordinator = LiveStateCoordinator(event_store, PortfolioService(), ReconciliationService())
    live = SimpleNamespace(
        connector=FakeConnector(balances=[{"equity": "1000.0"}], positions=[], open_orders=[]),
        apply_order_update=lambda order: (False, "out_of_order_order_update"),
    )

    decision = coordinator.recover_inflight_state(live, "BTCUSDT", restart_confidence="trusted", safe_mode_requested=True)

    assert decision.outcome == "safe_mode_boot"
    assert decision.action == "degrade"
    assert decision.recovered_orders == 0
    assert decision.metadata["effective_active_local_orders"][0]["state"] == "unknown"


def test_recover_inflight_state_does_not_degrade_only_for_historical_timed_out_order(tmp_path):
    event_store = EventStore(str(tmp_path))
    event_store.append(
        "orders",
        {"payload": {"clientOrderId": "cid-1", "orderId": "o-1", "status": "NEW", "symbol": "BTCUSDT"}},
    )
    coordinator = LiveStateCoordinator(event_store, PortfolioService(), ReconciliationService())
    live = SimpleNamespace(
        connector=FakeConnector(balances=[{"equity": "1000.0"}], positions=[], open_orders=[]),
        lifecycle_snapshot=lambda: [
            {
                "order_key": "cid-1",
                "client_order_id": "cid-1",
                "order_id": "o-1",
                "state": "timed_out",
                "confidence": "local",
            }
        ],
    )

    decision = coordinator.recover_inflight_state(live, "BTCUSDT", restart_confidence="trusted", safe_mode_requested=False)

    assert decision.outcome == "cold_restart"
    assert decision.action == "continue"
    assert decision.metadata["effective_active_local_orders"] == []
    assert decision.metadata["effective_historical_local_orders"][0]["state"] == "timed_out"


def test_reconcile_state_ignores_historical_timed_out_lifecycle_record_when_no_open_orders(tmp_path):
    event_store = EventStore(str(tmp_path))
    portfolio = PortfolioService()
    coordinator = LiveStateCoordinator(event_store, portfolio, ReconciliationService())
    event_store.append(
        "fills",
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": {"fill_id": "fill-1", "order_id": "o-1", "symbol": "BTC/USD", "side": "buy", "notional": 11.99963},
        },
    )

    class SpotConnector(FakeConnector):
        provider_id = "kraken_spot"

        def base_balance(self, symbol=None):  # noqa: ARG002
            return {"total": "0.0001782", "free": "0.0001782", "used": "0.0"}

        def book_ticker(self, symbol=None):  # noqa: ARG002
            return {"bidPrice": "67263.0", "askPrice": "67270.0"}

        def market_constraints(self, symbol=None):  # noqa: ARG002
            return {"min_order_size": "0.0001"}

        def quote_balance(self, symbol=None):  # noqa: ARG002
            return {"asset": "USD", "total": "22.6006", "free": "22.6006", "used": "0.0"}

    live = SimpleNamespace(
        connector=SpotConnector(
            balances=[{"equity": "24.5645888099"}],
            positions=[],
            open_orders=[],
        ),
        lifecycle_snapshot=lambda: [
            {
                "order_key": "cid-1",
                "client_order_id": "cid-1",
                "order_id": "o-1",
                "state": "timed_out",
                "confidence": "local",
            }
        ],
        authoritative_unrealized_pnl=lambda symbol: (
            UnrealizedPnlTruth(
                symbol=symbol,
                ts=datetime.now(timezone.utc),
                source="spot_trade_history_and_balance",
                confidence="authoritative",
                venue_value=1.2213266,
                reason="fifo_cost_basis_and_live_bid",
                evidence={"remaining_qty": 0.0001782, "remaining_basis_quote": 10.76494, "bid": 67263.0},
            ),
            [],
        ),
        authoritative_realized_pnl=lambda symbol, since_ms=None: (0.0, []),
        authoritative_fill_history=lambda symbol, side, since_ms=None: ([], []),
    )

    report = coordinator.reconcile_state(live, "BTC/USD", internal_exposure=11.98688139)

    assert report.ok is True
    assert report.code == "ok"
    assert report.details["order_lifecycle_confidence"] == TruthConfidenceLevel.AUTHORITATIVE.value
    assert report.details["active_order_lifecycle_snapshot"] == []
    assert report.details["order_lifecycle_snapshot"][0]["state"] == "timed_out"


def test_exchange_state_uses_spot_base_balance_as_exposure_truth(tmp_path):
    event_store = EventStore(str(tmp_path))
    coordinator = LiveStateCoordinator(event_store, PortfolioService(), ReconciliationService())

    class SpotConnector(FakeConnector):
        provider_id = "kraken_spot"

        def base_balance(self, symbol=None):  # noqa: ARG002
            return {"total": "0.00017824", "free": "0.00017824", "used": "0.0"}

        def book_ticker(self, symbol=None):  # noqa: ARG002
            return {"bidPrice": "67323.0", "askPrice": "67330.0"}

        def market_constraints(self, symbol=None):  # noqa: ARG002
            return {"min_order_size": "0.0001"}

    live = SimpleNamespace(
        connector=SpotConnector(
            balances=[{"equity": "33.0"}],
            positions=[],
            open_orders=[],
        ),
        authoritative_unrealized_pnl=lambda symbol: (
            UnrealizedPnlTruth(
                symbol=symbol,
                ts=datetime.now(timezone.utc),
                source="spot_trade_history_and_balance",
                confidence="authoritative",
                venue_value=0.0,
                reason="fifo_cost_basis_and_live_bid",
                evidence={"remaining_qty": 0.00017824, "remaining_basis_quote": 11.99965, "bid": 67323.0},
            ),
            [],
        ),
    )

    exchange = coordinator.exchange_state(live, "BTC/USD")

    assert exchange.exposure_notional == 0.00017824 * 67323.0
    assert exchange.position_count == 1
