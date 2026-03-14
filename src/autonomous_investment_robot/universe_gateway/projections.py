from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, TypeAlias

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text, create_engine, select
from sqlalchemy.orm import Mapped, Session, declarative_base, mapped_column, sessionmaker

from autonomous_investment_robot.universe_gateway.contracts import EventEnvelope

Base = declarative_base()

LatestTableType: TypeAlias = type["LatestSystemStateModel"]


class UniverseEventModel(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    stream: Mapped[str] = mapped_column(String(96), index=True)
    event_type: Mapped[str] = mapped_column(String(96), index=True)
    timestamp: Mapped[str] = mapped_column(String(40), index=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    mode: Mapped[str] = mapped_column(String(24), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_module: Mapped[str] = mapped_column(String(128), index=True)
    schema_version: Mapped[str] = mapped_column(String(24), default="v1")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class EventDedupeModel(Base):
    __tablename__ = "event_dedupe"

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    seen_at: Mapped[str] = mapped_column(String(40), index=True)


class LatestSystemStateModel(Base):
    __tablename__ = "latest_system_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LatestCapitalStateModel(Base):
    __tablename__ = "latest_capital_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LatestDecisionStateModel(Base):
    __tablename__ = "latest_decision_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LatestExecutionStateModel(Base):
    __tablename__ = "latest_execution_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LatestRiskStateModel(Base):
    __tablename__ = "latest_risk_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LatestAuditStateModel(Base):
    __tablename__ = "latest_audit_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LatestTelemetryStateModel(Base):
    __tablename__ = "latest_telemetry_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LatestSimulationStateModel(Base):
    __tablename__ = "latest_simulation_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuthUserModel(Base):
    __tablename__ = "auth_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(24), index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


LATEST_TABLE_BY_DOMAIN: dict[str, LatestTableType] = {
    "system": LatestSystemStateModel,
    "capital": LatestCapitalStateModel,
    "decision": LatestDecisionStateModel,
    "execution": LatestExecutionStateModel,
    "risk": LatestRiskStateModel,
    "audit": LatestAuditStateModel,
    "telemetry": LatestTelemetryStateModel,
    "simulation": LatestSimulationStateModel,
}


@dataclass
class UniverseProjectionStore:
    dsn: str

    def __post_init__(self) -> None:
        safe_dsn = str(self.dsn or "").strip()
        if not safe_dsn:
            db_path = Path("runs/latest/universe_gateway.db")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            safe_dsn = f"sqlite:///{db_path}"
        self.dsn = self._normalize_sqlalchemy_dsn(safe_dsn)
        self.engine = create_engine(self.dsn, future=True)
        self.session_factory = sessionmaker(bind=self.engine, future=True)
        self.migrate()

    @classmethod
    def from_env(cls) -> "UniverseProjectionStore":
        dsn = str(
            os.getenv("AUTONOMOUS_UNIVERSE_POSTGRES_DSN", "")
            or os.getenv("AUTONOMOUS_POSTGRES_DSN", "")
            or os.getenv("POSTGRES_DSN", "")
            or ""
        ).strip()
        return cls(dsn=dsn)

    @staticmethod
    def _normalize_sqlalchemy_dsn(raw_dsn: str) -> str:
        dsn = str(raw_dsn or "").strip()
        lower = dsn.lower()
        if lower.startswith("postgres://"):
            return "postgresql+psycopg://" + dsn[len("postgres://") :]
        if lower.startswith("postgresql://") and not lower.startswith("postgresql+"):
            return "postgresql+psycopg://" + dsn[len("postgresql://") :]
        return dsn

    def migrate(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def append_event(self, *, stream: str, envelope: EventEnvelope) -> bool:
        with self.session() as s:
            exists = s.get(EventDedupeModel, envelope.event_id)
            if exists is not None:
                return False
            s.add(EventDedupeModel(event_id=envelope.event_id, seen_at=self._utc_now_iso()))
            s.add(
                UniverseEventModel(
                    event_id=envelope.event_id,
                    stream=str(stream),
                    event_type=envelope.event_type,
                    timestamp=envelope.timestamp,
                    run_id=envelope.run_id,
                    symbol=envelope.symbol,
                    mode=envelope.mode,
                    confidence=float(envelope.confidence),
                    source_module=envelope.source_module,
                    schema_version=envelope.schema_version,
                    payload=dict(envelope.payload),
                )
            )
            return True

    def upsert_latest(self, *, domain: str, payload: dict[str, Any]) -> None:
        table = LATEST_TABLE_BY_DOMAIN.get(str(domain))
        if table is None:
            return
        with self.session() as s:
            row = s.get(table, 1)
            now = self._utc_now_iso()
            if row is None:
                s.add(table(id=1, updated_at=now, payload=dict(payload)))
                return
            row.updated_at = now
            row.payload = dict(payload)

    def get_latest(self, *, domain: str) -> dict[str, Any]:
        table = LATEST_TABLE_BY_DOMAIN.get(str(domain))
        if table is None:
            return {}
        with self.session() as s:
            row = s.get(table, 1)
            if row is None:
                return {}
            if isinstance(row.payload, dict):
                return dict(row.payload)
            return {}

    def recent_events(self, *, stream: str | None = None, event_type: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with self.session() as s:
            stmt = select(UniverseEventModel).order_by(UniverseEventModel.id.desc()).limit(max(1, int(limit)))
            rows = list(s.execute(stmt).scalars().all())
            out: list[dict[str, Any]] = []
            for row in rows:
                if stream and row.stream != stream:
                    continue
                if event_type and row.event_type != event_type:
                    continue
                out.append(
                    {
                        "event_id": row.event_id,
                        "stream": row.stream,
                        "event_type": row.event_type,
                        "timestamp": row.timestamp,
                        "run_id": row.run_id,
                        "symbol": row.symbol,
                        "mode": row.mode,
                        "confidence": row.confidence,
                        "source_module": row.source_module,
                        "schema_version": row.schema_version,
                        "payload": row.payload or {},
                    }
                )
            return out

    def upsert_user(self, *, username: str, role: str, password_hash: str, active: bool = True) -> None:
        with self.session() as s:
            stmt = select(AuthUserModel).where(AuthUserModel.username == str(username)).limit(1)
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                s.add(
                    AuthUserModel(
                        username=str(username),
                        role=str(role),
                        password_hash=str(password_hash),
                        active=bool(active),
                    )
                )
                return
            row.role = str(role)
            row.password_hash = str(password_hash)
            row.active = bool(active)

    def get_user(self, username: str) -> dict[str, Any] | None:
        with self.session() as s:
            stmt = select(AuthUserModel).where(AuthUserModel.username == str(username)).limit(1)
            row = s.execute(stmt).scalar_one_or_none()
            if row is None:
                return None
            return {
                "username": row.username,
                "role": row.role,
                "password_hash": row.password_hash,
                "active": bool(row.active),
            }

    def count_users(self) -> int:
        with self.session() as s:
            return int(s.query(AuthUserModel).count())

    def dump_state(self) -> str:
        payload = {
            "dsn": self.dsn,
            "latest": {name: self.get_latest(domain=name) for name in LATEST_TABLE_BY_DOMAIN.keys()},
            "users": self.count_users(),
        }
        return json.dumps(payload, sort_keys=True, default=str)
