from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import RobotSettings  # noqa: E402
from autonomous_investment_robot.connectors.cex.kraken_futures import KrakenFuturesConnector, KrakenFuturesSettings  # noqa: E402
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector  # noqa: E402
from autonomous_investment_robot.core.order_scheduler import OrderSubmissionScheduler  # noqa: E402
from autonomous_investment_robot.services.execution.live_kraken_futures_service import LiveKrakenFuturesService  # noqa: E402
from autonomous_investment_robot.services.execution.live_kraken_router_service import LiveKrakenRouterService  # noqa: E402
from autonomous_investment_robot.services.execution.live_kraken_spot_service import LiveKrakenSpotService  # noqa: E402
from autonomous_investment_robot.services.market_discovery import KrakenMarketDiscoveryService  # noqa: E402
from autonomous_investment_robot.services.ops.service import OpsService  # noqa: E402
from autonomous_investment_robot.services.reliability import HealthAudit110  # noqa: E402
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService  # noqa: E402


def _resolve_run_dir(settings: RobotSettings, explicit: str) -> str:
    if explicit:
        return explicit
    return str(settings.storage.run_dir)


def _discover_instruments(settings: RobotSettings, spot: KrakenSpotConnector, futures: KrakenFuturesConnector | None) -> list[dict[str, Any]]:
    coverage = getattr(settings, "market_coverage", None)
    enable_spot = bool(getattr(coverage, "enable_spot", True))
    enable_margin = bool(getattr(coverage, "enable_margin", True))
    enable_perps = bool(getattr(coverage, "enable_perps", True))
    enable_optional_venues = bool(getattr(coverage, "enable_optional_venues", True))
    discovery = KrakenMarketDiscoveryService(settings.storage.run_dir)
    result = discovery.discover(
        spot_connector=spot,
        futures_connector=futures,
        enable_spot=enable_spot,
        enable_margin=enable_margin,
        enable_perps=enable_perps,
        enable_optional_venues=enable_optional_venues,
    )
    return [x.__dict__ for x in result.instruments]


def _build_live_service(settings: RobotSettings) -> Any | None:
    mode = settings.execution_mode_enum().value
    if mode == "paper":
        return None
    provider = settings.live_provider()
    if provider != "kraken_spot":
        return None

    spot_connector = KrakenSpotConnector(settings.execution.kraken_spot)
    spot_live = LiveKrakenSpotService(
        settings=settings,
        run_id=settings.storage.run_dir.replace("/", "_"),
        connector=spot_connector,
    )
    coverage = getattr(settings, "market_coverage", None)
    enable_perps = bool(getattr(coverage, "enable_perps", True))
    futures_connector: KrakenFuturesConnector | None = None
    futures_live = None
    if enable_perps:
        futures_connector = KrakenFuturesConnector(KrakenFuturesSettings())
        futures_live = LiveKrakenFuturesService(
            settings=settings,
            run_id=settings.storage.run_dir.replace("/", "_"),
            connector=futures_connector,
        )

    instruments: list[dict[str, Any]] = []
    try:
        instruments = _discover_instruments(settings, spot_connector, futures_connector)
    except Exception:
        instruments = [{"symbol": s, "market_type": "spot", "venue": "kraken"} for s in settings.universe]
    return LiveKrakenRouterService(
        spot_service=spot_live,
        futures_service=futures_live,
        discovered_instruments=instruments,
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.kraken_spot.live_profit.yaml")
    p.add_argument("--run-dir", default="")
    p.add_argument("--symbol", default="")
    p.add_argument("--once", action="store_true")
    p.add_argument("--repair", action="store_true", default=True)
    p.add_argument("--no-repair", dest="repair", action="store_false")
    args = p.parse_args()

    settings = RobotSettings.from_file(args.config)
    run_dir = _resolve_run_dir(settings, args.run_dir)
    sqlite = None
    try:
        from autonomous_investment_robot.services.storage import SQLiteStore  # noqa: E402

        sqlite = SQLiteStore(run_dir)
    except ModuleNotFoundError as exc:
        if not str(exc).startswith("No module named 'sqlalchemy"):
            raise
    ops = OpsService(run_dir)
    if sqlite is None:
        ops.metrics["storage_backend_available"] = 0.0
    risk = RiskEngineService(settings.risk, safe_mode=settings.safe_mode_default)
    last_submission = None
    try:
        if sqlite is not None:
            last_submission = sqlite.latest_submission_epoch()
    except Exception:
        last_submission = None
    scheduler = OrderSubmissionScheduler(
        interval_s=60.0,
        initial_last_submission_ts=last_submission,
    )
    symbol = str(args.symbol or (settings.universe[0] if settings.universe else "XBTUSD")).strip().upper()

    audit_cfg = getattr(settings, "health_audit_110", None)
    auditor = HealthAudit110(
        run_dir=run_dir,
        interval_s=float(getattr(audit_cfg, "interval_s", 600.0)),
        health_threshold=float(getattr(audit_cfg, "health_threshold", 90.0)),
        stream_stale_after_s=float(getattr(audit_cfg, "stream_stale_after_s", 20.0)),
        scheduler_lag_grace_s=float(getattr(audit_cfg, "scheduler_lag_grace_s", 5.0)),
        watchdog_stall_timeout_s=float(getattr(settings.watchdog, "stall_timeout_s", 45.0)),
        max_rate_limit_events_60s=float(getattr(audit_cfg, "max_rate_limit_events_60s", 14.0)),
        heartbeat_file=str(getattr(settings.watchdog, "heartbeat_file", "health.json")),
        watchdog_state_file=str(getattr(settings.watchdog, "state_file", "watchdog_state.json")),
    )

    live = None
    try:
        live = _build_live_service(settings)
    except Exception:
        live = None

    if args.repair:
        report = auditor.audit_and_repair(
            symbol=symbol,
            mode=settings.execution_mode_enum().value,
            live=live,
            sqlite=sqlite,
            ops=ops,
            submission_scheduler=scheduler,
            order_submission_interval_s=60.0,
            risk_engine=risk,
            latest_feed_quotes=[],
            latest_feed_quality={},
            safe_probe_submitter=None,
            now_ts=time.time(),
        )
    else:
        report = auditor.run_once(
            symbol=symbol,
            mode=settings.execution_mode_enum().value,
            live=live,
            sqlite=sqlite,
            ops=ops,
            submission_scheduler=scheduler,
            order_submission_interval_s=60.0,
            risk_engine=risk,
            latest_feed_quotes=[],
            latest_feed_quality={},
            safe_probe_submitter=None,
            auto_repair=False,
            now_ts=time.time(),
        )

    print(json.dumps(report.to_dict(), indent=2, default=str))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
