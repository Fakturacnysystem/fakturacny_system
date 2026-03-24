from autonomous_investment_robot.services.portfolio_service.service import PortfolioService


def test_portfolio_service_rehydrates_fill_and_position_truth():
    service = PortfolioService()

    state = service.rehydrate_from_events(
        fill_events=[
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
                    "realized_pnl": 0.0,
                }
            },
            {
                "payload": {
                    "venue": "paper",
                    "order_id": "o2",
                    "fill_id": "f2",
                    "symbol": "BTCUSDT",
                    "side": "sell",
                    "notional": 40.0,
                    "fee": 0.1,
                    "slippage_cost": 0.05,
                    "status": "filled_partial_taker_timeout",
                    "realized_pnl": 3.5,
                }
            },
        ],
        position_events=[{"payload": {"symbol": "BTCUSDT", "exposure_notional": 55.0}}],
    )

    snapshot = state["BTCUSDT"]
    assert snapshot.exposure_notional == 55.0
    assert snapshot.realized_pnl == 3.5
    assert snapshot.cumulative_fees == 0.30000000000000004
    assert snapshot.cumulative_slippage == 0.15000000000000002
    assert snapshot.fill_count == 2
    assert snapshot.metadata["rehydrated_position_snapshot"] is True
    assert len(service.ledger_rows()) == 2


def test_portfolio_service_skips_invalid_fill_rows_during_rehydration():
    service = PortfolioService()

    state = service.rehydrate_from_events(
        fill_events=[
            {"payload": {"symbol": "BTCUSDT", "fill_id": "", "notional": 10.0, "side": "buy"}},
            {"payload": {"symbol": "BTCUSDT", "fill_id": "f2", "notional": 0.0, "side": "buy"}},
        ]
    )

    assert state == {}
    assert service.ledger_rows() == []


def test_portfolio_service_rehydrates_account_balance_baseline():
    service = PortfolioService()

    service.rehydrate_from_events(
        account_events=[
            {
                "payload": {
                    "baseline_balance": 1000.0,
                    "exchange_balance": 1012.5,
                }
            }
        ]
    )

    account = service.account_row(venue="binance_um_perps")
    assert account["baseline_balance"] == 1000.0
    assert account["exchange_balance"] == 1012.5
