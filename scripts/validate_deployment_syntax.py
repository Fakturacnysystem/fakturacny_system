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
        REPO / "docker-compose.yml",
        REPO / "infra" / "docker-compose.yml",
        REPO / "ops" / "docker-compose.server.yml",
        REPO / "infra" / "prometheus.yml",
        REPO / "ops" / "runtime_surface.json",
    ]
    results = [_validate_yaml(path) for path in manifests if path.exists()]
    root_compose = next((item for item in results if item["path"].endswith("docker-compose.yml")), None)
    if root_compose is not None and root_compose["status"] == "ok":
        root_path = Path(root_compose["path"])
        payload = yaml.safe_load(root_path.read_text(encoding="utf-8"))
        runtime_class = ((payload or {}).get("x-runtime-classification") or {}) if isinstance(payload, dict) else {}
        if runtime_class.get("status") != "legacy_blocked":
            results.append(
                {
                    "path": str(root_path),
                    "status": "error",
                    "error": "root compose must be marked legacy_blocked",
                }
            )
        services = ((payload or {}).get("services") or {}) if isinstance(payload, dict) else {}
        if any(isinstance(service, dict) and "build" in service for service in services.values()):
            results.append(
                {
                    "path": str(root_path),
                    "status": "error",
                    "error": "root compose must not define build contexts",
                }
            )
    server_path = REPO / "ops" / "docker-compose.server.yml"
    if server_path.exists():
        server_payload = yaml.safe_load(server_path.read_text(encoding="utf-8"))
        server_services = ((server_payload or {}).get("services") or {}) if isinstance(server_payload, dict) else {}
        trading_engine = server_services.get("trading-engine", {}) if isinstance(server_services, dict) else {}
        build = (trading_engine.get("build") or {}) if isinstance(trading_engine, dict) else {}
        if build.get("context") != ".." or build.get("dockerfile") != "Dockerfile":
            results.append(
                {
                    "path": str(server_path),
                    "status": "error",
                    "error": "server compose trading-engine must build from ../ with Dockerfile",
                }
            )
        if (trading_engine.get("command") or []) != ["bash", "scripts/container_start_tiny_live.sh"]:
            results.append(
                {
                    "path": str(server_path),
                    "status": "error",
                    "error": "server compose trading-engine must use scripts/container_start_tiny_live.sh",
                }
            )
        env = (trading_engine.get("environment") or {}) if isinstance(trading_engine, dict) else {}
        volumes = trading_engine.get("volumes") or []
        if env.get("TRADING_ENV_FILE") != "/runtime-secrets/runtime.env":
            results.append(
                {
                    "path": str(server_path),
                    "status": "error",
                    "error": "server compose trading-engine must define TRADING_ENV_FILE=/runtime-secrets/runtime.env",
                }
            )
        if env.get("SECRETS_DIR") != "/runtime-secrets":
            results.append(
                {
                    "path": str(server_path),
                    "status": "error",
                    "error": "server compose trading-engine must define SECRETS_DIR=/runtime-secrets",
                }
            )
        if "/home/martin/.config/trading-bot:/runtime-secrets:ro" not in volumes:
            results.append(
                {
                    "path": str(server_path),
                    "status": "error",
                    "error": "server compose trading-engine must mount /home/martin/.config/trading-bot to /runtime-secrets:ro",
                }
            )
        if "..:/app" not in volumes:
            results.append(
                {
                    "path": str(server_path),
                    "status": "error",
                    "error": "server compose trading-engine must mount repo root via ..:/app",
                }
            )
    dockerfile = REPO / "Dockerfile"
    if not dockerfile.exists():
        results.append(
            {
                "path": str(dockerfile),
                "status": "error",
                "error": "root Dockerfile is required for supported server deployment",
            }
        )
    print(json.dumps(results, indent=2, sort_keys=True))
    return 1 if any(item["status"] == "error" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
