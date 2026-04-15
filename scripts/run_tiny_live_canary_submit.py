#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parent.parent
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator
from autonomous_investment_robot.main import request_pause, resume_runtime
from autonomous_investment_robot.services.execution.live_kraken_spot_service import (
    LiveExecutionResult,
    LiveKrakenSpotService,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return str(value)


def _plan_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {str(k): _jsonable(v) for k, v in plan.items() if k != "intent"}


def _result_payload(result: LiveExecutionResult) -> dict[str, Any]:
    return {
        "status": str(result.status),
        "reason": str(result.reason),
        "order": _jsonable(result.order),
        "ledger_records": _jsonable(result.ledger_records),
        "gaps": [str(item) for item in result.gaps],
        "metadata": _jsonable(result.metadata),
    }


def _gate_truth(run_dir: Path) -> dict[str, Any]:
    operator = _read_json(run_dir / "kraken_spot_operator_summary.json")
    readiness = _read_json(run_dir / "readiness_summary.json") or _read_json(run_dir / "tiny_live_readiness_report.json")
    safety = _read_json(run_dir / "live_safety_summary.json")
    health = _read_json(run_dir / "health_summary.json")
    preflight_ok = (operator.get("preflight") or {}).get("ok")
    if preflight_ok is None:
        preflight_ok = health.get("preflight_ok")
    ordering_allowed = operator.get("ordering_allowed")
    if ordering_allowed is None:
        ordering_allowed = health.get("ordering_allowed", safety.get("ordering_allowed"))
    rollout_stage = operator.get("rollout_stage") or readiness.get("rollout_stage") or readiness.get("stage")
    mode = operator.get("mode")
    readiness_ready = readiness.get("readiness_ready", readiness.get("ready"))
    safety_ready = safety.get("safety_ready")
    blocking_reasons = list(health.get("blocking_reasons", []) or [])
    status = {
        "mode": mode,
        "rollout_stage": rollout_stage,
        "preflight_ok": bool(preflight_ok),
        "ordering_allowed": bool(ordering_allowed),
        "readiness_ready": bool(readiness_ready),
        "safety_ready": bool(safety_ready),
        "blocking_reasons": blocking_reasons,
        "trade_path_state": health.get("trade_path_state"),
        "health_summary_ts": health.get("ts"),
        "operator_summary_ts": operator.get("ts"),
        "ok": bool(
            mode == "live"
            and rollout_stage == "tiny_live"
            and preflight_ok
            and ordering_allowed
            and readiness_ready
            and safety_ready
            and not blocking_reasons
        ),
    }
    if not status["ok"]:
        reasons: list[str] = []
        if mode != "live":
            reasons.append(f"mode:{mode}")
        if rollout_stage != "tiny_live":
            reasons.append(f"rollout_stage:{rollout_stage}")
        if not preflight_ok:
            reasons.append("preflight_not_ok")
        if not ordering_allowed:
            reasons.append("ordering_not_allowed")
        if not readiness_ready:
            reasons.append("readiness_not_ready")
        if not safety_ready:
            reasons.append("safety_not_ready")
        reasons.extend(blocking_reasons)
        status["reasons"] = reasons
    return status


def _pause_acknowledged(run_dir: Path, *, reason: str) -> bool:
    for row in reversed(_read_jsonl(run_dir / "control_journal.jsonl")):
        payload = row.get("payload", row)
        if not isinstance(payload, dict):
            continue
        if str(payload.get("action", "")) != "pause":
            continue
        if str(payload.get("reason", "")) != reason:
            continue
        return True
    return False


def _wait_for_pause_ack(run_dir: Path, *, reason: str, timeout_s: float) -> bool:
    deadline = time.time() + max(1.0, float(timeout_s))
    while time.time() < deadline:
        if _pause_acknowledged(run_dir, reason=reason):
            return True
        time.sleep(0.5)
    return False


def _load_live_context(settings: RobotSettings) -> tuple[RobotOrchestrator, LiveKrakenSpotService]:
    orchestrator = RobotOrchestrator(settings)
    live = LiveKrakenSpotService(settings=settings, run_id=Path(settings.storage.run_dir).name)
    fill_events = orchestrator.event_store.load("fills")
    order_events = orchestrator.event_store.load("orders")
    position_events = orchestrator.event_store.load("positions")
    account_events = orchestrator.event_store.load("account")
    orchestrator.portfolio.rehydrate_from_events(
        fill_events=fill_events,
        position_events=position_events,
        account_events=account_events,
    )
    live.rehydrate_state(order_events=order_events, fill_events=fill_events)
    return orchestrator, live


def _pre_submit_truth(
    *,
    orchestrator: RobotOrchestrator,
    live: LiveKrakenSpotService,
    symbol: str,
) -> dict[str, Any]:
    preflight_ok, preflight_reason = live.preflight()
    exposure = abs(float(orchestrator.portfolio.snapshot(symbol).exposure_notional or 0.0))
    reconciliation = orchestrator.live_reconciliation.apply(
        live=live,
        symbol=symbol,
        exposure_notional=exposure,
        market_health=None,
    )
    lifecycle_snapshot = live.lifecycle_snapshot()
    active_lifecycle = [
        item
        for item in lifecycle_snapshot
        if isinstance(item, dict)
        and str(item.get("state", "")).lower() not in {"filled", "cancelled", "canceled", "rejected", "expired", "closed"}
    ]
    open_orders = live.connector.open_orders(symbol)
    return {
        "preflight_ok": bool(preflight_ok),
        "preflight_reason": str(preflight_reason),
        "reconciliation_ok": bool(reconciliation.ok),
        "reconciliation_report": None if reconciliation.report is None else _jsonable(reconciliation.report.to_dict()),
        "exposure_notional": float(reconciliation.exposure_notional),
        "open_order_count": len(open_orders) if isinstance(open_orders, list) else 0,
        "lifecycle_snapshot": _jsonable(lifecycle_snapshot),
        "active_lifecycle_snapshot": _jsonable(active_lifecycle),
    }


def run_canary(
    *,
    config_path: str,
    symbol: str,
    passive_offset_bps: float,
    expiry_seconds: int,
    quote_buffer_pct: float,
    pause_live_loop: bool,
    pause_wait_seconds: float,
) -> dict[str, Any]:
    settings = RobotSettings.from_file(str(REPO / config_path))
    run_dir = Path(settings.storage.run_dir)
    validate_path = run_dir / "tiny_live_canary_validate.json"
    result_path = run_dir / "tiny_live_canary_submit_result.json"
    once_path = run_dir / "tiny_live_canary_once.json"
    if settings.execution.provider_id != "kraken_spot":
        return {"status": "blocked", "reason": f"unsupported_provider:{settings.execution.provider_id}"}
    if settings.execution_mode_enum() != ExecutionMode.LIVE:
        return {"status": "blocked", "reason": f"invalid_mode:{settings.execution_mode_enum().value}"}
    if str(settings.rollout_stage().value) != "tiny_live":
        return {"status": "blocked", "reason": f"invalid_rollout_stage:{settings.rollout_stage().value}"}
    gate_truth = _gate_truth(run_dir)
    if not gate_truth.get("ok", False):
        return {"status": "blocked", "reason": "gate_truth_unhealthy", "gate_truth": gate_truth}

    orchestrator, live = _load_live_context(settings)
    pre_submit_truth = _pre_submit_truth(orchestrator=orchestrator, live=live, symbol=symbol)
    if not pre_submit_truth["preflight_ok"]:
        return {"status": "blocked", "reason": str(pre_submit_truth["preflight_reason"]), "pre_submit_truth": pre_submit_truth}
    if not pre_submit_truth["reconciliation_ok"]:
        return {"status": "blocked", "reason": "reconciliation_unhealthy", "pre_submit_truth": pre_submit_truth}
    if int(pre_submit_truth["open_order_count"]) > 0:
        return {"status": "blocked", "reason": "open_orders_present", "pre_submit_truth": pre_submit_truth}
    if list(pre_submit_truth["active_lifecycle_snapshot"]):
        return {"status": "blocked", "reason": "active_lifecycle_present", "pre_submit_truth": pre_submit_truth}

    pause_reason = "tiny_live_canary_submit"
    pause_payload: dict[str, Any] | None = None
    pause_acknowledged = False
    try:
        if pause_live_loop:
            pause_payload = request_pause(str(REPO / config_path), reason=pause_reason)
            pause_acknowledged = _wait_for_pause_ack(run_dir, reason=pause_reason, timeout_s=pause_wait_seconds)

        plan = live.prepare_tiny_live_canary(
            symbol=symbol,
            passive_offset_bps=passive_offset_bps,
            quote_buffer_pct=quote_buffer_pct,
            expiry_seconds=expiry_seconds,
        )
        validate_payload = {
            "status": "ok" if bool(plan.get("ok", False)) else "blocked",
            "phase": "validate_only",
            "generated_at": _now_iso(),
            "config": config_path,
            "run_dir": str(run_dir),
            "gate_truth": gate_truth,
            "pre_submit_truth": pre_submit_truth,
            "pause_requested": pause_payload,
            "pause_acknowledged": pause_acknowledged,
            "plan": _plan_payload(plan),
        }
        _write_json(validate_path, validate_payload)
        if not bool(plan.get("ok", False)):
            return {
                "status": "blocked",
                "reason": str(plan.get("reason", "validate_only_failed")),
                "validate_artifact": str(validate_path),
                "validate_payload": validate_payload,
            }

        if once_path.exists():
            return {
                "status": "blocked",
                "reason": "canary_already_executed",
                "once_marker": str(once_path),
                "validate_artifact": str(validate_path),
            }

        _write_json(
            once_path,
            {
                "status": "armed",
                "armed_at": _now_iso(),
                "config": config_path,
                "run_dir": str(run_dir),
                "client_order_id": str(plan.get("client_order_id", "")),
                "symbol": symbol,
            },
        )
        result = live.submit_tiny_live_canary(plan)
        ledger_result = orchestrator.live_ledger.apply_execution_result(
            symbol=symbol,
            provider_id="kraken_spot",
            result=result,
            fallback_intent_notional=float(plan.get("validation_target_notional", 0.0) or 0.0),
            fallback_side="buy",
            current_exposure=abs(float(orchestrator.portfolio.snapshot(symbol).exposure_notional or 0.0)),
            live=live,
        )
        reconciliation = orchestrator.live_reconciliation.apply(
            live=live,
            symbol=symbol,
            exposure_notional=float(ledger_result.exposure_notional),
            market_health=None,
        )
        final_status = (
            "ok"
            if str(result.status) in {"submitted", "filled_maker", "filled_taker_fallback", "filled_marketable_limit"}
            and bool(reconciliation.ok)
            else "blocked"
        )
        payload = {
            "status": final_status,
            "phase": "real_submit",
            "completed_at": _now_iso(),
            "config": config_path,
            "run_dir": str(run_dir),
            "gate_truth": gate_truth,
            "pre_submit_truth": pre_submit_truth,
            "pause_requested": pause_payload,
            "pause_acknowledged": pause_acknowledged,
            "plan": _plan_payload(plan),
            "result": _result_payload(result),
            "ledger_result": _jsonable(ledger_result),
            "reconciliation_ok": bool(reconciliation.ok),
            "reconciliation_report": None if reconciliation.report is None else _jsonable(reconciliation.report.to_dict()),
            "post_gate_truth": _gate_truth(run_dir),
        }
        _write_json(result_path, payload)
        _write_json(once_path, {**payload, "status": "completed"})
        return payload
    finally:
        if pause_live_loop and pause_payload is not None:
            resume_runtime(str(REPO / config_path), reason="tiny_live_canary_submit_complete")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.kraken_spot.tiny_live.yaml")
    parser.add_argument("--symbol", default="BTC/USD")
    parser.add_argument("--passive-offset-bps", type=float, default=100.0)
    parser.add_argument("--expiry-seconds", type=int, default=15)
    parser.add_argument("--quote-buffer-pct", type=float, default=0.02)
    parser.add_argument("--pause-live-loop", action="store_true", default=True)
    parser.add_argument("--no-pause-live-loop", dest="pause_live_loop", action="store_false")
    parser.add_argument("--pause-wait-seconds", type=float, default=12.0)
    args = parser.parse_args()
    payload = run_canary(
        config_path=args.config,
        symbol=str(args.symbol),
        passive_offset_bps=float(args.passive_offset_bps),
        expiry_seconds=max(1, int(args.expiry_seconds)),
        quote_buffer_pct=max(0.0, float(args.quote_buffer_pct)),
        pause_live_loop=bool(args.pause_live_loop),
        pause_wait_seconds=max(1.0, float(args.pause_wait_seconds)),
    )
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if str(payload.get("status", "")) == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
