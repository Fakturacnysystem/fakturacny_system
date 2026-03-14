from __future__ import annotations

from autonomous_investment_robot.universe_gateway.contracts import EventEnvelope
from autonomous_investment_robot.universe_gateway.projections import UniverseProjectionStore


def test_projection_store_deduplicates_event_ids(tmp_path) -> None:
    db_path = tmp_path / "gw.db"
    store = UniverseProjectionStore(dsn=f"sqlite:///{db_path}")

    envelope = EventEnvelope.build(
        event_type="capital_update",
        run_id="run-1",
        symbol="BTCUSD",
        mode="Live",
        confidence=0.9,
        source_module="capital-service",
        payload={"equity": 10_000.0},
        event_id="evt-1",
    )

    first = store.append_event(stream="autobot.events.capital", envelope=envelope)
    second = store.append_event(stream="autobot.events.capital", envelope=envelope)

    assert first is True
    assert second is False


def test_projection_store_upserts_latest_tables(tmp_path) -> None:
    db_path = tmp_path / "gw2.db"
    store = UniverseProjectionStore(dsn=f"sqlite:///{db_path}")
    store.upsert_latest(domain="capital", payload={"equity": 12_345.0})

    latest = store.get_latest(domain="capital")
    assert latest["equity"] == 12_345.0
