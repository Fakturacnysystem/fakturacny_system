from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any, Mapping

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, create_engine


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_sqlalchemy_dsn(raw_dsn: str) -> str:
    """Normalize DSN for SQLAlchemy using installed PostgreSQL driver."""
    dsn = str(raw_dsn or "").strip()
    if not dsn:
        return ""
    lower = dsn.lower()
    if lower.startswith("postgres://"):
        return "postgresql+psycopg://" + dsn[len("postgres://") :]
    if lower.startswith("postgresql://") and not lower.startswith("postgresql+"):
        return "postgresql+psycopg://" + dsn[len("postgresql://") :]
    return dsn


@dataclass(frozen=True)
class PostgresMirrorHealth:
    enabled: bool
    ok: bool
    reason: str
    dsn_set: bool
    backend: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "ok": bool(self.ok),
            "reason": str(self.reason),
            "dsn_set": bool(self.dsn_set),
            "backend": str(self.backend),
        }


class PostgresMirrorSink:
    """Non-blocking Postgres mirror sink for distributed analytics observability."""

    def __init__(
        self,
        *,
        dsn: str,
        run_id: str,
        enabled: bool = True,
        connect_timeout_s: float = 2.0,
    ) -> None:
        self.dsn = str(dsn or "").strip()
        self.sqlalchemy_dsn = _normalize_sqlalchemy_dsn(self.dsn)
        self.run_id = str(run_id)
        self.enabled = bool(enabled and self.sqlalchemy_dsn)
        self.connect_timeout_s = max(0.5, float(connect_timeout_s))
        self._health = PostgresMirrorHealth(
            enabled=self.enabled,
            ok=False,
            reason="disabled",
            dsn_set=bool(self.dsn),
            backend="postgres_mirror",
        )
        self._engine = None
        self._table = None
        if self.enabled:
            self._init()

    @classmethod
    def from_env(cls, *, run_id: str) -> "PostgresMirrorSink":
        dsn = str(
            os.getenv("AUTONOMOUS_POSTGRES_DSN", "")
            or os.getenv("POSTGRES_DSN", "")
            or ""
        ).strip()
        enabled = str(os.getenv("AUTONOMOUS_POSTGRES_MIRROR_ENABLED", "0") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        timeout_s = max(0.5, float(os.getenv("AUTONOMOUS_POSTGRES_CONNECT_TIMEOUT_S", "2.0") or "2.0"))
        return cls(
            dsn=dsn,
            run_id=run_id,
            enabled=enabled,
            connect_timeout_s=timeout_s,
        )

    def _init(self) -> None:
        try:
            args: dict[str, Any] = {}
            if self.sqlalchemy_dsn.startswith("postgresql"):
                args["connect_args"] = {"connect_timeout": int(self.connect_timeout_s)}
            self._engine = create_engine(self.sqlalchemy_dsn, future=True, pool_pre_ping=True, **args)
            metadata = MetaData()
            self._table = Table(
                "runtime_mirror_events",
                metadata,
                Column("id", Integer, primary_key=True, autoincrement=True),
                Column("ts", String(40), index=True, nullable=False),
                Column("run_id", String(128), index=True, nullable=False),
                Column("category", String(64), index=True, nullable=False),
                Column("symbol", String(32), index=True, nullable=False, default=""),
                Column("status", String(32), index=True, nullable=False, default=""),
                Column("payload_json", Text, nullable=False),
            )
            metadata.create_all(self._engine)
            self._health = PostgresMirrorHealth(
                enabled=True,
                ok=True,
                reason="ok",
                dsn_set=True,
                backend="postgres_mirror",
            )
        except Exception as exc:
            self._engine = None
            self._table = None
            self._health = PostgresMirrorHealth(
                enabled=True,
                ok=False,
                reason=f"init_failed:{exc}",
                dsn_set=bool(self.dsn),
                backend="postgres_mirror",
            )

    def health(self) -> PostgresMirrorHealth:
        return self._health

    def _insert(self, *, category: str, payload: Mapping[str, Any], symbol: str = "", status: str = "") -> bool:
        if not self.enabled or self._engine is None or self._table is None:
            return False
        try:
            row = {
                "ts": _utc_now_iso(),
                "run_id": self.run_id,
                "category": str(category),
                "symbol": str(symbol),
                "status": str(status),
                "payload_json": json.dumps(dict(payload), sort_keys=True, default=str),
            }
            with self._engine.begin() as conn:
                conn.execute(self._table.insert().values(**row))
            return True
        except Exception as exc:
            self._health = PostgresMirrorHealth(
                enabled=True,
                ok=False,
                reason=f"write_failed:{exc}",
                dsn_set=bool(self.dsn),
                backend="postgres_mirror",
            )
            return False

    def record_audit(self, event_type: str, payload: Mapping[str, Any]) -> bool:
        return self._insert(
            category=f"audit:{event_type}",
            payload=payload,
            symbol=str(payload.get("symbol", "") or ""),
            status=str(payload.get("status", "") or ""),
        )

    def record_decision(self, payload: Mapping[str, Any]) -> bool:
        return self._insert(
            category="decision",
            payload=payload,
            symbol=str(payload.get("symbol", "") or ""),
            status=str(payload.get("decision", "") or payload.get("status", "") or ""),
        )

    def record_execution(self, payload: Mapping[str, Any]) -> bool:
        return self._insert(
            category="execution",
            payload=payload,
            symbol=str(payload.get("symbol", "") or ""),
            status=str(payload.get("status", "") or ""),
        )

    def record_signal(self, payload: Mapping[str, Any]) -> bool:
        return self._insert(
            category="signal",
            payload=payload,
            symbol=str(payload.get("symbol", "") or ""),
            status=str(payload.get("regime", "") or ""),
        )
