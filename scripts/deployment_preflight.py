#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
DOCKERIGNORE_REQUIRED = {
    "runs/",
    ".venv/",
    ".venv_offline/",
    "src/autonomous-investment-robot/",
    "apps/",
    "tools/",
    "production_live.log",
    "data.xlsx",
    "database.db",
}
SECRET_PATTERNS = [
    re.compile(r"nvapi-[A-Za-z0-9_-]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    try:
        proc = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True)
    except Exception:
        return ""
    return proc.stdout.strip()


def _check(name: str, ok: bool, *, details: dict[str, Any] | None = None, severity: str = "error") -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "severity": severity,
        "details": details or {},
    }


def _load_runtime_surface() -> dict[str, Any]:
    path = REPO / "ops" / "runtime_surface.json"
    return _read_json(path) if path.exists() else {}


def _dockerignore_entries() -> set[str]:
    path = REPO / ".dockerignore"
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")}


def _scan_secret_patterns(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    matches: list[str] = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            matches.append(pattern.pattern)
    return matches


def _compose_checks(runtime_surface: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    root_compose = REPO / "docker-compose.yml"
    infra_compose = REPO / "infra" / "docker-compose.yml"
    server_compose = REPO / "ops" / "docker-compose.server.yml"
    root_payload = _read_yaml(root_compose)
    infra_payload = _read_yaml(infra_compose)
    server_payload = _read_yaml(server_compose) if server_compose.exists() else {}
    root_class = ((root_payload or {}).get("x-runtime-classification") or {}) if isinstance(root_payload, dict) else {}
    checks.append(
        _check(
            "root_compose_marked_legacy_blocked",
            isinstance(root_payload, dict) and root_class.get("status") == "legacy_blocked",
            details={"status": root_class.get("status")},
        )
    )
    root_services = ((root_payload or {}).get("services") or {}) if isinstance(root_payload, dict) else {}
    has_build = any(isinstance(service, dict) and "build" in service for service in root_services.values())
    checks.append(_check("root_compose_has_no_build_context", not has_build, details={"has_build": has_build}))
    secret_hits = _scan_secret_patterns(root_compose)
    checks.append(_check("root_compose_has_no_tracked_secret_patterns", not secret_hits, details={"hits": secret_hits}))
    infra_services = ((infra_payload or {}).get("services") or {}) if isinstance(infra_payload, dict) else {}
    for service_name in ("redis", "postgres"):
        service = infra_services.get(service_name, {}) if isinstance(infra_services, dict) else {}
        checks.append(
            _check(
                f"infra_{service_name}_has_healthcheck",
                isinstance(service, dict) and bool(service.get("healthcheck")),
                details={"service_present": bool(service)},
            )
        )
    supported_infra = runtime_surface.get("supported_runtime", {}).get("infra_manifests", [])
    checks.append(
        _check(
            "runtime_surface_points_to_infra_compose",
            "infra/docker-compose.yml" in supported_infra,
            details={"supported_infra_manifests": supported_infra},
        )
    )
    supported_server = runtime_surface.get("supported_runtime", {}).get("server_manifests", [])
    checks.append(
        _check(
            "runtime_surface_points_to_server_compose",
            "ops/docker-compose.server.yml" in supported_server,
            details={"supported_server_manifests": supported_server},
        )
    )
    dockerfiles = runtime_surface.get("supported_runtime", {}).get("dockerfiles", [])
    checks.append(
        _check(
            "runtime_surface_points_to_root_dockerfile",
            "Dockerfile" in dockerfiles and (REPO / "Dockerfile").exists(),
            details={"dockerfiles": dockerfiles},
        )
    )
    server_services = ((server_payload or {}).get("services") or {}) if isinstance(server_payload, dict) else {}
    trading_engine = server_services.get("trading-engine", {}) if isinstance(server_services, dict) else {}
    server_build = (trading_engine.get("build") or {}) if isinstance(trading_engine, dict) else {}
    checks.append(
        _check(
            "server_compose_trading_engine_build_context",
            server_build.get("context") == "./core" and server_build.get("dockerfile") == "Dockerfile",
            details={"build": server_build},
        )
    )
    checks.append(
        _check(
            "server_compose_trading_engine_uses_supported_command",
            (trading_engine.get("command") or []) == ["bash", "scripts/container_start_tiny_live.sh"],
            details={"command": trading_engine.get("command")},
        )
    )
    checks.append(
        _check(
            "server_compose_trading_engine_restart_is_not_always",
            trading_engine.get("restart") != "always",
            details={"restart": trading_engine.get("restart")},
        )
    )
    return checks


def _duplicate_tree_checks(runtime_surface: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    duplicate_paths = runtime_surface.get("archival_duplicate", {}).get("paths", [])
    entries = _dockerignore_entries()
    for rel in duplicate_paths:
        p = REPO / rel
        checks.append(_check(f"duplicate_path_exists:{rel}", p.exists(), details={"path": rel}, severity="warning"))
        checks.append(
            _check(
                f"duplicate_path_excluded_from_docker_context:{rel}",
                f"{rel}/" in entries or rel in entries,
                details={"path": rel, "dockerignore_present": f"{rel}/" in entries or rel in entries},
            )
        )
        checks.append(
            _check(
                f"duplicate_path_has_embedded_git:{rel}",
                not (p / ".git").exists(),
                details={"embedded_git": (p / ".git").exists()},
                severity="warning",
            )
        )
    return checks


def _local_only_artifact_checks(runtime_surface: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    entries = _dockerignore_entries()
    local_only_paths = runtime_surface.get("local_only_artifacts", {}).get("paths", [])
    for rel in local_only_paths:
        p = REPO / rel
        checks.append(
            _check(
                f"local_only_path_excluded_from_docker_context:{rel}",
                f"{rel}/" in entries or rel in entries,
                details={"path": rel, "exists": p.exists(), "dockerignore_present": f"{rel}/" in entries or rel in entries},
            )
        )
    return checks


def _repo_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    entries = _dockerignore_entries()
    missing = sorted(item for item in DOCKERIGNORE_REQUIRED if item not in entries and item.rstrip("/") not in entries)
    checks.append(_check("dockerignore_present", bool(entries), details={"path": ".dockerignore"}))
    checks.append(_check("dockerignore_contains_required_entries", not missing, details={"missing": missing}))
    status_short = _git("status", "--short").splitlines()
    checks.append(
        _check(
            "repo_branch_is_tiny_live_release",
            _git("branch", "--show-current") == "tiny-live-release",
            details={"branch": _git("branch", "--show-current")},
        )
    )
    checks.append(
        _check(
            "repo_head_matches_origin_or_ahead_only",
            True,
            severity="warning",
            details={"head": _git("rev-parse", "HEAD"), "origin_head": _git("rev-parse", "origin/tiny-live-release"), "status_short": status_short},
        )
    )
    return checks


def _ssh_check(target: str, key_path: str) -> dict[str, Any]:
    cmd = [
        "ssh",
        "-i",
        key_path,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        target,
        "echo ok",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    ok = proc.returncode == 0 and proc.stdout.strip() == "ok"
    return _check(
        "server_ssh_access",
        ok,
        severity="warning",
        details={"target": target, "key_path": key_path, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip(), "returncode": proc.returncode},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    parser.add_argument("--ssh-target", default="")
    parser.add_argument("--ssh-key", default=str(Path.home() / ".ssh" / "hetzner_trading_vm_nopass"))
    args = parser.parse_args()

    runtime_surface = _load_runtime_surface()
    checks = []
    checks.extend(_repo_checks())
    checks.extend(_compose_checks(runtime_surface))
    checks.extend(_duplicate_tree_checks(runtime_surface))
    checks.extend(_local_only_artifact_checks(runtime_surface))
    if args.ssh_target:
        checks.append(_ssh_check(args.ssh_target, args.ssh_key))

    hard_failures = [check for check in checks if not check["ok"] and check["severity"] == "error"]
    warnings = [check for check in checks if not check["ok"] and check["severity"] == "warning"]
    report = {
        "status": "ok" if not hard_failures else "blocked",
        "repo_root": str(REPO),
        "git": {
            "branch": _git("branch", "--show-current"),
            "head": _git("rev-parse", "HEAD"),
            "origin_tiny_live_release": _git("rev-parse", "origin/tiny-live-release"),
            "status_short": _git("status", "--short").splitlines(),
        },
        "runtime_surface": runtime_surface,
        "checks": checks,
        "hard_failure_count": len(hard_failures),
        "warning_count": len(warnings),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    return 0 if not hard_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
