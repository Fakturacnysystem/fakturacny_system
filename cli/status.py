from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import _load_yaml_like  # noqa: E402


def _latest_audit_events(run_dir: str, limit: int = 120) -> list[dict]:
    p = Path(run_dir) / "audit.log"
    if not p.exists():
        return []
    rows = []
    lines = p.read_text(encoding="utf-8").splitlines()
    for raw in lines[-max(1, limit) :]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except Exception:
            continue
    return rows


def _resolve_run_dir(config_path: str, explicit_run_dir: str) -> str:
    if explicit_run_dir:
        return explicit_run_dir
    try:
        cfg = _load_yaml_like(config_path)
        storage = cfg.get("storage", {}) if isinstance(cfg, dict) else {}
        value = storage.get("run_dir")
        if isinstance(value, str) and value.strip():
            return value
    except Exception:
        pass
    return "runs/kraken_spot_live"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.kraken_spot.live_profit.yaml")
    p.add_argument("--run-dir", default="")
    args = p.parse_args()

    run_dir = _resolve_run_dir(args.config, args.run_dir)
    submissions: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    storage_health: dict[str, Any] = {"ok": False, "reason": "storage_unavailable"}

    try:
        from autonomous_investment_robot.services.storage import SQLiteStore  # noqa: E402

        store = SQLiteStore(run_dir)
        submissions = store.recent_submissions(limit=120)
        positions = store.latest_positions(limit=20)
        orders = store.latest_orders(limit=20)
        storage_health = store.health()
    except ModuleNotFoundError as exc:
        if not str(exc).startswith("No module named 'sqlalchemy"):
            raise
        storage_health = {"ok": False, "reason": "sqlalchemy_missing"}

    audit = _latest_audit_events(run_dir, limit=120)

    latest_heartbeat = next((r for r in reversed(audit) if r.get("event_type") == "heartbeat"), {})
    out = {
        "run_dir": run_dir,
        "storage_health": storage_health,
        "latest_heartbeat": latest_heartbeat,
        "positions": positions,
        "recent_orders": orders,
        "recent_submissions": submissions,
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
