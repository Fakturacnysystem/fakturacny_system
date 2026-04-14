from __future__ import annotations

import json
import subprocess
import tarfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_deployment_preflight_reports_repo_truth_without_hard_failures() -> None:
    result = _run("python3", "scripts/deployment_preflight.py")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    check_names = {item["name"] for item in payload["checks"]}
    assert "root_compose_marked_legacy_blocked" in check_names
    assert "duplicate_path_excluded_from_docker_context:src/autonomous-investment-robot" in check_names
    assert "local_only_path_excluded_from_docker_context:apps" in check_names
    assert "local_only_path_excluded_from_docker_context:tools" in check_names
    assert "runtime_surface_points_to_server_compose" in check_names
    assert "runtime_surface_points_to_root_dockerfile" in check_names
    assert "server_compose_trading_engine_uses_supported_command" in check_names
    assert "server_compose_trading_engine_uses_runtime_env_file" in check_names
    assert "server_compose_trading_engine_uses_runtime_secrets_dir" in check_names
    assert "server_compose_trading_engine_mounts_runtime_secrets" in check_names
    assert "server_compose_trading_engine_mounts_repo_root" in check_names


def test_validate_deployment_syntax_accepts_server_manifest() -> None:
    result = _run("python3", "scripts/validate_deployment_syntax.py")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    paths = {item["path"] for item in payload}
    assert str(REPO_ROOT / "ops" / "docker-compose.server.yml") in paths
    assert str(REPO_ROOT / "docker-compose.yml") in paths


def test_verify_server_parity_accepts_matching_local_runtime_path() -> None:
    result = _run("python3", "scripts/verify_server_parity.py", "--runtime-path", str(REPO_ROOT))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["mismatches"] == []
    assert payload["required_local_files_present"] is True
    assert "ops/docker-compose.server.yml" in payload["files"]
    assert "scripts/verify_server_parity.py" in payload["files"]
    assert "scripts/container_start_tiny_live.sh" in payload["files"]


def test_runtime_status_and_healthcheck_scripts_read_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "kraken_spot_operator_summary.json").write_text(
        json.dumps(
            {
                "provider_id": "kraken_spot",
                "mode": "live",
                "rollout_stage": "tiny_live",
                "ordering_allowed": True,
                "preflight": {"ok": True, "reason": "ok"},
                "harmony": {"config_hash": "abc"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "readiness_summary.json").write_text(json.dumps({"readiness_ready": True}), encoding="utf-8")
    (run_dir / "live_safety_summary.json").write_text(json.dumps({"safety_ready": True}), encoding="utf-8")
    (run_dir / "health_summary.json").write_text(json.dumps({"preflight_ok": True}), encoding="utf-8")
    (run_dir / "config_truth_report.json").write_text(json.dumps({"config_hash": "abc"}), encoding="utf-8")
    (run_dir / "release_manifest.json").write_text(json.dumps({"release_fingerprint": "fp"}), encoding="utf-8")

    status = _run("python3", "scripts/runtime_status.py", "--run-dir", str(run_dir))
    health = _run("python3", "scripts/runtime_healthcheck.py", "--run-dir", str(run_dir))

    assert status.returncode == 0
    assert json.loads(status.stdout)["readiness_ready"] is True
    assert health.returncode == 0
    assert json.loads(health.stdout)["status"] == "ok"


def test_runtime_status_falls_back_to_health_and_live_safety_when_runtime_summary_omits_top_level_gate_fields(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "kraken_spot_operator_summary.json").write_text(
        json.dumps(
            {
                "provider_id": "kraken_spot",
                "mode": "live",
                "rollout_stage": "tiny_live",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "readiness_summary.json").write_text(json.dumps({"readiness_ready": True}), encoding="utf-8")
    (run_dir / "live_safety_summary.json").write_text(
        json.dumps({"ordering_allowed": True, "preflight_reason": "ok"}),
        encoding="utf-8",
    )
    (run_dir / "health_summary.json").write_text(
        json.dumps({"preflight_ok": True, "ordering_allowed": True}),
        encoding="utf-8",
    )

    status = _run("python3", "scripts/runtime_status.py", "--run-dir", str(run_dir))

    assert status.returncode == 0
    payload = json.loads(status.stdout)
    assert payload["preflight_ok"] is True
    assert payload["ordering_allowed"] is True
    assert payload["preflight_reason"] == "ok"


def test_runtime_healthcheck_allows_readonly_using_health_summary_fallback(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "kraken_spot_operator_summary.json").write_text(
        json.dumps(
            {
                "provider_id": "kraken_spot",
                "mode": "live_readonly",
                "rollout_stage": "shadow",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "readiness_summary.json").write_text(json.dumps({"readiness_ready": False}), encoding="utf-8")
    (run_dir / "live_safety_summary.json").write_text(json.dumps({"safety_ready": False}), encoding="utf-8")
    (run_dir / "health_summary.json").write_text(
        json.dumps({"preflight_ok": True, "ordering_allowed": False}),
        encoding="utf-8",
    )

    health = _run("python3", "scripts/runtime_healthcheck.py", "--run-dir", str(run_dir), "--allow-readonly")

    assert health.returncode == 0
    payload = json.loads(health.stdout)
    assert payload["status"] == "ok"
    assert payload["preflight_ok"] is True
    assert payload["ordering_allowed"] is False


def test_runtime_status_reads_current_run_boot_progress_summary_truth(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "kraken_spot_operator_summary.json").write_text(
        json.dumps(
            {
                "provider_id": "kraken_spot",
                "mode": "live",
                "rollout_stage": "tiny_live",
                "boot_phase": "preflight_pending",
                "status": "booting",
                "ordering_allowed": False,
                "preflight": {"ok": None, "reason": "boot_pending", "phase": "preflight_pending"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "readiness_summary.json").write_text(
        json.dumps({"readiness_ready": False, "boot_phase": "preflight_pending"}),
        encoding="utf-8",
    )
    (run_dir / "live_safety_summary.json").write_text(
        json.dumps({"safety_ready": False, "boot_phase": "preflight_pending"}),
        encoding="utf-8",
    )
    (run_dir / "health_summary.json").write_text(
        json.dumps({"preflight_ok": False, "ordering_allowed": False, "boot_phase": "preflight_pending"}),
        encoding="utf-8",
    )

    status = _run("python3", "scripts/runtime_status.py", "--run-dir", str(run_dir))
    health = _run("python3", "scripts/runtime_healthcheck.py", "--run-dir", str(run_dir))

    assert status.returncode == 0
    status_payload = json.loads(status.stdout)
    assert status_payload["mode"] == "live"
    assert status_payload["rollout_stage"] == "tiny_live"
    assert status_payload["ordering_allowed"] is False
    assert status_payload["preflight_ok"] is False
    assert status_payload["preflight_reason"] == "boot_pending"
    assert health.returncode == 1
    assert json.loads(health.stdout)["status"] == "blocked"


def test_collect_diagnostics_bundle_creates_manifest_and_tarball(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "kraken_spot_operator_summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    output_dir = tmp_path / "bundle"

    result = _run("python3", "scripts/collect_diagnostics_bundle.py", "--run-dir", str(run_dir), "--output", str(output_dir))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    bundle = Path(payload["bundle"])
    manifest = output_dir / f"{run_dir.name}_diagnostics_manifest.json"
    assert bundle.exists()
    assert manifest.exists()
    with tarfile.open(bundle, "r:gz") as tar:
        assert "kraken_spot_operator_summary.json" in tar.getnames()


def test_tiny_live_promotion_readiness_blocks_without_live_prereqs(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "kraken_spot_operator_summary.json").write_text(
        json.dumps(
            {
                "mode": "live_readonly",
                "rollout_stage": "shadow",
                "ordering_allowed": False,
                "preflight": {"ok": True, "reason": "ok"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "readiness_summary.json").write_text(
        json.dumps({"readiness_ready": False, "rollout_stage": "shadow"}),
        encoding="utf-8",
    )
    (run_dir / "live_safety_summary.json").write_text(
        json.dumps({"safety_ready": False, "ordering_allowed": False}),
        encoding="utf-8",
    )
    (run_dir / "rollback_preflight_liveprofit_paper.json").write_text(
        json.dumps({"rollback_ready": True}),
        encoding="utf-8",
    )
    (run_dir / "config_truth_report.json").write_text(
        json.dumps({"config_hash": "abc"}),
        encoding="utf-8",
    )

    result = _run(
        "python3",
        "scripts/tiny_live_promotion_readiness.py",
        "--run-dir",
        str(run_dir),
        "--secrets-dir",
        str(tmp_path / "secrets"),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["current_mode"] == "live_readonly"
    assert payload["current_rollout_stage"] == "shadow"
    assert payload["tiny_live_envelope"]["resolved_stage"] == "tiny_live"
    assert payload["tiny_live_envelope"]["runtime_mode"] == "live"
    assert payload["missing_live_prerequisites"] == [
        "kraken_spot_api_key_present",
        "kraken_spot_api_secret_present",
        "enable_live_trading_true",
        "ack_i_understand_risks_true",
    ]


def test_tiny_live_promotion_readiness_accepts_supported_trading_engine_env_file(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "kraken_spot_operator_summary.json").write_text(
        json.dumps(
            {
                "mode": "live",
                "rollout_stage": "tiny_live",
                "ordering_allowed": False,
                "preflight": {"ok": True, "reason": "ok"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "readiness_summary.json").write_text(
        json.dumps({"readiness_ready": False, "rollout_stage": "tiny_live", "preflight_ok": True}),
        encoding="utf-8",
    )
    (run_dir / "live_safety_summary.json").write_text(
        json.dumps({"safety_ready": False, "ordering_allowed": False}),
        encoding="utf-8",
    )
    (run_dir / "rollback_preflight_liveprofit_paper.json").write_text(
        json.dumps({"rollback_ready": True}),
        encoding="utf-8",
    )
    (run_dir / "config_truth_report.json").write_text(
        json.dumps({"config_hash": "abc"}),
        encoding="utf-8",
    )
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "KRAKEN_SPOT_API_KEY").write_text("k\n", encoding="utf-8")
    (secrets_dir / "KRAKEN_SPOT_API_SECRET").write_text("s\n", encoding="utf-8")
    (secrets_dir / "trading-engine.env").write_text(
        "ENABLE_LIVE_TRADING=true\nACK_I_UNDERSTAND_RISKS=true\n",
        encoding="utf-8",
    )

    result = _run(
        "python3",
        "scripts/tiny_live_promotion_readiness.py",
        "--run-dir",
        str(run_dir),
        "--secrets-dir",
        str(secrets_dir),
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["missing_live_prerequisites"] == []
