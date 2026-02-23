from pathlib import Path
import time

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.connectors.cex.binance_um_perps import BinanceConnectorError, BinanceUMPerpsConnector
from autonomous_investment_robot.connectors.cex.kraken_derivatives import KrakenDerivativesConnector
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator
from autonomous_investment_robot.services.data_ingestion.binance_ws_streams import BinanceWSStreams
from autonomous_investment_robot.services.data_ingestion.service import DataIngestionService
from autonomous_investment_robot.services.execution.live_binance_service import LiveBinanceService
from autonomous_investment_robot.services.execution.live_kraken_service import LiveKrakenService
from autonomous_investment_robot.services.replay.engine import ReplayEngine


def run_with_config(config_path: str) -> dict:
    settings = RobotSettings.from_file(config_path)
    orchestrator = RobotOrchestrator(settings)
    return orchestrator.boot()


def run_replay(config_path: str, source: str = "fixtures", run_id: str | None = None) -> dict:
    settings = RobotSettings.from_file(config_path)
    symbol = settings.universe[0]
    if source == "recordings":
        ing = DataIngestionService()
        resolved_run_id = ing.resolve_recording_run_id(settings.storage.run_dir, run_id=run_id)
        if resolved_run_id is None:
            return {"events": 0, "source": source, "status": "blocked", "reason": "recordings_missing"}
        health = ing.recordings_health(settings.storage.run_dir, resolved_run_id)
        bars = ing.replay_recordings(settings.storage.run_dir, run_id=resolved_run_id, symbol=symbol, source=source)
        return {
            "events": len(bars),
            "source": source,
            "run_id": resolved_run_id,
            "recording_health": health,
            "recording_index": ing.recordings_index(settings.storage.run_dir, resolved_run_id),
            "recording_meta": ing.replay_recordings_meta(settings.storage.run_dir, resolved_run_id),
        }
    engine = ReplayEngine()
    events = engine.from_csv(settings.fixtures.ohlcv_csv, symbol=symbol, venue=source)
    return {"events": len(events), "source": source}


def run_record(
    config_path: str,
    run_id: str = "latest",
    duration_seconds: int = 0,
    poll_interval_seconds: float = 1.0,
) -> dict:
    settings = RobotSettings.from_file(config_path)
    if settings.execution.provider_id != "binance_um_perps":
        return {
            "status": "blocked",
            "reason": f"record_not_supported_for_provider:{settings.execution.provider_id}",
            "mode": settings.execution.mode,
            "run_id": run_id,
        }
    ws = BinanceWSStreams(
        ws_base_url=settings.execution.binance.ws_stream_base_url,
        symbols=settings.universe,
        run_dir=settings.storage.run_dir,
    )
    out = {
        "status": "ready",
        "mode": settings.execution.mode,
        "run_id": run_id,
        "record_path": f"{settings.storage.run_dir}/recordings/{run_id}/market.jsonl",
        "combined_stream_url": ws.combined_stream_url(),
    }
    if duration_seconds <= 0:
        return out

    connector = BinanceUMPerpsConnector(settings.execution.binance)
    deadline = time.time() + max(1, int(duration_seconds))
    last_agg_ids: dict[str, int] = {}
    recorded = 0
    poll_interval_seconds = max(0.2, float(poll_interval_seconds))

    while time.time() < deadline:
        loop_started = time.time()
        for symbol in settings.universe:
            sym_l = symbol.lower()
            now_ms = int(time.time() * 1000)
            try:
                book = connector.book_ticker(symbol)
                book_evt = {
                    "stream": f"{sym_l}@bookTicker",
                    "data": {
                        "e": "bookTicker",
                        "E": now_ms,
                        "s": symbol,
                        "b": str(book.get("bidPrice", "0")),
                        "B": str(book.get("bidQty", "0")),
                        "a": str(book.get("askPrice", "0")),
                        "A": str(book.get("askQty", "0")),
                    },
                }
                ws.record_event(run_id, book_evt)
                recorded += 1
            except Exception:
                # Recording is best-effort; aggTrades may still provide replayable events.
                pass

            try:
                premium = connector.premium_index(symbol)
                evt_ms = int(premium.get("time", now_ms))
                mark_evt = {
                    "stream": f"{sym_l}@markPrice@1s",
                    "data": {
                        "e": "markPriceUpdate",
                        "E": evt_ms,
                        "s": symbol,
                        "p": str(premium.get("markPrice", "0")),
                        "i": str(premium.get("indexPrice", "0")),
                        "r": str(premium.get("lastFundingRate", "0")),
                    },
                }
                ws.record_event(run_id, mark_evt)
                recorded += 1
            except Exception:
                pass

            try:
                trades = connector.agg_trades(symbol, limit=20)
            except BinanceConnectorError:
                trades = []
            except Exception:
                trades = []

            last_seen = last_agg_ids.get(symbol, -1)
            fresh = [t for t in trades if int(t.get("a", -1)) > last_seen]
            fresh.sort(key=lambda t: int(t.get("a", -1)))
            for t in fresh:
                raw = {
                    "stream": f"{sym_l}@aggTrade",
                    "data": {
                        "e": "aggTrade",
                        "E": int(t.get("T", now_ms)),
                        "s": symbol,
                        "a": int(t.get("a", 0)),
                        "p": str(t.get("p", "0")),
                        "q": str(t.get("q", "0")),
                        "T": int(t.get("T", now_ms)),
                        "m": bool(t.get("m", False)),
                    },
                }
                ws.record_event(run_id, raw)
                recorded += 1
                last_seen = max(last_seen, int(t.get("a", last_seen)))
            last_agg_ids[symbol] = last_seen

        remaining = poll_interval_seconds - (time.time() - loop_started)
        if remaining > 0:
            time.sleep(remaining)

    out["status"] = "ok"
    out["events_recorded"] = recorded
    out["duration_seconds"] = int(duration_seconds)
    ing = DataIngestionService()
    out["recording_health"] = ing.recordings_health(settings.storage.run_dir, run_id)
    out["recording_index"] = ing.recordings_index(settings.storage.run_dir, run_id)
    out["recording_meta"] = ing.replay_recordings_meta(settings.storage.run_dir, run_id)
    return out


def emergency_flatten(config_path: str) -> dict:
    settings = RobotSettings.from_file(config_path)
    if settings.execution.provider_id == "kraken_derivatives":
        live = LiveKrakenService(
            settings=settings,
            run_id=settings.storage.run_dir.replace("/", "_"),
            connector=KrakenDerivativesConnector(settings.execution.kraken),
        )
    else:
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


def request_kill(config_path: str, reason: str = "operator_cli_kill") -> dict:
    settings = RobotSettings.from_file(config_path)
    run_dir = Path(settings.storage.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    marker = run_dir / "KILL"
    marker.write_text(reason + "\n", encoding="utf-8")
    return {"status": "kill_requested", "reason": reason, "kill_file": str(marker)}
