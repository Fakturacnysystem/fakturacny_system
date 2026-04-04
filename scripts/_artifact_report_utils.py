#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--run-id", help="Run ID under runs/. Defaults to runs/latest.")
    parser.add_argument("--run-dir", help="Explicit run directory. Overrides --run-id.")
    parser.add_argument("--output", help="Optional output file. Defaults to stdout.")
    return parser


def resolve_run_dir(*, run_id: str | None, run_dir: str | None) -> Path:
    if run_dir:
        path = Path(run_dir).expanduser().resolve()
    elif run_id:
        path = (REPO / "runs" / run_id).resolve()
    else:
        path = (REPO / "runs" / "latest").resolve()
    if not path.exists():
        raise SystemExit(f"run_not_found:{path}")
    if not path.is_dir():
        raise SystemExit(f"run_not_directory:{path}")
    return path


def load_json(run_dir: Path, name: str, *, required: bool = True, default: Any | None = None) -> Any:
    path = run_dir / name
    if not path.exists():
        if required:
            raise SystemExit(f"artifact_missing:{path}")
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_or_unavailable(run_dir: Path, name: str) -> Any:
    path = run_dir / name
    if not path.exists():
        return {
            "status": "unavailable",
            "reason": "artifact_missing",
            "artifact": name,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def emit_json(payload: Any, *, output: str | None) -> int:
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if output:
        path = Path(output).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0
