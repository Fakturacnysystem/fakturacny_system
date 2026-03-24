#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parent.parent


def _validate_yaml(path: Path) -> dict[str, str]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data is None:
            return {"path": str(path), "status": "empty"}
        return {"path": str(path), "status": "ok"}
    except Exception as exc:  # pragma: no cover
        return {"path": str(path), "status": "error", "error": str(exc)}


def main() -> int:
    manifests = [
        REPO / "infra" / "docker-compose.yml",
        REPO / "infra" / "prometheus.yml",
    ]
    results = [_validate_yaml(path) for path in manifests if path.exists()]
    print(json.dumps(results, indent=2, sort_keys=True))
    return 1 if any(item["status"] == "error" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
