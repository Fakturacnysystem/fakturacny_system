from __future__ import annotations

import time

from autonomous_investment_robot.services.storage import SQLiteStore


def test_sqlite_store_records_and_reads_rows(tmp_path) -> None:
    run_dir = tmp_path / "sqlite_run"
    store = SQLiteStore(str(run_dir))

    store.record_order(
        symbol="XBTEUR",
        side="buy",
        status="submitted",
        reason="ok",
        notional_quote=5.0,
        venue="kraken_spot",
        order_type="maker",
        payload={"txid": "T1"},
    )
    store.record_submission(
        symbol="XBTEUR",
        status="submitted",
        reason="ok",
        notional_quote=5.0,
        payload={"scheduler_probe": False},
    )

    health = store.health()
    assert health["orders"] >= 1
    assert health["submissions"] >= 1

    latest_orders = store.latest_orders(limit=5)
    latest_sub = store.recent_submissions(limit=5)
    assert latest_orders
    assert latest_sub
    assert latest_orders[0]["symbol"] == "XBTEUR"
    assert latest_sub[0]["symbol"] == "XBTEUR"


def test_sqlite_store_restores_latest_submission_epoch(tmp_path) -> None:
    run_dir = tmp_path / "sqlite_run_restore"
    store = SQLiteStore(str(run_dir))
    assert store.latest_submission_epoch() is None

    before = time.time()
    store.record_submission(
        symbol="ETHEUR",
        status="submitted",
        reason="scheduler_probe",
        notional_quote=2.5,
        payload={"scheduler_probe": True},
    )
    restored = store.latest_submission_epoch()
    assert restored is not None
    assert restored >= before - 1.0
