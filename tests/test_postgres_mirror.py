from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

from autonomous_investment_robot.services.distributed.postgres_mirror import PostgresMirrorSink


def test_postgres_mirror_from_env_disabled(monkeypatch: object) -> None:
    monkeypatch.delenv("AUTONOMOUS_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.setenv("AUTONOMOUS_POSTGRES_MIRROR_ENABLED", "1")
    sink = PostgresMirrorSink.from_env(run_id="disabled-env")
    health = sink.health().to_dict()
    assert bool(health.get("enabled")) is False
    assert sink.record_decision({"symbol": "XXBTZUSD", "decision": "hold"}) is False


def test_postgres_mirror_sqlite_roundtrip_rows(tmp_path: Path) -> None:
    dsn = f"sqlite:///{tmp_path / 'mirror_roundtrip.db'}"
    sink = PostgresMirrorSink(
        dsn=dsn,
        run_id="run-postgres-mirror-test",
        enabled=True,
    )
    health = sink.health().to_dict()
    assert bool(health.get("enabled")) is True
    assert bool(health.get("ok")) is True

    assert sink.record_decision({"symbol": "XXBTZUSD", "decision": "open"}) is True
    assert sink.record_execution({"symbol": "XXBTZUSD", "status": "submitted"}) is True
    assert sink.record_signal({"symbol": "XXBTZUSD", "regime": "TREND"}) is True
    assert sink.record_audit("distributed_runtime_boot", {"symbol": "XXBTZUSD", "status": "ok"}) is True

    engine = create_engine(dsn, future=True)
    with engine.begin() as conn:
        total = int(conn.execute(text("SELECT COUNT(*) FROM runtime_mirror_events")).scalar_one())
        cats = {
            str(row[0]): int(row[1])
            for row in conn.execute(
                text(
                    "SELECT category, COUNT(*) "
                    "FROM runtime_mirror_events "
                    "GROUP BY category"
                )
            ).all()
        }
    assert total >= 4
    assert "decision" in cats
    assert "execution" in cats
    assert "signal" in cats
    assert "audit:distributed_runtime_boot" in cats
