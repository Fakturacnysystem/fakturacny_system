from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from autonomous_investment_robot.universe_gateway.auth import AuthIdentity, AuthService, role_allows
from autonomous_investment_robot.universe_gateway.event_bus import UniverseEventBus
from autonomous_investment_robot.universe_gateway.frontend import render_command_center_html, render_pwa_manifest, render_service_worker
from autonomous_investment_robot.universe_gateway.projections import UniverseProjectionStore
from autonomous_investment_robot.universe_gateway.query_service import UniverseQueryService
from autonomous_investment_robot.universe_gateway.ws import UniverseWebSocketHub, redis_pubsub_bridge

try:  # pragma: no cover - optional dependency handling
    from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
except Exception as exc:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]
    WebSocket = None  # type: ignore[assignment]
    WebSocketDisconnect = Exception  # type: ignore[assignment]
    HTTPException = RuntimeError  # type: ignore[assignment]
    Response = object  # type: ignore[assignment]
    JSONResponse = object  # type: ignore[assignment]
    HTMLResponse = object  # type: ignore[assignment]
    FileResponse = object  # type: ignore[assignment]
    _FASTAPI_IMPORT_ERROR = exc
else:
    _FASTAPI_IMPORT_ERROR = None


LOGGER = logging.getLogger(__name__)
ASSET_DIR = Path(__file__).with_name("assets")

REQUEST_COUNT = Counter("universe_gateway_requests_total", "Total HTTP requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("universe_gateway_request_latency_seconds", "HTTP request latency", ["method", "path"])
WS_CONNECTIONS = Gauge("universe_gateway_ws_connections", "Active websocket connections", ["channel"])
WS_MESSAGES = Counter("universe_gateway_ws_messages_total", "WebSocket messages published", ["channel"])
EVENT_THROUGHPUT = Counter("universe_gateway_event_throughput_total", "Event throughput by domain", ["domain"])


ROLE_REQUIREMENTS_HTTP: dict[str, set[str]] = {
    "/api/system/status": {"observer"},
    "/api/system/version": {"observer"},
    "/api/system/environment": {"observer"},
    "/api/capital/state": {"observer"},
    "/api/capital/equity": {"observer"},
    "/api/capital/drawdown": {"observer"},
    "/api/brain/modules": {"observer"},
    "/api/brain/decision": {"observer"},
    "/api/strategies": {"observer"},
    "/api/strategies/ranking": {"observer"},
    "/api/execution/orders": {"operator"},
    "/api/execution/fills": {"operator"},
    "/api/execution/stats": {"operator"},
    "/api/telemetry/events": {"observer"},
    "/api/telemetry/distribution": {"observer"},
    "/api/audit/runtime": {"analyst"},
    "/api/audit/preflight": {"analyst"},
    "/api/audit/config": {"admin"},
    "/api/replay/sessions": {"analyst"},
    "/api/replay/events": {"analyst"},
    "/api/simulation/scenarios": {"analyst"},
    "/api/auth/users": {"admin"},
}

ROLE_REQUIREMENTS_WS: dict[str, set[str]] = {
    "capital": {"observer"},
    "decisions": {"observer"},
    "execution": {"operator"},
    "risk": {"operator"},
    "telemetry": {"observer"},
    "simulation": {"analyst"},
}


def create_universe_gateway_app(
    *,
    run_dir: str,
    redis_url: str | None = None,
    postgres_dsn: str | None = None,
    jwt_secret: str | None = None,
) -> Any:
    if FastAPI is None:  # pragma: no cover
        raise RuntimeError(f"fastapi_not_installed:{_FASTAPI_IMPORT_ERROR}")

    store = UniverseProjectionStore(dsn=str(postgres_dsn or ""))
    auth = AuthService(store=store, jwt_secret=str(jwt_secret or os.getenv("AUTONOMOUS_JWT_SECRET", "unsafe-dev-secret")))
    auth.ensure_default_admin()
    query = UniverseQueryService(run_dir=run_dir, projections=store)

    bus = UniverseEventBus(redis_url=str(redis_url or os.getenv("AUTONOMOUS_REDIS_URL", "") or ""))
    ws_hub = UniverseWebSocketHub()
    bridge_stop = asyncio.Event()
    bridge_task: asyncio.Task | None = None

    @asynccontextmanager
    async def _lifespan(_app: Any) -> Any:
        nonlocal bridge_task
        bridge_stop.clear()
        bridge_task = asyncio.create_task(redis_pubsub_bridge(bus=bus, hub=ws_hub, stop_event=bridge_stop))
        try:
            yield
        finally:
            bridge_stop.set()
            if bridge_task is not None:
                try:
                    await bridge_task
                except Exception:
                    pass

    app = FastAPI(title="Universe Gateway API", version="1.0.0", lifespan=_lifespan)

    def _extract_bearer_token(request: Request) -> str:
        auth_header = str(request.headers.get("Authorization", "") or "")
        if auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1].strip()
        return ""

    async def _require_identity(request: Request) -> AuthIdentity:
        token = _extract_bearer_token(request)
        if not token:
            raise HTTPException(status_code=401, detail="missing_bearer_token")
        try:
            return auth.parse_identity(token)
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"invalid_token:{exc}") from exc

    def _enforce_http_roles(path: str, identity: AuthIdentity) -> None:
        required = ROLE_REQUIREMENTS_HTTP.get(path, {"observer"})
        if not role_allows(identity.role, required):
            raise HTTPException(status_code=403, detail="insufficient_role")

    @app.middleware("http")
    async def _metrics_and_logging_middleware(request: Request, call_next: Callable[..., Any]) -> Response:
        started = time.time()
        path = request.url.path
        method = request.method.upper()
        try:
            response = await call_next(request)
            status = int(getattr(response, "status_code", 500))
        except Exception:
            REQUEST_COUNT.labels(method=method, path=path, status="500").inc()
            REQUEST_LATENCY.labels(method=method, path=path).observe(max(0.0, time.time() - started))
            raise
        REQUEST_COUNT.labels(method=method, path=path, status=str(status)).inc()
        REQUEST_LATENCY.labels(method=method, path=path).observe(max(0.0, time.time() - started))

        LOGGER.info(
            "universe_gateway_http ts=%s run_id=%s service=gateway-api severity=INFO event_type=http_request reason=ok method=%s path=%s status=%s latency_ms=%.2f",
            time.time(),
            query.api_system_environment().get("run_id", "latest"),
            method,
            path,
            status,
            (time.time() - started) * 1000.0,
        )
        return response

    # Auth
    @app.post("/api/auth/token")
    async def issue_token(payload: dict[str, Any]) -> dict[str, Any]:
        username = str(payload.get("username", "") or "")
        password = str(payload.get("password", "") or "")
        ttl_s = int(payload.get("ttl_s", 3600) or 3600)
        identity = auth.authenticate_user(username=username, password=password)
        if identity is None:
            raise HTTPException(status_code=401, detail="invalid_credentials")
        token = auth.issue_identity_token(identity, ttl_s=ttl_s)
        return {"access_token": token, "token_type": "bearer", "role": identity.role, "username": identity.username}

    @app.post("/api/auth/users")
    async def create_user(payload: dict[str, Any], identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/auth/users", identity)
        username = str(payload.get("username", "") or "").strip()
        role = str(payload.get("role", "observer") or "observer")
        password = str(payload.get("password", "") or "")
        if not username or not password:
            raise HTTPException(status_code=400, detail="username_and_password_required")
        if role not in {"observer", "analyst", "operator", "admin"}:
            raise HTTPException(status_code=400, detail="invalid_role")
        from autonomous_investment_robot.universe_gateway.auth import hash_password

        store.upsert_user(username=username, role=role, password_hash=hash_password(password), active=True)
        return {"ok": True, "username": username, "role": role}

    # Compatibility routes
    @app.get("/health")
    async def health() -> dict[str, Any]:
        return query.health_payload()

    @app.get("/status")
    async def status() -> dict[str, Any]:
        return query.status_payload()

    @app.get("/positions")
    async def positions(limit: int = 200) -> dict[str, Any]:
        return query.positions_payload(limit=limit)

    @app.get("/audit-events")
    async def audit_events(limit: int = 200) -> dict[str, Any]:
        return query.audit_events_payload(limit=limit)

    @app.get("/metrics")
    async def legacy_metrics() -> dict[str, Any]:
        return query.status_payload().get("dashboard_snapshot", {})

    @app.get("/ui", response_class=HTMLResponse)
    async def legacy_ui() -> str:
        return render_command_center_html()

    @app.get("/ui/manifest.webmanifest")
    async def ui_manifest() -> Response:
        return Response(content=render_pwa_manifest(), media_type="application/manifest+json")

    @app.get("/ui/sw.js")
    async def ui_service_worker() -> Response:
        return Response(content=render_service_worker(), media_type="application/javascript")

    @app.get("/ui/assets/{asset_name}")
    async def ui_asset(asset_name: str) -> Any:
        safe_name = str(asset_name or "").strip()
        if not safe_name or "/" in safe_name or "\\" in safe_name:
            raise HTTPException(status_code=404, detail="asset_not_found")
        path = ASSET_DIR / safe_name
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="asset_not_found")
        return FileResponse(path)

    @app.get("/favicon.ico")
    async def favicon() -> Any:
        path = ASSET_DIR / "icon-192.png"
        if path.exists():
            return FileResponse(path)
        raise HTTPException(status_code=404, detail="asset_not_found")

    @app.get("/internal/metrics")
    async def prometheus_metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # /api system
    @app.get("/api/system/status")
    async def api_system_status(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/system/status", identity)
        return query.api_system_status()

    @app.get("/api/system/version")
    async def api_system_version(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/system/version", identity)
        return query.api_system_version()

    @app.get("/api/system/environment")
    async def api_system_environment(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/system/environment", identity)
        return query.api_system_environment()

    # /api capital
    @app.get("/api/capital/state")
    async def api_capital_state(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/capital/state", identity)
        return query.api_capital_state()

    @app.get("/api/capital/equity")
    async def api_capital_equity(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/capital/equity", identity)
        return query.api_capital_equity()

    @app.get("/api/capital/drawdown")
    async def api_capital_drawdown(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/capital/drawdown", identity)
        return query.api_capital_drawdown()

    # /api brain + strategies
    @app.get("/api/brain/modules")
    async def api_brain_modules(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/brain/modules", identity)
        return query.api_brain_modules()

    @app.get("/api/brain/decision")
    async def api_brain_decision(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/brain/decision", identity)
        return query.api_brain_decision()

    @app.get("/api/strategies")
    async def api_strategies(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/strategies", identity)
        return query.api_strategies()

    @app.get("/api/strategies/ranking")
    async def api_strategies_ranking(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/strategies/ranking", identity)
        return query.api_strategies()

    # /api execution
    @app.get("/api/execution/orders")
    async def api_execution_orders(limit: int = 200, identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/execution/orders", identity)
        return query.api_execution_orders(limit=limit)

    @app.get("/api/execution/fills")
    async def api_execution_fills(limit: int = 200, identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/execution/fills", identity)
        return query.api_execution_fills(limit=limit)

    @app.get("/api/execution/stats")
    async def api_execution_stats(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/execution/stats", identity)
        return query.api_execution_stats()

    # /api telemetry
    @app.get("/api/telemetry/events")
    async def api_telemetry_events(limit: int = 200, identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/telemetry/events", identity)
        return query.api_telemetry_events(limit=limit)

    @app.get("/api/telemetry/distribution")
    async def api_telemetry_distribution(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/telemetry/distribution", identity)
        return query.api_telemetry_distribution()

    # /api audit
    @app.get("/api/audit/runtime")
    async def api_audit_runtime(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/audit/runtime", identity)
        return query.api_audit_runtime()

    @app.get("/api/audit/preflight")
    async def api_audit_preflight(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/audit/preflight", identity)
        return query.api_audit_preflight()

    @app.get("/api/audit/config")
    async def api_audit_config(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/audit/config", identity)
        return query.api_audit_config()

    # /api replay + simulation
    @app.get("/api/replay/sessions")
    async def api_replay_sessions(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/replay/sessions", identity)
        return query.api_replay_sessions()

    @app.get("/api/replay/events")
    async def api_replay_events(session_id: str | None = None, limit: int = 400, identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/replay/events", identity)
        return query.api_replay_events(session_id=session_id, limit=limit)

    @app.get("/api/simulation/scenarios")
    async def api_simulation_scenarios(identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/simulation/scenarios", identity)
        return query.api_simulation_scenarios()

    async def _ws_handler(websocket: WebSocket, channel: str) -> None:
        required_roles = ROLE_REQUIREMENTS_WS.get(channel, {"observer"})
        token = websocket.query_params.get("token")
        if not token:
            auth_header = str(websocket.headers.get("authorization", "") or "")
            if auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1].strip()
        if not token:
            await websocket.close(code=4401)
            return
        try:
            identity = auth.parse_identity(token)
        except Exception:
            await websocket.close(code=4401)
            return
        if not role_allows(identity.role, required_roles):
            await websocket.close(code=4403)
            return

        await websocket.accept()
        state = await ws_hub.connect(channel=channel, websocket=websocket, role=identity.role)
        WS_CONNECTIONS.labels(channel=channel).inc()

        # Initial snapshot payload
        initial_payload = {}
        if channel == "capital":
            initial_payload = query.api_capital_state()
        elif channel == "decisions":
            initial_payload = query.api_brain_decision()
        elif channel == "execution":
            initial_payload = query.api_execution_stats()
        elif channel == "risk":
            initial_payload = query.api_audit_runtime()
        elif channel == "telemetry":
            initial_payload = query.api_telemetry_events(limit=50)
        elif channel == "simulation":
            initial_payload = query.api_simulation_scenarios()

        await websocket.send_json({"type": "snapshot", "channel": channel, "payload": initial_payload})
        WS_MESSAGES.labels(channel=channel).inc()

        try:
            while True:
                msg = await websocket.receive_text()
                if msg.lower() in {"ping", "heartbeat"}:
                    await websocket.send_json({"type": "pong", "ts": time.time()})
                else:
                    await websocket.send_json({"type": "ack", "channel": channel})
        except WebSocketDisconnect:
            pass
        finally:
            await ws_hub.disconnect(state)
            WS_CONNECTIONS.labels(channel=channel).dec()

    @app.websocket("/ws/capital")
    async def ws_capital(websocket: WebSocket) -> None:
        await _ws_handler(websocket, "capital")

    @app.websocket("/ws/decisions")
    async def ws_decisions(websocket: WebSocket) -> None:
        await _ws_handler(websocket, "decisions")

    @app.websocket("/ws/execution")
    async def ws_execution(websocket: WebSocket) -> None:
        await _ws_handler(websocket, "execution")

    @app.websocket("/ws/risk")
    async def ws_risk(websocket: WebSocket) -> None:
        await _ws_handler(websocket, "risk")

    @app.websocket("/ws/telemetry")
    async def ws_telemetry(websocket: WebSocket) -> None:
        await _ws_handler(websocket, "telemetry")

    @app.websocket("/ws/simulation")
    async def ws_simulation(websocket: WebSocket) -> None:
        await _ws_handler(websocket, "simulation")

    # lightweight event ingestion path for runtime adapters
    @app.post("/api/telemetry/ingest")
    async def api_ingest_event(payload: dict[str, Any], identity: AuthIdentity = Depends(_require_identity)) -> dict[str, Any]:
        _enforce_http_roles("/api/audit/config", identity)  # admin role required for ingestion endpoint
        domain = str(payload.get("domain", "telemetry") or "telemetry")
        event_type = str(payload.get("event_type", "telemetry_alert") or "telemetry_alert")
        envelope = {
            "event_id": str(payload.get("event_id", "") or f"manual-{time.time_ns()}"),
            "event_type": event_type,
            "timestamp": str(payload.get("timestamp", time.time())),
            "run_id": str(payload.get("run_id", "latest") or "latest"),
            "symbol": str(payload.get("symbol", "") or ""),
            "mode": str(payload.get("mode", "Paper") or "Paper"),
            "confidence": float(payload.get("confidence", 0.0) or 0.0),
            "source_module": str(payload.get("source_module", "gateway") or "gateway"),
            "payload": payload.get("payload", {}),
            "schema_version": str(payload.get("schema_version", "v1") or "v1"),
        }
        from autonomous_investment_robot.universe_gateway.contracts import EventEnvelope

        typed = EventEnvelope.from_mapping(envelope)
        ok = bus.publish_event(domain=domain, envelope=typed)
        if ok:
            EVENT_THROUGHPUT.labels(domain=domain).inc()
        return {"ok": ok, "domain": domain, "event_id": typed.event_id}

    return app
