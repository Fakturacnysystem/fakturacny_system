from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.core.contracts import RecoveryDecision
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator
from autonomous_investment_robot.main import run_with_config


def test_kraken_spot_live_config_accepts_env_unlocks(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    settings = RobotSettings.from_file("config.kraken_spot.live.yaml")

    gate = settings.live_gate_status()
    assert gate["double_unlock_enabled"] is True
    assert gate["unlock_live_requested"] is True
    assert gate["unlock_acknowledged"] is True
    assert gate["unlock_sources"]["env_enable_live_trading"] is True
    assert gate["unlock_sources"]["env_ack_i_understand_risks"] is True


def test_kraken_spot_live_profit_config_requires_full_stage_unlock(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    result = run_with_config("config.kraken_spot.live_profit.yaml")

    assert result["status"] == "blocked"
    assert "ENABLE_FULL_LIVE_STAGE" in result["reason"]


def test_kraken_spot_live_profit_config_accepts_full_stage_unlock(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("ENABLE_FULL_LIVE_STAGE", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    settings = RobotSettings.from_file("config.kraken_spot.live_profit.yaml")

    gate = settings.live_gate_status()
    assert gate["full_live_stage_enabled"] is True
    assert gate["full_live_stage_required"] is True
    assert gate["full_live_stage_sources"]["env_allow_full_live_stage"] is True


def test_kraken_spot_tiny_live_config_is_real_money_without_full_stage_unlock(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    settings = RobotSettings.from_file("config.kraken_spot.tiny_live.yaml")

    gate = settings.live_gate_status()
    assert settings.rollout_stage().value == "tiny_live"
    assert gate["full_live_stage_required"] is False
    assert gate["rollout_profile"]["aggression_envelope"] == "tiny_size_probe_only"


def test_orchestrator_live_boot_reaches_live_loop_when_safe(monkeypatch, tmp_path: Path) -> None:
    from autonomous_investment_robot.core import orchestrator as orchestrator_module
    from autonomous_investment_robot.services.live_runtime.coordination import LiveBootState

    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    class FakeLiveKrakenSpot:
        def __init__(self, settings, run_id, connector):  # noqa: ARG002
            self.connector = SimpleNamespace(provider_id="kraken_spot", has_credentials=True)
            self.safe_mode = False
            self.flatten_only = False
            self.killed = False
            self.kill_reason = ""

        def preflight(self):
            return True, "ok"

    monkeypatch.setattr(orchestrator_module, "LiveKrakenSpotService", FakeLiveKrakenSpot)
    monkeypatch.setattr(orchestrator_module, "KrakenSpotConnector", lambda settings: object())
    monkeypatch.setattr(
        orchestrator_module.LiveRecoveryCoordinator,
        "boot_state",
        lambda self, live, symbol: LiveBootState(
            confidence="strong",
            details={"truth_confidence": {"level": "high", "reason": "boot_ok"}},
            recovery_decision=RecoveryDecision(
                symbol=symbol,
                ts=datetime.now(timezone.utc),
                outcome="clean_boot",
                action="continue",
                confidence="strong",
            ),
        ),
    )
    monkeypatch.setattr(
        orchestrator_module.LiveStateCoordinator,
        "exchange_state",
        lambda self, live, symbol: SimpleNamespace(balance_total=100.0),
    )
    monkeypatch.setattr(
        orchestrator_module.RobotOrchestrator,
        "_live_loop",
        lambda self, live, symbol, mode: {"status": "ok", "mode": mode.value, "reason": "loop_entered"},
    )

    config = json.loads(Path("config.kraken_spot.live.yaml").read_text(encoding="utf-8"))
    config["storage"]["run_dir"] = str(tmp_path / "kraken_spot_live")
    config_path = tmp_path / "config.live.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_with_config(str(config_path))

    assert result["status"] == "ok"
    assert result["reason"] == "loop_entered"
    summary_path = Path(result["operator_summary_path"])
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["preflight"]["ok"] is True
    assert summary["ordering_allowed"] is True
    assert summary["capital_protection"]["cost_basis_sell_block"] is True


def test_orchestrator_live_boot_blocks_when_preflight_fails_with_operator_summary(monkeypatch, tmp_path: Path) -> None:
    from autonomous_investment_robot.core import orchestrator as orchestrator_module
    from autonomous_investment_robot.services.live_runtime.coordination import LiveBootState

    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    class FakeLiveKrakenSpot:
        def __init__(self, settings, run_id, connector):  # noqa: ARG002
            self.connector = SimpleNamespace(provider_id="kraken_spot", has_credentials=True)

        def preflight(self):
            return False, "private_api_verified_failed"

    monkeypatch.setattr(orchestrator_module, "LiveKrakenSpotService", FakeLiveKrakenSpot)
    monkeypatch.setattr(orchestrator_module, "KrakenSpotConnector", lambda settings: object())
    monkeypatch.setattr(
        orchestrator_module.LiveRecoveryCoordinator,
        "boot_state",
        lambda self, live, symbol: LiveBootState(
            confidence="strong",
            details={},
            recovery_decision=RecoveryDecision(
                symbol=symbol,
                ts=datetime.now(timezone.utc),
                outcome="clean_boot",
                action="continue",
                confidence="strong",
            ),
        ),
    )
    monkeypatch.setattr(
        orchestrator_module.LiveStateCoordinator,
        "exchange_state",
        lambda self, live, symbol: SimpleNamespace(balance_total=100.0),
    )

    config = json.loads(Path("config.kraken_spot.live.yaml").read_text(encoding="utf-8"))
    config["storage"]["run_dir"] = str(tmp_path / "kraken_spot_live_blocked")
    config_path = tmp_path / "config.live.blocked.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_with_config(str(config_path))

    assert result["status"] == "blocked"
    assert result["reason"] == "private_api_verified_failed"
    summary = json.loads(Path(result["operator_summary_path"]).read_text(encoding="utf-8"))
    assert summary["preflight"]["ok"] is False
    assert summary["preflight"]["reason"] == "private_api_verified_failed"


def test_orchestrator_live_boot_emits_readiness_artifacts_when_preflight_raises(monkeypatch, tmp_path: Path) -> None:
    from autonomous_investment_robot.core import orchestrator as orchestrator_module

    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    class FakeLiveKrakenSpot:
        def __init__(self, settings, run_id, connector):  # noqa: ARG002
            self.connector = SimpleNamespace(provider_id="kraken_spot", has_credentials=True)

        def preflight(self):
            raise RuntimeError('trade_history_fetch_failed:kraken {"error":["EAPI:Invalid key"]}')

    monkeypatch.setattr(orchestrator_module, "LiveKrakenSpotService", FakeLiveKrakenSpot)
    monkeypatch.setattr(orchestrator_module, "KrakenSpotConnector", lambda settings: object())

    config = json.loads(Path("config.kraken_spot.tiny_live.yaml").read_text(encoding="utf-8"))
    config["storage"]["run_dir"] = str(tmp_path / "kraken_spot_tiny_live_blocked")
    config_path = tmp_path / "config.tiny.live.blocked.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_with_config(str(config_path))

    assert result["status"] == "blocked"
    assert "trade_history_fetch_failed" in result["reason"]
    run_dir = Path(config["storage"]["run_dir"])
    assert Path(result["operator_summary_path"]).exists()
    assert (run_dir / "tiny_live_readiness_report.json").exists()
    assert (run_dir / "safety_preflight_live_target.json").exists()
    assert (run_dir / "rollback_preflight_liveprofit_paper.json").exists()
    assert (run_dir / "tiny_live_envelope_summary.json").exists()
    assert (run_dir / "live_operator_start_procedure.json").exists()
    assert (run_dir / "health_summary.json").exists()
    assert (run_dir / "live_artifact_index.json").exists()
    assert (run_dir / "throughput_diagnostics.json").exists()
    assert (run_dir / "failure_taxonomy.json").exists()
    assert (run_dir / "decision_explainability.json").exists()
    summary = json.loads(Path(result["operator_summary_path"]).read_text(encoding="utf-8"))
    assert summary["preflight"]["ok"] is False
    assert "trade_history_fetch_failed" in summary["preflight"]["reason"]
    rollback = json.loads((run_dir / "rollback_preflight_liveprofit_paper.json").read_text(encoding="utf-8"))
    assert rollback["flatten_command"].endswith("--config config.kraken_spot.tiny_live.yaml")
    explainability = json.loads((run_dir / "decision_explainability.json").read_text(encoding="utf-8"))
    assert explainability["action_state"] == "blocked_preflight"


def test_live_runtime_summary_emits_capability_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    settings = RobotSettings.from_file("config.kraken_spot.live.yaml")
    settings.storage.run_dir = str(tmp_path / "live_runtime_summary")
    orchestrator = RobotOrchestrator(settings)
    market = SimpleNamespace(
        market_integrity=SimpleNamespace(status="continue", action="continue"),
        provider_capability=SimpleNamespace(provider_id="kraken_spot"),
        market_watch=SimpleNamespace(action="continue"),
        event_intelligence_report=SimpleNamespace(partial=True),
        execution_quality=SimpleNamespace(expected_fill_speed_ms=5.0),
        forecast=SimpleNamespace(symbol="BTC/USD"),
        quantum_state=SimpleNamespace(interference_report=SimpleNamespace(uncertainty_penalty=0.2)),
        edge_immunity_decision=SimpleNamespace(action="trade_smaller"),
    )
    decision_ctx = SimpleNamespace(
        meta_governor_decision=SimpleNamespace(action="continue"),
        policy_decision=SimpleNamespace(symbol="BTC/USD"),
        risk_decision=SimpleNamespace(allowed=True),
        adjusted_intent=SimpleNamespace(symbol="BTC/USD"),
        execution_plan=SimpleNamespace(style="maker"),
        synthetic_affect_state=SimpleNamespace(mode="calm"),
        capital_sovereignty_decision=SimpleNamespace(size_multiplier=0.8),
        position_morph_plan=SimpleNamespace(),
        adaptive_exit_allocation=SimpleNamespace(),
        execution_simulation_report=SimpleNamespace(),
        human_escalation_decision=SimpleNamespace(action="continue"),
    )

    summary_path = orchestrator._emit_live_runtime_summary(
        symbol="BTC/USD",
        mode=settings.execution_mode_enum(),
        market=market,
        decision_ctx=decision_ctx,
        step=1,
    )

    assert Path(summary_path).exists()
    assert (Path(settings.storage.run_dir) / "live_capability_matrix.json").exists()
    assert (Path(settings.storage.run_dir) / "live_activated_capabilities.json").exists()
    assert (Path(settings.storage.run_dir) / "live_still_gated_capabilities.json").exists()
    assert (Path(settings.storage.run_dir) / "live_doctrine_blocked_capabilities.json").exists()
    assert (Path(settings.storage.run_dir) / "throughput_diagnostics.json").exists()
    assert (Path(settings.storage.run_dir) / "failure_taxonomy.json").exists()
    assert (Path(settings.storage.run_dir) / "decision_explainability.json").exists()
    assert (Path(settings.storage.run_dir) / "health_summary.json").exists()


def test_orchestrator_live_boot_emits_tiny_live_readiness_artifacts(monkeypatch, tmp_path: Path) -> None:
    from autonomous_investment_robot.core import orchestrator as orchestrator_module
    from autonomous_investment_robot.services.live_runtime.coordination import LiveBootState

    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ACK_I_UNDERSTAND_RISKS", "true")
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")

    class FakeLiveKrakenSpot:
        def __init__(self, settings, run_id, connector):  # noqa: ARG002
            self.connector = SimpleNamespace(provider_id="kraken_spot", has_credentials=True)
            self.safe_mode = False
            self.flatten_only = False
            self.killed = False
            self.kill_reason = ""

        def preflight(self):
            return True, "ok"

    monkeypatch.setattr(orchestrator_module, "LiveKrakenSpotService", FakeLiveKrakenSpot)
    monkeypatch.setattr(orchestrator_module, "KrakenSpotConnector", lambda settings: object())
    monkeypatch.setattr(
        orchestrator_module.LiveRecoveryCoordinator,
        "boot_state",
        lambda self, live, symbol: LiveBootState(
            confidence="strong",
            details={"truth_confidence": {"level": "high", "reason": "boot_ok"}},
            recovery_decision=RecoveryDecision(
                symbol=symbol,
                ts=datetime.now(timezone.utc),
                outcome="clean_boot",
                action="continue",
                confidence="strong",
            ),
        ),
    )
    monkeypatch.setattr(
        orchestrator_module.LiveStateCoordinator,
        "exchange_state",
        lambda self, live, symbol: SimpleNamespace(balance_total=100.0),
    )
    monkeypatch.setattr(
        orchestrator_module.RobotOrchestrator,
        "_live_loop",
        lambda self, live, symbol, mode: {"status": "ok", "mode": mode.value, "reason": "loop_entered"},
    )

    config = json.loads(Path("config.kraken_spot.tiny_live.yaml").read_text(encoding="utf-8"))
    config["storage"]["run_dir"] = str(tmp_path / "kraken_spot_tiny_live")
    config_path = tmp_path / "config.tiny.live.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_with_config(str(config_path))

    assert result["status"] == "ok"
    run_dir = Path(config["storage"]["run_dir"])
    assert (run_dir / "tiny_live_readiness_report.json").exists()
    assert (run_dir / "tiny_live_envelope_summary.json").exists()
    assert (run_dir / "safety_preflight_live_target.json").exists()
    assert (run_dir / "rollback_preflight_liveprofit_paper.json").exists()
    assert (run_dir / "config_truth_report.json").exists()
    assert (run_dir / "release_manifest.json").exists()
    assert (run_dir / "deployment_stamp.json").exists()
    assert (run_dir / "runtime_fingerprint.json").exists()
    assert (run_dir / "readiness_summary.json").exists()
    assert (run_dir / "live_safety_summary.json").exists()
    assert (run_dir / "health_summary.json").exists()
    assert (run_dir / "live_artifact_index.json").exists()
    assert (run_dir / "throughput_diagnostics.json").exists()
    assert (run_dir / "failure_taxonomy.json").exists()
    assert (run_dir / "decision_explainability.json").exists()
    readiness = json.loads((run_dir / "tiny_live_readiness_report.json").read_text(encoding="utf-8"))
    assert readiness["stage"] == "tiny_live"
