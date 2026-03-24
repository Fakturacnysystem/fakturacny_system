import json
from pathlib import Path
from types import SimpleNamespace

from autonomous_investment_robot.config.settings import ExecutionSettings, RiskLimits, RobotSettings, StorageSettings, TCOSettings
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator
from autonomous_investment_robot.main import run_with_config
from autonomous_investment_robot.services.paper_runtime import MetricsCoordinator, PaperDecisionCoordinator


def test_paper_run_emits_observability_journals():
    result = run_with_config("config.perps_intraday.paper.yaml")
    assert result["status"] == "ok"
    run_dir = Path("runs/perps_intraday")
    assert (run_dir / "config_manifest.jsonl").exists()
    assert (run_dir / "signal_journal.jsonl").exists()
    assert (run_dir / "policy_journal.jsonl").exists()
    assert (run_dir / "execution_journal.jsonl").exists()
    assert (run_dir / "quantum_state_journal.jsonl").exists()
    assert (run_dir / "edge_immunity_journal.jsonl").exists()
    assert (run_dir / "event_intelligence_journal.jsonl").exists()
    assert (run_dir / "mastermind_journal.jsonl").exists()
    assert (run_dir / "decision_doctrine_journal.jsonl").exists()
    assert (run_dir / "decision_doctrine_summary.jsonl").exists()
    assert (run_dir / "mastermind_summary.jsonl").exists()
    assert (run_dir / "source_trust_journal.jsonl").exists()
    assert (run_dir / "freshness_novelty_journal.jsonl").exists()
    assert (run_dir / "asset_relevance_journal.jsonl").exists()
    assert (run_dir / "market_impact_journal.jsonl").exists()
    assert (run_dir / "priced_in_journal.jsonl").exists()
    assert (run_dir / "adversarial_narrative_journal.jsonl").exists()
    assert (run_dir / "data_provenance_journal.jsonl").exists()
    assert (run_dir / "learning_records.jsonl").exists()
    assert (run_dir / "pnl_attribution.jsonl").exists()
    assert (run_dir / "post_trade_summary.jsonl").exists()


def test_orchestrator_wires_live_runtime_observability():
    settings = RobotSettings.from_file("config.perps_intraday.paper.yaml")
    orchestrator = RobotOrchestrator(settings)

    assert orchestrator.live_ledger.observability is orchestrator.observability
    assert orchestrator.live_recovery.observability is orchestrator.observability
    assert orchestrator.live_reconciliation.observability is orchestrator.observability
    assert orchestrator.live_control.observability is orchestrator.observability
    assert orchestrator.live_market.market_integrity_service is orchestrator.market_integrity
    assert orchestrator.live_market.venue_capability_registry is orchestrator.venue_capabilities
    assert orchestrator.live_market.shared_venue_limit_governor is orchestrator.shared_venue_limits


def test_orchestrator_wires_paper_runtime_coordinator():
    settings = RobotSettings.from_file("config.perps_intraday.paper.yaml")
    orchestrator = RobotOrchestrator(settings)

    assert orchestrator.paper_runtime.event_store is orchestrator.event_store
    assert orchestrator.paper_runtime.observability is orchestrator.observability
    assert orchestrator.paper_runtime.oms is orchestrator.oms
    assert isinstance(orchestrator.paper_runtime.decision, PaperDecisionCoordinator)
    assert isinstance(orchestrator.paper_runtime.metrics, MetricsCoordinator)


def test_orchestrator_emits_provider_capability_journal():
    result = run_with_config("config.perps_intraday.paper.yaml")
    assert result["status"] == "ok"
    run_dir = Path("runs/perps_intraday")
    assert (run_dir / "provider_capability_journal.jsonl").exists()


def test_paper_runtime_coordinator_preserves_golden_checksums():
    settings = RobotSettings.from_file("config.perps_intraday.paper.yaml")
    orchestrator = RobotOrchestrator(settings)

    result = orchestrator.paper_runtime.run(symbol=settings.universe[0])
    fixture = json.loads(Path("tests/fixtures/replay/golden_checksums_perps_intraday.json").read_text(encoding="utf-8"))

    assert result["status"] == "ok"
    assert result["orders_checksum"] == fixture["orders_checksum"]
    assert result["fills_checksum"] == fixture["fills_checksum"]
    assert result["equity_checksum"] == fixture["equity_checksum"]


def test_live_readonly_boot_skips_signed_recovery_without_credentials(monkeypatch, tmp_path):
    from autonomous_investment_robot.core import orchestrator as orchestrator_module

    class FakeLiveKraken:
        def __init__(self, settings, run_id, connector):  # noqa: ARG002
            self.connector = SimpleNamespace(provider_id="kraken_derivatives", has_credentials=False)

        def preflight(self):
            return True, "readonly"

    monkeypatch.setattr(orchestrator_module, "LiveKrakenService", FakeLiveKraken)
    monkeypatch.setattr(orchestrator_module, "KrakenDerivativesConnector", lambda settings: object())
    settings = RobotSettings(
        storage=StorageSettings(run_dir=str(tmp_path)),
        provider_whitelist=["kraken_derivatives"],
        universe=["PI_XBTUSD"],
        execution=ExecutionSettings(mode="live_readonly", provider_id="kraken_derivatives"),
        risk=RiskLimits(
            max_daily_loss_pct=1.0,
            max_weekly_loss_pct=2.0,
            max_drawdown_pct=2.0,
            max_position_notional=10.0,
            max_exposure_notional=10.0,
            max_symbol_exposure_notional=10.0,
            max_cluster_exposure_notional=10.0,
            max_orders_per_min=5,
            leverage=0,
            max_spread_bps=10.0,
            min_depth_notional=10.0,
            stale_data_seconds=10.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=1.0,
            max_liquidation_spike=1.0,
            divergence_threshold_bps=10.0,
            crowding_score_kill=10.0,
        ),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )

    result = RobotOrchestrator(settings).boot()

    assert result["status"] == "ok"
    assert result["mode"] == "live_readonly"
    assert result["reason"] == "live_preflight_passed"
    truth_log = (Path(settings.storage.run_dir) / "events_truth.jsonl").read_text(encoding="utf-8")
    assert "readonly_without_credentials" in truth_log
