from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import JSON, Float, Integer, String, create_engine, desc
from sqlalchemy.orm import Mapped, Session, declarative_base, mapped_column, sessionmaker


Base = declarative_base()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrderRecordModel(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(128), default="")
    notional_quote: Mapped[float] = mapped_column(Float, default=0.0)
    venue: Mapped[str] = mapped_column(String(32), default="")
    order_type: Mapped[str] = mapped_column(String(16), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class FillRecordModel(Base):
    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(12))
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    fee_quote: Mapped[float] = mapped_column(Float, default=0.0)
    funding_quote: Mapped[float] = mapped_column(Float, default=0.0)
    interest_quote: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PositionRecordModel(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    signed_qty: Mapped[float] = mapped_column(Float, default=0.0)
    avg_entry_price: Mapped[float] = mapped_column(Float, default=0.0)
    mark_price: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl_quote: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl_quote: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PnLRecordModel(Base):
    __tablename__ = "pnl"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    realized_quote: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_quote: Mapped[float] = mapped_column(Float, default=0.0)
    fees_quote: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class FundingRecordModel(Base):
    __tablename__ = "funding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    funding_quote: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class InterestRecordModel(Base):
    __tablename__ = "interest"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    interest_quote: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SubmissionRecordModel(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(128), default="")
    notional_quote: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuditCheckpointModel(Base):
    __tablename__ = "audit_checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40), index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ModuleEventModel(Base):
    __tablename__ = "module_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40), index=True)
    module: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(96), index=True)
    reason: Mapped[str] = mapped_column(String(256), default="")
    symbol: Mapped[str] = mapped_column(String(32), index=True, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ViolationModel(Base):
    __tablename__ = "violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40), index=True)
    module: Mapped[str] = mapped_column(String(64), index=True)
    rule: Mapped[str] = mapped_column(String(128), index=True)
    reason: Mapped[str] = mapped_column(String(256), default="")
    symbol: Mapped[str] = mapped_column(String(32), index=True, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


@dataclass
class SQLiteStore:
    run_dir: str

    def __post_init__(self) -> None:
        base = Path(self.run_dir)
        base.mkdir(parents=True, exist_ok=True)
        self.db_path = base / "trading.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        self.session_factory = sessionmaker(bind=self.engine, future=True)
        self.migrate()

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

    def record_order(
        self,
        *,
        symbol: str,
        side: str,
        status: str,
        reason: str,
        notional_quote: float,
        venue: str = "",
        order_type: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.session() as s:
            s.add(
                OrderRecordModel(
                    ts=_utc_now(),
                    symbol=symbol,
                    side=side,
                    status=status,
                    reason=reason,
                    notional_quote=float(notional_quote),
                    venue=venue,
                    order_type=order_type,
                    payload=dict(payload or {}),
                )
            )

    def record_fill(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        fee_quote: float,
        funding_quote: float = 0.0,
        interest_quote: float = 0.0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.session() as s:
            s.add(
                FillRecordModel(
                    ts=_utc_now(),
                    symbol=symbol,
                    side=side,
                    qty=float(qty),
                    price=float(price),
                    fee_quote=float(fee_quote),
                    funding_quote=float(funding_quote),
                    interest_quote=float(interest_quote),
                    payload=dict(payload or {}),
                )
            )

    def record_position(
        self,
        *,
        symbol: str,
        signed_qty: float,
        avg_entry_price: float,
        mark_price: float,
        unrealized_pnl_quote: float,
        realized_pnl_quote: float,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.session() as s:
            s.add(
                PositionRecordModel(
                    ts=_utc_now(),
                    symbol=symbol,
                    signed_qty=float(signed_qty),
                    avg_entry_price=float(avg_entry_price),
                    mark_price=float(mark_price),
                    unrealized_pnl_quote=float(unrealized_pnl_quote),
                    realized_pnl_quote=float(realized_pnl_quote),
                    payload=dict(payload or {}),
                )
            )

    def record_submission(
        self,
        *,
        symbol: str,
        status: str,
        reason: str,
        notional_quote: float,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.session() as s:
            s.add(
                SubmissionRecordModel(
                    ts=_utc_now(),
                    symbol=symbol,
                    status=status,
                    reason=reason,
                    notional_quote=float(notional_quote),
                    payload=dict(payload or {}),
                )
            )

    def recent_submissions(self, limit: int = 60) -> list[dict[str, Any]]:
        with self.session() as s:
            rows = (
                s.query(SubmissionRecordModel)
                .order_by(desc(SubmissionRecordModel.id))
                .limit(max(1, int(limit)))
                .all()
            )
            return [
                {
                    "ts": r.ts,
                    "symbol": r.symbol,
                    "status": r.status,
                    "reason": r.reason,
                    "notional_quote": r.notional_quote,
                    "payload": r.payload,
                }
                for r in rows
            ]

    def latest_submission_epoch(self) -> float | None:
        with self.session() as s:
            row = (
                s.query(SubmissionRecordModel)
                .order_by(desc(SubmissionRecordModel.id))
                .limit(1)
                .first()
            )
            if row is None:
                return None
            raw_ts = str(row.ts or "").strip()
            if not raw_ts:
                return None
            try:
                ts = raw_ts
                if ts.endswith("Z"):
                    ts = ts[:-1] + "+00:00"
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return float(dt.timestamp())
            except Exception:
                return None

    def latest_orders(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.session() as s:
            rows = (
                s.query(OrderRecordModel)
                .order_by(desc(OrderRecordModel.id))
                .limit(max(1, int(limit)))
                .all()
            )
            return [
                {
                    "ts": r.ts,
                    "symbol": r.symbol,
                    "side": r.side,
                    "status": r.status,
                    "reason": r.reason,
                    "notional_quote": r.notional_quote,
                    "venue": r.venue,
                    "order_type": r.order_type,
                    "payload": r.payload,
                }
                for r in rows
            ]

    def latest_positions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.session() as s:
            rows = (
                s.query(PositionRecordModel)
                .order_by(desc(PositionRecordModel.id))
                .limit(max(1, int(limit)))
                .all()
            )
            return [
                {
                    "ts": r.ts,
                    "symbol": r.symbol,
                    "signed_qty": r.signed_qty,
                    "avg_entry_price": r.avg_entry_price,
                    "mark_price": r.mark_price,
                    "unrealized_pnl_quote": r.unrealized_pnl_quote,
                    "realized_pnl_quote": r.realized_pnl_quote,
                    "payload": r.payload,
                }
                for r in rows
            ]

    def record_audit_checkpoint(self, *, kind: str, payload: dict[str, Any] | None = None) -> None:
        with self.session() as s:
            s.add(
                AuditCheckpointModel(
                    ts=_utc_now(),
                    kind=str(kind or "health_audit_110"),
                    payload=dict(payload or {}),
                )
            )

    def latest_audit_checkpoints(self, kind: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self.session() as s:
            q = s.query(AuditCheckpointModel)
            if kind:
                q = q.filter(AuditCheckpointModel.kind == str(kind))
            rows = q.order_by(desc(AuditCheckpointModel.id)).limit(max(1, int(limit))).all()
            return [{"ts": r.ts, "kind": r.kind, "payload": r.payload} for r in rows]

    def record_module_event(
        self,
        *,
        module: str,
        action: str,
        reason: str = "",
        symbol: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.session() as s:
            s.add(
                ModuleEventModel(
                    ts=_utc_now(),
                    module=str(module or ""),
                    action=str(action or ""),
                    reason=str(reason or ""),
                    symbol=str(symbol or ""),
                    payload=dict(payload or {}),
                )
            )

    def latest_module_events(self, module: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with self.session() as s:
            q = s.query(ModuleEventModel)
            if module:
                q = q.filter(ModuleEventModel.module == str(module))
            rows = q.order_by(desc(ModuleEventModel.id)).limit(max(1, int(limit))).all()
            return [
                {
                    "ts": r.ts,
                    "module": r.module,
                    "action": r.action,
                    "reason": r.reason,
                    "symbol": r.symbol,
                    "payload": r.payload,
                }
                for r in rows
            ]

    def record_violation(
        self,
        *,
        module: str,
        rule: str,
        reason: str = "",
        symbol: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.session() as s:
            s.add(
                ViolationModel(
                    ts=_utc_now(),
                    module=str(module or ""),
                    rule=str(rule or ""),
                    reason=str(reason or ""),
                    symbol=str(symbol or ""),
                    payload=dict(payload or {}),
                )
            )

    def latest_violations(self, rule: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with self.session() as s:
            q = s.query(ViolationModel)
            if rule:
                q = q.filter(ViolationModel.rule == str(rule))
            rows = q.order_by(desc(ViolationModel.id)).limit(max(1, int(limit))).all()
            return [
                {
                    "ts": r.ts,
                    "module": r.module,
                    "rule": r.rule,
                    "reason": r.reason,
                    "symbol": r.symbol,
                    "payload": r.payload,
                }
                for r in rows
            ]

    def health(self) -> dict[str, Any]:
        with self.session() as s:
            return {
                "db_path": str(self.db_path),
                "orders": int(s.query(OrderRecordModel).count()),
                "fills": int(s.query(FillRecordModel).count()),
                "positions": int(s.query(PositionRecordModel).count()),
                "submissions": int(s.query(SubmissionRecordModel).count()),
                "audit_checkpoints": int(s.query(AuditCheckpointModel).count()),
                "module_events": int(s.query(ModuleEventModel).count()),
                "violations": int(s.query(ViolationModel).count()),
            }
