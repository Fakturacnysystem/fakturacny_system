from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import time
from typing import Any, Callable


SafeProbeSubmitter = Callable[[str], bool]


@dataclass
class AuditCheck:
    name: str
    ok: bool
    weight: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthAuditReport:
    ts: float
    health_score: float
    threshold: float
    ok: bool
    failed_checks: list[str]
    checks: list[AuditCheck]
    repair_actions_taken: list[str]
    restart_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": float(self.ts),
            "health_score": float(self.health_score),
            "threshold": float(self.threshold),
            "ok": bool(self.ok),
            "failed_checks": list(self.failed_checks),
            "checks": [asdict(x) for x in self.checks],
            "repair_actions_taken": list(self.repair_actions_taken),
            "restart_required": bool(self.restart_required),
        }


class HealthAudit110:
    """Comprehensive periodic health auditor with safe self-repair escalation.

    Hard safety invariant: this module never triggers forced SELL/CLOSE actions.
    Repairs are limited to cache resets, reconnect/reconcile attempts, and order cancellation.
    """

    def __init__(
        self,
        *,
        run_dir: str,
        interval_s: float = 600.0,
        health_threshold: float = 90.0,
        stream_stale_after_s: float = 20.0,
        scheduler_lag_grace_s: float = 5.0,
        watchdog_stall_timeout_s: float = 45.0,
        max_rate_limit_events_60s: float = 14.0,
        heartbeat_file: str = "health.json",
        watchdog_state_file: str = "watchdog_state.json",
    ) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.interval_s = max(60.0, float(interval_s))
        self.health_threshold = max(1.0, min(100.0, float(health_threshold)))
        self.stream_stale_after_s = max(1.0, float(stream_stale_after_s))
        self.scheduler_lag_grace_s = max(0.0, float(scheduler_lag_grace_s))
        self.watchdog_stall_timeout_s = max(1.0, float(watchdog_stall_timeout_s))
        self.max_rate_limit_events_60s = max(1.0, float(max_rate_limit_events_60s))
        self.heartbeat_path = self.run_dir / str(heartbeat_file or "health.json")
        self.watchdog_state_path = self.run_dir / str(watchdog_state_file or "watchdog_state.json")
        self.report_path = self.run_dir / "health_audit_110.json"
        self.report_log_path = self.run_dir / "health_audit_110.log"
        self.state_snapshot_path = self.run_dir / "health_audit_110_snapshot.json"

    @staticmethod
    def _finite(value: Any) -> bool:
        try:
            v = float(value)
        except Exception:
            return False
        return math.isfinite(v)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for row in items:
            key = str(row)
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
        return out

    @staticmethod
    def _is_rate_limit_error(exc: Exception | str | None) -> bool:
        text = str(exc or "").lower()
        if not text:
            return False
        tokens = (
            "rate limit",
            "rate-limit",
            "too many requests",
            "eapi:rate limit exceeded",
            "429",
        )
        return any(token in text for token in tokens)

    def _load_json_file(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _extract_services(self, live: Any | None) -> list[Any]:
        if live is None:
            return []
        out: list[Any] = []
        out.append(live)
        for attr in ("spot_service", "futures_service"):
            svc = getattr(live, attr, None)
            if svc is not None:
                out.append(svc)
        unique: list[Any] = []
        seen: set[int] = set()
        for svc in out:
            key = id(svc)
            if key in seen:
                continue
            seen.add(key)
            unique.append(svc)
        return unique

    def _latest_submission_age_s(
        self,
        *,
        now_ts: float,
        sqlite: Any | None,
        submission_scheduler: Any | None,
    ) -> float:
        if submission_scheduler is not None and hasattr(submission_scheduler, "last_submission_ts"):
            last_ts = self._safe_float(getattr(submission_scheduler, "last_submission_ts", 0.0), 0.0)
            if last_ts > 0.0:
                return max(0.0, now_ts - last_ts)
        if sqlite is not None and hasattr(sqlite, "latest_submission_epoch"):
            try:
                ts = sqlite.latest_submission_epoch()
                if ts is not None:
                    return max(0.0, now_ts - float(ts))
            except Exception:
                return float("inf")
        return float("inf")

    def _check_event_loop_liveness(
        self,
        *,
        now_ts: float,
        sqlite: Any | None,
        submission_scheduler: Any | None,
        order_submission_interval_s: float,
    ) -> AuditCheck:
        hb = self._load_json_file(self.heartbeat_path)
        progress_ts = self._safe_float(hb.get("last_progress_ts", hb.get("ts", 0.0)), 0.0)
        heartbeat_age = float("inf") if progress_ts <= 0.0 else max(0.0, now_ts - progress_ts)
        max_submission_age = max(60.0, float(order_submission_interval_s)) + self.scheduler_lag_grace_s
        submission_age = self._latest_submission_age_s(
            now_ts=now_ts,
            sqlite=sqlite,
            submission_scheduler=submission_scheduler,
        )
        ok = (heartbeat_age <= self.watchdog_stall_timeout_s) and (submission_age <= max_submission_age)
        return AuditCheck(
            name="event_loop_liveness",
            ok=ok,
            weight=15.0,
            details={
                "heartbeat_age_s": heartbeat_age,
                "stall_timeout_s": self.watchdog_stall_timeout_s,
                "submission_age_s": submission_age,
                "max_submission_age_s": max_submission_age,
            },
        )

    def _quote_components(self, quote: Any) -> tuple[float, float, float]:
        if isinstance(quote, dict):
            bid = self._safe_float(quote.get("bid", quote.get("bidPrice", 0.0)), 0.0)
            ask = self._safe_float(quote.get("ask", quote.get("askPrice", 0.0)), 0.0)
            ts = self._safe_float(quote.get("ts", quote.get("timestamp", 0.0)), 0.0)
            return bid, ask, ts
        bid = self._safe_float(getattr(quote, "bid", 0.0), 0.0)
        ask = self._safe_float(getattr(quote, "ask", 0.0), 0.0)
        ts = self._safe_float(getattr(quote, "ts", 0.0), 0.0)
        return bid, ask, ts

    def _check_market_data_integrity(
        self,
        *,
        now_ts: float,
        symbol: str,
        live: Any | None,
        latest_feed_quotes: list[Any] | None,
        latest_feed_quality: dict[str, Any] | None,
    ) -> AuditCheck:
        quotes = list(latest_feed_quotes or [])
        sanity_errors = 0
        fresh = 0
        total = 0
        for q in quotes:
            bid, ask, ts = self._quote_components(q)
            total += 1
            if bid <= 0.0 or ask <= 0.0 or ask < bid or (not self._finite(bid)) or (not self._finite(ask)):
                sanity_errors += 1
                continue
            age = float("inf") if ts <= 0.0 else max(0.0, now_ts - ts)
            if age <= self.stream_stale_after_s:
                fresh += 1

        fallback_snapshot: dict[str, Any] = {}
        if total == 0 and live is not None and hasattr(live, "market_snapshot"):
            try:
                fallback_snapshot = live.market_snapshot(symbol, max_age_s=self.stream_stale_after_s, force_refresh=False)
                bid = self._safe_float(fallback_snapshot.get("bid", 0.0), 0.0)
                ask = self._safe_float(fallback_snapshot.get("ask", 0.0), 0.0)
                ts = self._safe_float(fallback_snapshot.get("ts", now_ts), now_ts)
                total = 1
                if bid > 0.0 and ask > 0.0 and ask >= bid:
                    age = max(0.0, now_ts - ts)
                    if age <= self.stream_stale_after_s:
                        fresh = 1
                else:
                    sanity_errors += 1
            except Exception:
                sanity_errors += 1

        quality_ok = True
        for row in (latest_feed_quality or {}).values():
            if not isinstance(row, dict):
                continue
            score = row.get("score")
            if score is None:
                continue
            if not self._finite(score):
                quality_ok = False
                break

        futures_fields_ok = True
        if fallback_snapshot:
            for key in ("mark_price", "index_price", "funding_rate", "open_interest"):
                if key in fallback_snapshot and not self._finite(fallback_snapshot.get(key)):
                    futures_fields_ok = False
                    break

        ok = (fresh >= 1) and (sanity_errors == 0) and quality_ok and futures_fields_ok
        return AuditCheck(
            name="market_data_integrity",
            ok=ok,
            weight=15.0,
            details={
                "quotes_total": total,
                "fresh_quotes": fresh,
                "sanity_errors": sanity_errors,
                "stream_stale_after_s": self.stream_stale_after_s,
                "quality_map_size": len(latest_feed_quality or {}),
                "quality_ok": quality_ok,
                "futures_fields_ok": futures_fields_ok,
            },
        )

    def _check_account_execution_integrity(
        self,
        *,
        symbol: str,
        live: Any | None,
    ) -> AuditCheck:
        if live is None:
            return AuditCheck(
                name="account_execution_integrity",
                ok=False,
                weight=10.0,
                details={"reason": "live_service_missing"},
            )

        checks_ok = True
        details: dict[str, Any] = {}
        degraded_rate_limit = 0
        try:
            if hasattr(live, "_available_quote_balance"):
                ccy, free = live._available_quote_balance(symbol)
                details["quote_currency"] = str(ccy)
                details["quote_free"] = self._safe_float(free, 0.0)
        except Exception as exc:
            if self._is_rate_limit_error(exc):
                degraded_rate_limit += 1
                details["balance_error_rate_limited"] = str(exc)
            else:
                checks_ok = False
                details["balance_error"] = str(exc)

        try:
            if hasattr(live, "sync_fill_ledger"):
                snap = live.sync_fill_ledger(symbol, mark_price=0.0)
                if isinstance(snap, dict):
                    details["ledger_keys"] = sorted(list(snap.keys()))[:10]
        except Exception as exc:
            if self._is_rate_limit_error(exc):
                degraded_rate_limit += 1
                details["ledger_error_rate_limited"] = str(exc)
            else:
                checks_ok = False
                details["ledger_error"] = str(exc)

        try:
            if hasattr(live, "reconcile_live_state"):
                ok, reason = live.reconcile_live_state(internal_exposure=0.0)
                details["reconcile_reason"] = str(reason)
                if not bool(ok):
                    checks_ok = False
        except Exception as exc:
            if self._is_rate_limit_error(exc):
                degraded_rate_limit += 1
                details["reconcile_error_rate_limited"] = str(exc)
            else:
                checks_ok = False
                details["reconcile_error"] = str(exc)

        services = self._extract_services(live)
        open_order_queries = 0
        open_order_errors = 0
        for svc in services:
            conn = getattr(svc, "connector", None)
            if conn is None:
                continue
            if hasattr(conn, "open_orders"):
                open_order_queries += 1
                try:
                    _ = conn.open_orders()
                except Exception as exc:
                    open_order_errors += 1
                    if self._is_rate_limit_error(exc):
                        degraded_rate_limit += 1
                        details[f"open_orders_error_{open_order_queries}_rate_limited"] = str(exc)
                    else:
                        details[f"open_orders_error_{open_order_queries}"] = str(exc)
            if hasattr(conn, "open_positions"):
                try:
                    _ = conn.open_positions()
                except Exception as exc:
                    if self._is_rate_limit_error(exc):
                        degraded_rate_limit += 1
                        details.setdefault("open_positions_error_rate_limited", str(exc))
                    else:
                        details.setdefault("open_positions_error", str(exc))
                        checks_ok = False
        details["open_order_queries"] = open_order_queries
        details["open_order_errors"] = open_order_errors
        details["rate_limited_errors"] = degraded_rate_limit
        if open_order_errors > degraded_rate_limit:
            checks_ok = False

        return AuditCheck(
            name="account_execution_integrity",
            ok=checks_ok,
            weight=10.0,
            details=details,
        )

    def _check_profit_gate_integrity(
        self,
        *,
        live: Any | None,
        symbol: str,
    ) -> AuditCheck:
        services = self._extract_services(live)
        gate_services = 0
        open_lots_checked = 0
        errors: list[str] = []

        for svc in services:
            gate = getattr(svc, "profit_gate", None)
            if gate is None or not hasattr(gate, "config"):
                continue
            gate_services += 1
            cfg = getattr(gate, "config", None)
            target = self._safe_float(getattr(cfg, "min_net_profit_ratio", 0.0), 0.0)
            slip_bps = self._safe_float(getattr(cfg, "default_slippage_bps", 0.0), 0.0)
            if target < 0.003 - 1e-12:
                errors.append(f"{svc.__class__.__name__}:profit_target_below_floor")
            if slip_bps <= 0.0:
                errors.append(f"{svc.__class__.__name__}:slippage_non_positive")
            for key in ("default_entry_fee_bps", "default_exit_fee_bps"):
                if not self._finite(getattr(cfg, key, 0.0)):
                    errors.append(f"{svc.__class__.__name__}:{key}_nan")

            ledgers = getattr(svc, "_ledgers", {})
            if not isinstance(ledgers, dict):
                continue
            for lot_symbol, ledger in ledgers.items():
                qty = self._safe_float(getattr(ledger, "position_qty", 0.0), 0.0)
                if abs(qty) <= 1e-9:
                    continue
                lots = list(getattr(ledger, "lots", []) or [])
                if not lots:
                    errors.append(f"{svc.__class__.__name__}:{lot_symbol}:missing_lots")
                    continue
                open_lots_checked += 1
                try:
                    snap = svc.market_snapshot(str(lot_symbol), max_age_s=self.stream_stale_after_s, force_refresh=False)
                    tick_size = 0.0
                    if hasattr(svc, "_instrument_meta"):
                        meta = svc._instrument_meta(str(lot_symbol))
                        if isinstance(meta, dict):
                            tick_size = self._safe_float(meta.get("tick_size", 0.0), 0.0)
                    bid = self._safe_float((snap or {}).get("bid", 0.0), 0.0)
                    ask = self._safe_float((snap or {}).get("ask", 0.0), 0.0)
                    if qty > 0.0:
                        decision = gate.can_close_long(
                            lots=lots,
                            exit_price=max(bid, 0.0),
                            exit_qty=abs(qty),
                            tick_size=tick_size,
                        )
                    else:
                        decision = gate.can_close_short(
                            lots=lots,
                            exit_price=max(ask, 0.0),
                            close_qty=abs(qty),
                            tick_size=tick_size,
                        )
                    if not self._finite(getattr(decision, "required_exit_price", 0.0)):
                        errors.append(f"{svc.__class__.__name__}:{lot_symbol}:required_exit_non_finite")
                except Exception as exc:
                    errors.append(f"{svc.__class__.__name__}:{lot_symbol}:gate_eval_error:{exc}")

        ok = gate_services > 0 and not errors
        if gate_services == 0:
            errors.append("profit_gate_service_missing")

        return AuditCheck(
            name="profit_gate_integrity",
            ok=ok,
            weight=15.0,
            details={
                "gate_services": gate_services,
                "open_lots_checked": open_lots_checked,
                "errors": errors[:20],
            },
        )

    def _check_risk_integrity(self, *, risk_engine: Any | None) -> AuditCheck:
        if risk_engine is None:
            return AuditCheck(
                name="risk_system_integrity",
                ok=False,
                weight=10.0,
                details={"reason": "risk_engine_missing"},
            )
        details: dict[str, Any] = {}
        ok = True
        state = getattr(risk_engine, "state", None)
        limits = getattr(risk_engine, "limits", None)
        if state is None:
            ok = False
            details["state"] = "missing"
        else:
            details["kill_switch"] = bool(getattr(state, "kill_switch", False))
            details["safe_mode"] = bool(getattr(state, "safe_mode", False))
        if limits is None:
            ok = False
            details["limits"] = "missing"
        if hasattr(risk_engine, "_limits_complete"):
            try:
                details["limits_complete"] = bool(risk_engine._limits_complete())  # type: ignore[attr-defined]
                if not details["limits_complete"]:
                    ok = False
            except Exception as exc:
                ok = False
                details["limits_complete_error"] = str(exc)
        return AuditCheck(
            name="risk_system_integrity",
            ok=ok,
            weight=10.0,
            details=details,
        )

    def _count_recent_rate_limit_errors(self, max_lines: int = 120) -> int:
        path = self.run_dir / "audit.log"
        if not path.exists():
            return 0
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return 0
        total = 0
        for raw in lines[-max(1, int(max_lines)) :]:
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            payload = row.get("payload", {}) if isinstance(row, dict) else {}
            text = json.dumps(payload, sort_keys=True).lower()
            if "rate limit" in text or "429" in text:
                total += 1
        return total

    def _check_rate_limit_health(self, *, ops: Any | None, live: Any | None) -> AuditCheck:
        rate_limit_events = 0.0
        if ops is not None:
            metrics = getattr(ops, "metrics", {})
            if isinstance(metrics, dict):
                rate_limit_events = self._safe_float(metrics.get("rate_limit_events", 0.0), 0.0)
        recent_errors = float(self._count_recent_rate_limit_errors())
        cooldown_active = False
        for svc in self._extract_services(live):
            cooldown_until = self._safe_float(getattr(svc, "rate_limit_cooldown_until_s", 0.0), 0.0)
            if cooldown_until > time.time():
                cooldown_active = True
                break
        total_pressure = max(rate_limit_events, recent_errors)
        ok = total_pressure <= self.max_rate_limit_events_60s
        if cooldown_active and total_pressure > (self.max_rate_limit_events_60s * 0.5):
            ok = False
        return AuditCheck(
            name="rate_limit_api_health",
            ok=ok,
            weight=10.0,
            details={
                "rate_limit_events_metric": rate_limit_events,
                "recent_rate_limit_errors": recent_errors,
                "max_rate_limit_events_60s": self.max_rate_limit_events_60s,
                "cooldown_active": cooldown_active,
            },
        )

    def _persist_state_snapshot(self, *, sqlite: Any | None, reason: str) -> None:
        snapshot: dict[str, Any] = {
            "ts": time.time(),
            "reason": reason,
        }
        if sqlite is not None:
            try:
                if hasattr(sqlite, "latest_positions"):
                    snapshot["positions"] = sqlite.latest_positions(limit=80)
                if hasattr(sqlite, "latest_orders"):
                    snapshot["orders"] = sqlite.latest_orders(limit=80)
                if hasattr(sqlite, "recent_submissions"):
                    snapshot["submissions"] = sqlite.recent_submissions(limit=120)
            except Exception as exc:
                snapshot["storage_snapshot_error"] = str(exc)
        self.state_snapshot_path.write_text(json.dumps(snapshot, sort_keys=True, indent=2), encoding="utf-8")

    def _check_storage_integrity(self, *, sqlite: Any | None) -> AuditCheck:
        if sqlite is None:
            return AuditCheck(
                name="storage_integrity",
                ok=False,
                weight=10.0,
                details={"reason": "sqlite_store_missing"},
            )
        ok = True
        details: dict[str, Any] = {}
        try:
            health = sqlite.health()
            if isinstance(health, dict):
                details.update({
                    "orders": int(health.get("orders", 0) or 0),
                    "fills": int(health.get("fills", 0) or 0),
                    "positions": int(health.get("positions", 0) or 0),
                    "submissions": int(health.get("submissions", 0) or 0),
                })
            else:
                ok = False
                details["health_type"] = str(type(health).__name__)
        except Exception as exc:
            ok = False
            details["health_error"] = str(exc)

        try:
            if hasattr(sqlite, "record_audit_checkpoint"):
                sqlite.record_audit_checkpoint(
                    kind="health_audit_110",
                    payload={"ts": time.time(), "ok": ok},
                )
                details["checkpoint_written"] = True
            else:
                # Fallback filesystem checkpoint if older SQLite schema is in use.
                self._persist_state_snapshot(sqlite=sqlite, reason="audit110_checkpoint_fallback")
                details["checkpoint_written"] = True
                details["checkpoint_fallback"] = True
        except Exception as exc:
            ok = False
            details["checkpoint_error"] = str(exc)

        return AuditCheck(
            name="storage_integrity",
            ok=ok,
            weight=10.0,
            details=details,
        )

    def _check_submission_compliance(
        self,
        *,
        now_ts: float,
        symbol: str,
        sqlite: Any | None,
        submission_scheduler: Any | None,
        order_submission_interval_s: float,
        safe_probe_submitter: SafeProbeSubmitter | None,
        auto_repair: bool,
    ) -> AuditCheck:
        max_age = max(60.0, float(order_submission_interval_s)) + self.scheduler_lag_grace_s
        age = self._latest_submission_age_s(
            now_ts=now_ts,
            sqlite=sqlite,
            submission_scheduler=submission_scheduler,
        )
        repaired = False
        repair_error = ""
        if age > max_age and auto_repair and safe_probe_submitter is not None:
            try:
                repaired = bool(safe_probe_submitter("audit110_submission_gap"))
                if repaired:
                    age = self._latest_submission_age_s(
                        now_ts=time.time(),
                        sqlite=sqlite,
                        submission_scheduler=submission_scheduler,
                    )
            except Exception as exc:
                repair_error = str(exc)
        ok = age <= max_age
        return AuditCheck(
            name="submission_cadence_60s",
            ok=ok,
            weight=10.0,
            details={
                "submission_age_s": age,
                "max_age_s": max_age,
                "auto_probe_repaired": repaired,
                "probe_error": repair_error,
            },
        )

    def _check_watchdog_integrity(self, *, now_ts: float) -> AuditCheck:
        hb = self._load_json_file(self.heartbeat_path)
        wd = self._load_json_file(self.watchdog_state_path)
        progress_ts = self._safe_float(hb.get("last_progress_ts", hb.get("ts", 0.0)), 0.0)
        heartbeat_age = float("inf") if progress_ts <= 0.0 else max(0.0, now_ts - progress_ts)
        restart_count = int(self._safe_float(wd.get("restart_count", 0), 0.0))
        last_restart_ts = self._safe_float(wd.get("last_restart_ts", 0.0), 0.0)
        running = bool(wd.get("running", True if not wd else False))
        recent_restart = last_restart_ts > 0.0 and (now_ts - last_restart_ts) < 180.0
        restart_loop = restart_count >= 3 and recent_restart and (
            (not running) or (heartbeat_age > max(30.0, self.stream_stale_after_s * 2.0))
        )
        ok = (heartbeat_age <= (self.watchdog_stall_timeout_s * 1.2)) and running and (not restart_loop)
        return AuditCheck(
            name="watchdog_integrity",
            ok=ok,
            weight=5.0,
            details={
                "heartbeat_age_s": heartbeat_age,
                "running": running,
                "restart_count": restart_count,
                "last_restart_ts": last_restart_ts,
                "restart_loop": restart_loop,
            },
        )

    def _persist_report(self, report: HealthAuditReport) -> None:
        payload = report.to_dict()
        self.report_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        with self.report_log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, sort_keys=True) + "\n")

    def run_once(
        self,
        *,
        symbol: str,
        mode: str,
        live: Any | None,
        sqlite: Any | None,
        ops: Any | None,
        submission_scheduler: Any | None,
        order_submission_interval_s: float,
        risk_engine: Any | None,
        latest_feed_quotes: list[Any] | None = None,
        latest_feed_quality: dict[str, Any] | None = None,
        safe_probe_submitter: SafeProbeSubmitter | None = None,
        auto_repair: bool = True,
        now_ts: float | None = None,
    ) -> HealthAuditReport:
        _ = str(mode or "").strip().lower()
        ts = time.time() if now_ts is None else float(now_ts)
        checks: list[AuditCheck] = [
            self._check_event_loop_liveness(
                now_ts=ts,
                sqlite=sqlite,
                submission_scheduler=submission_scheduler,
                order_submission_interval_s=order_submission_interval_s,
            ),
            self._check_market_data_integrity(
                now_ts=ts,
                symbol=symbol,
                live=live,
                latest_feed_quotes=latest_feed_quotes,
                latest_feed_quality=latest_feed_quality,
            ),
            self._check_account_execution_integrity(symbol=symbol, live=live),
            self._check_profit_gate_integrity(live=live, symbol=symbol),
            self._check_risk_integrity(risk_engine=risk_engine),
            self._check_rate_limit_health(ops=ops, live=live),
            self._check_storage_integrity(sqlite=sqlite),
            self._check_submission_compliance(
                now_ts=ts,
                symbol=symbol,
                sqlite=sqlite,
                submission_scheduler=submission_scheduler,
                order_submission_interval_s=order_submission_interval_s,
                safe_probe_submitter=safe_probe_submitter,
                auto_repair=auto_repair,
            ),
            self._check_watchdog_integrity(now_ts=ts),
        ]

        total_weight = sum(x.weight for x in checks)
        earned = sum(x.weight for x in checks if x.ok)
        score = 0.0 if total_weight <= 0 else (earned / total_weight) * 100.0
        failed = [x.name for x in checks if not x.ok]
        report = HealthAuditReport(
            ts=ts,
            health_score=score,
            threshold=self.health_threshold,
            ok=(not failed) and (score >= self.health_threshold),
            failed_checks=failed,
            checks=checks,
            repair_actions_taken=[],
            restart_required=False,
        )
        self._persist_report(report)
        return report

    def _soft_repair(self, *, live: Any | None, symbol: str) -> list[str]:
        actions: list[str] = []
        if live is None:
            return actions
        for svc in self._extract_services(live):
            for attr in ("_ticker_cache", "_balance_cache", "_trades_cache", "_order_meta"):
                if hasattr(svc, attr):
                    try:
                        target = getattr(svc, attr)
                        if isinstance(target, dict):
                            target.clear()
                            actions.append(f"soft_clear_{svc.__class__.__name__}.{attr}")
                    except Exception:
                        continue
            for attr in ("_ticker_cache_ts", "_last_ledger_sync_ts"):
                if hasattr(svc, attr):
                    try:
                        target = getattr(svc, attr)
                        if isinstance(target, dict):
                            target.clear()
                            actions.append(f"soft_clear_{svc.__class__.__name__}.{attr}")
                    except Exception:
                        continue
            if hasattr(svc, "market_snapshot"):
                try:
                    svc.market_snapshot(symbol, max_age_s=self.stream_stale_after_s, force_refresh=True)
                    actions.append(f"soft_refresh_snapshot_{svc.__class__.__name__}")
                except Exception:
                    pass
            if hasattr(svc, "_refresh_instruments"):
                try:
                    svc._refresh_instruments(force=True)  # type: ignore[attr-defined]
                    actions.append(f"soft_refresh_instruments_{svc.__class__.__name__}")
                except Exception:
                    pass
            if hasattr(svc, "preflight"):
                try:
                    svc.preflight()
                    actions.append(f"soft_preflight_{svc.__class__.__name__}")
                except Exception:
                    pass
        return self._dedupe(actions)

    def _hard_repair(self, *, live: Any | None, sqlite: Any | None, symbol: str) -> list[str]:
        actions: list[str] = []
        if live is not None:
            for svc in self._extract_services(live):
                conn = getattr(svc, "connector", None)
                if conn is None:
                    continue
                if hasattr(conn, "cancel_all"):
                    try:
                        conn.cancel_all()
                        actions.append(f"hard_cancel_all_{svc.__class__.__name__}")
                    except Exception:
                        pass
                elif hasattr(conn, "cancel_all_orders"):
                    try:
                        conn.cancel_all_orders()
                        actions.append(f"hard_cancel_all_orders_{svc.__class__.__name__}")
                    except Exception:
                        pass
            if hasattr(live, "reconcile_live_state"):
                try:
                    live.reconcile_live_state(internal_exposure=0.0)
                    actions.append("hard_reconcile_live_state")
                except Exception:
                    pass
            if hasattr(live, "sync_fill_ledger"):
                try:
                    live.sync_fill_ledger(symbol, mark_price=0.0)
                    actions.append("hard_sync_fill_ledger")
                except Exception:
                    pass
        try:
            self._persist_state_snapshot(sqlite=sqlite, reason="hard_repair")
            actions.append("hard_state_snapshot")
        except Exception:
            pass
        return self._dedupe(actions)

    def audit_and_repair(
        self,
        *,
        symbol: str,
        mode: str,
        live: Any | None,
        sqlite: Any | None,
        ops: Any | None,
        submission_scheduler: Any | None,
        order_submission_interval_s: float,
        risk_engine: Any | None,
        latest_feed_quotes: list[Any] | None = None,
        latest_feed_quality: dict[str, Any] | None = None,
        safe_probe_submitter: SafeProbeSubmitter | None = None,
        now_ts: float | None = None,
    ) -> HealthAuditReport:
        actions: list[str] = []

        report = self.run_once(
            symbol=symbol,
            mode=mode,
            live=live,
            sqlite=sqlite,
            ops=ops,
            submission_scheduler=submission_scheduler,
            order_submission_interval_s=order_submission_interval_s,
            risk_engine=risk_engine,
            latest_feed_quotes=latest_feed_quotes,
            latest_feed_quality=latest_feed_quality,
            safe_probe_submitter=safe_probe_submitter,
            auto_repair=True,
            now_ts=now_ts,
        )
        actions.extend(report.repair_actions_taken)
        if report.ok:
            report.repair_actions_taken = self._dedupe(actions)
            self._persist_report(report)
            return report

        actions.extend(self._soft_repair(live=live, symbol=symbol))
        report = self.run_once(
            symbol=symbol,
            mode=mode,
            live=live,
            sqlite=sqlite,
            ops=ops,
            submission_scheduler=submission_scheduler,
            order_submission_interval_s=order_submission_interval_s,
            risk_engine=risk_engine,
            latest_feed_quotes=latest_feed_quotes,
            latest_feed_quality=latest_feed_quality,
            safe_probe_submitter=safe_probe_submitter,
            auto_repair=True,
            now_ts=None,
        )
        actions.extend(report.repair_actions_taken)
        if report.ok:
            report.repair_actions_taken = self._dedupe(actions)
            self._persist_report(report)
            return report

        actions.extend(self._hard_repair(live=live, sqlite=sqlite, symbol=symbol))
        report = self.run_once(
            symbol=symbol,
            mode=mode,
            live=live,
            sqlite=sqlite,
            ops=ops,
            submission_scheduler=submission_scheduler,
            order_submission_interval_s=order_submission_interval_s,
            risk_engine=risk_engine,
            latest_feed_quotes=latest_feed_quotes,
            latest_feed_quality=latest_feed_quality,
            safe_probe_submitter=safe_probe_submitter,
            auto_repair=True,
            now_ts=None,
        )
        actions.extend(report.repair_actions_taken)

        if report.ok:
            report.repair_actions_taken = self._dedupe(actions)
            self._persist_report(report)
            return report

        actions.append("full_restart_required")
        self._persist_state_snapshot(sqlite=sqlite, reason="full_restart_required")
        report.repair_actions_taken = self._dedupe(actions)
        report.restart_required = True
        self._persist_report(report)
        return report
