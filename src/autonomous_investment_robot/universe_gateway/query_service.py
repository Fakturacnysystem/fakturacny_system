from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autonomous_investment_robot.services.storage import SQLiteStore
from autonomous_investment_robot.services.universe_core.live_canary_envelope import LiveCanaryEnvelopeCompiler
from autonomous_investment_robot.universe_gateway.projections import UniverseProjectionStore
from autonomous_investment_robot.universe_gateway.run_registry import resolve_run_directory


MODE_LOOKUP = {
    "readonly": "Readonly",
    "paper": "Paper",
    "canary": "Canary",
    "live": "Live",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _tail_jsonl(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, int(limit)) :]:
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except Exception:
            continue
    return out


def _payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _payload_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [dict(item) for item in parsed if isinstance(item, dict)]
        except Exception:
            return []
    return []


def _normalize_mode(raw: Any) -> str:
    mode = str(raw or "Paper").strip()
    return MODE_LOOKUP.get(mode.lower(), mode.title() or "Paper")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _truthy(raw: Any) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class UniverseQueryService:
    run_dir: str
    projections: UniverseProjectionStore

    def __post_init__(self) -> None:
        selection_mode = str(os.getenv("AUTONOMOUS_UNIVERSE_RUN_SELECTION", "auto") or "auto")
        self.run_resolution = resolve_run_directory(run_dir=self.run_dir, selection_mode=selection_mode)
        self.run_path = Path(self.run_resolution.run_path)
        self.run_path.mkdir(parents=True, exist_ok=True)
        self.project_root = Path(self.run_resolution.project_root)
        self.sqlite = SQLiteStore(str(self.run_path))
        self.canary_compiler = LiveCanaryEnvelopeCompiler()

    def _config_payload(self) -> dict[str, Any]:
        candidates = [
            self.run_path / "runtime_config.effective.yaml",
            self.run_path / "effective_config.json",
            self.project_root / str(os.getenv("AUTONOMOUS_CONFIG_PATH", "") or ""),
        ]
        for path in candidates:
            if not str(path):
                continue
            if path.suffix == ".json":
                raw = _read_json(path, {})
                if isinstance(raw, dict) and raw:
                    return raw
                continue
            try:
                from autonomous_investment_robot.config.settings import _load_yaml_like

                if path.exists():
                    payload = _load_yaml_like(str(path))
                    if isinstance(payload, dict) and payload:
                        return dict(payload)
            except Exception:
                continue
        return {}

    def _live_gate_state(self) -> dict[str, Any]:
        runtime = self._runtime_health()
        compliance = self._compliance_report()
        config = self._config_payload()
        target_mode = str(self.run_resolution.target_mode or "unknown")
        runtime_mode = str(self.run_resolution.runtime_mode or _normalize_mode(runtime.get("mode", "unknown")))
        confirmation_file = str(
            os.getenv("AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE", self.project_root / "ops" / "live_operator_confirmation.txt")
        )
        approval_file = str(
            os.getenv("AUTONOMOUS_LIVE_OPERATOR_APPROVAL_ARTIFACT_FILE", self.project_root / "ops" / "live_governance_approval.json")
        )
        confirmation_path = Path(confirmation_file).expanduser()
        approval_path = Path(approval_file).expanduser()
        live_go = _truthy(os.getenv("AUTONOMOUS_LIVE_GO", "0"))
        approval_payload = _read_json(approval_path, {})
        approval_ok = bool(
            isinstance(approval_payload, dict)
            and bool(approval_payload.get("approved", False))
            and str(approval_payload.get("artifact_id", "")).strip()
            and str(approval_payload.get("approver", "")).strip()
        )
        manual_gate_required = target_mode in {"live", "canary"}
        manual_gate_present = bool(live_go and confirmation_path.exists() and approval_ok)
        invariants_ok = not bool(runtime.get("risk_kill_switch", False)) and str(runtime.get("status", "")).lower() not in {"error", "fatal", "blocked"}
        evidence_ready = any(
            (self.run_path / name).exists()
            for name in (
                "dashboard_snapshot.json",
                "health.json",
                "runtime_health.json",
                "runtime_audit.json",
                "runtime_audit_latest.json",
                "event_bus.jsonl",
            )
        )
        preflight = _read_json(self.project_root / "runs" / "preflight_live.json", {})
        deployment_gate_open = bool(preflight.get("ok", compliance.get("allowed", True)))
        envelope = self.canary_compiler.compile(
            rollout_stage=target_mode,
            manual_gate_required=manual_gate_required,
            manual_gate_present=manual_gate_present,
            safety_veto=not invariants_ok,
            evidence_ready=evidence_ready,
            deployment_gate_open=deployment_gate_open,
        )
        config_frozen = (self.run_path / "checksums.json").exists() or (self.run_path / "runtime_config.effective.yaml").exists()
        promoted = (self.run_path / "promote_main.marker").exists() or bool(_read_json(self.run_path / "last_good_overrides.json", {}))
        return {
            "target_mode": target_mode,
            "runtime_mode": runtime_mode,
            "manual_gate_required": manual_gate_required,
            "manual_gate_status": "open" if manual_gate_present else ("not_required" if not manual_gate_required else "locked"),
            "operator_approval_status": "approved" if approval_ok else "missing",
            "operator_approval_artifact_id": str(approval_payload.get("artifact_id", "") or ""),
            "confirmation_file": str(confirmation_path),
            "approval_file": str(approval_path),
            "config_freeze_status": "frozen" if config_frozen else "missing",
            "promotion_status": "promoted" if promoted else ("canary" if target_mode == "canary" else "standby"),
            "deployment_gate_open": deployment_gate_open,
            "canary_envelope": envelope.to_dict(),
            "requested_run_mode": self.run_resolution.requested_mode,
            "resolved_run_dir": str(self.run_path),
            "resolved_run_source": self.run_resolution.source,
            "config_mode": _normalize_mode(config.get("mode", "")),
        }

    def _runtime_health(self) -> dict[str, Any]:
        runtime = _read_json(self.run_path / "runtime_health.json", {})
        health = _read_json(self.run_path / "health.json", {})
        compliance = _read_json(self.run_path / "compliance_engine_report.json", {})
        diagnostics = _read_json(self.run_path / "distributed_runtime_diagnostics.json", {})

        merged = dict(health) if isinstance(health, dict) else {}
        if isinstance(runtime, dict):
            merged.update(runtime)
        if isinstance(compliance, dict):
            merged.setdefault("compliance_reason", compliance.get("reason", ""))
            merged.setdefault("compliance_allowed", compliance.get("allowed", True))
            merged.setdefault("provider", compliance.get("provider", merged.get("provider", "")))
        if isinstance(diagnostics, dict):
            merged.setdefault("distributed_enabled", diagnostics.get("enabled", False))
            merged.setdefault("node_role", diagnostics.get("node_role", "live"))
            merged.setdefault("allow_local_fallback", diagnostics.get("allow_local_fallback", True))

        merged["mode"] = _normalize_mode(merged.get("mode", "Paper"))
        merged["status"] = str(merged.get("status", "unknown") or "unknown")
        merged.setdefault("version", "0.1.0")
        merged.setdefault("run_id", self.run_path.name or self.run_resolution.run_path.name or "latest")
        merged.setdefault("updated_at", merged.get("ts", _utc_now_iso()))
        merged.setdefault("reason", merged.get("reason", merged.get("compliance_reason", "unknown")))
        merged.setdefault("symbol", merged.get("symbol", ""))
        return merged

    def _dashboard_snapshot(self) -> dict[str, Any]:
        snap = _read_json(self.run_path / "dashboard_snapshot.json", {})
        return snap if isinstance(snap, dict) else {}

    def _snapshot_groups(self) -> dict[str, Any]:
        groups = self._dashboard_snapshot().get("groups", {})
        return groups if isinstance(groups, dict) else {}

    def _watchdog_state(self) -> dict[str, Any]:
        state = _read_json(self.run_path / "watchdog_state.json", {})
        if isinstance(state, dict) and state:
            return state
        return {
            "status": self._runtime_health().get("status", "unknown"),
            "reason": self._runtime_health().get("reason", "unknown"),
        }

    def _mastermind_status(self) -> dict[str, Any]:
        raw = _read_json(self.run_path / "mastermind_status.json", {})
        return raw if isinstance(raw, dict) else {}

    def _distributed_diagnostics(self) -> dict[str, Any]:
        raw = _read_json(self.run_path / "distributed_runtime_diagnostics.json", {})
        return raw if isinstance(raw, dict) else {}

    def _llm_diagnostics(self) -> dict[str, Any]:
        raw = _read_json(self.run_path / "llm_self_improvement_diagnostics.json", {})
        return raw if isinstance(raw, dict) else {}

    def _harmony_report(self) -> dict[str, Any]:
        raw = _read_json(self.run_path / "harmony_report.json", {})
        return raw if isinstance(raw, dict) else {}

    def _compliance_report(self) -> dict[str, Any]:
        raw = _read_json(self.run_path / "compliance_engine_report.json", {})
        return raw if isinstance(raw, dict) else {}

    def _report_rows(self) -> list[dict[str, Any]]:
        rows = _read_json(self.run_path / "report.json", [])
        return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def _latest_report_row(self) -> dict[str, Any]:
        rows = self._report_rows()
        return rows[-1] if rows else {}

    def _order_plans(self) -> list[dict[str, Any]]:
        rows = _read_json(self.run_path / "order_plans.json", [])
        return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def _positions(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.sqlite.latest_positions(limit=max(1, int(limit)))
        return [dict(row) for row in rows]

    def _orders(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.sqlite.latest_orders(limit=max(1, int(limit)))
        return [dict(row) for row in rows]

    def _submissions(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.sqlite.recent_submissions(limit=max(1, int(limit)))
        return [dict(row) for row in rows]

    def _fills(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.sqlite.session() as s:
            rows = s.execute(
                __import__("sqlalchemy").text(
                    "SELECT ts, symbol, side, qty, price, fee_quote, funding_quote, interest_quote, payload FROM fills ORDER BY id DESC LIMIT :lim"
                ),
                {"lim": max(1, int(limit))},
            ).mappings().all()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = _payload_dict(item.get("payload"))
            out.append(item)
        return out

    def _module_events(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.sqlite.latest_module_events(limit=max(1, int(limit)))
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = _payload_dict(item.get("payload"))
            out.append(item)
        return out

    def _audit_rows(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = _tail_jsonl(self.run_path / "audit.log", limit=limit)
        rows.extend(_tail_jsonl(self.run_path / "event_bus.jsonl", limit=limit))
        rows.extend(_tail_jsonl(self.run_path / "universe_events" / "event_bus.jsonl", limit=limit))
        rows.extend(_tail_jsonl(self.run_path / "universe_events" / "events_universe.jsonl", limit=limit))
        return rows[-max(1, int(limit)) :]

    def _module_row(self, name: str, *, status: str, confidence: float, influence: float, last_update: Any, source: str) -> dict[str, Any]:
        return {
            "module_name": name,
            "status": str(status or "unknown"),
            "confidence": _clamp(confidence, 0.0, 1.0),
            "influence": _clamp(influence, 0.0, 1.0),
            "last_update": str(last_update or _utc_now_iso()),
            "source": source,
        }

    # Shared compatibility/read model layer
    def health_payload(self) -> dict[str, Any]:
        db = self.sqlite.health()
        return {
            "ok": True,
            "ts": _utc_now_iso(),
            "run_dir": str(self.run_path),
            "run_resolution": self.run_resolution.to_dict(),
            "sqlite": db,
            "runtime": self._runtime_health(),
            "watchdog": self._watchdog_state(),
        }

    def status_payload(self) -> dict[str, Any]:
        runtime = self._runtime_health()
        watchdog = self._watchdog_state()
        snapshot = self._dashboard_snapshot()
        system_state = self.projections.get_latest(domain="system")
        if not system_state:
            system_state = {
                "status": runtime.get("status", "unknown"),
                "provider": runtime.get("provider", "unknown"),
                "symbol": runtime.get("symbol", ""),
                "reason": runtime.get("reason", "unknown"),
                "distributed": self._distributed_diagnostics(),
                "mastermind": self._mastermind_status(),
            }
        return {
            "ts": _utc_now_iso(),
            "run_resolution": self.run_resolution.to_dict(),
            "runtime_health": runtime,
            "watchdog": watchdog,
            "dashboard_snapshot": snapshot,
            "system_state": system_state,
        }

    def positions_payload(self, limit: int = 200) -> dict[str, Any]:
        latest: dict[str, dict[str, Any]] = {}
        for row in self._positions(limit=limit):
            symbol = str(row.get("symbol", "") or "")
            if symbol and symbol not in latest:
                latest[symbol] = row
        return {"positions": list(latest.values()), "count": len(latest)}

    def audit_events_payload(self, limit: int = 200) -> dict[str, Any]:
        rows = self._audit_rows(limit=limit)
        return {"rows": rows, "count": len(rows)}

    # Universe /api contract
    def api_system_status(self) -> dict[str, Any]:
        runtime = self._runtime_health()
        audit = self.api_audit_runtime()
        return {
            "mode": str(runtime.get("mode", "Paper") or "Paper"),
            "version": str(runtime.get("version", "0.1.0") or "0.1.0"),
            "uptime": float(runtime.get("uptime", 0.0) or 0.0),
            "last_audit": str(audit.get("updated_at", runtime.get("updated_at", _utc_now_iso())) or _utc_now_iso()),
            "health": str(runtime.get("status", "unknown") or "unknown"),
            "reason": str(runtime.get("reason", "unknown") or "unknown"),
            "provider": str(runtime.get("provider", "unknown") or "unknown"),
            "symbol": str(runtime.get("symbol", "") or ""),
        }

    def api_system_version(self) -> dict[str, Any]:
        status = self.api_system_status()
        return {
            "version": status["version"],
            "schema_version": "v1",
            "service": "universe-gateway-api",
        }

    def api_system_environment(self) -> dict[str, Any]:
        status = self.api_system_status()
        diagnostics = self._distributed_diagnostics()
        gate = self._live_gate_state()
        return {
            "mode": status["mode"],
            "run_id": str(self._runtime_health().get("run_id", "latest") or "latest"),
            "environment": "production" if status["mode"] == "Live" else "staging",
            "node_role": str(diagnostics.get("node_role", "live") or "live"),
            "distributed_enabled": bool(diagnostics.get("enabled", False)),
            "requested_mode": gate.get("requested_run_mode", self.run_resolution.requested_mode),
            "target_mode": gate.get("target_mode", self.run_resolution.target_mode),
            "runtime_mode": gate.get("runtime_mode", self.run_resolution.runtime_mode),
            "resolved_run_dir": gate.get("resolved_run_dir", str(self.run_path)),
            "resolved_run_source": gate.get("resolved_run_source", self.run_resolution.source),
        }

    def api_capital_state(self) -> dict[str, Any]:
        latest = self.projections.get_latest(domain="capital")
        if latest:
            return latest

        report = self._latest_report_row()
        snapshot = self._dashboard_snapshot()
        groups = self._snapshot_groups()
        performance = groups.get("performance", {}) if isinstance(groups.get("performance"), dict) else {}
        risk = groups.get("risk", {}) if isinstance(groups.get("risk"), dict) else {}
        positions = self._positions(limit=40)
        unrealized = sum(float(row.get("unrealized_pnl_quote", 0.0) or 0.0) for row in positions)
        realized = sum(float(row.get("realized_pnl_quote", 0.0) or 0.0) for row in positions)

        equity = float(report.get("equity", 0.0) or 0.0)
        if equity <= 0.0:
            equity = float(snapshot.get("equity", 0.0) or 0.0)
        if equity <= 0.0:
            equity = float(performance.get("net_pnl_after_fees", 0.0) or 0.0) + 1.0

        profit = float(report.get("profit", report.get("pnl", snapshot.get("pnl", performance.get("pnl", 0.0)))) or 0.0)
        if profit == 0.0:
            profit = float(performance.get("net_pnl_after_fees", 0.0) or 0.0) + unrealized + realized

        drawdown = float(report.get("drawdown_pct", snapshot.get("drawdown_pct", risk.get("drawdown", 0.0))) or 0.0)
        allocation = float(risk.get("exposure_notional", 0.0) or 0.0)
        kill_switch = bool(risk.get("kill_switch_state", 0.0))
        survivability = 100.0 - abs(drawdown) * 2.0 - (25.0 if kill_switch else 0.0)

        return {
            "equity": equity,
            "drawdown_pct": drawdown,
            "profit": profit,
            "allocation": allocation,
            "survivability_score": _clamp(survivability, 0.0, 100.0),
            "positions_open": len([row for row in positions if abs(float(row.get("signed_qty", 0.0) or 0.0)) > 0.0]),
            "updated_at": _utc_now_iso(),
        }

    def api_capital_equity(self) -> dict[str, Any]:
        state = self.api_capital_state()
        return {
            "equity": state.get("equity", 0.0),
            "profit": state.get("profit", 0.0),
            "timestamp": str(state.get("updated_at", _utc_now_iso())),
        }

    def api_capital_drawdown(self) -> dict[str, Any]:
        state = self.api_capital_state()
        return {
            "drawdown_pct": state.get("drawdown_pct", 0.0),
            "survivability_score": state.get("survivability_score", 0.0),
            "timestamp": str(state.get("updated_at", _utc_now_iso())),
        }

    def api_brain_modules(self) -> dict[str, Any]:
        latest = self.projections.get_latest(domain="decision")
        modules = latest.get("modules") if isinstance(latest.get("modules"), list) else []
        if modules:
            return {"rows": modules}

        runtime = self._runtime_health()
        mastermind = self._mastermind_status()
        diagnostics = self._distributed_diagnostics()
        harmony = self._harmony_report()
        llm = self._llm_diagnostics()
        groups = self._snapshot_groups()
        execution = groups.get("execution", {}) if isinstance(groups.get("execution"), dict) else {}
        memory = groups.get("universe_memory", {}) if isinstance(groups.get("universe_memory"), dict) else {}
        decision = groups.get("decision", {}) if isinstance(groups.get("decision"), dict) else {}
        module_events = self._module_events(limit=80)
        last_event = module_events[0] if module_events else {}
        updated_at = last_event.get("ts", runtime.get("updated_at", _utc_now_iso()))

        rows = [
            self._module_row(
                "Mission Engine",
                status=runtime.get("status", "unknown"),
                confidence=0.82 if str(runtime.get("status", "")).lower() in {"ok", "running"} else 0.38,
                influence=0.86,
                last_update=runtime.get("updated_at", updated_at),
                source="runtime_health",
            ),
            self._module_row(
                "Strategy Parliament",
                status="ok" if float(decision.get("decision_tick_total", 0.0) or 0.0) >= 0.0 else "unknown",
                confidence=0.55 if mastermind.get("ok", False) else 0.22,
                influence=0.74,
                last_update=updated_at,
                source="mastermind_status",
            ),
            self._module_row(
                "Execution Layer",
                status="degraded" if float(execution.get("orders_rejected_total", 0.0) or 0.0) > 0.0 else "ok",
                confidence=1.0 - _clamp(float(execution.get("reject_rate", 0.0) or 0.0), 0.0, 1.0),
                influence=0.91,
                last_update=updated_at,
                source="dashboard_snapshot.execution",
            ),
            self._module_row(
                "Shield Layer",
                status="blocked" if mastermind.get("invariant_breach", False) else "ok",
                confidence=0.9 if not mastermind.get("invariant_breach", False) else 0.25,
                influence=0.96,
                last_update=runtime.get("updated_at", updated_at),
                source="mastermind_status",
            ),
            self._module_row(
                "Memory System",
                status="ok" if float(memory.get("universe_memory_trace_rows", 0.0) or 0.0) >= 0.0 else "unknown",
                confidence=0.68 if self.sqlite.health().get("module_events", 0) > 0 else 0.3,
                influence=0.63,
                last_update=updated_at,
                source="sqlite.module_events",
            ),
            self._module_row(
                "Meta Intelligence",
                status="disabled" if not llm.get("llm_enabled", False) else "ok",
                confidence=0.7 if llm.get("llm_enabled", False) else 0.18,
                influence=0.46,
                last_update=llm.get("ts", updated_at),
                source="llm_self_improvement_diagnostics",
            ),
            self._module_row(
                "Future Simulation",
                status="ok" if diagnostics.get("compute_bridge", {}).get("ok", False) or diagnostics else "unknown",
                confidence=0.72 if diagnostics else 0.28,
                influence=0.67,
                last_update=diagnostics.get("compute_bridge", {}).get("ts", updated_at),
                source="distributed_runtime_diagnostics",
            ),
            self._module_row(
                "Harmony Protocol",
                status="ok" if harmony else "unknown",
                confidence=0.78 if harmony else 0.2,
                influence=0.71,
                last_update=updated_at,
                source="harmony_report",
            ),
        ]
        return {"rows": rows}

    def api_brain_decision(self) -> dict[str, Any]:
        latest = self.projections.get_latest(domain="decision")
        if latest:
            return latest
        decisions = self.projections.recent_events(stream=None, event_type="decision_tick", limit=1)
        if decisions:
            return decisions[0]

        compliance = self._compliance_report()
        runtime = self._runtime_health()
        plans = self._order_plans()
        orders = self._orders(limit=1)
        strategy = "runtime_guardian"
        action = "hold"
        reason = str(runtime.get("reason", compliance.get("reason", "no_live_decision_published")) or "no_live_decision_published")
        symbol = str(runtime.get("symbol", "") or "")
        confidence = 0.52 if compliance.get("allowed", True) else 0.18

        if plans:
            first = plans[0]
            symbol = str(first.get("symbol", symbol) or symbol)
            action = str(first.get("side", first.get("action", "hold")) or "hold").lower()
            strategy = str(first.get("strategy", first.get("source", "order_plan")) or "order_plan")
            reason = str(first.get("reason", reason) or reason)
            confidence = _clamp(float(first.get("confidence", 0.74) or 0.74), 0.0, 1.0)
        elif orders:
            first = orders[0]
            symbol = str(first.get("symbol", symbol) or symbol)
            action = str(first.get("side", "hold") or "hold").lower()
            strategy = str(first.get("venue", strategy) or strategy)
            reason = str(first.get("reason", reason) or reason)
            confidence = 0.61 if str(first.get("status", "")).lower() in {"submitted", "filled"} else confidence

        return {
            "strategy": strategy,
            "action": action,
            "confidence": confidence,
            "symbol": symbol,
            "reason": reason,
            "timestamp": str(runtime.get("updated_at", _utc_now_iso())),
        }

    def api_strategies(self) -> dict[str, Any]:
        latest = self.projections.get_latest(domain="decision")
        ranking = latest.get("strategies") if isinstance(latest.get("strategies"), list) else []
        if ranking:
            return {"rows": ranking}

        plans = self._order_plans()
        if plans:
            rows = []
            for plan in plans[:8]:
                rows.append(
                    {
                        "strategy_id": str(plan.get("strategy", plan.get("source", "runtime_plan")) or "runtime_plan"),
                        "confidence": _clamp(float(plan.get("confidence", 0.7) or 0.7), 0.0, 1.0),
                        "vote_weight": 1.0 / max(1, len(plans[:8])),
                        "allocation_share": _clamp(float(plan.get("allocation_share", 0.0) or 0.0), 0.0, 1.0),
                        "status": str(plan.get("status", "active") or "active"),
                    }
                )
            return {"rows": rows}

        return {"rows": []}

    def api_execution_orders(self, limit: int = 200) -> dict[str, Any]:
        return {"rows": self._orders(limit=limit)}

    def api_execution_fills(self, limit: int = 200) -> dict[str, Any]:
        return {"rows": self._fills(limit=limit)}

    def api_execution_stats(self) -> dict[str, Any]:
        submissions = self._submissions(limit=500)
        fills = self._fills(limit=500)
        groups = self._snapshot_groups()
        execution = groups.get("execution", {}) if isinstance(groups.get("execution"), dict) else {}
        execution_qa = groups.get("execution_qa", {}) if isinstance(groups.get("execution_qa"), dict) else {}
        costs = groups.get("costs", {}) if isinstance(groups.get("costs"), dict) else {}
        risk = groups.get("risk", {}) if isinstance(groups.get("risk"), dict) else {}

        blocked = len([r for r in submissions if str(r.get("status", "")).lower() in {"blocked", "rejected", "deny", "error"}])
        submitted = len(submissions)
        rejected = len([r for r in submissions if str(r.get("status", "")).lower() in {"rejected", "error"}])
        filled = len(fills)

        if submitted == 0:
            submitted = int(float(execution.get("orders_submitted_total", execution.get("executions_submitted_total", 0.0)) or 0.0))
        if filled == 0:
            filled = int(float(execution.get("fills_confirmed_total", 0.0) or 0.0))
        if blocked == 0:
            blocked = int(float(execution.get("orders_rejected_total", 0.0) or 0.0) + float(risk.get("risk_reject_total", 0.0) or 0.0))
        if rejected == 0:
            rejected = int(float(execution.get("orders_rejected_total", 0.0) or 0.0))

        mean_latency = 0.0
        slippage = 0.0
        if fills:
            lat_candidates = [float(_payload_dict(row.get("payload")).get("latency_ms", 0.0) or 0.0) for row in fills]
            lat_candidates = [v for v in lat_candidates if v > 0]
            if lat_candidates:
                mean_latency = sum(lat_candidates) / len(lat_candidates)
            slip_candidates = [float(_payload_dict(row.get("payload")).get("slippage_bps", 0.0) or 0.0) for row in fills]
            slip_candidates = [v for v in slip_candidates if v >= 0]
            if slip_candidates:
                slippage = sum(slip_candidates) / len(slip_candidates)

        if mean_latency <= 0.0:
            mean_latency = float(execution_qa.get("latency_p50_ms", execution_qa.get("latency_p95_ms", 0.0)) or 0.0)
        if slippage <= 0.0:
            slippage = float(costs.get("slippage_bps", 0.0) or 0.0)

        return {
            "blocked_orders": blocked,
            "submitted_orders": submitted,
            "filled_orders": filled,
            "rejected_orders": rejected,
            "latency": mean_latency,
            "slippage": slippage,
        }

    def api_telemetry_events(self, limit: int = 200) -> dict[str, Any]:
        latest = self.projections.get_latest(domain="telemetry")
        rows = latest.get("events") if isinstance(latest.get("events"), list) else []
        if rows:
            return {"rows": rows[: max(1, int(limit))]}

        audit_rows = self._audit_rows(limit=max(1, int(limit)))
        mapped = []
        for row in reversed(audit_rows[-max(1, int(limit)) :]):
            payload = _payload_dict(row.get("payload"))
            nested = _payload_dict(payload.get("payload"))
            event_type = str(
                row.get("event_type")
                or payload.get("event_type")
                or row.get("kind")
                or payload.get("legacy_event_type")
                or "telemetry"
            )
            reason = str(
                row.get("reason")
                or payload.get("reason")
                or nested.get("reason")
                or nested.get("status")
                or payload.get("status")
                or row.get("message")
                or ""
            )
            mapped.append(
                {
                    "event_type": event_type,
                    "frequency": float(row.get("frequency", 1.0) or 1.0),
                    "reason": reason,
                    "timestamp": str(
                        row.get("ts")
                        or row.get("timestamp")
                        or payload.get("ts")
                        or payload.get("event_time")
                        or _utc_now_iso()
                    ),
                }
            )
        return {"rows": mapped}

    def api_telemetry_distribution(self) -> dict[str, Any]:
        events = self.api_telemetry_events(limit=1000).get("rows", [])
        freq: dict[str, int] = {}
        for event in events:
            kind = str(event.get("event_type", "unknown") or "unknown")
            freq[kind] = freq.get(kind, 0) + 1
        rows = [{"event_type": k, "frequency": v} for k, v in sorted(freq.items(), key=lambda item: item[1], reverse=True)]
        return {"rows": rows}

    def api_audit_runtime(self) -> dict[str, Any]:
        latest = self.projections.get_latest(domain="audit")
        if latest:
            payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else latest
            if isinstance(payload, dict) and any(
                key in payload for key in ("system_state", "hard_invariants_status", "drift_status", "gate_status", "readiness_stage")
            ):
                normalized = dict(payload)
                normalized.setdefault("updated_at", str(latest.get("timestamp", latest.get("updated_at", _utc_now_iso()))))
                gate = self._live_gate_state()
                normalized.setdefault("target_mode", gate.get("target_mode", self.run_resolution.target_mode))
                normalized.setdefault("runtime_mode", gate.get("runtime_mode", self.run_resolution.runtime_mode))
                normalized.setdefault("manual_gate_status", gate.get("manual_gate_status", "unknown"))
                normalized.setdefault("operator_approval_status", gate.get("operator_approval_status", "unknown"))
                normalized.setdefault("config_freeze_status", gate.get("config_freeze_status", "unknown"))
                normalized.setdefault("promotion_status", gate.get("promotion_status", "unknown"))
                normalized.setdefault("resolved_run_dir", gate.get("resolved_run_dir", str(self.run_path)))
                normalized.setdefault("resolved_run_source", gate.get("resolved_run_source", self.run_resolution.source))
                normalized.setdefault("canary_envelope", gate.get("canary_envelope", {}))
                return normalized

        runtime = self._runtime_health()
        compliance = self._compliance_report()
        mastermind = self._mastermind_status()
        diagnostics = self._distributed_diagnostics()
        gate = self._live_gate_state()
        system_state = str(runtime.get("status", "unknown") or "unknown")
        invariants_ok = bool(mastermind.get("ok", False)) and not bool(mastermind.get("invariant_breach", False))
        hard_invariants_status = "clean" if invariants_ok else "tripped"
        drift_status = "fallback" if diagnostics.get("allow_local_fallback", False) else "strict"
        gate_status = "open" if compliance.get("allowed", True) and gate.get("deployment_gate_open", True) else "blocked"
        if gate.get("manual_gate_required", False) and gate.get("manual_gate_status") != "open":
            gate_status = "blocked"

        if gate.get("target_mode") in {"live", "canary"} and gate.get("runtime_mode") == "paper":
            readiness_stage = "paper_fallback"
        elif system_state.lower() in {"ok", "running"} and gate_status == "open":
            readiness_stage = "operational"
        elif gate_status == "blocked":
            readiness_stage = "blocked"
        else:
            readiness_stage = "staging"

        return {
            "system_state": system_state,
            "hard_invariants_status": hard_invariants_status,
            "drift_status": drift_status,
            "gate_status": gate_status,
            "readiness_stage": readiness_stage,
            "updated_at": str(runtime.get("updated_at", _utc_now_iso())),
            "target_mode": gate.get("target_mode", self.run_resolution.target_mode),
            "runtime_mode": gate.get("runtime_mode", self.run_resolution.runtime_mode),
            "manual_gate_status": gate.get("manual_gate_status", "unknown"),
            "operator_approval_status": gate.get("operator_approval_status", "unknown"),
            "config_freeze_status": gate.get("config_freeze_status", "unknown"),
            "promotion_status": gate.get("promotion_status", "unknown"),
            "resolved_run_dir": gate.get("resolved_run_dir", str(self.run_path)),
            "resolved_run_source": gate.get("resolved_run_source", self.run_resolution.source),
            "canary_envelope": gate.get("canary_envelope", {}),
        }

    def api_audit_preflight(self) -> dict[str, Any]:
        runtime = dict(self.api_audit_runtime())
        runtime["preflight_checked_at"] = _utc_now_iso()
        return runtime

    def api_audit_config(self) -> dict[str, Any]:
        cfg = self._config_payload()
        runtime = self.api_audit_runtime()
        return {
            "system_state": runtime.get("system_state", "unknown"),
            "hard_invariants_status": runtime.get("hard_invariants_status", "unknown"),
            "drift_status": runtime.get("drift_status", "unknown"),
            "gate_status": runtime.get("gate_status", "unknown"),
            "readiness_stage": runtime.get("readiness_stage", "unknown"),
            "config": cfg,
        }

    def api_replay_sessions(self) -> dict[str, Any]:
        sessions = []
        root = self.run_path / "recordings"
        if root.exists():
            for child in sorted(root.iterdir(), reverse=True):
                if not child.is_dir():
                    continue
                sessions.append({"session_id": child.name, "path": str(child)})
        return {"rows": sessions}

    def api_replay_events(self, session_id: str | None = None, limit: int = 400) -> dict[str, Any]:
        if session_id:
            path = self.run_path / "recordings" / session_id / "market.jsonl"
        else:
            path = self.run_path / "universe_events" / "event_bus.jsonl"
            if not path.exists():
                path = self.run_path / "event_bus.jsonl"
        rows = _tail_jsonl(path, limit=max(1, int(limit)))
        return {"rows": rows, "count": len(rows)}

    def api_simulation_scenarios(self) -> dict[str, Any]:
        latest = self.projections.get_latest(domain="simulation")
        rows = latest.get("scenarios") if isinstance(latest.get("scenarios"), list) else []
        if rows:
            return {"rows": rows}

        capital = self.api_capital_state()
        harmony = self._harmony_report()
        profit = float(capital.get("profit", 0.0) or 0.0)
        drawdown = abs(float(capital.get("drawdown_pct", 0.0) or 0.0))
        cadence = float(harmony.get("order_cadence_s", 60.0) or 60.0)
        risk_bias = 12.0 if cadence >= 60.0 else 22.0
        return {
            "rows": [
                {"branch_probability": 0.55, "expected_pnl": profit, "risk_score": _clamp(drawdown + risk_bias, 0.0, 100.0)},
                {"branch_probability": 0.30, "expected_pnl": profit * 0.45, "risk_score": _clamp(drawdown + risk_bias + 18.0, 0.0, 100.0)},
                {"branch_probability": 0.15, "expected_pnl": profit - max(1.0, abs(profit) * 0.75), "risk_score": _clamp(drawdown + risk_bias + 40.0, 0.0, 100.0)},
            ]
        }
