from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.connectors.cex.binance_um_perps import BinanceUMPerpsConnector
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator
from autonomous_investment_robot.services.data_ingestion.binance_ws_streams import BinanceWSStreams
from autonomous_investment_robot.services.replay.engine import ReplayEngine
from autonomous_investment_robot.services.data_ingestion.service import DataIngestionService
from autonomous_investment_robot.services.execution.live_binance_service import LiveBinanceService


def run_with_config(config_path: str) -> dict:
    settings = RobotSettings.from_file(config_path)
    orchestrator = RobotOrchestrator(settings)
    return orchestrator.boot()


def run_replay(config_path: str, source: str = "fixtures") -> dict:
    settings = RobotSettings.from_file(config_path)
    symbol = settings.universe[0]
    if source == "recordings":
        ing = DataIngestionService()
        run_id = settings.storage.run_dir.rstrip("/").split("/")[-1]
        bars = ing.replay_recordings(settings.storage.run_dir, run_id=run_id, symbol=symbol, source=source)
        return {"events": len(bars), "source": source}
    engine = ReplayEngine()
    events = engine.from_csv(settings.fixtures.ohlcv_csv, symbol=symbol, venue=source)
    return {"events": len(events), "source": source}


def run_record(config_path: str, run_id: str = "latest") -> dict:
    settings = RobotSettings.from_file(config_path)
    ws = BinanceWSStreams(
        ws_base_url=settings.execution.binance.ws_stream_base_url,
        symbols=settings.universe,
        run_dir=settings.storage.run_dir,
    )
    return {
        "status": "ready",
        "mode": settings.execution.mode,
        "run_id": run_id,
        "record_path": f"{settings.storage.run_dir}/recordings/{run_id}/market.jsonl",
        "combined_stream_url": ws.combined_stream_url(),
    }


def emergency_flatten(config_path: str) -> dict:
    settings = RobotSettings.from_file(config_path)
    live = LiveBinanceService(
        settings=settings,
        run_id=settings.storage.run_dir.replace("/", "_"),
        connector=BinanceUMPerpsConnector(settings.execution.binance),
    )
    ok, reason = live.preflight()
    if not ok:
        return {"status": "blocked", "reason": reason}
    closed, close_reason = live.flatten_all_positions()
    return {"status": "ok" if closed else "error", "reason": close_reason}
