#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _write_env(path: Path, overrides: dict[str, str]) -> None:
    lines = [
        "#!/usr/bin/env bash",
        "# Restored by rollback_last_good.py",
    ]
    for k, v in sorted(overrides.items()):
        vv = str(v).replace('"', '\\"')
        lines.append(f'export {k}="{vv}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Restore env_overrides.sh from last_good_overrides.json")
    p.add_argument("--run-dir", default="runs/kraken_spot_live")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = Path(args.run_dir).expanduser()
    src = run_dir / "last_good_overrides.json"
    dst = run_dir / "env_overrides.sh"
    if not src.exists():
        print(json.dumps({"status": "blocked", "reason": "missing_last_good", "path": str(src)}))
        return 1
    payload = json.loads(src.read_text(encoding="utf-8"))
    overrides = payload.get("overrides", {})
    if not isinstance(overrides, dict):
        print(json.dumps({"status": "blocked", "reason": "invalid_last_good_payload"}))
        return 1
    _write_env(dst, {str(k): str(v) for k, v in overrides.items()})
    print(json.dumps({"status": "ok", "env_overrides": str(dst), "count": len(overrides)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
