from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from autonomous_investment_robot.main import emergency_flatten, run_with_config


REPO_ROOT = Path(__file__).resolve().parents[1]


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
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
