from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

import pytest

from autonomous_investment_robot.main import emergency_flatten, run_with_config


REPO_ROOT = Path(__file__).resolve().parents[1]


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    for key in (
        "KRAKEN_SPOT_API_KEY",
        "KRAKEN_SPOT_API_SECRET",
        "ENABLE_LIVE_TRADING",
        "ACK_I_UNDERSTAND_RISKS",
        "ENABLE_FULL_LIVE_STAGE",
        "TRADING_ENV_FILE",
        "SECRETS_DIR",
    ):
        env.pop(key, None)
    return env


def _run(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_live_subcommand_requires_explicit_config() -> None:
    result = _run("python3", "-m", "autonomous_investment_robot", "live", env=_base_env())

    assert result.returncode != 0
    assert "the following arguments are required: --config" in result.stderr


def test_flatten_subcommand_requires_explicit_config() -> None:
    result = _run("python3", "-m", "autonomous_investment_robot", "flatten", env=_base_env())

    assert result.returncode != 0
    assert "the following arguments are required: --config" in result.stderr


@pytest.mark.parametrize(
    ("script_name", "env_updates", "expected_error"),
    [
        (
            "run_live.sh",
            {},
            "unsupported_doctrine_target_use_kraken_spot_launch_path",
        ),
        (
            "run_live_canary.sh",
            {},
            "unsupported_doctrine_target_use_kraken_spot_launch_path",
        ),
        (
            "run_testnet.sh",
            {},
            "unsupported_doctrine_target_use_kraken_spot_launch_path",
        ),
        (
            "run_kraken_live.sh",
            {},
            "unsupported_doctrine_target_use_kraken_spot_launch_path",
        ),
        (
            "run_kraken_live_canary.sh",
            {},
            "unsupported_doctrine_target_use_kraken_spot_launch_path",
        ),
        (
            "run_kraken_live_readonly.sh",
            {},
            "unsupported_doctrine_target_use_kraken_spot_launch_path",
        ),
        (
            "run_kraken_testnet.sh",
            {},
            "unsupported_doctrine_target_use_kraken_spot_launch_path",
        ),
    ],
)
def test_order_capable_launch_scripts_require_explicit_true_unlock_env(
    script_name: str,
    env_updates: dict[str, str],
    expected_error: str,
) -> None:
    env = _base_env()
    env.update(env_updates)

    result = _run("bash", f"scripts/{script_name}", env=env)

    assert result.returncode != 0
    assert expected_error in result.stderr


@pytest.mark.parametrize(
    ("script_name", "env_updates", "expected_error"),
    [
        (
            "run_kraken_spot_tiny_live.sh",
            {
                "KRAKEN_SPOT_API_KEY": "k",
                "KRAKEN_SPOT_API_SECRET": "s",
                "ENABLE_LIVE_TRADING": "false",
                "ACK_I_UNDERSTAND_RISKS": "true",
            },
            "Env var must be set to true: ENABLE_LIVE_TRADING",
        ),
        (
            "run_kraken_spot_profit_full_throttle.sh",
            {
                "KRAKEN_SPOT_API_KEY": "k",
                "KRAKEN_SPOT_API_SECRET": "s",
                "ENABLE_LIVE_TRADING": "false",
                "ACK_I_UNDERSTAND_RISKS": "true",
            },
            "Env var must be set to true: ENABLE_LIVE_TRADING",
        ),
        (
            "run_kraken_ultra_profit_full_throttle.sh",
            {
                "KRAKEN_SPOT_API_KEY": "k",
                "KRAKEN_SPOT_API_SECRET": "s",
                "ENABLE_LIVE_TRADING": "true",
                "ACK_I_UNDERSTAND_RISKS": "true",
            },
            "Missing required env var: ENABLE_FULL_LIVE_STAGE",
        ),
    ],
)
def test_kraken_spot_launch_scripts_require_doctrine_unlocks(
    script_name: str,
    env_updates: dict[str, str],
    expected_error: str,
) -> None:
    env = _base_env()
    env.update(env_updates)

    result = _run("bash", f"scripts/{script_name}", env=env)

    assert result.returncode != 0
    assert expected_error in result.stderr


def test_direct_derivatives_config_launch_is_blocked_even_if_scripts_are_bypassed() -> None:
    result = run_with_config("config.kraken_derivatives.testnet.yaml")

    assert result["status"] == "blocked"
    assert result["reason"] == "Live trading blocked: unsupported_doctrine_target_use_kraken_spot"


def test_emergency_flatten_blocks_unsupported_derivative_config() -> None:
    result = emergency_flatten("config.kraken_derivatives.live_readonly.yaml")

    assert result["status"] == "blocked"
    assert result["reason"] == "flatten_blocked_unsupported_doctrine_target_use_kraken_spot"


def test_flatten_cli_supports_symbol_scope_and_freeze_only(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    class FakeLive:
        def preflight(self):
            return True, "ok"

        def freeze_new_openings(self, reason="freeze"):
            return True, reason

        def flatten_symbol(self, symbol, reason="flatten"):
            return True, f"{reason}:{symbol}"

    monkeypatch.setattr("autonomous_investment_robot.main.LiveKrakenSpotService", lambda settings, run_id, connector: FakeLive())
    monkeypatch.setattr("autonomous_investment_robot.main.KrakenSpotConnector", lambda settings: object())

    freeze = emergency_flatten(
        "config.kraken_spot.tiny_live.yaml",
        freeze_only=True,
        reason="operator_freeze",
    )
    flatten = emergency_flatten(
        "config.kraken_spot.tiny_live.yaml",
        symbol="BTC/USD",
        reason="operator_symbol_flatten",
    )

    assert freeze["status"] == "ok"
    assert freeze["freeze_only"] is True
    assert freeze["reason"] == "operator_freeze"
    assert flatten["status"] == "ok"
    assert flatten["scope"] == "symbol"
    assert flatten["symbol"] == "BTC/USD"
    assert flatten["reason"] == "operator_symbol_flatten:BTC/USD"


def test_emergency_flatten_protective_retry_ignores_full_stage_unlock_friction(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("ACK_I_UNDERSTAND_RISKS", raising=False)
    monkeypatch.delenv("ENABLE_FULL_LIVE_STAGE", raising=False)
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    class FakeLive:
        def preflight(self):
            return True, "ok"

        def freeze_new_openings(self, reason="freeze"):
            return True, reason

    monkeypatch.setattr("autonomous_investment_robot.main.LiveKrakenSpotService", lambda settings, run_id, connector: FakeLive())
    monkeypatch.setattr("autonomous_investment_robot.main.KrakenSpotConnector", lambda settings: object())

    result = emergency_flatten(
        "config.kraken_spot.live_profit.yaml",
        freeze_only=True,
        reason="operator_protective_freeze",
    )

    assert result["status"] == "ok"
    assert result["freeze_only"] is True
    assert result["reason"] == "operator_protective_freeze"
    assert os.getenv("ENABLE_LIVE_TRADING") is None
    assert os.getenv("ACK_I_UNDERSTAND_RISKS") is None
    assert os.getenv("ENABLE_FULL_LIVE_STAGE") is None


def test_emergency_flatten_fail_closed_on_preflight_exception(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    class FakeLive:
        def preflight(self):
            raise RuntimeError("preflight_transport_error")

    monkeypatch.setattr("autonomous_investment_robot.main.LiveKrakenSpotService", lambda settings, run_id, connector: FakeLive())
    monkeypatch.setattr("autonomous_investment_robot.main.KrakenSpotConnector", lambda settings: object())

    result = emergency_flatten("config.kraken_spot.tiny_live.yaml")

    assert result["status"] == "blocked"
    assert result["reason"] == "preflight_transport_error"


def test_emergency_flatten_fail_closed_when_connector_init_fails(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    def _boom(_settings):
        raise RuntimeError("ccxt_unavailable")

    monkeypatch.setattr("autonomous_investment_robot.main.KrakenSpotConnector", _boom)

    result = emergency_flatten("config.kraken_spot.tiny_live.yaml")

    assert result["status"] == "blocked"
    assert result["reason"] == "ccxt_unavailable"


def test_script_helper_honors_python_bin_override() -> None:
    env = _base_env()
    result = _run(
        "bash",
        "-lc",
        ". scripts/_common_env.sh && PYTHON_BIN=/bin/echo run_robot live-readonly --config config.kraken_spot.readonly_analysis.yaml",
        env=env,
    )

    assert result.returncode == 0
    assert "-m autonomous_investment_robot live-readonly --config config.kraken_spot.readonly_analysis.yaml" in result.stdout


def test_script_helper_prefers_repo_venv_dir_over_system_python(tmp_path: Path) -> None:
    fake_venv = tmp_path / "repo-venv" / "bin"
    fake_venv.mkdir(parents=True)
    fake_python = fake_venv / "python"
    fake_python.write_text("#!/usr/bin/env bash\necho fake-repo-venv-python\n", encoding="utf-8")
    fake_python.chmod(0o755)

    fake_path = tmp_path / "fake-path"
    fake_path.mkdir()
    fake_python311 = fake_path / "python3.11"
    fake_python311.write_text("#!/usr/bin/env bash\necho fake-system-python311\n", encoding="utf-8")
    fake_python311.chmod(0o755)

    env = _base_env()
    env["REPO_VENV_DIR"] = str(fake_venv.parent)
    env["PATH"] = f"{fake_path}:{env['PATH']}"

    result = _run(
        "bash",
        "-lc",
        ". scripts/_common_env.sh && resolve_python_bin",
        env=env,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == str(fake_python)


def test_script_helper_loads_runtime_env_from_secret_files(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "KRAKEN_SPOT_API_KEY").write_text("key-from-file\n", encoding="utf-8")
    (secrets_dir / "KRAKEN_SPOT_API_SECRET").write_text("secret-from-file\n", encoding="utf-8")
    (secrets_dir / "ENABLE_LIVE_TRADING").write_text("true\n", encoding="utf-8")
    (secrets_dir / "ACK_I_UNDERSTAND_RISKS").write_text("true\n", encoding="utf-8")

    env = _base_env()
    env["SECRETS_DIR"] = str(secrets_dir)

    result = _run(
        "bash",
        "-lc",
        "unset KRAKEN_SPOT_API_KEY KRAKEN_SPOT_API_SECRET ENABLE_LIVE_TRADING ACK_I_UNDERSTAND_RISKS; "
        "PYTHON_BIN=/bin/echo bash scripts/run_kraken_spot_tiny_live.sh",
        env=env,
    )

    assert result.returncode == 0
    assert "-m autonomous_investment_robot live --config config.kraken_spot.tiny_live.yaml" in result.stdout


def test_script_helper_loads_runtime_env_from_home_config(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    config_dir = fake_home / ".config" / "trading-bot"
    config_dir.mkdir(parents=True)
    (config_dir / "runtime.env").write_text(
        "\n".join(
            [
                "KRAKEN_SPOT_API_KEY=home-key",
                "KRAKEN_SPOT_API_SECRET=home-secret",
                "ENABLE_LIVE_TRADING=true",
                "ACK_I_UNDERSTAND_RISKS=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    env = _base_env()
    env["HOME"] = str(fake_home)

    result = _run(
        "bash",
        "-lc",
        "unset KRAKEN_SPOT_API_KEY KRAKEN_SPOT_API_SECRET ENABLE_LIVE_TRADING ACK_I_UNDERSTAND_RISKS; "
        "PYTHON_BIN=/bin/echo bash scripts/run_kraken_spot_tiny_live.sh",
        env=env,
    )

    assert result.returncode == 0
    assert "-m autonomous_investment_robot live --config config.kraken_spot.tiny_live.yaml" in result.stdout


def test_script_helper_loads_export_prefixed_runtime_env_from_home_config(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    config_dir = fake_home / ".config" / "trading-bot"
    config_dir.mkdir(parents=True)
    (config_dir / "runtime.env").write_text(
        "\n".join(
            [
                "export KRAKEN_SPOT_API_KEY=home-key",
                "export KRAKEN_SPOT_API_SECRET=home-secret",
                "export ENABLE_LIVE_TRADING=true",
                "export ACK_I_UNDERSTAND_RISKS=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    env = _base_env()
    env["HOME"] = str(fake_home)

    result = _run(
        "bash",
        "-lc",
        "unset KRAKEN_SPOT_API_KEY KRAKEN_SPOT_API_SECRET ENABLE_LIVE_TRADING ACK_I_UNDERSTAND_RISKS; "
        "PYTHON_BIN=/bin/echo bash scripts/run_kraken_spot_tiny_live.sh",
        env=env,
    )

    assert result.returncode == 0
    assert "-m autonomous_investment_robot live --config config.kraken_spot.tiny_live.yaml" in result.stdout


def test_script_helper_strips_shell_quotes_from_export_prefixed_runtime_env(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    config_dir = fake_home / ".config" / "trading-bot"
    config_dir.mkdir(parents=True)
    (config_dir / "runtime.env").write_text(
        "\n".join(
            [
                'export KRAKEN_SPOT_API_KEY="home-key"',
                "export KRAKEN_SPOT_API_SECRET='home-secret'",
                'export ENABLE_LIVE_TRADING="true"',
                "export ACK_I_UNDERSTAND_RISKS='true'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    env = _base_env()
    env["HOME"] = str(fake_home)

    result = _run(
        "bash",
        "-lc",
        "unset KRAKEN_SPOT_API_KEY KRAKEN_SPOT_API_SECRET ENABLE_LIVE_TRADING ACK_I_UNDERSTAND_RISKS; "
        "PYTHON_BIN=/bin/echo bash scripts/run_kraken_spot_tiny_live.sh",
        env=env,
    )

    assert result.returncode == 0
    assert "-m autonomous_investment_robot live --config config.kraken_spot.tiny_live.yaml" in result.stdout


def test_container_start_tiny_live_uses_supported_secret_loading(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    env_file = secrets_dir / "trading-engine.env"
    env_file.write_text(
        "\n".join(
            [
                "KRAKEN_SPOT_API_KEY=key-from-env-file",
                "KRAKEN_SPOT_API_SECRET=secret-from-env-file",
                "ENABLE_LIVE_TRADING=true",
                "ACK_I_UNDERSTAND_RISKS=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    env = _base_env()
    env["SECRETS_DIR"] = str(secrets_dir)

    result = _run(
        "bash",
        "-lc",
        "unset KRAKEN_SPOT_API_KEY KRAKEN_SPOT_API_SECRET ENABLE_LIVE_TRADING ACK_I_UNDERSTAND_RISKS; "
        "CONTAINER_BOOT_READONLY_ONCE=true PYTHON_BIN=/bin/echo bash scripts/container_start_tiny_live.sh",
        env=env,
    )

    assert result.returncode == 0
    assert "-m autonomous_investment_robot live --config config.kraken_spot.tiny_live.yaml" in result.stdout


def test_container_start_tiny_live_prefers_explicit_secrets_dir_over_home_runtime_env(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    config_dir = fake_home / ".config" / "trading-bot"
    config_dir.mkdir(parents=True)
    (config_dir / "runtime.env").write_text(
        "\n".join(
            [
                "KRAKEN_SPOT_API_KEY=home-key",
                "KRAKEN_SPOT_API_SECRET=home-secret",
                "ENABLE_LIVE_TRADING=true",
                "ACK_I_UNDERSTAND_RISKS=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    env = _base_env()
    env["HOME"] = str(fake_home)
    env["SECRETS_DIR"] = str(secrets_dir)

    result = _run(
        "bash",
        "-lc",
        "unset KRAKEN_SPOT_API_KEY KRAKEN_SPOT_API_SECRET ENABLE_LIVE_TRADING ACK_I_UNDERSTAND_RISKS; "
        "CONTAINER_BOOT_READONLY_ONCE=true PYTHON_BIN=/bin/echo bash scripts/container_start_tiny_live.sh",
        env=env,
    )

    assert result.returncode == 0
    assert "-m autonomous_investment_robot live-readonly --config config.kraken_spot.readonly_analysis.yaml" in result.stdout
    assert '"missing_tiny_live_prerequisites"' in result.stderr


def test_container_start_tiny_live_downgrades_to_readonly_without_live_prereqs(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    env = _base_env()
    env["HOME"] = str(fake_home)
    env["SECRETS_DIR"] = str(secrets_dir)

    result = _run(
        "bash",
        "-lc",
        "unset KRAKEN_SPOT_API_KEY KRAKEN_SPOT_API_SECRET ENABLE_LIVE_TRADING ACK_I_UNDERSTAND_RISKS; "
        "CONTAINER_BOOT_READONLY_ONCE=true PYTHON_BIN=/bin/echo bash scripts/container_start_tiny_live.sh",
        env=env,
    )

    assert result.returncode == 0
    assert "-m autonomous_investment_robot live-readonly --config config.kraken_spot.readonly_analysis.yaml" in result.stdout
    assert '"mode":"readonly_fallback"' in result.stderr
    assert '"missing_tiny_live_prerequisites"' in result.stderr


def test_container_start_tiny_live_enforces_minimum_readonly_loop_interval(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    env = _base_env()
    env["HOME"] = str(fake_home)
    env["SECRETS_DIR"] = str(secrets_dir)
    proc = subprocess.Popen(
        (
            "bash",
            "-lc",
            "unset KRAKEN_SPOT_API_KEY KRAKEN_SPOT_API_SECRET ENABLE_LIVE_TRADING ACK_I_UNDERSTAND_RISKS; "
            "PYTHON_BIN=/bin/echo READONLY_FALLBACK_INTERVAL_SECONDS=5 bash scripts/container_start_tiny_live.sh",
        ),
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    try:
        proc.communicate(timeout=1)
        pytest.fail("container_start_tiny_live.sh unexpectedly exited without looping")
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        _, stderr = proc.communicate()

    assert '"mode":"readonly_fallback"' in stderr
