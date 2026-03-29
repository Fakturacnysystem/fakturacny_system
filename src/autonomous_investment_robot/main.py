import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.binance_um_perps import BinanceConnectorError, BinanceUMPerpsConnector
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator
from autonomous_investment_robot.services.data_ingestion.binance_ws_streams import BinanceWSStreams
from autonomous_investment_robot.services.data_ingestion.service import DataIngestionService
from autonomous_investment_robot.services.execution.live_kraken_spot_service import LiveKrakenSpotService
from autonomous_investment_robot.services.human_escalation_layer.service import HumanEscalationLayer
from autonomous_investment_robot.services.replay.engine import ReplayEngine


def _control_marker_payload(*, action: str, reason: str) -> dict:
    return {
        "action": action,
        "reason": reason,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "source": "operator_cli",
    }


def run_with_config(config_path: str) -> dict:
    try:
        settings = RobotSettings.from_file(config_path)
        orchestrator = RobotOrchestrator(settings)
        return orchestrator.boot()
    except Exception as exc:
        return {"status": "blocked", "reason": str(exc), "config": config_path}


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


def run_replay_report(config_path: str) -> dict:
    return run_with_config(config_path)


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


def emergency_flatten(
    config_path: str,
    *,
    symbol: str | None = None,
    scope: str = "all",
    freeze_only: bool = False,
    reason: str = "operator_cli_flatten",
) -> dict:
    try:
        settings = RobotSettings.from_file(config_path)
    except Exception as exc:
        # Protective operations should not be blocked by live-launch unlock friction.
        # Retry once with temporary unlock flags, but still require real credentials
        # and a successful provider preflight before any flatten action is sent.
        first_error = str(exc)
        if "Live trading blocked until configured:" not in first_error:
            return {"status": "blocked", "reason": first_error, "config": config_path}
        retry_env = {
            "ENABLE_LIVE_TRADING": "true",
            "ACK_I_UNDERSTAND_RISKS": "true",
            "ENABLE_FULL_LIVE_STAGE": "true",
        }
        original_env = {key: os.getenv(key) for key in retry_env}
        try:
            for key, value in retry_env.items():
                os.environ[key] = value
            settings = RobotSettings.from_file(config_path)
        except Exception as retry_exc:
            return {
                "status": "blocked",
                "reason": f"{first_error}; protective_retry_failed:{retry_exc}",
                "config": config_path,
            }
        finally:
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    if settings.execution.provider_id != "kraken_spot":
        return {
            "status": "blocked",
            "reason": "flatten_blocked_unsupported_doctrine_target_use_kraken_spot",
            "config": config_path,
        }
    if settings.execution_mode_enum() != ExecutionMode.LIVE:
        return {
            "status": "blocked",
            "reason": f"flatten_blocked_invalid_mode:{settings.execution_mode_enum().value}",
            "config": config_path,
        }
    try:
        live = LiveKrakenSpotService(
            settings=settings,
            run_id=settings.storage.run_dir.replace("/", "_"),
            connector=KrakenSpotConnector(settings.execution.kraken_spot),
        )
    except Exception as exc:
        return {"status": "blocked", "reason": str(exc), "config": config_path}
    try:
        ok, preflight_reason = live.preflight()
    except Exception as exc:
        return {"status": "blocked", "reason": str(exc), "config": config_path}
    if not ok:
        return {"status": "blocked", "reason": preflight_reason}
    if freeze_only:
        if not hasattr(live, "freeze_new_openings"):
            return {"status": "blocked", "reason": "freeze_only_not_supported"}
        try:
            frozen, freeze_reason = live.freeze_new_openings(reason=reason)
        except Exception as exc:
            return {"status": "blocked", "reason": str(exc), "config": config_path}
        return {"status": "ok" if frozen else "error", "reason": freeze_reason, "freeze_only": True}
    if symbol is not None:
        if not hasattr(live, "flatten_symbol"):
            return {"status": "blocked", "reason": "flatten_symbol_not_supported"}
        try:
            closed, close_reason = live.flatten_symbol(symbol, reason=reason)
        except Exception as exc:
            return {"status": "blocked", "reason": str(exc), "config": config_path}
        return {"status": "ok" if closed else "error", "reason": close_reason, "scope": "symbol", "symbol": symbol}
    if scope != "all":
        if not hasattr(live, "flatten_scope"):
            return {"status": "blocked", "reason": "flatten_scope_not_supported"}
        try:
            closed, close_reason = live.flatten_scope(scope=scope, symbol=symbol, reason=reason)
        except Exception as exc:
            return {"status": "blocked", "reason": str(exc), "config": config_path}
        return {"status": "ok" if closed else "error", "reason": close_reason, "scope": scope, "symbol": symbol}
    try:
        closed, close_reason = live.flatten_all_positions()
    except Exception as exc:
        return {"status": "blocked", "reason": str(exc), "config": config_path}
    return {"status": "ok" if closed else "error", "reason": close_reason, "scope": "all"}


def request_kill(config_path: str, reason: str = "operator_cli_kill") -> dict:
    settings = RobotSettings.from_file(config_path)
    run_dir = Path(settings.storage.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    marker = run_dir / "KILL"
    marker.write_text(reason + "\n", encoding="utf-8")
    return {"status": "kill_requested", "reason": reason, "kill_file": str(marker)}


def request_pause(config_path: str, reason: str = "operator_cli_pause") -> dict:
    settings = RobotSettings.from_file(config_path)
    run_dir = Path(settings.storage.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    marker = run_dir / "PAUSE.json"
    already_present = marker.exists()
    marker.write_text(json.dumps(_control_marker_payload(action="pause", reason=reason), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "pause_requested",
        "reason": reason,
        "pause_file": str(marker),
        "already_present": already_present,
    }


def resume_runtime(config_path: str, reason: str = "operator_cli_resume") -> dict:
    settings = RobotSettings.from_file(config_path)
    run_dir = Path(settings.storage.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    marker = run_dir / "PAUSE.json"
    prior_reason = ""
    was_paused = marker.exists()
    if was_paused:
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                prior_reason = str(payload.get("reason", ""))
        except Exception:
            prior_reason = ""
        marker.unlink()
    return {
        "status": "resume_requested",
        "reason": reason,
        "pause_file": str(marker),
        "was_paused": was_paused,
        "prior_pause_reason": prior_reason,
    }


def acknowledge_manual_review(
    run_dir: str,
    *,
    decision_key: str | None = None,
    reviewer: str = "operator",
    notes: str = "",
) -> dict:
    layer = HumanEscalationLayer(run_dir)
    payload = layer.acknowledge(decision_key=decision_key, reviewer=reviewer, notes=notes)
    return {
        "status": "acknowledged",
        "run_dir": run_dir,
        "decision_key": payload["decision_key"],
        "reviewer": payload["reviewer"],
    }
