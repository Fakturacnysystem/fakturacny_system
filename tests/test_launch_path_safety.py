from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


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
            {
                "EXCHANGE_API_KEY": "k",
                "EXCHANGE_API_SECRET": "s",
                "TESTNET_VALIDATED": "true",
                "ENABLE_LIVE_TRADING": "false",
                "ACK_I_UNDERSTAND_RISKS": "true",
            },
            "Env var must be set to true: ENABLE_LIVE_TRADING",
        ),
        (
            "run_live_canary.sh",
            {
                "EXCHANGE_API_KEY": "k",
                "EXCHANGE_API_SECRET": "s",
                "TESTNET_VALIDATED": "true",
                "ENABLE_LIVE_TRADING": "true",
                "ACK_I_UNDERSTAND_RISKS": "false",
            },
            "Env var must be set to true: ACK_I_UNDERSTAND_RISKS",
        ),
        (
            "run_testnet.sh",
            {
                "EXCHANGE_API_KEY": "k",
                "EXCHANGE_API_SECRET": "s",
                "ENABLE_LIVE_TRADING": "false",
                "ACK_I_UNDERSTAND_RISKS": "true",
            },
            "Env var must be set to true: ENABLE_LIVE_TRADING",
        ),
        (
            "run_kraken_live.sh",
            {
                "KRAKEN_API_KEY": "k",
                "KRAKEN_API_SECRET": "s",
                "TESTNET_VALIDATED": "true",
                "ENABLE_LIVE_TRADING": "true",
                "ACK_I_UNDERSTAND_RISKS": "false",
            },
            "Env var must be set to true: ACK_I_UNDERSTAND_RISKS",
        ),
        (
            "run_kraken_live_canary.sh",
            {
                "KRAKEN_API_KEY": "k",
                "KRAKEN_API_SECRET": "s",
                "TESTNET_VALIDATED": "true",
                "ENABLE_LIVE_TRADING": "false",
                "ACK_I_UNDERSTAND_RISKS": "true",
            },
            "Env var must be set to true: ENABLE_LIVE_TRADING",
        ),
        (
            "run_kraken_testnet.sh",
            {
                "KRAKEN_API_KEY": "k",
                "KRAKEN_API_SECRET": "s",
                "ENABLE_LIVE_TRADING": "true",
                "ACK_I_UNDERSTAND_RISKS": "false",
            },
            "Env var must be set to true: ACK_I_UNDERSTAND_RISKS",
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
