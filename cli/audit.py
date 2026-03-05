from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import _load_yaml_like  # noqa: E402
from autonomous_investment_robot.services.storage import SQLiteStore  # noqa: E402


def _ts_ok(ts: str, since_iso: str) -> bool:
    if not since_iso:
        return True
    try:
        l = ts.replace("Z", "+00:00")
        r = since_iso.replace("Z", "+00:00")
        dl = datetime.fromisoformat(l)
        dr = datetime.fromisoformat(r)
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)
        if dr.tzinfo is None:
            dr = dr.replace(tzinfo=timezone.utc)
        return dl >= dr
    except Exception:
        return True


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.kraken_spot.live_profit.yaml")
    p.add_argument("--since", default="")
    p.add_argument("--limit", type=int, default=200)
    args = p.parse_args()

    cfg = _load_yaml_like(args.config)
    storage = cfg.get("storage", {}) if isinstance(cfg, dict) else {}
    run_dir = str(storage.get("run_dir", "runs/kraken_spot_live") or "runs/kraken_spot_live")
    store = SQLiteStore(run_dir)

    module_events = store.latest_module_events(limit=max(1, int(args.limit)))
    violations = store.latest_violations(limit=max(1, int(args.limit)))

    module_events = [r for r in module_events if _ts_ok(str(r.get("ts", "")), args.since)]
    violations = [r for r in violations if _ts_ok(str(r.get("ts", "")), args.since)]

    audit_file = Path(run_dir) / "audit.log"
    audit_rows: list[dict] = []
    if audit_file.exists():
        lines = [ln for ln in audit_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for ln in lines[-max(1, int(args.limit)) :]:
            try:
                row = json.loads(ln)
                if isinstance(row, dict):
                    audit_rows.append(row)
            except Exception:
                continue

    out = {
        "status": "ok",
        "run_dir": run_dir,
        "since": args.since,
        "module_events": module_events,
        "violations": violations,
        "audit_tail": audit_rows,
        "counts": {
            "module_events": len(module_events),
            "violations": len(violations),
            "audit_tail": len(audit_rows),
        },
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
