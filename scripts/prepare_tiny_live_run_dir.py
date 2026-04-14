#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parent.parent
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector, KrakenSpotConnectorError


RESET_EVIDENCE_NAMES = (
    "events_account.jsonl",
    "events_orders.jsonl",
    "events_fills.jsonl",
    "events_positions.jsonl",
    "events_truth.jsonl",
    "lifecycle_journal.jsonl",
    "lifecycle_evidence_journal.jsonl",
    "execution_journal.jsonl",
    "control_journal.jsonl",
    "reconciliation_journal.jsonl",
    "reconciliation_report.jsonl",
    "execution_lifecycle_report.json",
    "health_summary.json",
    "readiness_summary.json",
    "live_safety_summary.json",
    "kraken_spot_operator_summary.json",
)


def _now_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:
        return 0


def inspect_local_runtime_state(run_dir: Path) -> dict[str, Any]:
    evidence: dict[str, int] = {}
    for name in RESET_EVIDENCE_NAMES:
        path = run_dir / name
        if name.endswith(".jsonl"):
            count = _read_jsonl_count(path)
        else:
            count = 1 if path.exists() and path.stat().st_size > 0 else 0
        if count > 0:
            evidence[name] = count
    return {
        "run_dir": str(run_dir),
        "exists": run_dir.exists(),
        "has_local_runtime_state": bool(evidence),
        "evidence_counts": evidence,
    }


def inspect_exchange_state(settings: RobotSettings) -> dict[str, Any]:
    if settings.execution.provider_id != "kraken_spot":
        return {"ok": False, "reason": f"unsupported_provider:{settings.execution.provider_id}"}
    if settings.execution_mode_enum() != ExecutionMode.LIVE:
        return {"ok": False, "reason": f"unsupported_mode:{settings.execution_mode_enum().value}"}
    symbol = settings.universe[0] if settings.universe else ""
    if not symbol:
        return {"ok": False, "reason": "empty_universe"}
    try:
        connector = KrakenSpotConnector(settings.execution.kraken_spot)
        open_orders = connector.open_orders(symbol)
        balance = connector.base_balance(symbol)
        constraints = connector.market_constraints(symbol)
    except KrakenSpotConnectorError as exc:
        return {"ok": False, "reason": str(exc)}
    except Exception as exc:
        return {"ok": False, "reason": f"exchange_probe_failed:{exc}"}

    total_qty = float(balance.get("total", 0.0) or 0.0)
    free_qty = float(balance.get("free", 0.0) or 0.0)
    min_qty = float(constraints.get("min_order_size", 0.0) or 0.0)
    tolerance = max(1e-8, min_qty, total_qty * 0.02)
    flat = abs(total_qty) <= tolerance
    return {
        "ok": True,
        "symbol": symbol,
        "open_order_count": len(open_orders),
        "base_total_qty": total_qty,
        "base_free_qty": free_qty,
        "tolerance_qty": tolerance,
        "flat": flat,
        "reason": "exchange_flat_no_open_orders" if flat and not open_orders else "exchange_session_active",
    }


def _archive_target(active_run_dir: Path, archive_root: Path) -> Path:
    archive_root.mkdir(parents=True, exist_ok=True)
    return archive_root / f"{active_run_dir.name}_prelaunch_{_now_token()}"


def prepare_tiny_live_run_dir(
    settings: RobotSettings,
    *,
    archive_root: Path | None = None,
) -> dict[str, Any]:
    run_dir = Path(settings.storage.run_dir)
    archive_root = archive_root or (REPO / "run_archives")
    local = inspect_local_runtime_state(run_dir)
    exchange = inspect_exchange_state(settings)
    payload: dict[str, Any] = {
        "status": "ok",
        "run_dir": str(run_dir),
        "archive_root": str(archive_root),
        "local_runtime_state": local,
        "exchange_state": exchange,
        "action": "none",
        "reason": "no_local_runtime_state",
    }
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=True)
    if not local["has_local_runtime_state"]:
        return payload
    if not exchange.get("ok"):
        payload["action"] = "preserve_existing_session"
        payload["reason"] = f"exchange_probe_unavailable:{exchange.get('reason', 'unknown')}"
        return payload
    if int(exchange.get("open_order_count", 0) or 0) > 0 or not bool(exchange.get("flat")):
        payload["action"] = "preserve_existing_session"
        payload["reason"] = "exchange_session_active"
        return payload

    archive_path = _archive_target(run_dir, archive_root)
    shutil.move(str(run_dir), str(archive_path))
    run_dir.mkdir(parents=True, exist_ok=True)
    payload["action"] = "archive_and_reset"
    payload["reason"] = "exchange_flat_and_local_runtime_state_present"
    payload["archived_run_dir"] = str(archive_path)
    archive_manifest = {
        **payload,
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
    (archive_path / "tiny_live_session_prepare.json").write_text(
        json.dumps(archive_manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.kraken_spot.tiny_live.yaml")
    parser.add_argument("--archive-root", default=str(REPO / "run_archives"))
    args = parser.parse_args()

    settings = RobotSettings.from_file(str(REPO / args.config))
    payload = prepare_tiny_live_run_dir(settings, archive_root=Path(args.archive_root))
    active_run_dir = Path(settings.storage.run_dir)
    active_run_dir.mkdir(parents=True, exist_ok=True)
    (active_run_dir / "tiny_live_session_prepare.json").write_text(
        json.dumps(
            {
                **payload,
                "prepared_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
