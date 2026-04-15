from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from autonomous_investment_robot.config.settings import (
    DoctrineSettings,
    ExecutionSettings,
    HarmonySettings,
    LiveUnlockSettings,
    MarketWatchSettings,
    RiskLimits,
    RobotSettings,
    SafetySettings,
    StorageSettings,
    TCOSettings,
)
from autonomous_investment_robot.services.harmony_config_resolver.service import HarmonyConfigResolver
from autonomous_investment_robot.services.market_watch_service.service import MarketWatchService


def _limits() -> RiskLimits:
    return RiskLimits(
        max_daily_loss_pct=1.0,
        max_weekly_loss_pct=2.0,
        max_drawdown_pct=2.0,
        max_position_notional=100.0,
        max_exposure_notional=100.0,
        max_symbol_exposure_notional=100.0,
        max_cluster_exposure_notional=100.0,
        max_orders_per_min=5,
        leverage=0,
        target_portfolio_vol=0.05,
        cvar_limit_pct=1.0,
        stress_loss_limit_pct=2.0,
        max_spread_bps=15.0,
        min_depth_notional=1000.0,
        stale_data_seconds=10.0,
        min_margin_buffer=2.0,
        max_funding_cost_per_day=0.0,
        max_oi_spike_pct=0.0,
        max_liquidation_spike=0.0,
        divergence_threshold_bps=10.0,
        crowding_score_kill=12.0,
    )


def _settings(tmp_path: Path, *, market_watch: MarketWatchSettings | None = None) -> RobotSettings:
    return RobotSettings(
        provider_whitelist=["kraken_spot"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_spot"),
        safety=SafetySettings(
            live_unlock=LiveUnlockSettings(
                enable_live_trading=True,
                ack_i_understand_risks=True,
                require_testnet_passed=False,
            )
        ),
        doctrine=DoctrineSettings(
            target_provider="kraken_spot",
            product_target="spot",
            long_only=True,
            never_open_new_short_exposure=True,
            minimum_sell_net_profit_bps=120.0,
            enforce_cost_basis_sell_block=True,
            enforce_net_profit_sell_block=True,
            block_non_reduce_only_sells=True,
        ),
        harmony=HarmonySettings(enabled=True, default_order_cadence_s=5.0),
        market_watch=market_watch or MarketWatchSettings(enabled=True),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=60.0, max_impact_bps=25.0),
        storage=StorageSettings(run_dir=str(tmp_path / "run")),
    )


def test_harmony_resolver_prefers_autonomous_order_cadence(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_ORDER_CADENCE_S", "7")
    monkeypatch.setenv("AUTONOMOUS_LIVE_POLL_SECONDS", "13")
    monkeypatch.setenv("AUTONOMOUS_POLL_SECONDS", "21")
    monkeypatch.setenv("AUTONOMOUS_ORDER_COOLDOWN_S", "34")

    report = HarmonyConfigResolver(_settings(tmp_path)).resolve()

    assert report["order_cadence_s"] == 7.0
    assert report["order_cadence_source"] == "AUTONOMOUS_ORDER_CADENCE_S"
    assert report["live_gate_status"]["doctrine_launch_safe"] is True


def test_harmony_resolver_writes_boot_and_runtime_reports(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    settings = _settings(tmp_path)
    resolver = HarmonyConfigResolver(settings)

    paths = resolver.write_reports(settings.storage.run_dir)

    runtime_path = Path(paths["harmony_report"])
    boot_path = Path(paths["harmony_boot_report"])
    assert runtime_path.exists()
    assert boot_path.exists()
    runtime_payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    boot_payload = json.loads(boot_path.read_text(encoding="utf-8"))
    assert runtime_payload["provider_target"] == "kraken_spot"
    assert runtime_payload["doctrine"]["long_only"] is True
    assert boot_payload["live_gate_status"]["doctrine_launch_safe"] is True


def test_market_watch_blackout_blocks_new_entries(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=1)).strftime("%H:%M")
    end = (now + timedelta(minutes=1)).strftime("%H:%M")
    settings = _settings(
        tmp_path,
        market_watch=MarketWatchSettings(
            enabled=True,
            blackout_windows=[{"start": start, "end": end, "label": "maintenance"}],
            block_new_entries_on_blackout=True,
        ),
    )

    report = MarketWatchService(settings).evaluate(
        symbol="BTC/USD",
        ts=now,
        snapshot=SimpleNamespace(spread_bps=4.0, depth_notional=50000.0),
        forecast=SimpleNamespace(regime="RANGE", liquidity_regime="GOOD"),
    )

    assert report.action == "block_entries"
    assert report.blackout_active is True
    assert "blackout:maintenance" in report.reasons


def test_market_watch_degrades_on_spread_and_liquidity_weakness(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    settings = _settings(
        tmp_path,
        market_watch=MarketWatchSettings(
            enabled=True,
            entry_block_max_spread_bps=35.0,
            entry_degrade_max_spread_bps=15.0,
            entry_block_min_depth_notional=15000.0,
            entry_degrade_min_depth_notional=30000.0,
            liquidity_map_min_depth_notional=30000.0,
        ),
    )

    report = MarketWatchService(settings).evaluate(
        symbol="BTC/USD",
        ts=datetime.now(timezone.utc),
        snapshot=SimpleNamespace(spread_bps=18.0, depth_notional=25000.0),
        forecast=SimpleNamespace(regime="RANGE", liquidity_regime="THIN"),
    )

    assert report.action == "degrade"
    assert report.score < 0.70
    assert "spread_degraded" in report.reasons
    assert "liquidity_map_degraded" in report.reasons


def test_market_watch_dead_market_only_degrades_when_microstructure_is_healthy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    settings = _settings(tmp_path, market_watch=MarketWatchSettings(enabled=True))

    report = MarketWatchService(settings).evaluate(
        symbol="BTC/USD",
        ts=datetime.now(timezone.utc),
        snapshot=SimpleNamespace(spread_bps=0.02, depth_notional=500000.0),
        forecast=SimpleNamespace(regime="RANGE", liquidity_regime="GOOD"),
        regime_assessment=SimpleNamespace(label="dead_market"),
    )

    assert report.action == "degrade"
    assert "regime_watch:dead_market" in report.reasons
