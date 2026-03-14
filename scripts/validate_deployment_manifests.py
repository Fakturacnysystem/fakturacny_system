#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml  # type: ignore

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must parse to a YAML mapping")
    return raw


def _status_row(
    *,
    check_id: str,
    status: str,
    required: bool,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": str(check_id),
        "status": str(status),
        "required": bool(required),
        **dict(details or {}),
    }


def _all_pass(rows: Iterable[Mapping[str, Any]]) -> bool:
    return all(str(row.get("status", "")) == "pass" for row in rows)


def _validate_compose(path: Path, *, required_services: set[str]) -> dict[str, Any]:
    data = _load_yaml(path)
    services = data.get("services", {})
    if not isinstance(services, dict):
        raise ValueError(f"{path}: services must be a mapping")
    service_names = set(str(x) for x in services.keys())
    missing = sorted(required_services.difference(service_names))
    ok = not missing
    return {
        "file": str(path.relative_to(ROOT)),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "services": sorted(service_names),
        "missing_required": missing,
    }


def _validate_env_example(path: Path, *, required_keys: set[str]) -> dict[str, Any]:
    found: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            found.add(key)
    missing = sorted(required_keys.difference(found))
    ok = not missing
    return {
        "file": str(path.relative_to(ROOT)),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "keys_count": len(found),
        "missing_required": missing,
    }


def _runtime_evidence_checks(run_dir: Path | None) -> list[dict[str, Any]]:
    if run_dir is None:
        return [
            _status_row(
                check_id="runtime_evidence_bundle",
                status="blocked",
                required=True,
                details={
                    "reason": "runtime_evidence_run_dir_missing",
                    "expected_files": [
                        "distributed_runtime_diagnostics.json",
                        "audit.log",
                        "event_bus.jsonl",
                    ],
                },
            )
        ]
    if not run_dir.exists() or not run_dir.is_dir():
        return [
            _status_row(
                check_id="runtime_evidence_bundle",
                status="blocked",
                required=True,
                details={
                    "reason": "runtime_evidence_run_dir_not_found",
                    "run_dir": str(run_dir),
                },
            )
        ]

    checks: list[dict[str, Any]] = []
    diag_path = run_dir / "distributed_runtime_diagnostics.json"
    audit_path = run_dir / "audit.log"
    event_bus_path = run_dir / "event_bus.jsonl"

    if not diag_path.exists():
        checks.append(
            _status_row(
                check_id="runtime_diag_json",
                status="fail",
                required=True,
                details={"file": str(diag_path), "reason": "missing"},
            )
        )
    else:
        try:
            diag = json.loads(diag_path.read_text(encoding="utf-8"))
            if not isinstance(diag, dict):
                raise ValueError("diagnostics_not_mapping")
            backend = str(dict(diag.get("compute_bridge", {})).get("backend", "")).strip()
            mirror_enabled = bool(dict(diag.get("postgres_mirror", {})).get("enabled", False))
            checks.append(
                _status_row(
                    check_id="runtime_diag_json",
                    status="pass" if backend == "redis_streams" and mirror_enabled else "fail",
                    required=True,
                    details={
                        "file": str(diag_path),
                        "compute_bridge_backend": backend,
                        "postgres_mirror_enabled": mirror_enabled,
                    },
                )
            )
        except Exception as exc:
            checks.append(
                _status_row(
                    check_id="runtime_diag_json",
                    status="fail",
                    required=True,
                    details={"file": str(diag_path), "reason": f"parse_failed:{exc}"},
                )
            )

    if not audit_path.exists():
        checks.append(
            _status_row(
                check_id="audit_log_distributed_rankings",
                status="fail",
                required=True,
                details={"file": str(audit_path), "reason": "missing"},
            )
        )
    else:
        content = audit_path.read_text(encoding="utf-8", errors="ignore")
        checks.append(
            _status_row(
                check_id="audit_log_distributed_rankings",
                status="pass" if "distributed_compute_rankings" in content else "fail",
                required=True,
                details={"file": str(audit_path)},
            )
        )

    if not event_bus_path.exists():
        checks.append(
            _status_row(
                check_id="event_bus_execution_decision_topics",
                status="fail",
                required=True,
                details={"file": str(event_bus_path), "reason": "missing"},
            )
        )
    else:
        content = event_bus_path.read_text(encoding="utf-8", errors="ignore")
        has_execution = "execution" in content
        has_decision = "decision" in content
        checks.append(
            _status_row(
                check_id="event_bus_execution_decision_topics",
                status="pass" if has_execution and has_decision else "fail",
                required=True,
                details={
                    "file": str(event_bus_path),
                    "has_execution": has_execution,
                    "has_decision": has_decision,
                },
            )
        )
    return checks


def _docker_runtime_check(*, skip: bool) -> dict[str, Any]:
    if skip:
        return _status_row(
            check_id="docker_host_runtime",
            status="skipped",
            required=False,
            details={"reason": "explicit_skip"},
        )
    docker_path = shutil.which("docker")
    if docker_path:
        return _status_row(
            check_id="docker_host_runtime",
            status="pass",
            required=False,
            details={"docker_path": docker_path},
        )
    return _status_row(
        check_id="docker_host_runtime",
        status="blocked",
        required=False,
        details={"reason": "docker_not_available_on_host"},
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate deployment manifests and distributed readiness evidence.")
    parser.add_argument(
        "--runtime-evidence-run-dir",
        default="",
        help="Run directory path for distributed runtime evidence validation.",
    )
    parser.add_argument(
        "--require-runtime-evidence",
        action="store_true",
        help="Return non-zero when rollout claim is not runtime-evidence ready.",
    )
    parser.add_argument(
        "--skip-docker-check",
        action="store_true",
        help="Skip host docker availability classification for constrained environments.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    compose_checks = [
        _validate_compose(ROOT / "docker-compose.live.yml", required_services={"live-node", "redis", "postgres"}),
        _validate_compose(ROOT / "docker-compose.compute.yml", required_services={"compute-node", "redis", "postgres"}),
        _validate_compose(
            ROOT / "docker-compose.full.yml",
            required_services={"live-node", "compute-node", "redis", "postgres"},
        ),
    ]
    env_checks = [
        _validate_env_example(
            ROOT / "deploy" / "live-node.env.example",
            required_keys={
                "AUTONOMOUS_NODE_ROLE",
                "AUTONOMOUS_DISTRIBUTED_ENABLED",
                "AUTONOMOUS_COMPUTE_BRIDGE",
                "AUTONOMOUS_REDIS_URL",
                "AUTONOMOUS_POSTGRES_MIRROR_ENABLED",
                "AUTONOMOUS_POSTGRES_DSN",
            },
        ),
        _validate_env_example(
            ROOT / "deploy" / "compute-node.env.example",
            required_keys={
                "AUTONOMOUS_NODE_ROLE",
                "AUTONOMOUS_DISTRIBUTED_ENABLED",
                "AUTONOMOUS_COMPUTE_BRIDGE",
                "AUTONOMOUS_REDIS_URL",
            },
        ),
    ]
    static_checks = compose_checks + env_checks
    static_ok = all(bool(item.get("ok")) for item in static_checks)

    runtime_dir = Path(args.runtime_evidence_run_dir).expanduser() if str(args.runtime_evidence_run_dir).strip() else None
    runtime_checks = _runtime_evidence_checks(runtime_dir)
    runtime_checks.append(_docker_runtime_check(skip=bool(args.skip_docker_check)))

    required_runtime = [row for row in runtime_checks if bool(row.get("required", False))]
    runtime_ready = _all_pass(required_runtime)
    rollout_claim_ready = bool(static_ok and runtime_ready)
    ok = bool(static_ok and (rollout_claim_ready if args.require_runtime_evidence else True))

    payload = {
        "ok": ok,
        "rollout_claim_ready": rollout_claim_ready,
        "require_runtime_evidence": bool(args.require_runtime_evidence),
        "checks": static_checks,
        "runtime_checks": runtime_checks,
    }
    print(json.dumps(payload, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
